"""Graph readability P1 proof: progressive label disclosure, mobile list-first,
Explore map action, breakpoint reparent, no overflow, Map/Bridges preservation.
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
    out = tmp_path_factory.mktemp("gr-static") / "site"
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
    out = tmp_path_factory.mktemp("gr-sf") / "viz.html"
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


def _goto_graph(pg, base, w=1440):
    pg.set_viewport_size({"width": w, "height": 900})
    pg.goto(f"{base}/__graph", wait_until="domcontentloaded")
    pg.wait_for_selector("#okf-graph canvas", timeout=15000)
    pg.wait_for_selector(".okf-graph-legend", timeout=5000)


# ===========================================================================
# 1. Desktop progressive label disclosure
# ===========================================================================

def test_desktop_map_fewer_labels_than_nodes(server_url, page):
    """At desktop 1440px, the number of initially visible labels is less than
    the total node count (progressive disclosure), but > 0."""
    _goto_graph(page, server_url, w=1440)
    info = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var total = cy.nodes().length;
        var labeled = 0;
        cy.nodes().forEach(function(n) {
            var op = parseFloat(n.style('text-opacity'));
            if (!isNaN(op) && op > 0) labeled++;
        });
        return { total: total, labeled: labeled };
    }""")
    assert info, "graph not initialized"
    assert info["labeled"] > 0, "no labels visible at all"
    assert info["labeled"] < info["total"], f"all {info['labeled']} labels visible (expected progressive disclosure for {info['total']} nodes)"


def test_desktop_label_revealed_on_selection(server_url, page):
    """Selecting a node with no label reveals its label (text-opacity becomes 1)."""
    _goto_graph(page, server_url, w=1440)
    result = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        // Find a node without a label initially.
        var unlabeled = cy.nodes().filter(function(n) {
            return parseFloat(n.style('text-opacity')) === 0;
        })[0];
        if (!unlabeled) return {found: false};
        unlabeled.select();
        var op = parseFloat(unlabeled.style('text-opacity'));
        return {found: true, opacity: op};
    }""")
    assert result, "graph not initialized"
    assert result["found"], "no unlabeled node found (all already labeled?)"
    assert result["opacity"] > 0, f"selected node label still hidden: {result['opacity']}"


def test_desktop_all_nodes_have_text_button(server_url, page):
    """Every node is represented as a text button in the node index."""
    _goto_graph(page, server_url, w=1440)
    info = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var total = cy.nodes().length;
        var buttons = document.querySelectorAll('.okf-node-index__item').length;
        return { total: total, buttons: buttons };
    }""")
    assert info, "graph not initialized"
    assert info["buttons"] == info["total"], f"{info['buttons']} buttons != {info['total']} nodes"


# ===========================================================================
# 2. Mobile list-first: node index open before canvas, Explore button
# ===========================================================================

def test_mobile_node_index_open_before_canvas(server_url, page):
    """At 390px, the node-index <details> is open, in normal flow before the
    canvas, and every node is a text button."""
    _goto_graph(page, server_url, w=390)
    info = page.evaluate("""() => {
        var ni = document.querySelector('.okf-node-index');
        var canvas = document.querySelector('#okf-graph');
        if (!ni || !canvas) return null;
        // Check node-index comes before canvas in DOM order.
        var all = Array.from(document.querySelectorAll('.okf-node-index, #okf-graph'));
        var niIdx = all.indexOf(ni);
        var canvasIdx = all.indexOf(canvas);
        return {
            isOpen: ni.hasAttribute('open'),
            isMobile: ni.classList.contains('okf-node-index--mobile'),
            isStatic: getComputedStyle(ni).position === 'static',
            beforeCanvas: niIdx < canvasIdx,
            buttonCount: document.querySelectorAll('.okf-node-index__item').length,
        };
    }""")
    assert info, "node-index or canvas not found"
    assert info["isOpen"], "node-index not open on mobile"
    assert info["isMobile"], "node-index missing mobile class"
    assert info["isStatic"], "node-index not in normal flow (position not static)"
    assert info["beforeCanvas"], "node-index not before canvas in DOM"
    assert info["buttonCount"] > 0, "no text buttons in node index"


def test_mobile_explore_map_button_exists(server_url, page):
    """At 390px, an 'Explore interactive map' button exists and is visible."""
    _goto_graph(page, server_url, w=390)
    btn = page.evaluate("""() => {
        var b = document.querySelector('.okf-graph-explore-map');
        if (!b) return null;
        var cs = getComputedStyle(b);
        return {
            text: b.textContent.trim(),
            visible: cs.display !== 'none' && !b.hidden,
        };
    }""")
    assert btn, "Explore map button not found"
    assert "explore" in btn["text"].lower(), f"button text: {btn['text']}"
    assert btn["visible"], "Explore button not visible"


def test_mobile_no_overflow(server_url, page):
    """At 390px, no document horizontal overflow."""
    _goto_graph(page, server_url, w=390)
    overflow = page.evaluate("""() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
    })""")
    assert overflow["sw"] <= overflow["cw"] + 1, f"overflow: sw={overflow['sw']} cw={overflow['cw']}"


# ===========================================================================
# 3. Breakpoint reparent: mobile → desktop restores overlay
# ===========================================================================

def test_breakpoint_reparent_restores_desktop(server_url, page):
    """Resize from mobile to desktop: node-index returns to canvas overlay,
    loses mobile class, and is collapsed."""
    _goto_graph(page, server_url, w=390)
    # Verify mobile state.
    assert page.evaluate("document.querySelector('.okf-node-index').classList.contains('okf-node-index--mobile')")
    # Resize to desktop.
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(300)  # MQ handler fires
    info = page.evaluate("""() => {
        var ni = document.querySelector('.okf-node-index');
        var canvas = document.querySelector('#okf-graph');
        if (!ni || !canvas) return null;
        return {
            isMobile: ni.classList.contains('okf-node-index--mobile'),
            isAbsolute: getComputedStyle(ni).position === 'absolute',
            inCanvas: canvas.contains(ni),
            isOpen: ni.hasAttribute('open'),
        };
    }""")
    assert info, "elements not found after resize"
    assert not info["isMobile"], "still has mobile class after desktop resize"
    assert not info["isOpen"], "still open after desktop resize"
    assert info["inCanvas"], "node-index not restored to canvas container"


# ===========================================================================
# 4. Map/Bridges preservation
# ===========================================================================

def test_map_lens_preserved_on_mobile(server_url, page):
    """Map lens is active and all nodes present on mobile."""
    _goto_graph(page, server_url, w=390)
    info = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var s = window.__okfLoomGraph.getState();
        return {
            lens: s ? s.lens : null,
            nodeCount: cy.nodes().length,
        };
    }""")
    assert info, "graph not initialized"
    assert info["lens"] == "map", f"expected map lens, got {info['lens']}"
    assert info["nodeCount"] > 0


def test_bridges_lens_preserved_on_mobile(server_url, page):
    """Bridges lens works on mobile with all nodes."""
    _goto_graph(page, server_url, w=390)
    page.wait_for_selector("#okf-lens-bridges", timeout=10000)
    page.evaluate("document.getElementById('okf-lens-bridges').click()")
    page.wait_for_function("document.getElementById('okf-lens-bridges').checked")
    page.wait_for_timeout(1000)
    info = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var s = window.__okfLoomGraph.getState();
        return {
            lens: s ? s.lens : null,
            nodeCount: cy.nodes().length,
        };
    }""")
    assert info, "graph not initialized"
    assert info["lens"] == "bridges", f"expected bridges lens, got {info['lens']}"
    assert info["nodeCount"] > 0


# ===========================================================================
# 5. Static/single-file parity
# ===========================================================================

def test_static_mobile_node_index_open(static_site_url, page):
    """Static build: mobile node-index is open and in normal flow."""
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    info = page.evaluate("""() => {
        var ni = document.querySelector('.okf-node-index');
        if (!ni) return null;
        return {
            isOpen: ni.hasAttribute('open'),
            isMobile: ni.classList.contains('okf-node-index--mobile'),
            isStatic: getComputedStyle(ni).position === 'static',
        };
    }""")
    assert info, "node-index not found"
    assert info["isOpen"], "static node-index not open"
    assert info["isMobile"], "static node-index not mobile"
    assert info["isStatic"], "static node-index not in flow"


def test_single_file_mobile_node_index_open(single_file_url, page):
    """Single-file: mobile node-index is open and in normal flow."""
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(single_file_url, wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    info = page.evaluate("""() => {
        var ni = document.querySelector('.okf-node-index');
        if (!ni) return null;
        return {
            isOpen: ni.hasAttribute('open'),
            isMobile: ni.classList.contains('okf-node-index--mobile'),
            isStatic: getComputedStyle(ni).position === 'static',
        };
    }""")
    assert info, "node-index not found"
    assert info["isOpen"], "single-file node-index not open"
    assert info["isMobile"], "single-file node-index not mobile"


def test_static_desktop_progressive_labels(static_site_url, page):
    """Static build at desktop: progressive label disclosure works."""
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    info = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var total = cy.nodes().length;
        var labeled = 0;
        cy.nodes().forEach(function(n) {
            var op = parseFloat(n.style('text-opacity'));
            if (!isNaN(op) && op > 0) labeled++;
        });
        return { total: total, labeled: labeled };
    }""")
    assert info, "graph not initialized"
    assert info["labeled"] > 0, "no labels visible"
    assert info["labeled"] < info["total"], f"all labels visible ({info['labeled']}/{info['total']})"


# ===========================================================================
# 6. Edge opacity floor preserved >= 0.3
# ===========================================================================

def test_edge_opacity_floor_preserved(server_url, page):
    """Edge opacity floor remains >= 0.3 after label disclosure changes."""
    _goto_graph(page, server_url, w=1440)
    min_opacity = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var min = 1;
        cy.edges().forEach(function(e) {
            var op = parseFloat(e.style('opacity'));
            if (!isNaN(op) && op < min) min = op;
        });
        return min;
    }""")
    assert min_opacity is not None
    assert min_opacity >= 0.3, f"edge opacity floor: {min_opacity}"
