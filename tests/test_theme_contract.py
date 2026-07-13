"""Canonical frontend theme-state contract (Editorial Workbench hardening).

Pinned invariants (hardening plan "State ownership contract" + Phase 2):

  * viewer/static/theme.js is the ONE client-side owner of theme state: the
    only writer of ``data-theme`` and of the theme/modifier localStorage keys
    among all viewer JS assets.
  * Its THEMES / LEGACY_THEMES manifests mirror the backend contract in
    ``okf_loom.theme`` exactly (names AND order for THEMES; full mapping for
    the legacy migrations).
  * Every page target ships theme.js BEFORE its consumers (wiki.js /
    graph.js / renderers.js) so ``window.OKFLoomTheme`` exists when they run:
    static + spa builds link it in <head>; the single-file build inlines it
    first.
  * A concrete configured theme (viewer config.json) is server-painted into
    ``data-theme`` on every target; an UNCONFIGURED bundle emits no
    ``data-theme`` at all — the built-in default must never masquerade as an
    author-configured preference (it would override the Swiss Auto/OS
    fallback and freeze OS-following).

Browser-level state transitions (reload/navigation, OS changes, storage
denial, migration) are proved in tests/test_theme_state_browser.py.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from okf_loom import Bundle
from okf_loom.render import build_site, render_single_file
from okf_loom.theme import EXPLICIT_THEMES, LEGACY_THEME_MIGRATIONS

from conftest import TOOLKIT_ROOT

STATIC_DIR = TOOLKIT_ROOT / "scripts" / "okf_loom" / "viewer" / "static"
THEME_JS = STATIC_DIR / "theme.js"


def _theme_js_source() -> str:
    return THEME_JS.read_text(encoding="utf-8")


# --- manifest parity (plan Phase 1.2) ---------------------------------------


def test_theme_js_themes_manifest_matches_backend() -> None:
    """theme.js THEMES mirrors okf_loom.theme.EXPLICIT_THEMES (values + order)."""
    src = _theme_js_source()
    m = re.search(r"var THEMES = \[([^\]]*)\];", src)
    assert m, "theme.js THEMES manifest missing"
    js_themes = tuple(re.findall(r'"([^"]+)"', m.group(1)))
    assert js_themes == EXPLICIT_THEMES


def test_theme_js_legacy_migrations_match_backend() -> None:
    """theme.js LEGACY_THEMES mirrors okf_loom.theme.LEGACY_THEME_MIGRATIONS."""
    src = _theme_js_source()
    m = re.search(r"var LEGACY_THEMES = \{(.*?)\};", src, re.DOTALL)
    assert m, "theme.js LEGACY_THEMES manifest missing"
    js_map = dict(re.findall(r'(\w+):\s*"([^"]+)"', m.group(1)))
    assert js_map == LEGACY_THEME_MIGRATIONS


def test_theme_js_declares_canonical_storage_keys() -> None:
    """Family and mode persist under dedicated validated keys; the retired
    key remains only for one-time migration + explicit-choice mirroring."""
    src = _theme_js_source()
    assert 'var FAMILY_KEY = "okf-theme-family";' in src
    assert 'var MODE_KEY = "okf-theme-mode";' in src
    assert 'var LEGACY_KEY = "okf-theme";' in src


# --- single-writer ownership (state-ownership contract) ----------------------

# Writers of theme state: any set/remove of the theme or modifier keys, or a
# write of the resolved data-theme attribute. Only theme.js may match.
_THEME_WRITE_RE = re.compile(
    r"""localStorage\s*\.\s*(?:setItem|removeItem)\s*\(\s*["']
        (?:okf-theme(?:-family|-mode)?|okf-contrast|okf-border)["']
     |  \.setAttribute\s*\(\s*["']data-(?:theme|okf-contrast|okf-border)["']
     |  localStorage\s*\[\s*["']okf-theme""",
    re.VERBOSE,
)


@pytest.mark.parametrize(
    "js_file",
    sorted(p for p in STATIC_DIR.glob("*.js") if p.name != "theme.js"),
    ids=lambda p: p.name,
)
def test_only_theme_js_writes_theme_state(js_file: Path) -> None:
    """No other viewer asset writes theme storage or the data-theme root —
    per-surface interpretation is what the hardening plan removed."""
    src = js_file.read_text(encoding="utf-8")
    hits = _THEME_WRITE_RE.findall(src)
    assert not hits, (
        f"{js_file.name} writes theme state directly; "
        "route it through window.OKFLoomTheme (viewer/static/theme.js)"
    )


def test_theme_js_never_persists_inside_os_change_handler() -> None:
    """The OS colour-scheme handler only re-applies (derived value); it must
    not write storage — persisting there froze Auto after one change."""
    src = _theme_js_source()
    m = re.search(r"var onSchemeChange = function \(\) \{(.*?)\};", src, re.DOTALL)
    assert m, "OS colour-scheme handler missing from theme.js"
    assert "localStorage" not in m.group(1)
    assert "writeKey" not in m.group(1)


# --- wiring: every output target loads theme.js first ------------------------


@pytest.fixture()
def demo_bundle(tmp_path: Path) -> Path:
    """Throwaway copy of the demo bundle (tests may write viewer config)."""
    import shutil

    dest = tmp_path / "bundle"
    shutil.copytree(TOOLKIT_ROOT / "samples" / "demo_bundle", dest)
    return dest


def _configure_theme(bundle_root: Path, theme: str) -> None:
    cfg_dir = bundle_root / ".okf-loom" / "viewer"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"theme": theme}), encoding="utf-8"
    )


@pytest.mark.parametrize("target", ["static", "spa"])
def test_built_sites_ship_theme_js_before_consumers(
    demo_bundle: Path, tmp_path: Path, target: str
) -> None:
    out = tmp_path / target
    build_site(Bundle.load(demo_bundle), out, target=target)
    assert (out / "__static" / "theme.js").is_file(), "theme.js not emitted"

    pages = [out / "index.html", out / "__graph.html", out / "__search.html"]
    pages.append(next(out.rglob("orders.html")))
    for page in pages:
        html = page.read_text(encoding="utf-8")
        theme_at = html.find("/theme.js")
        assert theme_at > 0, f"{page.name}: theme.js script tag missing"
        assert "__THEME_JS_LINK__" not in html, f"{page.name}: placeholder leaked"
        for consumer in ("/wiki.js", "/graph.js", "/renderers.js"):
            at = html.find(consumer)
            if at >= 0:
                assert theme_at < at, (
                    f"{page.name}: theme.js must load before {consumer} "
                    "(consumers read window.OKFLoomTheme)"
                )


def test_single_file_inlines_theme_js_first(demo_bundle: Path, tmp_path: Path) -> None:
    out = tmp_path / "viz.html"
    render_single_file(Bundle.load(demo_bundle), out)
    html = out.read_text(encoding="utf-8")
    assert "OKFLoomTheme" in html, "theme.js not inlined into single-file output"
    # theme.js executes before graph.js in the shared inline <script>
    # (probes are code strings unique to each asset — CSS comments also
    # mention GRAPH_COLORS, so the constant name alone is ambiguous).
    theme_at = html.find('var FAMILY_KEY = "okf-theme-family";')
    graph_at = html.find("function graphPalette()")
    assert theme_at > 0 and graph_at > 0
    assert theme_at < graph_at, "theme.js must be inlined before graph.js"


# --- server-rendered popover state parity -------------------------------------


@pytest.mark.parametrize("theme", EXPLICIT_THEMES)
def test_theme_button_html_splits_family_and_mode_at_last_hyphen(theme: str) -> None:
    """The renderer's family/mode split (rpartition) matches theme.js's
    lastIndexOf("-") parsing for every concrete theme, so the server-painted
    aria-checked state agrees with the client resolver."""
    from okf_loom.render import _theme_button_html

    family, _, mode = theme.rpartition("-")
    html = _theme_button_html(theme)
    assert f'data-okf-set="family" data-okf-val="{family}" aria-checked="true"' in html
    assert f'data-okf-set="mode" data-okf-val="{mode}" aria-checked="true"' in html


# --- configured default is painted; the built-in default is not --------------


def test_unconfigured_bundle_emits_no_data_theme(
    demo_bundle: Path, tmp_path: Path
) -> None:
    """No author configuration → no data-theme anywhere: theme.js resolves
    the Swiss Auto/OS fallback and keeps following the OS."""
    out = tmp_path / "site"
    build_site(Bundle.load(demo_bundle), out, target="static")
    for page in ("index.html", "__graph.html", "__search.html"):
        head = (out / page).read_text(encoding="utf-8").split("<body", 1)[0]
        assert "data-theme=" not in head, f"{page}: built-in default painted"
    sf = tmp_path / "viz.html"
    render_single_file(Bundle.load(demo_bundle), sf)
    html = sf.read_text(encoding="utf-8")
    assert '<html lang="en">' in html
    assert 'window.OKF_LOOM_INITIAL_THEME = "auto"' in html


def test_configured_theme_is_server_painted_everywhere(
    demo_bundle: Path, tmp_path: Path
) -> None:
    """A concrete configured theme survives first boot: the server paints it
    into data-theme on every target (theme.js treats it as the configured
    preference unless a saved user preference exists)."""
    _configure_theme(demo_bundle, "swiss-dark")
    bundle = Bundle.load(demo_bundle)
    out = tmp_path / "site"
    build_site(bundle, out, target="static")
    pages = [out / "index.html", out / "__graph.html", out / "__search.html"]
    pages.append(next(out.rglob("orders.html")))
    for page in pages:
        head = page.read_text(encoding="utf-8").split("<body", 1)[0]
        assert ' data-theme="swiss-dark"' in head, f"{page.name}: configured theme lost"
    sf = tmp_path / "viz.html"
    render_single_file(bundle, sf)
    assert ' data-theme="swiss-dark"' in sf.read_text(encoding="utf-8").split("<body", 1)[0]
