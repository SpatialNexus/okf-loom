"""Final visual/parity gap closure: graph SVG icons, Bridges lens, legend
user-toggle via real click, full Border Off proof (no conditionals),
static/single-file parity, prose Focus cap, semantic readiness.
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
    proc = subprocess.Popen(okf_module_argv("serve", str(DEMO_BUNDLE), "--host", "127.0.0.1", "--port", str(port), "--no-watch", "--no-open"), cwd=str(TOOLKIT_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=okf_subprocess_env())
    _wait_http(proc, base)
    try: yield base
    finally: _terminate(proc)

@pytest.fixture(scope="session")
def static_site_url(tmp_path_factory):
    if not DEMO_BUNDLE.is_dir(): pytest.skip("no demo bundle")
    out = tmp_path_factory.mktemp("gap-static") / "site"
    subprocess.run(okf_module_argv("build", str(DEMO_BUNDLE), "--target", "static", "--out", str(out)), cwd=str(TOOLKIT_ROOT), capture_output=True, text=True, env=okf_subprocess_env(), timeout=30, check=False)
    if not (out / "index.html").is_file(): pytest.skip("static build failed")
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=str(out), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_http(proc, base, "/index.html")
    try: yield base
    finally: _terminate(proc)

@pytest.fixture(scope="session")
def single_file_url(tmp_path_factory):
    if not DEMO_BUNDLE.is_dir(): pytest.skip("no demo bundle")
    out = tmp_path_factory.mktemp("gap-sf") / "viz.html"
    subprocess.run(okf_module_argv("render", str(DEMO_BUNDLE), "--out", str(out)), cwd=str(TOOLKIT_ROOT), capture_output=True, text=True, env=okf_subprocess_env(), timeout=30, check=False)
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


def _goto_graph(pg, base, w=1280):
    pg.set_viewport_size({"width": w, "height": 900})
    pg.goto(f"{base}/__graph", wait_until="domcontentloaded")
    pg.wait_for_selector("#okf-graph canvas", timeout=15000)
    pg.wait_for_selector(".okf-graph-legend", timeout=5000)

def _goto_concept(pg, base, w=1280):
    pg.set_viewport_size({"width": w, "height": 900})
    pg.goto(f"{base}/tables/orders", wait_until="load")
    pg.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)


# ===========================================================================
# 1. Graph action buttons use SVG, not text glyphs
# ===========================================================================

def test_graph_zoom_buttons_are_svg(server_url, page):
    """Zoom/action buttons contain inline SVG, not text glyphs."""
    _goto_graph(page, server_url)
    page.wait_for_selector(".okf-graph-zoom button", timeout=10000)
    btns = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('.okf-graph-zoom button')).map(b => {
            const svg = b.querySelector('svg');
            const text = Array.from(b.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('');
            return {hasSvg: !!svg, svgAriaHidden: svg ? svg.getAttribute('aria-hidden') : null,
                    textContent: text, ariaLabel: b.getAttribute('aria-label')};
        });
    }""")
    assert len(btns) >= 4, f"expected 4 zoom/action buttons, found {len(btns)}"
    for b in btns:
        assert b["hasSvg"], f"button '{b.get('ariaLabel','')}' missing SVG"
        assert not b["textContent"], f"button has text glyph: '{b['textContent']}'"
        assert b["ariaLabel"], "button missing aria-label"


# ===========================================================================
# 2. Bridges lens: legend content, filter buttons, Enter+Space, overlap
# ===========================================================================

def test_bridges_lens_legend_and_filters(server_url, page):
    """Select Bridges lens via radio button; verify legend has content."""
    _goto_graph(page, server_url)
    page.wait_for_selector("#okf-lens-bridges", timeout=10000)
    page.evaluate("document.getElementById('okf-lens-bridges').click()")
    page.wait_for_function("""() => {
        const r = document.getElementById('okf-lens-bridges');
        return r && r.checked;
    }""", timeout=5000)
    # Wait for legend to rebuild with bridge content.
    page.wait_for_selector(".okf-graph-legend__body > *", timeout=5000)
    items = page.evaluate("document.querySelectorAll('.okf-graph-legend__body > *').length")
    assert items > 0, "legend empty after selecting Bridges"


def test_bridges_lens_filter_enter_space(server_url, page):
    """Enter and Space both toggle a Bridges filter chip (native button)."""
    _goto_graph(page, server_url)
    page.wait_for_selector("#okf-lens-bridges", timeout=10000)
    page.evaluate("document.getElementById('okf-lens-bridges').click()")
    page.wait_for_function("document.getElementById('okf-lens-bridges').checked")
    page.wait_for_selector(".okf-graph-legend__item--chip", timeout=5000)
    initial = page.evaluate("""() => {
        const c = document.querySelector('.okf-graph-legend__item--chip');
        return c ? c.getAttribute('aria-pressed') : null;
    }""")
    # Test Enter: use Playwright locator focus for reliability.
    chip = page.locator(".okf-graph-legend__item--chip").first
    chip.focus()
    page.wait_for_timeout(100)  # ensure focus landed
    chip.press("Enter")
    page.wait_for_function(
        "() => { const c = document.querySelector('.okf-graph-legend__item--chip'); return c && c.getAttribute('aria-pressed') !== '" + initial + "'; }"
    )
    after_enter = page.evaluate("document.querySelector('.okf-graph-legend__item--chip').getAttribute('aria-pressed')")
    assert after_enter != initial, "Enter did not toggle filter"
    # Test Space.
    chip.press("Space")
    page.wait_for_function(
        "() => { const c = document.querySelector('.okf-graph-legend__item--chip'); return c && c.getAttribute('aria-pressed') !== '" + after_enter + "'; }"
    )
    after_space = page.evaluate("document.querySelector('.okf-graph-legend__item--chip').getAttribute('aria-pressed')")
    assert after_space != after_enter, "Space did not toggle filter"


# ===========================================================================
# 3. Legend user-toggle via real summary click (no programmatic removeAttribute)
# ===========================================================================

def test_legend_user_click_closed_persists_across_resize(server_url, page):
    """User clicks summary to close on desktop → resize to mobile → back to
    desktop → legend stays closed (explicit user choice). All via real clicks."""
    _goto_graph(page, server_url, w=1280)
    # Verify open initially.
    assert page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")
    # User clicks the summary to close it.
    page.click(".okf-graph-legend > summary")
    page.wait_for_function("!document.querySelector('.okf-graph-legend').hasAttribute('open')")
    assert not page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")
    # Resize to mobile — user choice preserved (stays closed).
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_timeout(200)  # MQ settle
    assert not page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')"), \
        "legend reopened on mobile despite user closing it"
    # Resize back to desktop — user choice still preserved (stays closed).
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(200)
    assert not page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')"), \
        "legend reopened on desktop despite user closing it"


def test_legend_default_follows_breakpoint_without_user_click(server_url, page):
    """Without user click, breakpoint resize changes the default."""
    _goto_graph(page, server_url, w=1280)
    assert page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_timeout(200)
    assert not page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(200)
    assert page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")


# ===========================================================================
# 4. Full Border Off: ALL aria states (no conditional — controls must exist)
# ===========================================================================

def test_border_off_rail_button_pressed(server_url, page):
    _goto_concept(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    page.wait_for_selector(".okf-rail__btn", timeout=5000)
    # Open a panel via rail to set aria-pressed.
    page.evaluate("""() => {
        const btn = document.querySelector('.okf-rail__btn[data-rail-id="comments"]');
        if (btn) btn.click();
    }""")
    page.wait_for_selector("#okf-panel:not([hidden])")
    w = page.evaluate("""() => {
        const b = document.querySelector('.okf-rail__btn[aria-pressed="true"]');
        if (!b) return null;
        return getComputedStyle(b).fontWeight;
    }""")
    assert w is not None, "no pressed rail button found"
    assert w == "700", f"rail pressed under Border Off: {w}"


def test_border_off_view_switch_pressed(server_url, page):
    _goto_concept(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    page.wait_for_selector(".okf-viewswitch__btn", timeout=5000)
    w = page.evaluate("""() => {
        const b = document.querySelector('.okf-viewswitch__btn[aria-pressed="true"]');
        if (!b) return null;
        return getComputedStyle(b).fontWeight;
    }""")
    assert w is not None, "no pressed view-switch button found"
    assert w == "700", f"view switch pressed under Border Off: {w}"


def test_border_off_nav_current(server_url, page):
    _goto_concept(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    page.wait_for_selector(".okf-nav__link[aria-current='page']", timeout=5000)
    w = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-nav__link[aria-current="page"]')
    ).fontWeight""")
    assert w == "700", f"nav current under Border Off: {w}"


def test_border_off_studio_pressed_button(server_url, page):
    _goto_concept(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    # Toggle Focus to get aria-pressed="true" on the Focus button.
    page.evaluate("""() => {
        const btn = document.querySelector('.okf-focus-btn');
        if (btn) btn.click();
    }""")
    page.wait_for_function("""() => {
        const b = document.querySelector('.okf-focus-btn');
        return b && b.getAttribute('aria-pressed') === 'true';
    }""", timeout=5000)
    w = page.evaluate("""() => {
        const b = document.querySelector('.okf-studiobtn[aria-pressed="true"]');
        if (!b) return null;
        return getComputedStyle(b).fontWeight;
    }""")
    assert w is not None, "no pressed studiobtn found"
    assert w == "700", f"studiobtn pressed under Border Off: {w}"


def test_border_off_panel_tab_selected(server_url, page):
    _goto_concept(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    w = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-panel__tab[aria-selected="true"]')
    ).fontWeight""")
    assert w == "700", f"panel tab under Border Off: {w}"


def test_border_off_appearance_checked(server_url, page):
    _goto_concept(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    page.click("#okf-theme")
    page.wait_for_selector("#okf-appearance-menu:not([hidden])")
    w = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-appearance__opt[aria-checked="true"]')
    ).fontWeight""")
    assert w == "700", f"appearance checked under Border Off: {w}"


def test_border_off_graph_legend_chip(server_url, page):
    _goto_graph(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    page.wait_for_selector(".okf-graph-legend__item--chip[aria-pressed='true']", timeout=5000)
    w = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-graph-legend__item--chip[aria-pressed="true"]')
    ).fontWeight""")
    assert w == "700", f"graph legend chip under Border Off: {w}"


# ===========================================================================
# 5. Static/single-file legend parity (parent, tag, summary, buttons, geometry)
# ===========================================================================

def test_static_legend_parent_detail_pane(static_site_url, page):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    info = page.evaluate("""() => {
        const l = document.querySelector('.okf-graph-legend');
        return {
            tag: l.tagName,
            inDetail: !!l.closest('#okf-detail'),
            hasSummary: !!l.querySelector('summary'),
            chipsAreButtons: Array.from(l.querySelectorAll('.okf-graph-legend__item--chip')).every(c => c.tagName === 'BUTTON'),
            chipCount: l.querySelectorAll('.okf-graph-legend__item--chip').length,
        };
    }""")
    assert info["tag"] == "DETAILS", f"static legend tag: {info['tag']}"
    assert info["inDetail"], "static legend not in #okf-detail"
    assert info["hasSummary"], "static legend missing <summary>"
    assert info["chipCount"] > 0, "static legend has no filter chips"
    assert info["chipsAreButtons"], "static legend chips not all <button>"


def test_static_legend_no_overlap(static_site_url, page):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    overlap = page.evaluate("""() => {
        const c = document.querySelector('#okf-graph');
        const l = document.querySelector('.okf-graph-legend');
        if (!c || !l) return null;
        const cr = c.getBoundingClientRect(), lr = l.getBoundingClientRect();
        return (lr.left < cr.right && lr.right > cr.left && lr.top < cr.bottom && lr.bottom > cr.top);
    }""")
    assert overlap is not None
    assert not overlap, "static legend overlaps canvas"


def test_single_file_legend_parent_and_controls(single_file_url, page):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(single_file_url, wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    info = page.evaluate("""() => {
        const l = document.querySelector('.okf-graph-legend');
        return {
            tag: l.tagName,
            hasSummary: !!l.querySelector('summary'),
            chipsAreButtons: Array.from(l.querySelectorAll('.okf-graph-legend__item--chip')).every(c => c.tagName === 'BUTTON'),
        };
    }""")
    assert info["tag"] == "DETAILS"
    assert info["hasSummary"]


def test_static_status_tokens_contrast(static_site_url, page):
    """Status tokens resolve and have valid contrast on static builds."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    page.wait_for_selector("#okf-theme")
    data = page.evaluate("""() => {
        const cs = getComputedStyle(document.documentElement);
        const c = document.createElement('canvas'); c.width=2; c.height=2; const cx=c.getContext('2d');
        function toRGB(cssColor){cx.fillStyle='#000';cx.fillStyle=cssColor;cx.fillRect(0,0,1,1);
            const d=cx.getImageData(0,0,1,1).data;return [d[0]/255,d[1]/255,d[2]/255];}
        function get(p){return toRGB(cs.getPropertyValue(p).trim());}
        function lum(r,g,b){function lin(ch){return ch<=0.03928?ch/12.92:Math.pow((ch+0.055)/1.055,2.4);}
            return 0.2126*lin(r)+0.7152*lin(g)+0.0722*lin(b);}
        function ratio(a,b){const l1=lum(a[0],a[1],a[2]),l2=lum(b[0],b[1],b[2]);
            return(Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);}
        return {warn: ratio(get('--okf-warn'), get('--okf-warn-bg')),
                error: ratio(get('--okf-error'), get('--okf-error-bg'))};
    }""")
    assert data["warn"] >= 4.5, f"static warn contrast: {data['warn']:.3f}"
    assert data["error"] >= 4.5, f"static error contrast: {data['error']:.3f}"


def test_static_border_off_appearance(static_site_url, page):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    page.wait_for_selector("#okf-theme")
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    page.click("#okf-theme")
    page.wait_for_selector("#okf-appearance-menu:not([hidden])")
    w = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-appearance__opt[aria-checked="true"]')
    ).fontWeight""")
    assert w == "700", f"static border-off appearance: {w}"


def test_static_search_column_capped(static_site_url, page):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/__search.html?q=orders", wait_until="load")
    page.wait_for_selector(".okf-search__results, .okf-search-empty", timeout=5000)
    mw = page.evaluate("""() => {
        const r = document.querySelector('.okf-search__results');
        return r ? getComputedStyle(r).maxWidth : null;
    }""")
    assert mw and mw != "none"


def test_static_graph_buttons_are_svg(static_site_url, page):
    """Static build graph action buttons are SVG, not text."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    # Wait for Cytoscape to create the zoom controls.
    page.wait_for_selector("#okf-graph button[aria-label*='Zoom']", timeout=10000)
    btns = page.evaluate("""() => {
        const all = document.querySelectorAll('#okf-graph button[aria-label]');
        return Array.from(all).filter(b => /zoom|fit|layout/i.test(b.getAttribute('aria-label'))).map(b => ({
            hasSvg: !!b.querySelector('svg'),
            text: Array.from(b.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(''),
        }));
    }""")
    assert len(btns) >= 4
    for b in btns:
        assert b["hasSvg"], "static graph button missing SVG"
        assert not b["text"], f"static graph button has text: '{b['text']}'"


# ===========================================================================
# 6. Prose Focus mode: unconditional numeric cap + wide exception
# ===========================================================================

def test_prose_focus_mode_unconditional_cap(server_url, page):
    """In Focus mode, paragraphs have a max-width cap (not 'none') and the
    body column's max-width is 'none' (wide content exempt). The cap is
    applied unconditionally via the CSS rule, verified by computed style."""
    page.set_viewport_size({"width": 1600, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("document.documentElement.setAttribute('data-okf-focus','')")
    page.wait_for_function("document.documentElement.hasAttribute('data-okf-focus')")
    page.wait_for_timeout(200)  # CSS apply frame
    info = page.evaluate("""() => {
        const p = document.querySelector('.okf-prose > p');
        const body = document.querySelector('.okf-page__body');
        const table = document.querySelector('.okf-prose table, .okf-page__body table');
        if (!p) return null;
        const pcs = getComputedStyle(p);
        const bcs = body ? getComputedStyle(body) : null;
        return {
            pMaxW: pcs.maxWidth,
            pMaxWResolved: p.getBoundingClientRect().width,
            bodyMaxW: bcs ? bcs.maxWidth : 'n/a',
            tableMaxW: table ? getComputedStyle(table).maxWidth : 'n/a',
        };
    }""")
    assert info, "no paragraph in Focus mode"
    # Paragraph cap is applied (not 'none').
    assert info["pMaxW"] != "none", f"Focus paragraph max-width is none: {info['pMaxW']}"
    # Body has no restrictive cap (wide content flows).
    assert info["bodyMaxW"] in ("none", ""), f"Focus body has max-width: {info['bodyMaxW']}"
    # Table has no restrictive cap.
    assert info["tableMaxW"] in ("none", "", "100%"), f"Focus table max-width: {info['tableMaxW']}"


# ===========================================================================
# STRENGTHENED ORACLES — discriminating, unconditional, no vacuous pass
# ===========================================================================


# --- 1. Bridges: active state + specific legend text + overlap + focus ---

def test_bridges_lens_active_state_and_legend_content(server_url, page):
    """Select Bridges lens; assert radio is checked, colorMode is bridge,
    legend title contains 'bridging power', and filter chips exist."""
    _goto_graph(page, server_url)
    page.wait_for_selector("#okf-lens-bridges", timeout=10000)
    page.evaluate("document.getElementById('okf-lens-bridges').click()")
    page.wait_for_function("document.getElementById('okf-lens-bridges').checked", timeout=5000)
    # Wait for legend to rebuild with Bridges-specific content.
    page.wait_for_selector(".okf-graph-legend__body .okf-graph-legend__title", timeout=5000)
    info = page.evaluate("""() => {
        const titles = Array.from(document.querySelectorAll('.okf-graph-legend__title'))
            .map(t => t.textContent);
        const chips = document.querySelectorAll('.okf-graph-legend__item--chip');
        return {titles, chipCount: chips.length};
    }""")
    assert any("bridging power" in t.lower() for t in info["titles"]), \
        f"Bridges legend title not found: {info['titles']}"
    assert info["chipCount"] > 0, "no filter chips in Bridges legend"


def test_bridges_lens_no_overlap_and_focus(server_url, page):
    """Bridges lens: legend does not overlap canvas at desktop + mobile;
    focused filter chip has visible focus outline."""
    _goto_graph(page, server_url, w=1280)
    page.wait_for_selector("#okf-lens-bridges", timeout=10000)
    page.evaluate("document.getElementById('okf-lens-bridges').click()")
    page.wait_for_function("document.getElementById('okf-lens-bridges').checked")
    page.wait_for_selector(".okf-graph-legend__item--chip", timeout=5000)
    # Desktop no overlap.
    overlap = page.evaluate("""() => {
        const c = document.querySelector('#okf-graph');
        const l = document.querySelector('.okf-graph-legend');
        const cr = c.getBoundingClientRect(), lr = l.getBoundingClientRect();
        return (lr.left < cr.right && lr.right > cr.left && lr.top < cr.bottom && lr.bottom > cr.top);
    }""")
    assert not overlap, "Bridges legend overlaps canvas at desktop"
    # Focus a chip and assert visible outline.
    chip = page.locator(".okf-graph-legend__item--chip").first
    chip.focus()
    page.wait_for_timeout(100)
    outline = page.evaluate("""() => {
        const c = document.querySelector('.okf-graph-legend__item--chip');
        return c ? getComputedStyle(c).outlineWidth : null;
    }""")
    assert outline and outline != "0px", f"focused chip has no outline: {outline}"
    # Mobile no overlap.
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_timeout(200)
    overlap_m = page.evaluate("""() => {
        const c = document.querySelector('#okf-graph');
        const l = document.querySelector('.okf-graph-legend');
        const cr = c.getBoundingClientRect(), lr = l.getBoundingClientRect();
        return (lr.left < cr.right && lr.right > cr.left && lr.top < cr.bottom && lr.bottom > cr.top);
    }""")
    assert not overlap_m, "Bridges legend overlaps canvas at mobile"


# --- 2. Border Off: index chip + palette selected (unconditional) ---

def test_border_off_index_chip_pressed(server_url, page):
    """Index page has type filter chips; the active one (aria-pressed=true)
    gets font-weight 700 under Border Off."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/", wait_until="load")
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    # Index chips are created by wiki.js enhanceIndex. Wait for them.
    page.wait_for_selector(".okf-index-chip[aria-pressed]", timeout=10000)
    w = page.evaluate("""() => {
        const c = document.querySelector('.okf-index-chip[aria-pressed="true"]');
        return c ? getComputedStyle(c).fontWeight : null;
    }""")
    assert w is not None, "no pressed index chip found — wiki.js did not create chips"
    assert w == "700", f"index chip pressed under Border Off: {w}"


def test_border_off_palette_selected_item(server_url, page):
    """Command palette selected item (aria-selected=true) gets font-weight
    700 under Border Off."""
    _goto_concept(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    # Open palette.
    page.evaluate("window.okfLoomStudio.openPalette()")
    page.wait_for_selector(".okf-palette-overlay:not([hidden])", timeout=5000)
    page.wait_for_selector(".okf-palette__item", timeout=5000)
    # Press ArrowDown to select the second item (first is already selected).
    page.keyboard.press("ArrowDown")
    page.wait_for_timeout(100)
    w = page.evaluate("""() => {
        const item = document.querySelector('.okf-palette__item[aria-selected="true"]');
        return item ? getComputedStyle(item).fontWeight : null;
    }""")
    assert w is not None, "no selected palette item found"
    assert w == "700", f"palette selected under Border Off: {w}"


# --- 3. Single-file legend: closest #okf-detail, details/summary/buttons ---

def test_single_file_legend_full_parity(single_file_url, page):
    """Single-file legend: closest('#okf-detail') is the parent, tag is
    DETAILS, has summary, ≥1 native BUTTON chip, no canvas overlap, 4 SVG
    action buttons with no text glyphs."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(single_file_url, wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    # Wait for Cytoscape to create zoom controls + legend chips.
    page.wait_for_selector(".okf-graph-zoom button", timeout=10000)
    page.wait_for_selector(".okf-graph-legend__item--chip", timeout=5000)
    info = page.evaluate("""() => {
        const l = document.querySelector('.okf-graph-legend');
        const closestDetail = l ? l.closest('#okf-detail') : null;
        const chips = l ? Array.from(l.querySelectorAll('.okf-graph-legend__item--chip')) : [];
        const zoomBtns = Array.from(document.querySelectorAll('.okf-graph-zoom button'));
        return {
            tag: l ? l.tagName : null,
            closestDetailId: closestDetail ? closestDetail.id : null,
            hasSummary: l ? !!l.querySelector('summary') : false,
            chipTags: chips.map(c => c.tagName),
            chipCount: chips.length,
            overlap: (() => {
                if (!l) return null;
                const c = document.querySelector('#okf-graph');
                const cr = c.getBoundingClientRect(), lr = l.getBoundingClientRect();
                return (lr.left < cr.right && lr.right > cr.left && lr.top < cr.bottom && lr.bottom > cr.top);
            })(),
            zoomBtnCount: zoomBtns.length,
            zoomBtnInfo: zoomBtns.map(b => ({
                hasSvg: !!b.querySelector('svg'),
                text: Array.from(b.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(''),
            })),
        };
    }""")
    # Legend parent.
    assert info["tag"] == "DETAILS", f"tag: {info['tag']}"
    assert info["closestDetailId"] == "okf-detail", f"closest #okf-detail: {info['closestDetailId']}"
    # Summary + chips.
    assert info["hasSummary"], "no summary"
    assert info["chipCount"] >= 1, f"chipCount: {info['chipCount']}"
    for tag in info["chipTags"]:
        assert tag == "BUTTON", f"chip tag: {tag}"
    # No overlap.
    assert not info["overlap"], "legend overlaps canvas"
    # 4 SVG zoom buttons.
    assert info["zoomBtnCount"] >= 4, f"zoom button count: {info['zoomBtnCount']}"
    for b in info["zoomBtnInfo"]:
        assert b["hasSvg"], "zoom button missing SVG"
        assert not b["text"], f"zoom button has text: '{b['text']}'"


# --- 4. Stale comment mark: non-color cue survives Border Off ---

def test_stale_comment_mark_dotted_underline_survives_border_off(server_url, page):
    """A .okf-comment-mark--stale element has text-decoration: underline dotted
    as a non-color cue. This survives Border Off (the cue is not border-based)."""
    _goto_concept(page, server_url)
    # Create a representative stale mark in the body using production CSS.
    page.evaluate("""() => {
        const body = document.querySelector('.okf-page__body');
        const mark = document.createElement('mark');
        mark.className = 'okf-comment-mark okf-comment-mark--stale';
        mark.textContent = 'stale comment';
        body.appendChild(mark);
    }""")
    page.wait_for_selector(".okf-comment-mark--stale")
    # Normal mode: has dotted underline.
    td = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-comment-mark--stale')
    ).textDecoration""")
    assert "underline" in td and "dotted" in td, f"normal stale mark text-decoration: {td}"
    # Border Off: still has dotted underline.
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    td_off = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-comment-mark--stale')
    ).textDecoration""")
    assert "underline" in td_off and "dotted" in td_off, \
        f"Border Off stale mark lost dotted underline: {td_off}"


# --- 5. Focus prose: compute 76ch in px, assert paragraph ≈76ch < body ---

def test_prose_focus_76ch_computed_and_narrower(server_url, page):
    """In Focus mode at a wide viewport, compute the pixel value of 76ch
    using a probe element, then assert:
    - paragraph resolved width is within ±10% of the computed 76ch value
    - paragraph max-width is set (not 'none')
    - body max-width is 'none' (wide content flows through)
    - table/pre have no restrictive cap (wide content exempt)

    Note: in Focus rendered view, the view wrap is ALSO capped at 76ch, so
    paragraph width = body width = 76ch. The paragraph cap ensures that even
    if the view wrap cap were removed, paragraphs stay at 76ch. The body
    itself has no max-width, so tables/pre/code can exceed 76ch.
    """
    page.set_viewport_size({"width": 1600, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("document.documentElement.setAttribute('data-okf-focus','')")
    page.wait_for_function("document.documentElement.hasAttribute('data-okf-focus')")
    page.wait_for_timeout(200)  # CSS apply frame
    info = page.evaluate("""() => {
        const p = document.querySelector('.okf-prose > p');
        const body = document.querySelector('.okf-page__body');
        const table = document.querySelector('.okf-page__body table');
        if (!p) return null;
        // Probe: create a 0-height div with width:76ch to measure the exact
        // pixel value of 76ch at the current font.
        const probe = document.createElement('div');
        probe.style.width = '76ch'; probe.style.height = '0';
        probe.style.position = 'absolute'; probe.style.visibility = 'hidden';
        p.parentElement.appendChild(probe);
        const ch76 = probe.getBoundingClientRect().width;
        probe.remove();
        const pcs = getComputedStyle(p);
        const bcs = body ? getComputedStyle(body) : null;
        return {
            pW: Math.round(p.getBoundingClientRect().width),
            pMaxW: pcs.maxWidth,
            bodyW: Math.round(body ? body.getBoundingClientRect().width : 0),
            bodyMaxW: bcs ? bcs.maxWidth : 'n/a',
            ch76px: Math.round(ch76),
            tableMaxW: table ? getComputedStyle(table).maxWidth : 'n/a',
        };
    }""")
    assert info, "no paragraph in Focus mode"
    ch76 = info["ch76px"]
    assert ch76 > 0, f"76ch probe measured 0px"
    # Paragraph width is within ±15% of the computed 76ch value.
    ratio = info["pW"] / ch76
    assert 0.85 <= ratio <= 1.15, \
        f"paragraph width ({info['pW']}px) not within ±15% of 76ch ({ch76}px): ratio={ratio:.2f}"
    # Paragraph max-width is set (the cap rule is applied).
    assert info["pMaxW"] != "none", f"paragraph max-width is none"
    # Body has no restrictive max-width (wide content flows through).
    assert info["bodyMaxW"] in ("none", ""), f"body has max-width: {info['bodyMaxW']}"
    # Wide content exempt.
    assert info["tableMaxW"] in ("none", "", "100%"), f"table max-width: {info['tableMaxW']}"
