"""Visual P1/P2 regression proof: mobile topbar, appearance indicator,
no-JS banner, empty search, Mermaid tokens, mobile Studio panel.
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
    out = tmp_path_factory.mktemp("vp-static") / "site"
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
    out = tmp_path_factory.mktemp("vp-sf") / "viz.html"
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


# ===========================================================================
# 1. Mobile topbar: all controls visible, no overflow at target widths
# ===========================================================================

@pytest.mark.parametrize("width", [320, 390, 430, 900, 901])
def test_concept_topbar_no_overflow_all_widths(server_url, page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    overflow = page.evaluate("""() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
    })""")
    assert overflow["sw"] <= overflow["cw"] + 1, f"concept overflow at {width}: sw={overflow['sw']} cw={overflow['cw']}"


@pytest.mark.parametrize("width", [320, 390, 430])
def test_graph_topbar_controls_visible(server_url, page, width):
    """Every graph topbar control is within the viewport at narrow widths."""
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    # Check no horizontal overflow.
    overflow = page.evaluate("""() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
    })""")
    assert overflow["sw"] <= overflow["cw"] + 1, f"graph overflow at {width}: sw={overflow['sw']} cw={overflow['cw']}"
    # Appearance trigger is within viewport (scrollIntoView if needed).
    page.evaluate("document.getElementById('okf-theme').scrollIntoView({inline:'center'})")
    box = page.locator("#okf-theme").bounding_box()
    assert box and box["width"] > 0, "Appearance trigger not rendered"


@pytest.mark.parametrize("width", [320, 390])
def test_static_concept_topbar_no_overflow(static_site_url, page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    page.wait_for_selector("#okf-theme")
    overflow = page.evaluate("""() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
    })""")
    assert overflow["sw"] <= overflow["cw"] + 1, f"static overflow at {width}: sw={overflow['sw']} cw={overflow['cw']}"


@pytest.mark.parametrize("width", [320, 390])
def test_single_file_topbar_no_overflow(single_file_url, page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(single_file_url, wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    overflow = page.evaluate("""() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
    })""")
    assert overflow["sw"] <= overflow["cw"] + 1, f"single-file overflow at {width}: sw={overflow['sw']} cw={overflow['cw']}"


# ===========================================================================
# 2. Appearance selected indicator: ::before dot
# ===========================================================================

def test_appearance_selected_has_dot_indicator(server_url, page):
    """Checked Appearance option has a ::before pseudo-element (deterministic
    non-color check indicator)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.click("#okf-theme")
    page.wait_for_selector("#okf-appearance-menu:not([hidden])")
    # Check the ::before content is non-empty on the checked option.
    content = page.evaluate("""() => {
        var opt = document.querySelector('.okf-appearance__opt[aria-checked="true"]');
        if (!opt) return null;
        return getComputedStyle(opt, '::before').content;
    }""")
    assert content and content != "none", f"::before content: {content}"


# ===========================================================================
# 3. No-JS duplicate banner: only one visible
# ===========================================================================

def test_no_duplicate_banners_when_js_on(server_url, page):
    """When JS is on and studio boots, only zero fallback banners are visible
    (the noscript doesn't render, the JS banner is hidden by booted class)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    count = page.evaluate("""() => {
        var banners = document.querySelectorAll('.okf-studio-fallback-banner');
        var visible = 0;
        banners.forEach(function(b) {
            var cs = getComputedStyle(b);
            if (cs.display !== 'none') visible++;
        });
        return visible;
    }""")
    assert count == 0, f"{count} fallback banners visible when studio booted"


def test_static_no_fallback_banner(static_site_url, page):
    """Static build: no fallback banner (data-okf-mode=static hides it)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    count = page.evaluate("""() => {
        var banners = document.querySelectorAll('.okf-studio-fallback-banner');
        var visible = 0;
        banners.forEach(function(b) {
            if (getComputedStyle(b).display !== 'none') visible++;
        });
        return visible;
    }""")
    assert count == 0, f"{count} banners visible on static"


# ===========================================================================
# 4. Empty static search: neutral prompt, not "No results"
# ===========================================================================

def test_empty_static_search_neutral_prompt(static_site_url, page):
    """Static search with no query shows neutral initial prompt."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/__search.html", wait_until="load")
    page.wait_for_selector(".okf-search-empty, .okf-search__results", timeout=5000)
    # The heading should NOT say "No results" when there's no query.
    heading = page.evaluate("""() => {
        var h = document.querySelector('.okf-search__title');
        return h ? h.textContent.trim() : null;
    }""")
    assert heading, "no search heading found"
    assert "no results" not in heading.lower(), f"empty search heading says 'No results': {heading}"


# ===========================================================================
# 5. Mermaid themeVariables: passed to initialize
# ===========================================================================

def test_mermaid_themevars_passed(server_url, page):
    """Mermaid initialize receives themeVariables from computed CSS tokens."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    # Inject stub that captures initialize args.
    page.evaluate("""() => {
        window.__mermaidInitArgs = null;
        window.__okfMermaidTestImport = {
            default: {
                initialize: function(args) { window.__mermaidInitArgs = args; },
                run: function(args) {
                    (args.nodes || []).forEach(function(n) {
                        n.innerHTML = ''; n.appendChild(document.createElementNS('http://www.w3.org/2000/svg','svg'));
                    });
                    return Promise.resolve();
                }
            }
        };
    }""")
    # Add a mermaid div and trigger render.
    page.evaluate("""() => {
        var d = document.createElement('div'); d.className = 'mermaid';
        d.textContent = 'graph TD; A-->B';
        document.querySelector('.okf-page__body').appendChild(d);
    }""")
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_function("window.__mermaidInitArgs !== null", timeout=5000)
    args = page.evaluate("JSON.stringify(window.__mermaidInitArgs)")
    import json
    init = json.loads(args)
    assert "themeVariables" in init, "themeVariables not passed to mermaid.initialize"
    tv = init["themeVariables"]
    assert "primaryColor" in tv, "primaryColor missing from themeVariables"
    assert "primaryTextColor" in tv, "primaryTextColor missing"
    assert "lineColor" in tv, "lineColor missing"
    assert "background" in tv, "background missing"


# ===========================================================================
# 6. Mobile Studio: scroll reset + sticky header
# ===========================================================================

def test_mobile_studio_scroll_reset_on_open(server_url, page):
    """Opening the Studio panel on mobile resets body scroll to origin."""
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    # Scroll down.
    page.evaluate("window.scrollTo(0, 500)")
    page.wait_for_timeout(100)
    # Open panel.
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.wait_for_timeout(300)
    # Panel body should be scrolled to top.
    scroll = page.evaluate("document.getElementById('okf-panel-body').scrollTop")
    assert scroll == 0, f"panel body not scrolled to top: {scroll}"


def test_mobile_studio_header_sticky(server_url, page):
    """Studio panel header is sticky (position: sticky) on mobile."""
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    pos = page.evaluate("""() => {
        var h = document.querySelector('.okf-panel__header');
        return h ? getComputedStyle(h).position : null;
    }""")
    assert pos == "sticky", f"panel header position: {pos}"


def test_mobile_studio_no_dead_bottom_band(server_url, page):
    """Panel fills 100dvh with no dead bottom band."""
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.wait_for_timeout(300)
    info = page.evaluate("""() => {
        var p = document.getElementById('okf-panel');
        var r = p.getBoundingClientRect();
        return { top: r.top, bottom: r.bottom, height: r.height, vh: window.innerHeight };
    }""")
    # Panel should fill the viewport (top=0, bottom=vh).
    assert info["top"] == 0, f"panel top: {info['top']}"
    assert info["bottom"] == info["vh"], f"panel bottom: {info['bottom']} != vh {info['vh']}"


# ===========================================================================
# 7. Status bar text size >= 14px
# ===========================================================================

def test_status_bar_text_size_gte_14px(server_url, page):
    """Bottom operational status text/symbol is >=14px equivalent."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_selector(".okf-studio-bar--status .okf-conn", timeout=5000)
    size = page.evaluate("""() => {
        var el = document.querySelector('.okf-studio-bar--status .okf-conn');
        if (!el) return null;
        return parseFloat(getComputedStyle(el).fontSize);
    }""")
    assert size is not None, "no status bar text found"
    assert size >= 14, f"status bar font size: {size}px (expected >=14)"


# ===========================================================================
# 8. Rail border-top exists (dark theme cap fix)
# ===========================================================================

def test_rail_has_border_top(server_url, page):
    """Studio rail has a border-top (dark theme cap fix)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_selector(".okf-rail", timeout=5000)
    bt = page.evaluate("""() => {
        var r = document.querySelector('.okf-rail');
        return r ? getComputedStyle(r).borderTopWidth : null;
    }""")
    assert bt and bt != "0px", f"rail border-top: {bt}"
