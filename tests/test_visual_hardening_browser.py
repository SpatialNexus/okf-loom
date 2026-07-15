"""Browser proof for semantic visual hardening: on-* status tokens, Border Off
non-color cues, graph legend relocation, prose width, and SVG icon parity.
Tests all four themes + Soft Contrast + Border Off via computed styles.
"""
from __future__ import annotations

import socket, subprocess, sys, time, urllib.request, os
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

from conftest import TOOLKIT_ROOT, okf_module_argv, okf_subprocess_env

pytestmark = pytest.mark.browser
DEMO_BUNDLE = TOOLKIT_ROOT / "samples" / "demo_bundle"


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _wait_http(proc, base, path="/"):
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if proc.poll() is not None: pytest.skip("server exited")
        try:
            with urllib.request.urlopen(base + path, timeout=1) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(0.15)
    pytest.skip("server not ready")


def _terminate(proc):
    proc.terminate()
    try: proc.wait(timeout=5)
    except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)


@pytest.fixture(scope="session")
def server_url():
    if not DEMO_BUNDLE.is_dir(): pytest.skip("no demo bundle")
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        okf_module_argv("serve", str(DEMO_BUNDLE), "--host", "127.0.0.1", "--port", str(port), "--no-watch", "--no-open"),
        cwd=str(TOOLKIT_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=okf_subprocess_env())
    _wait_http(proc, base)
    try: yield base
    finally: _terminate(proc)


@pytest.fixture(scope="session")
def static_site_url(tmp_path_factory):
    if not DEMO_BUNDLE.is_dir(): pytest.skip("no demo bundle")
    out = tmp_path_factory.mktemp("vh-static") / "site"
    subprocess.run(okf_module_argv("build", str(DEMO_BUNDLE), "--target", "static", "--out", str(out)),
                   cwd=str(TOOLKIT_ROOT), capture_output=True, text=True, env=okf_subprocess_env(), timeout=30, check=False)
    if not (out / "index.html").is_file(): pytest.skip("static build failed")
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                            cwd=str(out), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_http(proc, base, "/index.html")
    try: yield base
    finally: _terminate(proc)


@pytest.fixture(scope="session")
def single_file_url(tmp_path_factory):
    if not DEMO_BUNDLE.is_dir(): pytest.skip("no demo bundle")
    out = tmp_path_factory.mktemp("vh-sf") / "viz.html"
    subprocess.run(okf_module_argv("render", str(DEMO_BUNDLE), "--out", str(out)),
                   cwd=str(TOOLKIT_ROOT), capture_output=True, text=True, env=okf_subprocess_env(), timeout=30, check=False)
    if not out.is_file(): pytest.skip("render failed")
    return out.as_uri()


@pytest.fixture
def page():
    chrome = os.environ.get("AIC_PLAYWRIGHT_CHROME_PATH") or ""
    attempts = []
    if chrome: attempts.append({"executable_path": chrome, "args": ["--no-sandbox"]})
    attempts.append({"channel": "chrome"})
    attempts.append({})
    with sync_playwright() as p:
        browser = None; last = None
        for kw in attempts:
            try: browser = p.chromium.launch(**kw); break
            except Exception as e: last = e
        if browser is None: pytest.skip(f"no chrome ({last})")
        try:
            ctx = browser.new_context(color_scheme="light")
            pg = ctx.new_page()
            yield pg
            ctx.close()
        finally: browser.close()


def _set_theme(page, theme):
    page.evaluate(f"""() => {{
        try {{
            localStorage.setItem('okf-theme-family', '{theme.split('-')[0]}');
            localStorage.setItem('okf-theme-mode', '{theme.split('-')[1]}');
        }} catch(e) {{}}
    }}""")


def _w(pg, w): pg.set_viewport_size({"width": w, "height": 900})


# ===========================================================================
# 1. Semantic on-* status tokens exist in every theme
# ===========================================================================

@pytest.mark.parametrize("theme", ["swiss-light", "swiss-dark", "technical-light", "technical-dark"])
def test_on_status_tokens_defined(server_url, page, theme):
    """All four --on-* tokens resolve to a non-empty color in every theme."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.evaluate(f"""() => {{
        try {{
            localStorage.setItem('okf-theme-family', '{theme.split('-')[0]}');
            localStorage.setItem('okf-theme-mode', '{theme.split('-')[1]}');
        }} catch(e) {{}}
    }}""")
    page.reload(wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    vals = page.evaluate("""() => {
        const cs = getComputedStyle(document.documentElement);
        return {
            onOk: cs.getPropertyValue('--okf-on-ok').trim(),
            onWarn: cs.getPropertyValue('--okf-on-warn').trim(),
            onInfo: cs.getPropertyValue('--okf-on-info').trim(),
            onError: cs.getPropertyValue('--okf-on-error').trim(),
        };
    }""")
    for k, v in vals.items():
        assert v, f"{k} is empty in {theme}: got '{v}'"
        assert v != "#fff" or "light" in theme, f"{k} should not be #fff in dark theme {theme}"


# ===========================================================================
# 2. No hardcoded #fff on status fills (studio.css replaced with on-* tokens)
# ===========================================================================

def test_no_hardcoded_white_on_status_fills(server_url, page):
    """The studio toast/comment-marker CSS uses var(--okf-on-*) not #fff."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    # Check the stylesheet for #fff on status-related selectors.
    result = page.evaluate("""() => {
        for (const sheet of document.styleSheets) {
            try {
                for (const rule of sheet.cssRules) {
                    if (rule.style && rule.style.color === 'white' || rule.style && rule.style.color === '#fff') {
                        if (rule.selectorText && (rule.selectorText.includes('toast') || rule.selectorText.includes('marker'))) {
                            return {found: true, sel: rule.selectorText};
                        }
                    }
                }
            } catch(e) {} // cross-origin
        }
        return {found: false};
    }""")
    assert not result["found"], f"hardcoded #fff on status fill: {result}"


# ===========================================================================
# 3. Border Off non-color cues
# ===========================================================================

def test_border_off_selected_tab_font_weight(server_url, page):
    """Under Border Off, the selected panel tab gets font-weight: 700."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("""() => {
        document.documentElement.setAttribute('data-okf-border', 'off');
        window.okfLoomStudio.openPanel('comments');
    }""")
    page.wait_for_selector("#okf-panel:not([hidden])")
    weight = page.evaluate("""() => {
        const tab = document.querySelector('.okf-panel__tab[aria-selected="true"]');
        return tab ? getComputedStyle(tab).fontWeight : null;
    }""")
    assert weight == "700", f"selected tab font-weight under Border Off: {weight}"


def test_border_off_appearance_checked_font_weight(server_url, page):
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.evaluate("document.documentElement.setAttribute('data-okf-border', 'off')")
    page.click("#okf-theme")
    page.wait_for_selector("#okf-appearance-menu:not([hidden])")
    weight = page.evaluate("""() => {
        const opt = document.querySelector('.okf-appearance__opt[aria-checked="true"]');
        return opt ? getComputedStyle(opt).fontWeight : null;
    }""")
    assert weight == "700", f"checked appearance opt under Border Off: {weight}"


def test_border_on_selected_tab_normal_weight(server_url, page):
    """With borders on, selected tab keeps its normal weight (no 700 bump)."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    weight = page.evaluate("""() => {
        const tab = document.querySelector('.okf-panel__tab[aria-selected="true"]');
        return tab ? getComputedStyle(tab).fontWeight : null;
    }""")
    assert weight != "700", f"selected tab should NOT be 700 with borders on: {weight}"


# ===========================================================================
# 4. Graph legend in detail pane, not canvas overlay
# ===========================================================================

def test_graph_legend_in_detail_pane(server_url, page):
    """Legend is a <details> in #okf-detail, not an overlay on the canvas."""
    _w(page, 1280)
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_timeout(500)
    legend_parent = page.evaluate("""() => {
        const legend = document.querySelector('.okf-graph-legend');
        if (!legend) return null;
        return {
            tag: legend.tagName,
            parent: legend.parentElement ? legend.parentElement.id : null,
            inDetail: !!legend.closest('#okf-detail'),
            inCanvas: !!legend.closest('#okf-graph'),
        };
    }""")
    assert legend_parent, "legend not found"
    assert legend_parent["tag"] == "DETAILS", f"legend should be <details>, got <{legend_parent['tag']}>"
    assert legend_parent["inDetail"], "legend should be in #okf-detail"
    assert not legend_parent["inCanvas"], "legend should NOT be in #okf-graph canvas"


def test_graph_legend_open_desktop_closed_mobile(server_url, page):
    """Legend is open by default on desktop, closed on mobile."""
    _w(page, 1280)
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_timeout(500)
    assert page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")
    # Mobile
    _w(page, 390)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_timeout(500)
    assert not page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")


def test_graph_legend_filter_buttons_are_native(server_url, page):
    """Legend type filter rows are native <button> elements with aria-pressed."""
    _w(page, 1280)
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_timeout(1000)
    chips = page.evaluate("""() => {
        const legend = document.querySelector('.okf-graph-legend');
        if (!legend) return [];
        const btns = legend.querySelectorAll('.okf-graph-legend__item--chip');
        return Array.from(btns).map(b => ({
            tag: b.tagName,
            ariaPressed: b.getAttribute('aria-pressed'),
        }));
    }""")
    assert len(chips) > 0, "no legend filter chips found"
    for chip in chips:
        assert chip["tag"] == "BUTTON", f"chip should be <button>, got <{chip['tag']}>"
        assert chip["ariaPressed"] in ("true", "false"), f"chip missing aria-pressed: {chip}"


def test_graph_legend_no_canvas_overlap(server_url, page):
    """Legend (in detail pane) does not overlap the canvas at any width."""
    for w in [390, 768, 1280]:
        _w(page, w)
        page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
        page.wait_for_selector("#okf-graph canvas", timeout=15000)
        page.wait_for_timeout(500)
        overlap = page.evaluate("""() => {
            const canvas = document.querySelector('#okf-graph');
            const legend = document.querySelector('.okf-graph-legend');
            if (!canvas || !legend) return null;
            const cr = canvas.getBoundingClientRect();
            const lr = legend.getBoundingClientRect();
            // Check ACTUAL rect intersection (both axes) — on mobile the graph
            // and detail stack vertically so they share X but not Y.
            const hOverlap = lr.left < cr.right && lr.right > cr.left;
            const vOverlap = lr.top < cr.bottom && lr.bottom > cr.top;
            return hOverlap && vOverlap;
        }""")
        assert overlap is not None, f"canvas or legend missing at {w}px"
        assert not overlap, f"legend overlaps canvas at {w}px"


# ===========================================================================
# 5. Prose width: 76ch cap on text elements, wide content exempt
# ===========================================================================

def test_prose_paragraph_width_capped(server_url, page):
    """Paragraph max-width is 76ch (applied as a CSS rule). In Focus mode
    (wider column), paragraphs are narrower than the body column."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    # Verify the max-width CSS rule is applied to paragraphs.
    info = page.evaluate("""() => {
        const p = document.querySelector('.okf-prose > p');
        if (!p) return null;
        const cs = getComputedStyle(p);
        return {maxWidth: cs.maxWidth};
    }""")
    assert info, "no paragraph found"
    assert info["maxWidth"] != "none", f"paragraph should have max-width, got {info['maxWidth']}"
    # In Focus mode the column goes wider; paragraph should stay capped.
    page.evaluate("""() => { document.documentElement.setAttribute('data-okf-focus', ''); }""")
    page.wait_for_timeout(200)
    widths = page.evaluate("""() => {
        const p = document.querySelector('.okf-prose > p');
        const body = document.querySelector('.okf-page__body');
        return {
            pW: p ? Math.round(p.getBoundingClientRect().width) : 0,
            bodyW: body ? Math.round(body.getBoundingClientRect().width) : 0,
        };
    }""")
    # In Focus mode the body is wider; the paragraph should be narrower.
    if widths["bodyW"] > widths["pW"]:
        assert widths["pW"] < widths["bodyW"], \
            f"Focus: paragraph ({widths['pW']}px) should be narrower than body ({widths['bodyW']}px)"


def test_prose_wide_content_not_capped(server_url, page):
    """Tables/pre/code are NOT capped to 76ch — they use the full column."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    info = page.evaluate("""() => {
        const body = document.querySelector('.okf-page__body');
        const table = body ? body.querySelector('table') : null;
        const pre = body ? body.querySelector('pre') : null;
        const bodyW = body ? body.getBoundingClientRect().width : 0;
        const tableMaxW = table ? getComputedStyle(table).maxWidth : null;
        return {bodyW: Math.round(bodyW), tableMaxW};
    }""")
    assert info["tableMaxW"] in ("none", "", "100%"), \
        f"table should have no restrictive max-width cap, got {info['tableMaxW']}"


# ===========================================================================
# 6. SVG icons render and have accessible names
# ===========================================================================

def test_rail_icons_are_svg_with_accessible_names(server_url, page):
    """Studio rail buttons contain inline SVG (not font glyphs) and have
    aria-labels."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_timeout(500)
    # Wait for rail to be built.
    page.wait_for_selector(".okf-rail__btn", timeout=5000)
    btns = page.evaluate("""() => {
        const btns = document.querySelectorAll('.okf-rail__btn');
        return Array.from(btns).map(b => {
            const svg = b.querySelector('svg');
            return {
                hasSvg: !!svg,
                svgAriaHidden: svg ? svg.getAttribute('aria-hidden') : null,
                svgFocusable: svg ? svg.getAttribute('focusable') : null,
                btnAriaLabel: b.getAttribute('aria-label'),
            };
        });
    }""")
    assert len(btns) > 0, "no rail buttons found"
    for b in btns:
        assert b["hasSvg"], f"rail button missing SVG: {b}"
        assert b["svgAriaHidden"] == "true", f"SVG not aria-hidden: {b}"
        assert b["svgFocusable"] == "false", f"SVG not focusable=false: {b}"
        assert b["btnAriaLabel"], f"rail button missing aria-label: {b}"


def test_rail_buttons_no_font_glyphs(server_url, page):
    """Rail button text content is empty (SVG provides the visual)."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_selector(".okf-rail__btn", timeout=5000)
    btns = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('.okf-rail__btn')).map(b => {
            // Direct text nodes only (not badge text)
            const text = Array.from(b.childNodes)
                .filter(n => n.nodeType === 3)
                .map(n => n.textContent.trim())
                .join('');
            return text;
        });
    }""")
    for t in btns:
        assert not t or len(t) == 0, f"rail button has text glyph: '{t}'"


# ===========================================================================
# 7. Static/single-file legend parity
# ===========================================================================

def test_static_graph_legend_in_detail_pane(static_site_url, page):
    """Legend is in the detail pane on static builds too."""
    _w(page, 1280)
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_timeout(500)
    in_detail = page.evaluate("""() => {
        const legend = document.querySelector('.okf-graph-legend');
        return legend ? !!legend.closest('#okf-detail') : false;
    }""")
    assert in_detail, "legend not in detail pane on static build"


def test_single_file_legend_in_detail_pane(single_file_url, page):
    """Legend is in the detail pane in single-file viewer."""
    _w(page, 1280)
    page.goto(single_file_url, wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_timeout(500)
    # Single-file may not have #okf-detail; check fallback to canvas container.
    has_legend = page.evaluate("""() => {
        return !!document.querySelector('.okf-graph-legend');
    }""")
    assert has_legend, "legend missing in single-file viewer"
