"""Asset loaders for the OKF viewer.

Resolves templates, static assets, viewer config, and type palettes with
bundle-level override support.

Override precedence (highest first):
    1. ``<bundle_root>/.okf-loom/viewer/templates/<name>.html``  (template)
       ``<bundle_root>/.okf-loom/viewer/static/<name>``           (static asset)
       ``<bundle_root>/.okf-loom/viewer/palette.json``            (type palette)
       ``<bundle_root>/.okf-loom/viewer/config.json``             (viewer config)
    2. Built-in viewer assets stored inside ``scripts/okf_loom/viewer/``.

Templates use ``str.replace``-style placeholders (NOT ``string.Template``),
because concept bodies frequently contain literal ``$`` characters that
would clash with ``$id`` substitution. Placeholder tokens are uppercase,
wrapped in double underscores, e.g. ``__TITLE__``, ``__BODY__``.

Security: every override mechanism (templates, static assets, type palette,
plugins) is gated on the **effective active-code gate** (current spec §14):

    effective_allow = bundle_cfg.viewer.allow_active_code AND operator_consent

The bundle's own ``allow_active_code: true`` is necessary but NOT
sufficient — the operator must ALSO grant consent via the
``OKF_LOOM_ALLOW_ACTIVE_CODE`` environment variable (values ``"1"`` / ``"true"`` /
``"yes"``) or the ``--allow-active-code`` CLI flag (which calls
:func:`set_operator_consent`). This prevents a bundle from turning on
arbitrary viewer-side code execution (template HTML, static JS, plugin
Python) on its own; a bundle shipping ``allow_active_code: true`` with a
malicious override still produces the built-in (safe) viewer unless the
operator explicitly opts in.

See ``viewer/OVERRIDES.md`` for the full override reference.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zlib
from pathlib import Path
from typing import Any

from ..exceptions import OKFError
from ..model import Bundle
from ..theme import EXPLICIT_THEMES, legacy_theme_message

_THIS_DIR = Path(__file__).resolve().parent
_BUILTIN_TEMPLATES = _THIS_DIR / "templates"
_BUILTIN_STATIC = _THIS_DIR / "static"
_OKF_VIEWER_SUBDIR = Path(".okf-loom") / "viewer"

# The one explicit override/static-asset name scope: the built-in viewer
# asset file names. This frozenset is the single source of truth shared by
# file emission (``list_builtin_static``), loading (``load_static`` /
# ``_resolve_static``), the live ``/__static`` handler (server.py), and the
# content-version hasher (``asset_version``). Only these names may be
# loaded, served, or overridden as viewer static assets; an override for any
# other name is ignored, and loading/hashing an unknown name raises /
# degrades gracefully. Derived from the on-disk built-in set so it cannot
# drift from what is actually shipped.
STATIC_ASSET_NAMES: frozenset[str] = (
    frozenset(p.name for p in _BUILTIN_STATIC.iterdir() if p.is_file())
    if _BUILTIN_STATIC.is_dir() else frozenset()
)


def is_known_static_asset(name: str) -> bool:
    """True iff ``name`` is in the built-in viewer static-asset scope."""
    return name in STATIC_ASSET_NAMES

# ---------------------------------------------------------------------------
# Bundle-local media the viewer displays (image-rich bundles): the live
# server serves exactly these extensions from the bundle tree, and the
# static/spa build copies exactly these into the site output. Nothing else
# ever routes to the media path — config/secrets (.yaml, .token,
# extensionless files) are structurally unservable regardless of the §5
# visibility checks. Keep in sync with ``server._EXT_CONTENT_TYPES`` (a
# type missing there ships as application/octet-stream under nosniff —
# download, never render).
# ---------------------------------------------------------------------------
BUNDLE_MEDIA_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".ico",
    ".svg", ".mp4", ".webm", ".pdf",
})

# ---------------------------------------------------------------------------
# Operator consent (P1-40): the bundle's allow_active_code is necessary but
# not sufficient — the operator must also opt in via env or CLI flag.
# ---------------------------------------------------------------------------
#
# Operator consent is a process-wide constant (env var / CLI flag), so it is
# read once and cached. The bundle-level allow_active_code is re-read per
# bundle root (and cached per root — see _OVERRIDES_CACHE below).
#
#: Environment variable name. Truthy tokens: "1", "true", "yes" (case-insensitive).
OPERATOR_CONSENT_ENV: str = "OKF_LOOM_ALLOW_ACTIVE_CODE"
_TRUTHY_OPERATOR_TOKENS: frozenset[str] = frozenset({"1", "true", "yes"})

# Module-level override (set by the CLI ``--allow-active-code`` flag, which is
# outside this file's ownership — see cli.py REPORT). ``None`` means "not set
# via CLI; consult the env var". A CLI ``--allow-active-code`` MUST win over
# the env var either way (operator's most-recent explicit choice), so the
# setter stores the explicit bool.
_operator_consent_override: bool | None = None


def set_operator_consent(granted: bool) -> None:
    """Record an explicit operator-consent decision (CLI ``--allow-active-code``).

    Mirrors the env-var path but wins over it (the operator's most-recent
    explicit choice on the command line is authoritative). Resets the
    per-bundle override cache so the new decision takes effect immediately.
    """
    global _operator_consent_override
    _operator_consent_override = bool(granted)
    clear_overrides_cache()


def operator_consent() -> bool:
    """True iff the operator has consented to active code for this process.

    Precedence: explicit CLI override (:func:`set_operator_consent`) wins;
    otherwise the ``OKF_LOOM_ALLOW_ACTIVE_CODE`` env var is consulted (truthy
    tokens: ``"1"`` / ``"true"`` / ``"yes"``; anything else ⇒ no consent).

    This is fail-closed: an unset env var, an empty string, ``"0"``,
    ``"false"``, or an unrecognised token all yield ``False``.
    """
    if _operator_consent_override is not None:
        return _operator_consent_override
    raw = os.environ.get(OPERATOR_CONSENT_ENV, "")
    return raw.strip().lower() in _TRUTHY_OPERATOR_TOKENS


def bundle_cfg_allow_active_code(bundle_root: str | Path | Bundle) -> bool:
    """Read the bundle's own ``viewer.allow_active_code`` from okf-loom.config.yaml.

    Fail-closed: any config-read error ⇒ ``False`` (no active code).
    """
    try:
        from ..config import OkfConfig

        if isinstance(bundle_root, Bundle):
            root = bundle_root.root
        else:
            root = Path(bundle_root)
        return OkfConfig.load(root).viewer.allow_active_code
    except Exception:
        return False  # fail-closed


def effective_allow_active_code(bundle_root: str | Path | Bundle) -> bool:
    """The effective active-code gate (current spec §14).

    ``effective = bundle_cfg.allow_active_code AND operator_consent()``.

    A bundle cannot enable active code on its own; the operator must opt in
    via ``OKF_LOOM_ALLOW_ACTIVE_CODE`` or ``--allow-active-code``. This is the
    load-bearing security property: template/static/palette overrides and
    plugin discovery all consult this helper.
    """
    if not operator_consent():
        return False
    return bundle_cfg_allow_active_code(bundle_root)


# Per-bundle-root cache of the resolved effective gate (P2-45). Without this,
# every template / static / palette load during a render re-reads
# ``okf-loom.config.yaml`` from disk — O(N) reads for a constant per-bundle
# decision. The cache is keyed by the resolved bundle-root path string.
#
# Invalidation: operator consent is a process constant; bundle config can
# change. ``set_operator_consent`` clears the whole cache. The bundle
# watcher's reload path (server.py) calls ``clear_overrides_cache(root)``
# for the reloaded root so a config edit + .md touch is picked up on the
# next request. A pure config edit (no .md touch) requires a server
# restart, matching the existing watcher contract documented in run_server.
_OVERRIDES_CACHE: dict[str, bool] = {}


def clear_overrides_cache(bundle_root: str | Path | None = None) -> None:
    """Drop the cached effective-gate decision.

    With no argument, clears every cached root (used when operator consent
    changes process-wide). With a root, clears only that root's entry.

    Note: the asset-version cache (:func:`asset_version`) holds ONLY
    process-constant builtin digests — mutable override digests are computed
    fresh on every call and are never memoized — so it does not need to be
    invalidated here. A gate toggle re-runs :func:`_overrides_allowed`
    (whose own cache this call drops) and re-resolves builtin-vs-override
    on the next :func:`asset_version` / :func:`load_static` call.
    """
    if bundle_root is None:
        _OVERRIDES_CACHE.clear()
        return
    key = str(Path(bundle_root).resolve())
    _OVERRIDES_CACHE.pop(key, None)


# ---------------------------------------------------------------------------
# Type palette
# ---------------------------------------------------------------------------

def stable_hue(s: str) -> int:
    """Deterministic hue (0..359) for a string.

    Uses ``zlib.crc32`` rather than the process-randomized ``hash`` so colours
    are stable across runs and machines.

    iter3 CRI3-004: this per-name hash is still the FALLBACK hue source
    for a type that is not in the bundle's sorted type list (e.g. a
    concept appearing in graph.json before the palette was computed, or
    a type added live by a CLI mutator that has not re-resolved yet — see
    render.py:404). For the COMMON case (palette pre-computed for the
    bundle's known types) prefer :func:`auto_palette`, which uses a
    golden-angle hue spread that maximally separates adjacent types.
    """
    return zlib.crc32(s.encode("utf-8")) % 360


# iter3 CRI3-004: golden-angle hue step (137.508°). For any set of N hues,
# multiplying by this step and taking mod 360 produces a sequence whose
# adjacent values are maximally separated on the hue wheel — the standard
# technique for generating N visually-distinct hues without collisions.
# Choosing it over a hash-based spread fixes the iter-2 residual where two
# types whose names hashed within ~20° of each other (Dataset/Playbook,
# Reference/Table) read as the same colour on the graph canvas.
_GOLDEN_ANGLE_HUE_STEP = 137.508


# ---------------------------------------------------------------------------
# Type icons (UI overhaul phase 1)
# ---------------------------------------------------------------------------
# A curated icon per COMMON knowledge-base type name, with a generic
# document fallback for everything else. Unlike colours (which stay on the
# neutral golden-angle auto-palette — see auto_palette's no-domain-bias
# note), icons key on generic type-name *shapes* (dataset→cylinder,
# table→grid, playbook→open book) and always degrade to the fallback, so
# no type is second-class — just less pictorial.
#
# Each value is the inner markup of a 24×24 stroke-based SVG (Lucide-style
# geometry, stroke=currentColor so icons inherit text/type colour).
_TYPE_ICON_PATHS: dict[str, str] = {
    "database": (
        '<ellipse cx="12" cy="5" rx="8" ry="3"/>'
        '<path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/>'
        '<path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>'
    ),
    "table": (
        '<rect x="3" y="3" width="18" height="18" rx="2"/>'
        '<path d="M3 9h18M3 15h18M12 3v18"/>'
    ),
    "server": (
        '<rect x="2" y="3" width="20" height="7" rx="2"/>'
        '<rect x="2" y="14" width="20" height="7" rx="2"/>'
        '<path d="M6 6.5h.01M6 17.5h.01"/>'
    ),
    "book-open": (
        '<path d="M2 4h6a4 4 0 0 1 4 4v12a3 3 0 0 0-3-3H2z"/>'
        '<path d="M22 4h-6a4 4 0 0 0-4 4v12a3 3 0 0 1 3-3h7z"/>'
    ),
    "bookmark": (
        '<path d="M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>'
    ),
    "trending": (
        '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>'
    ),
    "branch": (
        '<circle cx="5" cy="5" r="2.5"/><circle cx="5" cy="19" r="2.5"/>'
        '<circle cx="19" cy="12" r="2.5"/>'
        '<path d="M5 7.5v9M7.2 6.2c5 1 9.3 3 9.3 5.8"/>'
    ),
    "book": (
        '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5z"/>'
        '<path d="M9 7h6"/>'
    ),
    "shield": (
        '<path d="M12 22s8-3 8-10V5l-8-3-8 3v7c0 7 8 10 8 10z"/>'
    ),
    "zap": (
        '<path d="M13 2L3 14h7l-1 8 11-13h-8l1-7z"/>'
    ),
    "box": (
        '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v9"/>'
    ),
    "people": (
        '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 21a6.5 6.5 0 0 1 13 0"/>'
        '<path d="M16 3.5a3.5 3.5 0 0 1 0 7M21.5 21a6.5 6.5 0 0 0-4.5-6.2"/>'
    ),
    "file": (
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 2v6h6M9 13h6M9 17h6"/>'
    ),
}

# Normalized type-name → icon key. Lookup lowercases and strips a trailing
# "s" so Dataset/datasets/DATASET all hit "dataset".
_TYPE_ICON_SYNONYMS: dict[str, str] = {
    "dataset": "database", "data": "database", "warehouse": "database",
    "table": "table", "view": "table", "sheet": "table",
    "service": "server", "api": "server", "system": "server", "app": "server",
    "playbook": "book-open", "runbook": "book-open", "guide": "book-open",
    "procedure": "book-open", "howto": "book-open", "tutorial": "book-open",
    "reference": "bookmark", "spec": "bookmark", "standard": "bookmark",
    "doc": "bookmark", "document": "bookmark",
    "metric": "trending", "kpi": "trending", "measure": "trending",
    "decision": "branch", "adr": "branch", "rfc": "branch",
    "glossary": "book", "term": "book", "definition": "book",
    "policy": "shield", "rule": "shield", "security": "shield",
    "event": "zap", "topic": "zap", "stream": "zap",
    "model": "box", "schema": "box", "entity": "box",
    "person": "people", "people": "people", "team": "people",
    "owner": "people", "user": "people",
}


def type_icon_key(type_name: str | None) -> str:
    """Resolve a concept type name to an icon key (fallback: ``file``)."""
    t = (type_name or "").strip().lower()
    if t.endswith("s") and t[:-1] in _TYPE_ICON_SYNONYMS:
        t = t[:-1]
    return _TYPE_ICON_SYNONYMS.get(t, "file")


def type_icon_paths() -> dict[str, str]:
    """The icon-key → SVG-inner-markup map (for client-side node glyphs)."""
    return dict(_TYPE_ICON_PATHS)


def type_icon_svg(type_name: str | None, *, size: int = 16,
                  cls: str = "okf-type-icon") -> str:
    """Inline SVG icon for a concept type.

    stroke=currentColor: the icon takes the colour of the surrounding
    text, so callers colour it via CSS (e.g. the type accent). Only OUR
    static path strings are interpolated — the (untrusted) type name never
    reaches the markup.
    """
    paths = _TYPE_ICON_PATHS[type_icon_key(type_name)]
    return (
        f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f'{paths}</svg>'
    )


def hsl_color(hue: int, *, sat: int = 62, light: int = 48) -> str:
    """Format an HSL colour string."""
    return f"hsl({hue % 360}, {sat}%, {light}%)"


def auto_palette(types: list[str]) -> dict[str, str]:
    """Generate a distinct colour for each type via golden-angle hue spread.

    iter3 CRI3-004: was a per-name crc32 hash. For the common 4-12 type
    catalog the hash approach produced clustered hues (Dataset/Playbook +
    Reference/Table pairs were near-indistinguishable on the graph canvas).
    Switching to a golden-angle spread over the SORTED type list
    guarantees maximally distinct adjacent hues for any N, while staying
    deterministic per bundle (the sorted type list is stable across runs).

    The palette deliberately avoids hardcoding any domain-specific types
    (no BigQuery / Stack Overflow bias) — every type gets a colour derived
    purely from its position in the sorted list.

    A bundle ``.okf-loom/viewer/palette.json`` override still wins per-type
    (resolve_palette applies overrides after this); the golden-angle
    spread only sets the auto-generated defaults.
    """
    out: dict[str, str] = {}
    # Sort first so the palette is stable across runs and machines (a
    # different insertion order would otherwise reshuffle hues). sorted()
    # also strips empties and dedupes implicitly when combined with the
    # enumerate-and-assign loop (a duplicate type gets the same hue).
    sorted_unique = sorted({t for t in types if t})
    for i, t in enumerate(sorted_unique):
        hue = int((i * _GOLDEN_ANGLE_HUE_STEP) % 360)
        out[t] = hsl_color(hue)
    return out


def load_palette_override(bundle: Bundle) -> dict[str, str]:
    """Read ``.okf-loom/viewer/palette.json`` if present.

    Schema: ``{"<type>": "<css-color>"}``. Invalid JSON, wrong shape, or
    values that fail the CSS-colour allowlist → that entry (or the whole
    file) is dropped.

    Every value is run through :func:`_sanitize_css_color` (P1-41) before
    being returned. Palette values are interpolated into ``style="...";``
    attributes in the rendered HTML; a naive HTML-escape alone does NOT
    stop CSS injection (``red;position:fixed;top:0`` has no HTML-unsafe
    characters), so values are validated against a strict CSS-colour
    allowlist. Anything that does not match is dropped (fail-closed).
    """
    path = bundle.root / _OKF_VIEWER_SUBDIR / "palette.json"
    if not path.is_file():
        return {}
    # P1-4 (security): refuse to follow a palette.json that escapes the bundle
    # root via symlink. Fail closed to the auto palette (return {}).
    from ..paths import path_within_bundle
    if not path_within_bundle(path, bundle.root):
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, str):
            # Non-string values (numbers, bools, lists) are dropped — they
            # cannot be a safe CSS colour and would interpolate verbatim.
            continue
        sanitized = _sanitize_css_color(v)
        if sanitized:
            out[k] = sanitized
        # else: value rejected by the allowlist; drop the key fail-closed.
    return out


# ---------------------------------------------------------------------------
# CSS-colour allowlist (P1-41). Palette values are interpolated into inline
# ``style="background:<color>"`` attributes; HTML-escaping alone does not
# stop CSS-meta-character injection (``;``, ``:``, ``url(...)``, etc.), so
# values MUST match one of these shapes to land in the rendered HTML.
# ---------------------------------------------------------------------------

# Named CSS colours (CSS3 subset; covers the common cross-browser set).
_CSS_NAMED_COLORS: frozenset[str] = frozenset({
    "aliceblue", "antiquewhite", "aqua", "aquamarine", "azure", "beige",
    "bisque", "black", "blanchedalmond", "blue", "blueviolet", "brown",
    "burlywood", "cadetblue", "chartreuse", "chocolate", "coral",
    "cornflowerblue", "cornsilk", "crimson", "cyan", "darkblue", "darkcyan",
    "darkgoldenrod", "darkgray", "darkgreen", "darkgrey", "darkkhaki",
    "darkmagenta", "darkolivegreen", "darkorange", "darkorchid", "darkred",
    "darksalmon", "darkseagreen", "darkslateblue", "darkslategray",
    "darkslategrey", "darkturquoise", "darkviolet", "deeppink",
    "deepskyblue", "dimgray", "dimgrey", "dodgerblue", "firebrick",
    "floralwhite", "forestgreen", "fuchsia", "gainsboro", "ghostwhite",
    "gold", "goldenrod", "gray", "green", "greenyellow", "grey", "honeydew",
    "hotpink", "indianred", "indigo", "ivory", "khaki", "lavender",
    "lavenderblush", "lawngreen", "lemonchiffon", "lightblue", "lightcoral",
    "lightcyan", "lightgoldenrodyellow", "lightgray", "lightgreen",
    "lightgrey", "lightpink", "lightsalmon", "lightseagreen",
    "lightskyblue", "lightslategray", "lightslategrey", "lightsteelblue",
    "lightyellow", "lime", "limegreen", "linen", "magenta", "maroon",
    "mediumaquamarine", "mediumblue", "mediumorchid", "mediumpurple",
    "mediumseagreen", "mediumslateblue", "mediumspringgreen",
    "mediumturquoise", "mediumvioletred", "midnightblue", "mintcream",
    "mistyrose", "moccasin", "navajowhite", "navy", "oldlace", "olive",
    "olivedrab", "orange", "orangered", "orchid", "palegoldenrod",
    "palegreen", "paleturquoise", "palevioletred", "papayawhip",
    "peachpuff", "peru", "pink", "plum", "powderblue", "purple", "rebeccapurple",
    "red", "rosybrown", "royalblue", "saddlebrown", "salmon",
    "sandybrown", "seagreen", "seashell", "sienna", "silver", "skyblue",
    "slateblue", "slategray", "slategrey", "snow", "springgreen",
    "steelblue", "tan", "teal", "thistle", "tomato", "turquoise", "violet",
    "wheat", "white", "whitesmoke", "yellow", "yellowgreen",
    "transparent", "currentcolor",
})

# Strict allowlist of CSS-colour shapes. Anchored (full-match) so a value
# like ``red;position:fixed`` is rejected (the ``;`` breaks the match).
#   * #rgb / #rgba / #rrggbb / #rrggbbaa hex
#   * rgb() / rgba() with numbers and optional commas/spaces/alpha
#   * hsl() / hsla() likewise
#   * a bare CSS named colour
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_RGB_FUNC_RE = re.compile(
    r"^rgba?\(\s*[\d.]+\s*%?\s*(,\s*[\d.]+\s*%?\s*){2,3}\)$"
)
# hsl/hsla: hue (number + optional unit) + saturation% + lightness% + an
# optional alpha (the alpha may be a bare number, unlike sat/light which
# CSS requires as percentages). Anchored full-match.
_HSL_FUNC_RE = re.compile(
    r"^hsla?\(\s*-?\d+(?:\.\d+)?\s*(?:deg|rad|turn|grad)?\s*"
    r"(?:,\s*\d+(?:\.\d+)?%\s*){2}"   # saturation + lightness (both %)
    r"(?:,\s*[\d.]+\s*%?\s*)?"        # optional alpha (number or %)
    r"\)$"
)


def _sanitize_css_color(value: str) -> str:
    """Return ``value`` iff it matches the strict CSS-colour allowlist.

    Returns ``""`` (empty) for anything that does not match — so the caller
    can drop the entry fail-closed. The check is anchored full-match;
    CSS-meta-character payloads (``;``, ``url(...)``, ``expression()``) and
    HTML/JS payloads are all rejected because they cannot satisfy any of the
    allowed shapes.

    This is a denylist-by-shape allowlist: we accept ONLY the known-safe
    shapes, not "anything without a semicolon".
    """
    if not isinstance(value, str):
        return ""
    v = value.strip()
    if not v:
        return ""
    low = v.lower()
    if low in _CSS_NAMED_COLORS:
        return v
    if _HEX_COLOR_RE.match(v):
        return v
    if _RGB_FUNC_RE.match(v):
        return v
    if _HSL_FUNC_RE.match(v):
        return v
    return ""


def resolve_palette(bundle: Bundle) -> dict[str, str]:
    """Auto palette merged with bundle overrides (override wins).

    Bundle palette overrides are gated on the effective active-code gate
    (P1-41 defense in depth): even though palette values are CSS-validated,
    an untrusted bundle should not be able to recolour the UI at all unless
    the operator has opted into active code. When the gate is closed, only
    the auto-generated palette is returned.
    """
    types = sorted(t for t in bundle.types() if t)
    pal = auto_palette(types)
    if _overrides_allowed(bundle):
        pal.update(load_palette_override(bundle))
    return pal


# ---------------------------------------------------------------------------
# Viewer config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict[str, Any] = {
    "name": None,
    "default_layout": "cose",
    # No configured theme by default: only an AUTHOR-set value may act as
    # the "configured preference" in the resolution contract (saved user
    # preference > configured preference > Swiss Auto/OS fallback). A
    # concrete built-in default here would be indistinguishable from real
    # configuration downstream and would override the Swiss-first fallback.
    "theme": None,
    "cdn": True,
}


_ALLOWED_LAYOUTS = frozenset({"cose", "concentric", "breadthfirst", "circle", "grid"})
_ALLOWED_THEMES = frozenset(EXPLICIT_THEMES)


class ViewerConfigError(OKFError, ValueError):
    """Raised when bundle-local ``viewer/config.json`` is invalid."""


def _viewer_config_value(
    path: Path, key: str, value: Any
) -> Any:
    """Validate one viewer config value without interpolation fallbacks."""
    field = f"{path}:{key}"
    if key == "name":
        if value is None:
            return None
        if not isinstance(value, str):
            raise ViewerConfigError(f"{field} must be a string or null")
        if not value.strip():
            raise ViewerConfigError(f"{field} must not be empty or whitespace")
        return value
    if key == "cdn":
        if not isinstance(value, bool):
            raise ViewerConfigError(f"{field} must be a boolean")
        return value
    if key in {"default_layout", "theme"}:
        if key == "theme" and value is None:
            # Explicit null is accepted as "unconfigured", identical to
            # omitting the key: the configured slot stays empty and the
            # Swiss Auto/OS fallback governs (parity with the None default).
            return None
        if not isinstance(value, str):
            raise ViewerConfigError(f"{field} must be a string")
        if not value.strip():
            raise ViewerConfigError(f"{field} must not be empty or whitespace")
        if key == "theme":
            migration = legacy_theme_message(field, value)
            if migration:
                raise ViewerConfigError(migration)
            allowed = _ALLOWED_THEMES
        else:
            allowed = _ALLOWED_LAYOUTS
        if value not in allowed:
            raise ViewerConfigError(
                f"{field}: unsupported value {value!r}; "
                f"expected one of {sorted(allowed)}"
            )
        return value
    raise AssertionError(f"unhandled viewer config key: {key}")


def load_config(bundle: Bundle) -> dict[str, Any]:
    """Read ``.okf-loom/viewer/config.json`` and merge over defaults.

    Supported keys:
        name (str|None): display name for the bundle in the viewer UI.
            Falls back to ``bundle.name``.
        default_layout (str): one of cose, concentric, breadthfirst, circle,
            grid. Used as the initial Cytoscape layout in the single-file and
            full-page graph views.
        theme (str|None): one of "technical-light", "technical-dark",
            "swiss-light", "swiss-dark"; None/null (the default) means
            unconfigured —
            configured initial theme for every viewer output. A saved user
            preference (``localStorage['okf-theme-family']`` /
            ``['okf-theme-mode']``, owned by viewer/static/theme.js, which
            also migrates the retired ``okf-theme`` key once) overrides it;
            otherwise this value applies, then Swiss Auto/OS fallback.
        cdn (bool): if False, the single-file / graph templates omit the
            CDN ``<script>`` tag for Cytoscape.js. The graph view will then
            degrade (no rendering) but the page still loads — useful for
            fully offline packaging where the user inlines their own copy.
            Markdown bodies are always rendered server-side; no client-side
            markdown parser is used.

    All values are VALIDATED against their allowed sets before use, so a
    malicious config.json cannot inject arbitrary values into template
    contexts (defence against supply-chain XSS via config interpolation).
    Invalid files raise :class:`ViewerConfigError` with the file and field;
    they never silently disappear behind defaults.
    """
    cfg = dict(_DEFAULT_CONFIG)
    path = bundle.root / _OKF_VIEWER_SUBDIR / "config.json"
    if path.is_file():
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as e:
            raise ViewerConfigError(f"could not read viewer config {path}: {e}") from e
        try:
            data = json.loads(source)
        except json.JSONDecodeError as e:
            raise ViewerConfigError(
                f"invalid viewer config {path}: malformed JSON at "
                f"line {e.lineno} column {e.colno}: {e.msg}"
            ) from e
        if not isinstance(data, dict):
            raise ViewerConfigError(
                f"invalid viewer config {path}: expected a JSON object at the "
                f"top level, got {type(data).__name__}"
            )
        unknown = sorted(set(data) - set(_DEFAULT_CONFIG))
        if unknown:
            raise ViewerConfigError(
                f"invalid viewer config {path}: unknown key(s) "
                f"{', '.join(repr(key) for key in unknown)}; "
                f"expected only {sorted(_DEFAULT_CONFIG)}"
            )
        for key, value in data.items():
            cfg[key] = _viewer_config_value(path, key, value)
    return cfg


# ---------------------------------------------------------------------------
# Template / static resolution (with bundle overrides)
# ---------------------------------------------------------------------------

def _bundle_override_path(bundle: Bundle, sub: str, name: str) -> Path:
    return bundle.root / _OKF_VIEWER_SUBDIR / sub / name


def _overrides_allowed(bundle: Bundle) -> bool:
    """Check if bundle template/static/palette overrides are allowed.

    Consults the **effective active-code gate** (P1-40):
    ``bundle_cfg.allow_active_code AND operator_consent()``. A bundle cannot
    enable its own overrides; the operator must opt in via
    ``OKF_LOOM_ALLOW_ACTIVE_CODE`` or ``--allow-active-code``.

    The per-root decision is cached (P2-45) so repeated template/static
    loads during a render do not re-read ``okf-loom.config.yaml`` from disk. Use
    :func:`clear_overrides_cache` (or :func:`set_operator_consent`) to
    invalidate.
    """
    try:
        key = str(bundle.root.resolve())
    except Exception:
        # If the root cannot be resolved (shouldn't happen for a loaded
        # bundle), fall back to the raw path string but still compute.
        key = str(bundle.root)
    cached = _OVERRIDES_CACHE.get(key)
    if cached is not None:
        return cached
    allowed = effective_allow_active_code(bundle)
    _OVERRIDES_CACHE[key] = allowed
    return allowed


def load_template(name: str, bundle: Bundle | None = None) -> str:
    """Return the named template, honouring bundle overrides.

    Bundle overrides (``.okf-loom/viewer/templates/<name>``) are only loaded when
    ``allow_active_code`` is true — they can carry arbitrary HTML/scripts.
    """
    if bundle is not None and _overrides_allowed(bundle):
        override = _bundle_override_path(bundle, "templates", name)
        # P1-4 (security): refuse to follow a bundle template override whose
        # resolved path escapes the bundle root via symlink (e.g. an override
        # symlinked to ~/.aws/credentials). Fail CLOSED to the builtin
        # template — the override is untrusted bundle content; without this
        # check the secret would be served over HTTP (serve) and written into
        # built output (build/render).
        from ..paths import path_within_bundle
        if override.is_file() and path_within_bundle(override, bundle.root):
            return _strip_template_doc_comment(override.read_text(encoding="utf-8"))
    builtin = _BUILTIN_TEMPLATES / name
    if not builtin.is_file():
        raise FileNotFoundError(f"Template not found: {name}")
    return _strip_template_doc_comment(builtin.read_text(encoding="utf-8"))


# iter3 P2-4: templates carry a leading ``<!-- ... -->`` documentation block
# (placeholder contract for maintainers). Without stripping, this ~10 KB
# comment ships in EVERY generated HTML page across static/spa/serve/single-
# file targets (~47% of page bytes). The comment sits between
# ``<!DOCTYPE html>`` and ``<html>`` — never meaningful content — so stripping
# it at load time is safe for both builtin and override templates.
_TEMPLATE_DOC_RE = re.compile(
    r"(<!DOCTYPE html>\s*)<!--.*?-->\s*(<html)",
    re.DOTALL | re.IGNORECASE,
)


def _strip_template_doc_comment(html: str) -> str:
    """Remove the leading template documentation comment block.

    Only strips a ``<!-- ... -->`` block that appears between ``<!DOCTYPE
    html>`` and ``<html>`` — body comments (including the
    ``<!-- okf:generated:index begin/end -->`` markers) are never touched.
    """
    return _TEMPLATE_DOC_RE.sub(r"\1\2", html, count=1)


def _resolve_static(name: str, bundle: Bundle | None = None) -> tuple[str, bool]:
    """Resolve a static asset to ``(content, is_override)``.

    Single resolution path shared by :func:`load_static`,
    :func:`asset_version`, and the live ``/__static`` handler. Enforces the
    one explicit override-name scope (see :data:`STATIC_ASSET_NAMES`):
    unknown names raise ``FileNotFoundError`` here, so loaders, the hasher,
    and the server all reject out-of-scope names at the same boundary.

    A bundle override is honoured only when ALL of: the name is in scope, the
    effective active-code gate is open, the override file exists, and the
    resolved path stays within the bundle root (P1-4 symlink-escape guard).
    ``is_override`` is ``True`` iff the returned bytes came from the bundle
    tree (mutable content) rather than the built-ins (process-constant).
    """
    if name not in STATIC_ASSET_NAMES:
        raise FileNotFoundError(f"Static asset not found: {name}")
    if bundle is not None and _overrides_allowed(bundle):
        override = _bundle_override_path(bundle, "static", name)
        # P1-4 (security): same symlink-escape containment as load_template.
        from ..paths import path_within_bundle
        if override.is_file() and path_within_bundle(override, bundle.root):
            return override.read_text(encoding="utf-8"), True
    builtin = _BUILTIN_STATIC / name
    if not builtin.is_file():
        raise FileNotFoundError(f"Static asset not found: {name}")
    return builtin.read_text(encoding="utf-8"), False


def load_static(name: str, bundle: Bundle | None = None) -> str:
    """Return the named static asset, honouring bundle overrides.

    Bundle overrides (``.okf-loom/viewer/static/<name>``) are only loaded when
    ``allow_active_code`` is true — they can carry arbitrary JS. Only names in
    :data:`STATIC_ASSET_NAMES` (the built-in viewer asset set) are loadable;
    unknown names raise ``FileNotFoundError``.
    """
    content, _is_override = _resolve_static(name, bundle)
    return content


def list_builtin_static() -> list[str]:
    """Names of all built-in static assets (used for static-site emission).

    Derived from :data:`STATIC_ASSET_NAMES` so the file-emission list, the
    override-name scope, and the versioning hasher all share one source of
    truth.
    """
    return sorted(STATIC_ASSET_NAMES)


# ---------------------------------------------------------------------------
# Deterministic asset versioning (cache-busting)
# ---------------------------------------------------------------------------
#
# External viewer asset URLs (the ``/__static/<name>`` references emitted into
# live/serve, SPA, and static-build HTML) carry a content-derived ``?v=``
# query so a browser or CDN fetches the fresh bytes after any asset edit
# (builtin upgrade or bundle override change). The single digest contract:
#
#   * The version is the first :data:`_ASSET_VERSION_LEN` hex chars of the
#     SHA-256 of the resolved asset content (the same bytes
#     :func:`_resolve_static` returns — builtin or bundle override).
#   * Same content ⇒ same version, deterministically, across runs and
#     machines (no per-process timestamp or random salt).
#   * Any content change ⇒ a different version with overwhelming probability.
#   * The version is identical for live serve, SPA build, and static build,
#     because all three resolve the same source content through
#     :func:`_resolve_static`.
#
# Mutable-override freshness (no stale-cache race):
#
#   Only process-constant BUILTIN digests are memoized (keyed by name).
#   Mutable bundle-ROOT override digests are computed from the currently
#   resolved bytes on EVERY call and are NEVER stored in the cache. This
#   makes a stale-set race structurally impossible: there is no cached
#   override value for a concurrent reader to restore after the file has
#   been edited, and freshness never depends on the bundle watcher or a
#   manual ``clear_overrides_cache``. A gate toggle re-runs
#   ``_overrides_allowed`` (its own cache is cleared by
#   :func:`set_operator_consent`) and re-resolves builtin-vs-override, so
#   the version flips without any version-cache invalidation.
#
# Routing impact: none. The live server routes on ``urlparse().path``
# (``/__static/<name>``), so the ``?v=`` query is ignored; static-site web
# servers ignore query strings on files. CSP ``default-src 'self'`` is
# unaffected — a same-origin URL with a query is still ``'self'``.
#
# Single-file output is intentionally NOT versioned: it inlines CSS/JS
# directly into the HTML, so there are no external asset URLs to bust.

# 16 hex chars = 64 bits of SHA-256. Collision-safe for cache-busting (cf.
# git's 7-40 hex of SHA-1, npm's 8 hex of SHA-512); short enough to keep
# emitted URLs tidy.
_ASSET_VERSION_LEN: int = 16

# BUILTIN-name → version. Holds ONLY process-constant built-in digests
# (override digests are never stored — see the freshness note above), so it
# needs no invalidation: builtin content does not change during a process.
_ASSET_VERSION_CACHE: dict[str, str] = {}


def asset_version(name: str, bundle: Bundle | None = None) -> str:
    """Deterministic content-derived version string for a resolved static asset.

    Returns the first :data:`_ASSET_VERSION_LEN` hex chars of the SHA-256 of
    the asset content :func:`_resolve_static` resolves (builtin unless a
    bundle override is effective). The value is a pure function of the
    resolved bytes: identical across processes, runs, and machines, and
    stable across the live/SPA/static emit paths (the single digest
    contract).

    Freshness model: a BUILTIN digest is memoized by name (process-constant,
    race-free); a bundle-OVERRIDE digest is recomputed from the currently
    resolved bytes on every call and is never cached, so an override edit is
    reflected immediately with no watcher/manual cache clear and no stale-set
    race. Returns an empty string only for an unknown/out-of-scope name
    (callers that reference real builtins never hit this; it exists so a
    typo cannot raise during a render).
    """
    try:
        content, is_override = _resolve_static(name, bundle)
    except FileNotFoundError:
        return ""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:_ASSET_VERSION_LEN]
    if is_override:
        # Mutable bundle-root content: never memoize. The value returned is
        # always derived from the bytes resolved on THIS call, so a stale
        # value cannot be restored by a concurrent completion.
        return digest
    cached = _ASSET_VERSION_CACHE.get(name)
    if cached is not None:
        return cached
    _ASSET_VERSION_CACHE[name] = digest
    return digest


def versioned_asset_url(
    name: str, static_prefix: str, bundle: Bundle | None = None
) -> str:
    """Asset URL with a content-derived ``?v=`` cache-busting query.

    ``static_prefix`` is preserved verbatim — absolute ``/__static`` for
    serve/spa, relative ``__static`` / ``../../__static`` for static builds
    — so CSP ``'self'`` and existing path routing are unaffected. When no
    version can be computed (unknown asset name) the plain URL is returned
    with no query, so routing never depends on the version being present.
    """
    version = asset_version(name, bundle)
    if not version:
        return f"{static_prefix}/{name}"
    return f"{static_prefix}/{name}?v={version}"
