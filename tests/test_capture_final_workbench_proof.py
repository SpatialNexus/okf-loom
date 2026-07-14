from __future__ import annotations

from types import SimpleNamespace

import capture_final_workbench_proof as final_proof


def test_final_matrix_covers_all_live_theme_surface_pairs():
    scenarios = final_proof.final_scenarios()
    expected_surfaces = {"index", "concept", "search", "graph-map", "studio-comments"}

    actual = {
        (scenario.theme, scenario.surface)
        for scenario in scenarios
        if scenario.source == "live" and scenario.variant == "default"
    }

    assert actual == {
        (theme, surface)
        for theme in final_proof.CANONICAL_THEMES
        for surface in expected_surfaces
    }


def test_final_matrix_has_static_single_file_mobile_and_environment_handoffs():
    scenarios = final_proof.final_scenarios()

    assert {scenario.source for scenario in scenarios} == {
        "live", "static", "single-file"
    }
    assert {
        scenario.theme for scenario in scenarios if scenario.source == "single-file"
    } == set(final_proof.CANONICAL_THEMES)
    assert any(s.viewport == final_proof.MOBILE for s in scenarios)
    assert any(s.modifiers["border"] == "off" for s in scenarios)
    assert any(s.modifiers["contrast"] == "soft" for s in scenarios)
    assert any(s.action == "appearance" for s in scenarios)
    assert any(s.action == "bridges" for s in scenarios)
    assert any(s.environment.get("no_js") for s in scenarios)
    assert any(s.environment.get("reduced_motion") for s in scenarios)
    assert any(s.environment.get("forced_colors") for s in scenarios)


def test_post_fix_matrix_has_required_visual_closure_states_and_unique_names():
    scenarios = final_proof.final_scenarios()
    variants = {scenario.variant for scenario in scenarios}

    assert {
        "mobile-topbar", "list-first", "post-explore", "first-frame",
        "end-of-list", "appearance-selected", "static-no-js-banner",
        "static-js-on-no-banner", "neutral-empty",
        "dark-utility-rail", "mermaid-light", "mermaid-dark", "focus-explore",
        "focus-node-index", "focus-tab", "focus-composer", "focus-close",
        "focus-bottom-control", "forced-colors-graph", "forced-colors-comments",
        "reduced-motion-asserted", "focus-header", "bridges-legend",
    } <= variants
    assert {
        scenario.source for scenario in scenarios if scenario.variant == "mobile-topbar"
    } == {"live", "static", "single-file"}
    names = [
        f"{s.source}__{s.surface}__{s.theme}__{s.viewport['width']}px__{s.variant}.png"
        for s in scenarios
    ]
    assert len(names) == len(set(names))
    assert len(names) == 62


def test_static_banner_scenarios_cover_js_disabled_and_enabled_states():
    scenarios = final_proof.final_scenarios()
    no_js = next(s for s in scenarios if s.variant == "static-no-js-banner")
    js_on = next(s for s in scenarios if s.variant == "static-js-on-no-banner")

    assert no_js.source == js_on.source == "static"
    assert no_js.environment == {"no_js": True}
    assert no_js.action == "no-js-banner"
    assert js_on.environment == {}
    assert js_on.action == "js-on-banner"


def test_reduced_motion_is_an_asserted_explore_scenario_not_still_only():
    scenarios = [
        scenario for scenario in final_proof.final_scenarios()
        if scenario.variant == "reduced-motion-asserted"
    ]

    assert len(scenarios) == 1
    assert scenarios[0].environment == {"reduced_motion": True}
    assert scenarios[0].action == "reduced-explore"


def test_seed_script_uses_canonical_family_mode_and_modifier_keys():
    scenario = final_proof.Scenario(
        "live", "concept", "/demo/showcase", "concept", "technical-dark",
        modifiers={"contrast": "soft", "border": "off"},
    )

    script = final_proof._seed_script(scenario)

    assert "okf-theme-family" in script
    assert "okf-theme-mode" in script
    assert "okf-contrast" in script
    assert "okf-border" in script
    assert '"family": "technical"' in script
    assert '"mode": "dark"' in script


def test_single_file_builder_uses_supported_build_target(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(final_proof.subprocess, "run", fake_run)
    final_proof._build_single_file(tmp_path / "bundle", tmp_path / "out")

    assert seen["argv"][-2:] == ["--target", "single-file"]
    assert seen["kwargs"]["capture_output"] is True
