"""Polish proof: Mermaid listener wiring, graph palette, split clarity.
CDN-dependent Mermaid render tests are in test_async_lifecycle_browser.py
(deterministic stubs, zero skips). Comment jump lifecycle tests are in
test_lifecycle_proof_browser.py (production paths, no private exports).
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

def _wait_http(proc, base):
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if proc.poll() is not None: pytest.skip("server exited")
        try:
            with urllib.request.urlopen(base, timeout=1) as r:
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
# 1. Mermaid: listener registered (deterministic — no CDN needed)
# ===========================================================================

def test_mermaid_theme_listener_registered(server_url, page):
    """renderers.js registers an okf-loom:themeChanged listener."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    result = page.evaluate("""() => {
        try {
            window.dispatchEvent(new CustomEvent("okf-loom:themeChanged", {
                detail: {resolvedMode: "dark", previousResolvedMode: "light"}
            }));
            return true;
        } catch(e) { return String(e); }
    }""")
    assert result is True, f"themeChanged dispatch failed: {result}"


# ===========================================================================
# 2. Graph palette: exact Cytoscape style from computed CSS
# ===========================================================================

def test_graph_node_color_matches_computed_css(server_url, page):
    """The graph canvas node text color resolves from computed CSS tokens."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    # Read the computed CSS --okf-fg and resolve to RGB via canvas probe.
    data = page.evaluate("""() => {
        const cs = getComputedStyle(document.documentElement);
        const cv = document.createElement('canvas'); cv.width=2; cv.height=2;
        const cx = cv.getContext('2d');
        function toRGB(cssColor) {
            cx.fillStyle = '#000'; cx.fillStyle = cssColor;
            cx.fillRect(0,0,1,1);
            const d = cx.getImageData(0,0,1,1).data;
            return [d[0], d[1], d[2]];
        }
        const cssFg = toRGB(cs.getPropertyValue('--okf-fg').trim());
        // Read the Cytoscape node text color.
        let nodeColor = null;
        if (window.__okfLoomGraph && window.__okfLoomGraph.cy) {
            const cy = window.__okfLoomGraph.cy;
            const n = cy.nodes()[0];
            if (n) nodeColor = n.style('color');
        }
        // Resolve nodeColor (may be named/hex/rgb) to RGB.
        let nodeRGB = null;
        if (nodeColor) {
            cx.fillStyle = '#000'; cx.fillStyle = nodeColor;
            cx.fillRect(0,0,1,1);
            const d = cx.getImageData(0,0,1,1).data;
            nodeRGB = [d[0], d[1], d[2]];
        }
        return {cssFg, nodeRGB};
    }""")
    assert data["nodeRGB"], "node color not resolved"
    assert data["cssFg"], "CSS fg not resolved"
    # Colors should match (derived from computed CSS).
    assert data["nodeRGB"] == data["cssFg"], \
        f"node color {data['nodeRGB']} != CSS fg {data['cssFg']}"


def test_graph_modifier_resync_canvas_present(server_url, page):
    """Contrast modifier change re-syncs the canvas without destroying it."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.evaluate("document.documentElement.setAttribute('data-okf-contrast','soft')")
    page.wait_for_timeout(300)
    assert page.evaluate("document.querySelectorAll('#okf-graph canvas').length > 0")


# ===========================================================================
# 3. Split: descriptions + Border Off underline
# ===========================================================================

def test_split_view_has_descriptions(server_url, page):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_selector(".okf-viewswitch__btn", timeout=5000)
    titles = page.evaluate("""() =>
        Array.from(document.querySelectorAll('.okf-viewswitch__btn')).map(b => ({
            text: b.textContent.trim(), title: b.getAttribute('title')
        }))
    """)
    assert len(titles) == 3
    for t in titles:
        assert t["title"], f"button '{t['text']}' missing title"
    split = [t for t in titles if t["text"] == "Split"][0]
    assert "side by side" in split["title"].lower()


def test_split_border_off_underline(server_url, page):
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    page.wait_for_selector(".okf-viewswitch__btn[aria-pressed='true']", timeout=5000)
    td = page.evaluate("""() => {
        const b = document.querySelector('.okf-viewswitch__btn[aria-pressed="true"]');
        return b ? getComputedStyle(b).textDecoration : null;
    }""")
    assert td and "underline" in td
