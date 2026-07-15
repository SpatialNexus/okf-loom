#!/usr/bin/env python3
"""Capture the final Editorial Workbench parity matrix.

The matrix is intentionally pairwise outside the live all-theme surface pass:
live proves every canonical theme on index/concept/search/graph/studio, while
static and single-file add representative export parity, mobile, modifiers,
Appearance, reduced motion, forced colors, and no-JS fallback.  This avoids a
Cartesian explosion while preserving one direct artifact for every contract
row.  Every screenshot has a normalized manifest record.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    from scripts.capture_support import (
        CANONICAL_THEMES,
        display_path,
        launch_chromium,
        wait_for_capture_ready,
        wait_for_graph_layout_after,
        write_capture_manifest,
    )
    from scripts.capture_viewer_proof import _LiveServer, _StaticServer, _build_static_site
except ModuleNotFoundError:  # pragma: no cover - direct invocation path
    from capture_support import (
        CANONICAL_THEMES,
        display_path,
        launch_chromium,
        wait_for_capture_ready,
        wait_for_graph_layout_after,
        write_capture_manifest,
    )
    from capture_viewer_proof import _LiveServer, _StaticServer, _build_static_site

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE = REPO_ROOT / "docs-bundle"
DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}
READY_TIMEOUT_MS = 20_000


@dataclass(frozen=True)
class Scenario:
    source: str
    surface: str
    route: str
    target: str
    theme: str
    viewport: dict[str, int] = field(default_factory=lambda: dict(DESKTOP))
    variant: str = "default"
    modifiers: dict[str, str] = field(
        default_factory=lambda: {"contrast": "high", "border": "on"}
    )
    environment: dict[str, object] = field(default_factory=dict)
    action: str | None = None


def final_scenarios() -> list[Scenario]:
    """Return the bounded final matrix in deterministic capture order."""
    scenarios: list[Scenario] = []
    live_surfaces = (
        ("index", "/", "index", None),
        ("concept", "/demo/showcase", "rendering", None),
        ("search", "/__search?q=studio", "search", None),
        ("graph-map", "/__graph", "graph", None),
        ("studio-comments", "/demo/showcase", "studio", "studio"),
    )
    for theme in CANONICAL_THEMES:
        for surface, route, target, action in live_surfaces:
            scenarios.append(Scenario("live", surface, route, target, theme, action=action))

    # Export parity is pairwise: every static surface once, every single-file
    # theme once. Live above remains the exhaustive theme/surface owner.
    scenarios.extend((
        Scenario("static", "index", "/index.html", "index", "swiss-light"),
        Scenario("static", "concept", "/demo/showcase.html", "rendering", "technical-dark"),
        Scenario("static", "search", "/__search.html", "search", "swiss-dark"),
        Scenario("static", "graph-map", "/__graph.html", "graph", "technical-light"),
    ))
    scenarios.extend(
        Scenario("single-file", "graph-map", "/index.html", "graph", theme)
        for theme in CANONICAL_THEMES
    )

    scenarios.extend((
        Scenario("live", "studio-comments", "/demo/showcase", "studio", "technical-dark",
                 viewport=dict(MOBILE), variant="mobile", action="studio"),
        Scenario("live", "graph-map", "/__graph", "graph", "swiss-light",
                 viewport=dict(MOBILE), variant="mobile"),
        Scenario("static", "concept", "/demo/showcase.html", "rendering", "swiss-dark",
                 viewport=dict(MOBILE), variant="mobile"),
        Scenario("single-file", "graph-map", "/index.html", "graph", "technical-light",
                 viewport=dict(MOBILE), variant="mobile"),
        Scenario("live", "index", "/", "index", "swiss-light",
                 variant="appearance", action="appearance"),
        Scenario("live", "concept", "/demo/showcase", "rendering", "technical-light",
                 variant="border-off", modifiers={"contrast": "high", "border": "off"}),
        Scenario("live", "search", "/__search?q=studio", "search", "swiss-dark",
                 variant="soft-contrast", modifiers={"contrast": "soft", "border": "on"}),
        Scenario("live", "graph-bridges", "/__graph", "graph", "technical-dark",
                 variant="bridges-legend", action="bridges"),
        Scenario("static", "concept", "/demo/showcase.html", "concept", "swiss-light",
                 variant="static-no-js-banner", environment={"no_js": True},
                 action="no-js-banner"),
        Scenario("live", "graph-map", "/__graph", "graph", "swiss-dark",
                 variant="reduced-motion", environment={"reduced_motion": True}),
        Scenario("live", "index", "/", "index", "swiss-light",
                 variant="forced-colors", environment={"forced_colors": True}),
        # Post-c2d02d4 closure frames: narrow topbars, mobile graph disclosure,
        # untouched/end-state Studio, and explicit visual assertions.
        Scenario("live", "concept", "/demo/showcase", "rendering", "swiss-light",
                 viewport=dict(MOBILE), variant="mobile-topbar", action="mobile-topbar"),
        Scenario("static", "index", "/index.html", "index", "swiss-light",
                 viewport=dict(MOBILE), variant="mobile-topbar", action="mobile-topbar"),
        Scenario("single-file", "graph-map", "/index.html", "graph", "swiss-light",
                 viewport=dict(MOBILE), variant="mobile-topbar", action="mobile-topbar"),
        Scenario("live", "graph-list", "/__graph", "graph", "swiss-light",
                 viewport=dict(MOBILE), variant="list-first", action="list-first"),
        Scenario("live", "graph-canvas", "/__graph", "graph", "swiss-light",
                 viewport=dict(MOBILE), variant="post-explore", action="explore"),
        Scenario("live", "studio-comments", "/demo/showcase", "studio", "swiss-light",
                 viewport=dict(MOBILE), variant="first-frame", action="studio-first"),
        Scenario("live", "studio-comments", "/demo/showcase", "studio", "swiss-light",
                 viewport=dict(MOBILE), variant="end-of-list", action="studio-end"),
        Scenario("live", "index", "/", "index", "swiss-light",
                 variant="appearance-selected", action="appearance-radio"),
        Scenario("static", "concept", "/demo/showcase.html", "concept", "swiss-light",
                 variant="static-js-on-no-banner", action="js-on-banner"),
        Scenario("static", "search", "/__search.html", "search", "swiss-light",
                 variant="neutral-empty", action="neutral-search"),
        Scenario("live", "concept", "/demo/showcase", "rendering", "technical-dark",
                 variant="dark-utility-rail", action="dark-rail"),
        Scenario("live", "concept", "/demo/showcase", "rendering", "swiss-light",
                 variant="mermaid-light", action="mermaid"),
        Scenario("live", "concept", "/demo/showcase", "rendering", "technical-dark",
                 variant="mermaid-dark", action="mermaid"),
        Scenario("live", "graph-map", "/__graph", "graph", "swiss-light",
                 viewport=dict(MOBILE), variant="focus-explore", action="focus-explore"),
        Scenario("live", "graph-list", "/__graph", "graph", "swiss-light",
                 viewport=dict(MOBILE), variant="focus-node-index", action="focus-node-index"),
        Scenario("live", "studio-comments", "/demo/showcase", "studio", "swiss-light",
                 viewport=dict(MOBILE), variant="focus-tab", action="studio-focus-tab"),
        Scenario("live", "studio-comments", "/demo/showcase", "studio", "swiss-light",
                 viewport=dict(MOBILE), variant="focus-composer", action="studio-focus-composer"),
        Scenario("live", "studio-comments", "/demo/showcase", "studio", "swiss-light",
                 viewport=dict(MOBILE), variant="focus-close", action="studio-focus-close"),
        Scenario("live", "concept", "/demo/showcase", "concept", "swiss-light",
                 viewport=dict(MOBILE), variant="focus-bottom-control", action="focus-bottom"),
        Scenario("live", "graph-map", "/__graph", "graph", "swiss-light",
                 viewport=dict(MOBILE), variant="forced-colors-graph",
                 environment={"forced_colors": True}, action="explore"),
        Scenario("live", "studio-comments", "/demo/showcase", "studio", "swiss-light",
                 viewport=dict(MOBILE), variant="forced-colors-comments",
                 environment={"forced_colors": True}, action="studio-first"),
        Scenario("live", "graph-map", "/__graph", "graph", "swiss-dark",
                 viewport=dict(MOBILE), variant="reduced-motion-asserted",
                 environment={"reduced_motion": True}, action="reduced-explore"),
        Scenario("live", "index", "/", "index", "swiss-light",
                 variant="focus-header", action="focus-header"),
    ))
    return scenarios


def _build_single_file(bundle: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(REPO_ROOT / "scripts" / "okf-loom"), "build", str(bundle),
         "--out", str(out_dir), "--target", "single-file"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if proc.returncode:
        raise RuntimeError(
            f"single-file build failed (rc={proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )


def _seed_script(scenario: Scenario) -> str:
    family, mode = scenario.theme.rsplit("-", 1)
    payload = {
        "family": family,
        "mode": mode,
        "contrast": scenario.modifiers["contrast"],
        "border": scenario.modifiers["border"],
    }
    return """(() => {
      const p = %s;
      try {
        localStorage.setItem('okfGraphTourDone', '1');
        localStorage.setItem('okf-theme-family', p.family);
        localStorage.setItem('okf-theme-mode', p.mode);
        localStorage.removeItem('okf-theme');
        localStorage.setItem('okf-contrast', p.contrast);
        localStorage.setItem('okf-border', p.border);
      } catch (e) {}
    })();""" % json.dumps(payload, sort_keys=True)


def _context_for(browser, scenario: Scenario):
    kwargs: dict[str, object] = {
        "viewport": scenario.viewport,
        "device_scale_factor": 1,
        "color_scheme": "dark" if scenario.theme.endswith("-dark") else "light",
        "java_script_enabled": not bool(scenario.environment.get("no_js")),
    }
    if scenario.environment.get("reduced_motion"):
        kwargs["reduced_motion"] = "reduce"
    if scenario.environment.get("forced_colors"):
        kwargs["forced_colors"] = "active"
    context = browser.new_context(**kwargs)
    if not scenario.environment.get("no_js"):
        context.add_init_script(_seed_script(scenario))
    return context


def _open_studio(page, scenario: Scenario) -> None:
    page.wait_for_function(
        "typeof window.okfLoomStudio === 'object'", timeout=READY_TIMEOUT_MS
    )
    if scenario.viewport["width"] <= 900:
        page.locator(".okf-studio-open-btn").click()
    else:
        page.locator('.okf-rail__btn[data-rail-id="comments"]').click()
    wait_for_capture_ready(page, "studio", timeout_ms=READY_TIMEOUT_MS)


def _explore_graph(page) -> dict:
    page.locator(".okf-graph-explore-map").wait_for(
        state="visible", timeout=READY_TIMEOUT_MS
    )
    page.locator(".okf-graph-explore-map").click()
    page.wait_for_function(
        "document.activeElement && document.activeElement.id === 'okf-graph'",
        timeout=READY_TIMEOUT_MS,
    )
    return page.evaluate("""() => {
      const cy = window.__okfLoomGraph && window.__okfLoomGraph.cy;
      const canvas = document.querySelector('#okf-graph canvas');
      const box = canvas && canvas.getBoundingClientRect();
      let labeled = 0;
      if (cy) cy.nodes().forEach(n => {
        const opacity = parseFloat(n.style('text-opacity'));
        if (!Number.isNaN(opacity) && opacity > 0) labeled += 1;
      });
      return {active_element: document.activeElement.id, labeled_nodes: labeled,
        canvas_width: box ? Math.round(box.width) : 0,
        canvas_height: box ? Math.round(box.height) : 0};
    }""")


def _apply_action(page, scenario: Scenario) -> tuple[dict, dict]:
    assertions: dict = {}
    if scenario.action == "appearance":
        page.get_by_role("button", name="Appearance settings").click()
        page.locator("#okf-appearance-menu:not([hidden])").wait_for(
            state="visible", timeout=READY_TIMEOUT_MS
        )
    elif scenario.action in {
        "studio", "studio-first", "studio-end", "studio-focus-tab",
        "studio-focus-composer", "studio-focus-close",
    }:
        _open_studio(page, scenario)
        if scenario.action == "studio-end":
            page.evaluate("""() => {
              const body = document.getElementById('okf-panel-body');
              body.scrollTop = body.scrollHeight;
            }""")
            page.wait_for_function("""() => {
              const body = document.getElementById('okf-panel-body');
              return body.scrollHeight - body.scrollTop - body.clientHeight <= 1;
            }""", timeout=READY_TIMEOUT_MS)
        focus_selector = {
            "studio-focus-composer": 'textarea[aria-label="Comment for agent"]',
            "studio-focus-close": ".okf-panel__close",
        }.get(scenario.action)
        focus_selector_used = None
        if scenario.action == "studio-focus-tab":
            page.keyboard.press("ArrowRight")
            page.wait_for_function(
                "document.activeElement && document.activeElement.id === "
                "'okf-panel-tab--changes'",
                timeout=READY_TIMEOUT_MS,
            )
            focus_selector_used = ".okf-panel__tab:nth-of-type(2)"
        elif scenario.action == "studio-focus-close":
            page.keyboard.press("Shift+Tab")
            page.wait_for_function(
                "document.activeElement && "
                "document.activeElement.classList.contains('okf-panel__close')",
                timeout=READY_TIMEOUT_MS,
            )
            focus_selector_used = ".okf-panel__close"
        elif focus_selector:
            page.locator(focus_selector).focus()
            focus_selector_used = focus_selector
        assertions = page.evaluate("""() => {
          const panel = document.getElementById('okf-panel');
          const body = document.getElementById('okf-panel-body');
          const box = panel.getBoundingClientRect();
          return {title_visible: !!document.querySelector('.okf-panel__title'),
            tabs: document.querySelectorAll('.okf-panel__tab').length,
            close_visible: !!document.querySelector('.okf-panel__close'),
            panel_bottom: Math.round(box.bottom), viewport_height: innerHeight,
            at_list_end: body.scrollHeight - body.scrollTop - body.clientHeight <= 1};
        }""")
        if focus_selector_used:
            assertions["focus_selector"] = focus_selector_used
    elif scenario.action == "bridges":
        previous = page.evaluate("() => window.__okfLoomGraph.layoutStats.lastAppliedSeq")
        page.get_by_role("radio", name="Bridges").click()
        wait_for_graph_layout_after(page, previous, timeout_ms=READY_TIMEOUT_MS)
        assertions = {"lens": "Bridges"}
    elif scenario.action in {"explore", "reduced-explore"}:
        if scenario.action == "reduced-explore":
            page.evaluate("""() => {
              window.__captureScrollBehaviors = [];
              const original = Element.prototype.scrollIntoView;
              Element.prototype.scrollIntoView = function(options) {
                window.__captureScrollBehaviors.push(options ? options.behavior : 'auto');
                return original.apply(this, arguments);
              };
            }""")
        assertions = _explore_graph(page)
        if scenario.action == "reduced-explore":
            behaviors = page.evaluate("window.__captureScrollBehaviors")
            reduced = page.evaluate(
                "matchMedia('(prefers-reduced-motion: reduce)').matches"
            )
            if not reduced or not behaviors or any(b != "auto" for b in behaviors):
                raise RuntimeError(
                    f"reduced-motion Explore assertion failed: "
                    f"reduced={reduced}, behaviors={behaviors}"
                )
            assertions.update({
                "reduced_motion_matches": reduced,
                "scroll_behaviors": behaviors,
                "assertion": "Explore uses auto scrolling and focuses graph",
            })
    elif scenario.action == "mobile-topbar":
        assertions = page.evaluate("""() => {
          const controls = [...document.querySelectorAll('.okf-topbar button, .okf-topbar a, .okf-topbar input, .okf-topbar select')]
            .filter(el => { const r = el.getBoundingClientRect(); return r.width && r.height; })
            .map(el => { const r = el.getBoundingClientRect(); return {
              label: el.getAttribute('aria-label') || el.textContent.trim() || el.id,
              left: Math.round(r.left), right: Math.round(r.right)}; });
          return {controls, viewport_width: innerWidth,
            all_controls_visible: controls.length > 0 && controls.every(x => x.left >= 0 && x.right <= innerWidth + 1),
            no_horizontal_overflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1};
        }""")
        if not assertions["all_controls_visible"] or not assertions["no_horizontal_overflow"]:
            raise RuntimeError(f"mobile topbar assertion failed: {assertions}")
    elif scenario.action == "list-first":
        assertions = page.evaluate("""() => {
          const index = document.querySelector('.okf-node-index');
          const graph = document.getElementById('okf-graph');
          const ir = index.getBoundingClientRect(), gr = graph.getBoundingClientRect();
          return {node_index_top: Math.round(ir.top), graph_top: Math.round(gr.top),
            node_index_left: Math.round(ir.left), node_index_right: Math.round(ir.right),
            node_index_width: Math.round(ir.width), viewport_width: innerWidth,
            node_index_full_width: Math.abs(ir.left) <= 1 &&
              Math.abs(ir.right - innerWidth) <= 1 && Math.abs(ir.width - innerWidth) <= 1,
            explore_visible: !!document.querySelector('.okf-graph-explore-map'),
            list_precedes_graph: ir.top < gr.top};
        }""")
        if not assertions["list_precedes_graph"] or not assertions["node_index_full_width"]:
            raise RuntimeError(f"mobile graph is not list-first/full-width: {assertions}")
    elif scenario.action == "appearance-radio":
        page.get_by_role("button", name="Appearance settings").click()
        option = page.locator('.okf-appearance__opt[aria-checked="true"]').first
        option.focus()
        assertions = page.evaluate("""() => {
          const option = document.querySelector('.okf-appearance__opt[aria-checked="true"]');
          return {selected_indicator: getComputedStyle(option, '::before').content,
            active_role: document.activeElement && document.activeElement.getAttribute('role')};
        }""")
    elif scenario.action in {"no-js-banner", "js-on-banner"}:
        assertions = page.evaluate("""() => {
          const banners = [...document.querySelectorAll('.okf-studio-fallback-banner')]
            .filter(el => getComputedStyle(el).display !== 'none');
          return {visible_banners: banners.length, consolidated: banners.length === 1,
            hidden: banners.length === 0, text: banners.map(x => x.textContent.trim())};
        }""")
        expected = 1 if scenario.action == "no-js-banner" else 0
        if assertions["visible_banners"] != expected:
            raise RuntimeError(
                f"expected {expected} visible static banner(s): {assertions}"
            )
    elif scenario.action == "neutral-search":
        assertions = page.evaluate("""() => {
          const heading = document.querySelector('.okf-search__title').textContent.trim();
          return {heading, neutral: !/no results/i.test(heading)};
        }""")
        if not assertions["neutral"]:
            raise RuntimeError(f"static empty search is not neutral: {assertions}")
    elif scenario.action == "dark-rail":
        page.wait_for_function(
            "typeof window.okfLoomStudio === 'object'", timeout=READY_TIMEOUT_MS
        )
        page.locator('.okf-rail__btn[data-rail-id="comments"]').focus()
        assertions = {"active_element": "comments utility rail button"}
    elif scenario.action == "mermaid":
        page.locator(".mermaid svg").first.wait_for(
            state="visible", timeout=READY_TIMEOUT_MS
        )
        page.locator(".mermaid").first.scroll_into_view_if_needed()
        assertions = page.evaluate("""() => {
          const svg = document.querySelector('.mermaid svg');
          const root = getComputedStyle(document.documentElement);
          const canvas = document.createElement('canvas');
          const context = canvas.getContext('2d');
          function token(name) { return root.getPropertyValue(name).trim(); }
          function hex(value) {
            context.fillStyle = '#000'; context.fillStyle = value;
            context.fillRect(0, 0, 1, 1);
            const data = context.getImageData(0, 0, 1, 1).data;
            return '#' + [data[0], data[1], data[2]]
              .map(v => v.toString(16).padStart(2, '0')).join('');
          }
          function luminance(color) {
            const values = [1, 3, 5].map(offset => parseInt(color.slice(offset, offset + 2), 16) / 255)
              .map(value => value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4));
            return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
          }
          function contrast(a, b) {
            const one = luminance(a), two = luminance(b);
            return Math.round(((Math.max(one, two) + 0.05) /
              (Math.min(one, two) + 0.05)) * 100) / 100;
          }
          const variables = {
            primaryColor: hex(token('--okf-bg-elev')),
            primaryTextColor: hex(token('--okf-fg')),
            primaryBorderColor: hex(token('--okf-fg-muted')),
            secondaryColor: hex(token('--okf-bg-inset')),
            secondaryTextColor: hex(token('--okf-fg')),
            secondaryBorderColor: hex(token('--okf-fg-muted')),
            tertiaryColor: hex(token('--okf-accent-bg')),
            tertiaryTextColor: hex(token('--okf-fg')),
            tertiaryBorderColor: hex(token('--okf-accent')),
            lineColor: hex(token('--okf-fg-muted')),
            actorBkg: hex(token('--okf-bg-elev')),
            actorBorder: hex(token('--okf-fg-muted')),
            actorTextColor: hex(token('--okf-fg')),
            actorLineColor: hex(token('--okf-fg-muted')),
            noteBkgColor: hex(token('--okf-bg-elev')),
            noteBorderColor: hex(token('--okf-fg-muted')),
            noteTextColor: hex(token('--okf-fg')),
            activationBkgColor: hex(token('--okf-bg-inset')),
            activationBorderColor: hex(token('--okf-fg-muted')),
            signalColor: hex(token('--okf-fg')),
            signalTextColor: hex(token('--okf-fg')),
            labelBoxBkgColor: hex(token('--okf-bg-elev')),
            labelBoxBorderColor: hex(token('--okf-border-strong')),
            labelTextColor: hex(token('--okf-fg')),
            loopTextColor: hex(token('--okf-fg')),
            background: hex(token('--okf-bg')),
            mainBkg: hex(token('--okf-bg-elev')),
            textColor: hex(token('--okf-fg')),
            fontFamily: token('--okf-font-body') || 'sans-serif',
            fontSize: '14px'
          };
          const contrastRatios = {
            line_on_background: contrast(variables.lineColor, variables.background),
            primary_border_on_primary: contrast(variables.primaryBorderColor, variables.primaryColor),
            secondary_border_on_secondary: contrast(variables.secondaryBorderColor, variables.secondaryColor),
            tertiary_border_on_tertiary: contrast(variables.tertiaryBorderColor, variables.tertiaryColor),
            primary_text_on_primary: contrast(variables.primaryTextColor, variables.primaryColor),
            secondary_text_on_secondary: contrast(variables.secondaryTextColor, variables.secondaryColor),
            tertiary_text_on_tertiary: contrast(variables.tertiaryTextColor, variables.tertiaryColor),
            text_on_background: contrast(variables.textColor, variables.background)
          };
          const essential = [contrastRatios.line_on_background,
            contrastRatios.primary_border_on_primary,
            contrastRatios.secondary_border_on_secondary,
            contrastRatios.tertiary_border_on_tertiary];
          const text = [contrastRatios.primary_text_on_primary,
            contrastRatios.secondary_text_on_secondary,
            contrastRatios.tertiary_text_on_tertiary,
            contrastRatios.text_on_background];
          return {svg_visible: !!svg,
            resolved_theme: document.documentElement.dataset.theme,
            mermaid_theme: 'base', themeVariables: variables,
            svg_font_size: getComputedStyle(svg).fontSize,
            contrast_ratios: contrastRatios,
            essential_line_border_min: Math.min(...essential),
            text_min: Math.min(...text),
            contrast_pass: Math.min(...essential) >= 3 && Math.min(...text) >= 4.5};
        }""")
        if not assertions["contrast_pass"]:
            raise RuntimeError(
                f"Mermaid contrast failed for {scenario.theme}: "
                f"{assertions['contrast_ratios']}"
            )
    elif scenario.action in {"focus-explore", "focus-node-index", "focus-header", "focus-bottom"}:
        selector = {
            "focus-explore": ".okf-graph-explore-map",
            "focus-node-index": ".okf-node-index__item",
            "focus-header": ".okf-brand-link",
            "focus-bottom": ".okf-studio-open-btn",
        }[scenario.action]
        if scenario.action == "focus-bottom":
            page.wait_for_function(
                "typeof window.okfLoomStudio === 'object'", timeout=READY_TIMEOUT_MS
            )
        page.locator(selector).first.focus()
        assertions = {"focus_selector": selector}

    readiness = wait_for_capture_ready(page, scenario.target, timeout_ms=READY_TIMEOUT_MS)
    focused = page.evaluate("""() => {
      const el = document.activeElement;
      if (!el) return null;
      const style = getComputedStyle(el);
      return {tag: el.tagName, id: el.id, class_name: String(el.className || ''),
        role: el.getAttribute('role'), label: el.getAttribute('aria-label'),
        text: (el.textContent || '').trim(), outline_style: style.outlineStyle,
        outline_width: style.outlineWidth,
        outline_width_px: parseFloat(style.outlineWidth) || 0,
        outline_color: style.outlineColor};
    }""")
    assertions["focused_element"] = focused
    if scenario.action in {"studio-focus-tab", "studio-focus-close"} and (
        not focused or focused["outline_width_px"] < 2
    ):
        raise RuntimeError(
            f"focused {scenario.action} outline is below 2px: {focused}"
        )
    return readiness, assertions


def _capture_scenario(browser, base: str, scenario: Scenario, out_dir: Path) -> tuple[Path, dict]:
    context = _context_for(browser, scenario)
    try:
        page = context.new_page()
        page.goto(f"{base}{scenario.route}", wait_until="load", timeout=READY_TIMEOUT_MS)
        readiness_target = "concept" if scenario.target == "studio" else scenario.target
        readiness = wait_for_capture_ready(page, readiness_target, timeout_ms=READY_TIMEOUT_MS)
        if not scenario.environment.get("no_js"):
            page.wait_for_function(
                "theme => window.OKFLoomTheme && "
                "window.OKFLoomTheme.getState().theme === theme",
                arg=scenario.theme,
                timeout=READY_TIMEOUT_MS,
            )
        assertions = {}
        if scenario.action:
            readiness, assertions = _apply_action(page, scenario)
        runtime_state = None
        if not scenario.environment.get("no_js"):
            runtime_state = page.evaluate("() => window.OKFLoomTheme.getState()")
        width = scenario.viewport["width"]
        filename = (
            f"{scenario.source}__{scenario.surface}__{scenario.theme}__"
            f"{width}px__{scenario.variant}.png"
        )
        path = out_dir / filename
        page.screenshot(path=str(path), full_page=False)
        record = {
            "file": filename,
            "source": scenario.source,
            "route": scenario.route,
            "theme": scenario.theme,
            "modifiers": scenario.modifiers,
            "viewport": scenario.viewport,
            "device_scale_factor": 1,
            "readiness": readiness,
            "environment": scenario.environment,
            "variants": {
                "surface": scenario.surface,
                "state": scenario.variant,
                "runtime_theme_state": runtime_state,
                "assertions": assertions,
            },
        }
        return path, record
    finally:
        context.close()


def run(bundle: Path, out_dir: Path, chrome_path: str | None = None) -> tuple[list[Path], Path]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in (*out_dir.glob("*.png"), *out_dir.glob("*.json")):
        stale.unlink()
    captures: list[Path] = []
    records: list[dict] = []
    scenarios = final_scenarios()
    with tempfile.TemporaryDirectory(prefix="okf-final-proof-") as tmp:
        tmp_path = Path(tmp)
        static_dir = tmp_path / "static"
        single_dir = tmp_path / "single-file"
        _build_static_site(bundle, static_dir)
        _build_single_file(bundle, single_dir)
        with sync_playwright() as playwright:
            launched = launch_chromium(playwright, chrome_path)
            browser = launched.browser
            try:
                grouped = {
                    source: [s for s in scenarios if s.source == source]
                    for source in ("live", "static", "single-file")
                }
                with _LiveServer(bundle) as base:
                    for scenario in grouped["live"]:
                        path, record = _capture_scenario(browser, base, scenario, out_dir)
                        captures.append(path)
                        records.append(record)
                with _StaticServer(static_dir) as base:
                    for scenario in grouped["static"]:
                        path, record = _capture_scenario(browser, base, scenario, out_dir)
                        captures.append(path)
                        records.append(record)
                with _StaticServer(single_dir) as base:
                    for scenario in grouped["single-file"]:
                        path, record = _capture_scenario(browser, base, scenario, out_dir)
                        captures.append(path)
                        records.append(record)
            finally:
                browser.close()
    manifest = write_capture_manifest(
        out_dir, records, repo_root=REPO_ROOT, browser_source=launched.source
    )
    return captures, manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    default_date = dt.datetime.now(dt.timezone.utc).date().isoformat()
    parser.add_argument(
        "--out-dir", type=Path,
        default=REPO_ROOT / "docs" / "screenshots" / f"{default_date}-editorial-workbench-final",
    )
    parser.add_argument("--chrome")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    bundle, out_dir = args.bundle.resolve(), args.out_dir.resolve()
    if not bundle.is_dir():
        print(f"ERROR: bundle directory not found: {bundle}", file=sys.stderr)
        return 1
    try:
        captures, manifest = run(bundle, out_dir, args.chrome)
    except (ImportError, RuntimeError, SystemExit) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"# wrote {len(captures)} final proof screenshots and manifest to {out_dir}")
    for path in [*captures, manifest]:
        print(f"  {display_path(path, REPO_ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
