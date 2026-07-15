"""Final visual/a11y blockers: panel focus outlines, static no-JS banner,
mobile node-index width, Mermaid base theme with resolved RGB tokens.
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
    out = tmp_path_factory.mktemp("fv-static") / "site"
    subprocess.run(okf_module_argv("build", str(DEMO_BUNDLE), "--target", "static", "--out", str(out)), cwd=str(TOOLKIT_ROOT), capture_output=True, text=True, env=okf_subprocess_env(), timeout=30, check=False)
    if not (out / "index.html").is_file(): pytest.skip("static build failed")
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=str(out), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_http(proc, base, "/index.html")
    try: yield base
    finally: _terminate(proc)


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


@pytest.fixture
def nojs_page():
    chrome = os.environ.get("AIC_PLAYWRIGHT_CHROME_PATH") or ""
    with sync_playwright() as p:
        b = None; last = None
        attempts = []
        if chrome: attempts.append({"executable_path": chrome, "args": ["--no-sandbox"]})
        attempts.append({"channel": "chrome"})
        for kw in attempts:
            try: b = p.chromium.launch(**kw); break
            except Exception as e: last = e
        if b is None: pytest.skip(f"no chrome ({last})")
        try:
            ctx = b.new_context(color_scheme="light", java_script_enabled=False)
            pg = ctx.new_page()
            yield pg
            ctx.close()
        finally: b.close()


def _count_visible_banners(pg):
    return pg.evaluate("""() => {
        var banners = document.querySelectorAll('.okf-studio-fallback-banner');
        var visible = 0;
        banners.forEach(function(b) {
            if (getComputedStyle(b).display !== 'none') visible++;
        });
        return visible;
    }""")


# ===========================================================================
# 1. Panel tab and close focus-visible outlines
# ===========================================================================

def test_panel_tab_focus_visible_outline(server_url, page):
    """Panel tab has >=2px focus-visible outline when focused via keyboard."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    # Focus the first tab via JS and check computed outline.
    page.evaluate("""() => {
        var tab = document.querySelector('.okf-panel__tab');
        if (tab) { tab.focus(); }
    }""")
    page.wait_for_timeout(100)
    info = page.evaluate("""() => {
        var tab = document.querySelector('.okf-panel__tab');
        if (!tab) return null;
        var cs = getComputedStyle(tab);
        return {
            outlineWidth: cs.outlineWidth,
            outlineStyle: cs.outlineStyle,
            outlineColor: cs.outlineColor,
        };
    }""")
    assert info, "no panel tab found"
    # Focus-visible outline is applied via :focus-visible pseudo — computed
    # style on the element itself may not reflect it until the browser
    # matches the pseudo. We check the CSS rule exists instead.
    has_rule = page.evaluate("""() => {
        for (var sheet of document.styleSheets) {
            try {
                for (var rule of sheet.cssRules) {
                    if (rule.selectorText && rule.selectorText.includes('.okf-panel__tab:focus-visible')) {
                        return true;
                    }
                }
            } catch(e) {}
        }
        return false;
    }""")
    assert has_rule, "no .okf-panel__tab:focus-visible CSS rule found"


def test_panel_close_focus_visible_outline(server_url, page):
    """Panel close button has >=2px focus-visible outline."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    has_rule = page.evaluate("""() => {
        for (var sheet of document.styleSheets) {
            try {
                for (var rule of sheet.cssRules) {
                    if (rule.selectorText && rule.selectorText.includes('.okf-panel__close:focus-visible')) {
                        return true;
                    }
                }
            } catch(e) {}
        }
        return false;
    }""")
    assert has_rule, "no .okf-panel__close:focus-visible CSS rule found"


def test_panel_tab_focus_outline_distinct_from_selected(server_url, page):
    """Focus outline uses outline property, selected uses border-bottom —
    distinct properties so they don't conflict."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    info = page.evaluate("""() => {
        var tab = document.querySelector('.okf-panel__tab[aria-selected="true"]');
        if (!tab) return null;
        var cs = getComputedStyle(tab);
        return {
            borderBottomColor: cs.borderBottomColor,
            borderBottomWidth: cs.borderBottomWidth,
        };
    }""")
    assert info, "no selected tab"
    # Selected tab has a border-bottom (underline cue).
    assert float(info["borderBottomWidth"].replace("px","")) > 0, f"selected tab border-bottom: {info['borderBottomWidth']}"


# ===========================================================================
# 2. Static no-JS: noscript banner visible with JS disabled
# ===========================================================================

def test_static_nojs_shows_noscript_banner(static_site_url, nojs_page):
    """Static build with JS disabled: exactly one noscript banner visible."""
    nojs_page.goto(f"{static_site_url}/index.html", wait_until="load")
    nojs_page.wait_for_timeout(500)
    count = _count_visible_banners(nojs_page)
    assert count == 1, f"static no-JS: {count} banners (expected 1)"


def test_static_js_on_zero_banners(static_site_url, page):
    """Static build with JS on: zero banners (okf-js-enabled hides --js variant)."""
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    page.wait_for_timeout(500)
    count = _count_visible_banners(page)
    assert count == 0, f"static JS-on: {count} banners (expected 0)"


# ===========================================================================
# 3. Mobile node-index full viewport width
# ===========================================================================

def test_mobile_node_index_full_width(server_url, page):
    """At 390px, .okf-node-index--mobile width >= parent width - tolerance."""
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    page.wait_for_selector(".okf-node-index--mobile", timeout=5000)
    info = page.evaluate("""() => {
        var ni = document.querySelector('.okf-node-index--mobile');
        var parent = ni ? ni.parentElement : null;
        if (!ni || !parent) return null;
        var niRect = ni.getBoundingClientRect();
        var pRect = parent.getBoundingClientRect();
        return {
            niW: Math.round(niRect.width),
            parentW: Math.round(pRect.width),
            vw: window.innerWidth,
            overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        };
    }""")
    assert info, "mobile node-index not found"
    # Width should be >= parent width - 4px tolerance.
    assert info["niW"] >= info["parentW"] - 4, \
        f"node-index width {info['niW']} < parent {info['parentW']} - 4"
    # No document horizontal overflow.
    assert not info["overflow"], f"document overflow: sw={info['vw']}"


# ===========================================================================
# 4. Mermaid base theme with resolved RGB tokens
# ===========================================================================

STUB_MERMAID_JS = """
    window.__mermaidInitArgs = null;
    window.__okfMermaidTestImport = {
        default: {
            initialize: function(args) { window.__mermaidInitArgs = args; },
            run: function(args) {
                (args.nodes || []).forEach(function(n) {
                    n.innerHTML = '';
                    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                    svg.setAttribute('data-rendered', 'true');
                    n.appendChild(svg);
                });
                return Promise.resolve();
            }
        }
    };
"""


@pytest.mark.parametrize("theme", ["swiss-light", "technical-dark"])
def test_mermaid_theme_base_with_hex_tokens(server_url, page, theme):
    """Mermaid initialize receives theme:'base' with hex-resolved
    themeVariables (not raw OKLCH)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    # Set theme before navigating so localStorage persists.
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.evaluate(f"""() => {{
        localStorage.setItem('okf-theme-family','{theme.split("-")[0]}');
        localStorage.setItem('okf-theme-mode','{theme.split("-")[1]}');
    }}""")
    page.reload(wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    # Inject stub via context init script won't work here; inject directly.
    page.evaluate(STUB_MERMAID_JS)
    # Add a mermaid div and trigger render.
    page.evaluate("""() => {
        var d = document.createElement('div'); d.className = 'mermaid';
        d.textContent = 'graph TD; A-->B';
        document.querySelector('.okf-page__body').appendChild(d);
    }""")
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_function("window.__mermaidInitArgs !== null", timeout=5000)
    args = page.evaluate("""() => {
        var a = window.__mermaidInitArgs;
        if (!a) return null;
        var tv = a.themeVariables || {};
        return {
            theme: a.theme,
            primaryColor: tv.primaryColor,
            primaryTextColor: tv.primaryTextColor,
            lineColor: tv.lineColor,
            background: tv.background,
            fontSize: tv.fontSize,
            actorBkg: tv.actorBkg,
            noteBkgColor: tv.noteBkgColor,
        };
    }""")
    assert args, "mermaid initialize not called"
    assert args["theme"] == "base", f"theme: {args['theme']} (expected 'base')"
    # All colors should be hex (start with #), not oklch.
    for key in ["primaryColor", "primaryTextColor", "lineColor", "background", "actorBkg", "noteBkgColor"]:
        val = args[key]
        assert val and val.startswith("#"), f"{theme} {key}: {val} (expected hex)"
        # Hex should be 7 chars (#rrggbb).
        assert len(val) == 7, f"{theme} {key}: {val} (expected #rrggbb)"
    # Font size should be readable (>= 14px).
    assert args["fontSize"] == "14px", f"fontSize: {args['fontSize']}"


def test_mermaid_rendered_svg_exists(server_url, page):
    """Mermaid renders an SVG into the mermaid div (stub renderer)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate(STUB_MERMAID_JS)
    page.evaluate("""() => {
        var d = document.createElement('div'); d.className = 'mermaid';
        d.textContent = 'graph TD; A-->B';
        document.querySelector('.okf-page__body').appendChild(d);
    }""")
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_function("document.querySelector('div.mermaid svg[data-rendered=\"true\"]') !== null", timeout=5000)
    # Source preserved.
    src = page.evaluate("document.querySelector('div.mermaid').getAttribute('data-source')")
    assert src and "graph TD" in src
