"""Unit tests for the OKF viewer assets module.

Currently focused on the type-palette algorithm (iter3 CRI3-004):
``auto_palette`` switched from a per-name crc32 hash to a golden-angle
hue spread over the sorted type list so adjacent types get maximally
distinct hues. The iter-2 visual review specifically called out
Dataset/Playbook and Reference/Table pairs as visually indistinguishable
under the old hash — these tests pin the new behaviour.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from okf_loom.config import _ALLOWED_STUDIO_THEMES
from okf_loom.exceptions import OKFError
from okf_loom.render import _THEMES
from okf_loom.theme import CONFIGURABLE_THEMES, EXPLICIT_THEMES
from okf_loom.viewer import assets


# ---------------------------------------------------------------------------
# iter3 CRI3-004 — auto_palette uses golden-angle hue spread
# ---------------------------------------------------------------------------


# Hue extraction from an hsl(...) string. Tolerates the whitespace/comma
# variants hsl_color may emit across Python format strings.
_HSL_HUE_RE = re.compile(r"hsla?\(\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)


def _hue(color: str) -> float:
    m = _HSL_HUE_RE.match(color.strip())
    assert m, f"not an hsl color: {color!r}"
    return float(m.group(1)) % 360


def _hue_distance(a: float, b: float) -> float:
    """Shortest arc distance between two hues on the 360° wheel."""
    d = abs(a - b) % 360
    return min(d, 360 - d)


def test_auto_palette_returns_one_color_per_type() -> None:
    """Every non-empty type gets exactly one colour; empties are dropped."""
    pal = assets.auto_palette(["Dataset", "Table", "Playbook", "Reference", ""])
    assert set(pal.keys()) == {"Dataset", "Table", "Playbook", "Reference"}
    # Every value is a valid hsl() string (the renderer's CSS-colour
    # allowlist accepts hsl(); a malformed entry would survive the
    # auto-palette path but break the bundle-override sanitiser).
    for v in pal.values():
        assert v.startswith("hsl("), f"non-hsl color in auto palette: {v!r}"


def test_auto_palette_is_deterministic_across_call_order() -> None:
    """The palette is keyed off the SORTED type list, so a different input
    order must produce the same mapping (stable across runs + machines;
    a hash-of-the-input-order would not have this property).
    """
    types_a = ["Dataset", "Table", "Playbook", "Reference"]
    types_b = list(reversed(types_a))
    types_c = ["Playbook", "Reference", "Dataset", "Table"]
    pal_a = assets.auto_palette(types_a)
    pal_b = assets.auto_palette(types_b)
    pal_c = assets.auto_palette(types_c)
    assert pal_a == pal_b == pal_c, (
        "auto_palette is not order-independent — the sorted-list seeding "
        "is broken"
    )


def test_auto_palette_dedupes_repeated_types() -> None:
    """A repeated type in the input gets a single palette entry (the set
    comprehension in auto_palette strips dups)."""
    pal = assets.auto_palette(["Dataset", "Dataset", "Table", "Table"])
    assert pal == assets.auto_palette(["Dataset", "Table"])


def test_auto_palette_no_two_types_share_a_hue() -> None:
    """iter3 CRI3-004: the whole point of the golden-angle spread is that
    adjacent types in the sorted list get maximally distinct hues. With
    up to 12 types in a typical catalog, every hue must be unique."""
    types = ["Dataset", "Table", "Playbook", "Reference", "Metric",
             "Service", "API", "PlaybookRun", "Decision", "Note",
             "Glossary", "Owner"]
    pal = assets.auto_palette(types)
    hues = sorted({_hue(c) for c in pal.values()})
    assert len(hues) == len(pal), (
        f"two types share a hue under golden-angle spread: {pal!r}"
    )


def test_auto_palette_fixes_iter2_collision_pairs() -> None:
    """iter3 CRI3-004: the iter-2 visual review specifically called out
    Dataset/Playbook and Reference/Table pairs as near-indistinguishable
    under the old crc32 hash (their hues landed within ~20° of each other
    at 62% saturation). Under the golden-angle spread, every adjacent
    pair in a small type catalog must be ≥ 30° apart on the hue wheel so
    a user can tell the two apart on the graph canvas at a glance.
    """
    types = sorted({"Dataset", "Table", "Playbook", "Reference"})
    pal = assets.auto_palette(types)
    hues = {t: _hue(pal[t]) for t in types}
    # Every PAIR must be at least 30° apart — far above the JND for hue
    # at 62% saturation, and enough that two adjacent legend swatches
    # read as different colours.
    pairs = [
        ("Dataset", "Playbook"),
        ("Reference", "Table"),
        ("Dataset", "Reference"),
        ("Table", "Playbook"),
    ]
    for a, b in pairs:
        d = _hue_distance(hues[a], hues[b])
        assert d >= 30.0, (
            f"{a} (h={hues[a]:.1f}°) and {b} (h={hues[b]:.1f}°) are only "
            f"{d:.1f}° apart — under the 30° minimum for visual "
            f"distinctness at 62% saturation. Palette: {pal!r}"
        )


def test_auto_palette_handles_empty_and_single_type() -> None:
    """Edge cases: empty list → empty palette; one type → one entry at
    the seed hue (0°)."""
    assert assets.auto_palette([]) == {}
    assert assets.auto_palette([""]) == {}
    pal = assets.auto_palette(["Dataset"])
    assert set(pal.keys()) == {"Dataset"}
    # The first type in the sorted list is at index 0 → hue 0.
    assert _hue(pal["Dataset"]) == 0.0


def test_auto_palette_first_three_hues_follow_golden_angle() -> None:
    """The first three types in the sorted list must land at hue 0°,
    ~137.5°, and ~275° — the canonical golden-angle progression. This
    pins the algorithm against accidental re-ordering: if the seeding
    changes (e.g. someone re-introduces the hash), this test fails
    loudly with the expected-vs-actual hues.
    """
    pal = assets.auto_palette(["A", "B", "C"])
    h_a = _hue(pal["A"])
    h_b = _hue(pal["B"])
    h_c = _hue(pal["C"])
    assert h_a == 0.0, f"first hue should be 0°, got {h_a}"
    assert abs(h_b - 137.508) < 1.0, (
        f"second hue should be ~137.5° (golden angle), got {h_b}"
    )
    assert abs(h_c - 275.016) < 1.0, (
        f"third hue should be ~275° (2× golden angle mod 360), got {h_c}"
    )


def test_stable_hue_still_exists_for_render_fallback() -> None:
    """render.py:404 falls back to ``hsl_color(stable_hue(type))`` for a
    type that is not in the resolved palette (e.g. a concept whose type
    was added live by a CLI mutator that has not re-resolved yet). The
    golden-angle change must NOT remove that fallback path — stable_hue
    still exists and still produces a stable 0..359 hue for any string.
    """
    h1 = assets.stable_hue("Reference")
    h2 = assets.stable_hue("Reference")
    assert h1 == h2, "stable_hue must be deterministic across calls"
    assert 0 <= h1 < 360, f"stable_hue out of range: {h1}"
    # And the two utilities compose (render.py:404 pattern).
    color = assets.hsl_color(assets.stable_hue("Dataset"))
    assert color.startswith("hsl(")


# ---------------------------------------------------------------------------
# Editorial Workbench hardening — public viewer config validation
# ---------------------------------------------------------------------------


def _viewer_bundle(tmp_path, content: str | None = None):
    if content is not None:
        config_dir = tmp_path / ".okf-loom" / "viewer"
        config_dir.mkdir(parents=True)
        (config_dir / "config.json").write_text(content, encoding="utf-8")
    return SimpleNamespace(root=tmp_path, name="test-bundle")


def test_viewer_config_absent_uses_validated_defaults(tmp_path) -> None:
    assert assets.load_config(_viewer_bundle(tmp_path)) == {
        "name": None,
        "default_layout": "cose",
        "theme": "technical-light",
        "cdn": True,
    }


def test_viewer_config_accepts_all_fields_and_special_characters_in_name(tmp_path) -> None:
    data = {
        "name": 'Research </script> & "Review"',
        "default_layout": "grid",
        "theme": "swiss-dark",
        "cdn": False,
    }
    assert assets.load_config(_viewer_bundle(tmp_path, json.dumps(data))) == data


@pytest.mark.parametrize("theme", EXPLICIT_THEMES)
def test_viewer_config_accepts_every_concrete_theme(tmp_path, theme: str) -> None:
    cfg = assets.load_config(_viewer_bundle(tmp_path, json.dumps({"theme": theme})))
    assert cfg["theme"] == theme


def test_backend_theme_manifests_match_renderer_and_yaml_contract() -> None:
    assert tuple(_THEMES) == EXPLICIT_THEMES
    assert assets._ALLOWED_THEMES == frozenset(EXPLICIT_THEMES)
    assert _ALLOWED_STUDIO_THEMES == CONFIGURABLE_THEMES


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('{"theme":', r"config\.json.*line 1 column"),
        ('["swiss-light"]', r"config\.json.*JSON object.*list"),
        ('{"mystery": true}', r"config\.json.*unknown key.*mystery"),
        ('{"cdn": "false"}', r"config\.json.*cdn.*boolean"),
        ('{"default_layout": "spiral"}', r"default_layout.*spiral.*expected one of"),
        ('{"theme": ""}', r"theme.*empty or whitespace"),
        ('{"theme": "   "}', r"theme.*empty or whitespace"),
        ('{"theme": "<script>"}', r"theme.*<script>.*expected one of"),
    ],
)
def test_viewer_config_rejects_invalid_input_with_context(
    tmp_path, content: str, message: str
) -> None:
    with pytest.raises(assets.ViewerConfigError, match=message):
        assets.load_config(_viewer_bundle(tmp_path, content))


def test_viewer_config_error_is_project_domain_and_value_error(tmp_path) -> None:
    with pytest.raises(assets.ViewerConfigError) as caught:
        assets.load_config(_viewer_bundle(tmp_path, '{"theme":'))
    assert isinstance(caught.value, OKFError)
    assert isinstance(caught.value, ValueError)


@pytest.mark.parametrize(
    ("legacy", "replacement"),
    [
        ("light", "technical-light"),
        ("dark", "technical-dark"),
        ("pastel", "swiss-light"),
        ("sepia", "swiss-light"),
        ("midnight", "technical-dark"),
    ],
)
def test_viewer_config_rejects_legacy_theme_with_migration(
    tmp_path, legacy: str, replacement: str
) -> None:
    content = json.dumps({"theme": legacy})
    with pytest.raises(
        assets.ViewerConfigError,
        match=rf"legacy theme {legacy!r}.*replace it with {replacement!r}",
    ):
        assets.load_config(_viewer_bundle(tmp_path, content))
