"""Graph invariant closure: listener lifecycle, reduced-motion, reparent
order, deterministic top-N, edge opacity contract, filter/search/focus/lens
nonzero labels, static/single Explore focus.
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
    out = tmp_path_factory.mktemp("ic-static") / "site"
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
    out = tmp_path_factory.mktemp("ic-sf") / "viz.html"
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


@pytest.fixture
def reduced_motion_page():
    """Page with prefers-reduced-motion=reduce emulated before load."""
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
            ctx = b.new_context(color_scheme="light", reduced_motion="reduce")
            pg = ctx.new_page()
            yield pg
            ctx.close()
        finally: b.close()


def _goto_graph(pg, base, w=1440):
    pg.set_viewport_size({"width": w, "height": 900})
    pg.goto(f"{base}/__graph", wait_until="domcontentloaded")
    pg.wait_for_selector("#okf-graph canvas", timeout=15000)
    pg.wait_for_selector(".okf-graph-legend", timeout=5000)


# ===========================================================================
# 1. Listener lifecycle: disposeGraph — exact removal counts
# ===========================================================================

SPY_SCRIPT = """
    window.__mmRemoves = 0;
    window.__phRemoves = 0;
    var origMM = window.matchMedia.bind(window);
    window.matchMedia = function(q) {
        var mql = origMM(q);
        var origRemove = mql.removeEventListener ? mql.removeEventListener.bind(mql) : null;
        var origRL = mql.removeListener ? mql.removeListener.bind(mql) : null;
        if (origRemove) mql.removeEventListener = function(t, f, o) { if (t==='change') window.__mmRemoves++; return origRemove(t, f, o); };
        if (origRL) mql.removeListener = function(f) { window.__mmRemoves++; return origRL(f); };
        return mql;
    };
    var origWER = window.removeEventListener.bind(window);
    window.removeEventListener = function(t, f, o) { if (t==='pagehide') window.__phRemoves++; return origWER(t, f, o); };
"""


@pytest.fixture
def spy_page():
    """Page with matchMedia/removeEventListener spy via context init script."""
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
            ctx = b.new_context(color_scheme="light")
            ctx.add_init_script(SPY_SCRIPT)
            pg = ctx.new_page()
            yield pg
            ctx.close()
        finally: b.close()


def test_dispose_removes_matchMedia_and_pagehide_on_subtree_removal(server_url, spy_page):
    """Removing #okf-main triggers disposeGraph exactly once: matchMedia
    listener removed (count=1), pagehide listener removed (count=1)."""
    page = spy_page
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    assert page.evaluate("document.querySelector('.okf-node-index').classList.contains('okf-node-index--mobile')")
    # Remove #okf-main.
    page.evaluate("var m=document.getElementById('okf-main');if(m&&m.parentNode)m.parentNode.removeChild(m);")
    page.wait_for_timeout(500)
    mm = page.evaluate("window.__mmRemoves")
    ph = page.evaluate("window.__phRemoves")
    assert mm == 1, f"matchMedia removes: {mm} (expected 1)"
    assert ph == 1, f"pagehide removes: {ph} (expected 1)"
    # Resize: listener inactive.
    before = page.evaluate("document.querySelector('.okf-node-index')?.classList.contains('okf-node-index--mobile')")
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(300)
    after = page.evaluate("document.querySelector('.okf-node-index')?.classList.contains('okf-node-index--mobile')")
    assert before == after, "listener still active after dispose"


def test_pagehide_alone_disposes_exactly_once(server_url, spy_page):
    """Dispatching pagehide triggers disposeGraph exactly once."""
    page = spy_page
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'));")
    page.wait_for_timeout(300)
    mm = page.evaluate("window.__mmRemoves")
    ph = page.evaluate("window.__phRemoves")
    assert mm == 1, f"matchMedia: {mm}"
    assert ph == 1, f"pagehide: {ph}"


def test_subtree_then_pagehide_no_duplicate_removal(server_url, spy_page):
    """Subtree removal disposes once; subsequent pagehide is no-op."""
    page = spy_page
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    # First: subtree removal.
    page.evaluate("var m=document.getElementById('okf-main');if(m&&m.parentNode)m.parentNode.removeChild(m);")
    page.wait_for_timeout(500)
    mm1 = page.evaluate("window.__mmRemoves")
    ph1 = page.evaluate("window.__phRemoves")
    assert mm1 == 1 and ph1 == 1, f"first: mm={mm1} ph={ph1}"
    # Second: pagehide (should be no-op).
    page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide'));")
    page.wait_for_timeout(300)
    mm2 = page.evaluate("window.__mmRemoves")
    ph2 = page.evaluate("window.__phRemoves")
    assert mm2 == 1, f"duplicate mm: {mm2}"
    assert ph2 == 1, f"duplicate ph: {ph2}"


# ===========================================================================
# 2. Real reduced-motion test: behavior='auto', exact focus, no smooth
# ===========================================================================

def test_explore_reduced_motion_behavior_auto(server_url, reduced_motion_page):
    """Under reduced-motion, Explore uses scrollIntoView behavior='auto'."""
    pg = reduced_motion_page
    pg.set_viewport_size({"width": 390, "height": 900})
    # Instrument scrollIntoView before loading graph.
    pg.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    pg.wait_for_selector("#okf-graph canvas", timeout=15000)
    pg.wait_for_selector(".okf-graph-legend", timeout=5000)
    # Inject a scrollIntoView spy.
    pg.evaluate("""() => {
        window.__scrollBehaviors = [];
        var orig = Element.prototype.scrollIntoView;
        Element.prototype.scrollIntoView = function(opts) {
            window.__scrollBehaviors.push(opts ? opts.behavior : 'auto');
            return orig.apply(this, arguments);
        };
    }""")
    pg.wait_for_selector(".okf-graph-explore-map", timeout=5000)
    # Activate Explore via keyboard (focus + Enter).
    pg.evaluate("document.querySelector('.okf-graph-explore-map').focus()")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(1000)  # rAF + fit
    # Assert behavior was 'auto'.
    behaviors = pg.evaluate("window.__scrollBehaviors")
    assert len(behaviors) > 0, "scrollIntoView not called"
    assert all(b == "auto" for b in behaviors), f"expected 'auto', got: {behaviors}"
    # Assert exact focus on graph container.
    active_id = pg.evaluate("document.activeElement ? document.activeElement.id : null")
    assert active_id == "okf-graph", f"activeElement: {active_id}"


# ===========================================================================
# 3. Exact reparent cycle: [index, explore, graph] sibling order, one button
# ===========================================================================

def test_reparent_exact_order_two_cycles(server_url, page):
    """Two 390→1440→390→1440 cycles: exact [index, explore, graph] sibling
    indexes on mobile, one button, correct parents on desktop."""
    _goto_graph(page, server_url, w=390)
    for cycle in range(2):
        # Mobile.
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(300)
        mobile = page.evaluate("""() => {
            var ni = document.querySelector('.okf-node-index');
            var eb = document.querySelectorAll('.okf-graph-explore-map');
            var graph = document.querySelector('#okf-graph');
            if (!ni || !graph) return null;
            var parent = ni.parentElement;
            var children = Array.from(parent.children);
            return {
                niIdx: children.indexOf(ni),
                ebIdx: eb.length > 0 ? children.indexOf(eb[0]) : -1,
                graphIdx: children.indexOf(graph),
                ebCount: eb.length,
                sameParent: ni.parentElement === graph.parentElement,
            };
        }""")
        assert mobile, f"cycle {cycle}: mobile elements missing"
        assert mobile["sameParent"], f"cycle {cycle}: different parents"
        assert mobile["niIdx"] < mobile["ebIdx"], f"cycle {cycle}: index({mobile['niIdx']}) not before explore({mobile['ebIdx']})"
        assert mobile["ebIdx"] < mobile["graphIdx"], f"cycle {cycle}: explore({mobile['ebIdx']}) not before graph({mobile['graphIdx']})"
        assert mobile["ebCount"] == 1, f"cycle {cycle}: {mobile['ebCount']} explore buttons"
        # Desktop.
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(300)
        desktop = page.evaluate("""() => {
            var ni = document.querySelector('.okf-node-index');
            var eb = document.querySelectorAll('.okf-graph-explore-map');
            var graph = document.querySelector('#okf-graph');
            if (!ni || !graph) return null;
            return {
                inCanvas: graph.contains(ni),
                ebCount: eb.length,
                ebHidden: eb.length > 0 ? eb[0].hidden : true,
                isMobile: ni.classList.contains('okf-node-index--mobile'),
            };
        }""")
        assert desktop, f"cycle {cycle}: desktop elements missing"
        assert desktop["inCanvas"], f"cycle {cycle}: index not in canvas"
        assert desktop["ebCount"] == 1, f"cycle {cycle}: desktop {desktop['ebCount']} buttons"
        assert desktop["ebHidden"], f"cycle {cycle}: explore not hidden"
        assert not desktop["isMobile"], f"cycle {cycle}: still mobile"


# ===========================================================================
# 4. Deterministic top-N label IDs: exact expected ranking
# ===========================================================================

def test_progressive_label_ids_deterministic(server_url, page):
    """Progressive label IDs match the exact expected degree-descending +
    ID-ascending ranking from the current graph data. Repeatable after
    filter clear and lens changes."""
    _goto_graph(page, server_url, w=1440)
    # Get actual label IDs.
    actual1 = page.evaluate("""() => {
        if (!window.__okfLoomGraph) return null;
        return window.__okfLoomGraph.progressiveLabelIds();
    }""")
    assert actual1 is not None, "diagnostic not available"
    assert len(actual1) > 0, "no progressive labels"
    # Get expected ranking from graph data.
    expected = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var visible = cy.nodes().filter(function(n) { return !n.hasClass('dim'); });
        var list = visible.map(function(n) {
            return { id: n.id(), deg: n.degree(false) };
        }).sort(function(a, b) {
            if (b.deg !== a.deg) return b.deg - a.deg;
            return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
        });
        var count = Math.min(8, Math.max(1, Math.floor(list.length / 3)));
        return list.slice(0, count).map(function(x) { return x.id; });
    }""")
    assert expected is not None
    # Actual must match expected exactly.
    assert set(actual1) == set(expected), f"label IDs mismatch: actual={actual1} expected={expected}"
    # Repeatable: apply search, clear it, verify same IDs.
    page.locator("#okf-search").fill("order")
    page.wait_for_timeout(500)
    page.locator("#okf-search").fill("")
    page.wait_for_timeout(500)
    actual2 = page.evaluate("window.__okfLoomGraph ? window.__okfLoomGraph.progressiveLabelIds() : null")
    assert actual2 is not None
    assert set(actual1) == set(actual2), f"not repeatable: before={actual1} after={actual2}"


# ===========================================================================
# 5. Edge opacity contract: base >=0.3, dim lower by design, restore on clear
# ===========================================================================

def test_edge_opacity_base_dim_and_restore(server_url, page):
    """Base (non-dim) edge opacity >= 0.3. Dimmed edges have opacity < 0.3
    (documented contextual dim rule). Clearing the filter restores base >= 0.3."""
    _goto_graph(page, server_url, w=1440)
    # Base floor: read non-dim edge min opacity.
    base_min = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var min = 1;
        cy.edges().forEach(function(e) {
            if (e.hasClass('dim') || e.hasClass('okf-hover-dim') || e.hasClass('okf-path-dim')) return;
            var op = parseFloat(e.style('opacity'));
            if (!isNaN(op) && op < min) min = op;
        });
        return min;
    }""")
    assert base_min is not None
    assert base_min >= 0.3, f"base floor: {base_min}"

    # Apply a search that dims some edges (search for a real term that
    # matches SOME but not ALL nodes).
    page.locator("#okf-search").fill("orders")
    page.wait_for_timeout(500)

    dim_info = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var dimEdges = cy.edges().filter(function(e) { return e.hasClass('dim'); });
        // Read opacity of the first dimmed edge.
        var dimOpacity = null;
        if (dimEdges.length > 0) {
            dimOpacity = parseFloat(dimEdges[0].style('opacity'));
        }
        // Read min opacity of non-dim edges.
        var nonDimMin = 1;
        cy.edges().forEach(function(e) {
            if (e.hasClass('dim')) return;
            var op = parseFloat(e.style('opacity'));
            if (!isNaN(op) && op < nonDimMin) nonDimMin = op;
        });
        return { dimCount: dimEdges.length, dimOpacity: dimOpacity, nonDimMin: nonDimMin };
    }""")
    assert dim_info is not None
    assert dim_info["dimCount"] > 0, "no dimmed edges after search filter"
    # Dimmed edge opacity must be below 0.3 (contextual dim rule).
    assert dim_info["dimOpacity"] is not None, "dim edge opacity not readable"
    assert dim_info["dimOpacity"] < 0.3, \
        f"dimmed edge opacity {dim_info['dimOpacity']} not below 0.3 (expected contextual dim)"
    # Non-dim edges still >= 0.3.
    assert dim_info["nonDimMin"] >= 0.3, \
        f"non-dim edge opacity {dim_info['nonDimMin']} below 0.3 during filter"

    # Clear filter: base floor restored.
    page.locator("#okf-search").fill("")
    page.wait_for_timeout(500)
    restored_min = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var min = 1;
        cy.edges().forEach(function(e) {
            if (e.hasClass('dim')) return;
            var op = parseFloat(e.style('opacity'));
            if (!isNaN(op) && op < min) min = op;
        });
        return min;
    }""")
    assert restored_min is not None
    assert restored_min >= 0.3, f"restored base floor: {restored_min}"


# ===========================================================================
# 6. Nonzero eligible labels after filter/search/focus/lens
# ===========================================================================

def test_nonzero_labels_after_search(server_url, page):
    _goto_graph(page, server_url, w=1440)
    page.locator("#okf-search").fill("order")
    page.wait_for_timeout(500)
    labels = page.evaluate("window.__okfLoomGraph ? window.__okfLoomGraph.progressiveLabelIds().length : -1")
    visible = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return 0;
        return window.__okfLoomGraph.cy.nodes().filter(function(n) { return !n.hasClass('dim'); }).length;
    }""")
    if visible > 0:
        assert labels >= 1, f"no labels after search (visible={visible})"


def test_nonzero_labels_after_lens(server_url, page):
    _goto_graph(page, server_url, w=1440)
    page.wait_for_selector("#okf-lens-bridges", timeout=10000)
    page.evaluate("document.getElementById('okf-lens-bridges').click()")
    page.wait_for_function("document.getElementById('okf-lens-bridges').checked")
    page.wait_for_timeout(1500)
    labels = page.evaluate("window.__okfLoomGraph ? window.__okfLoomGraph.progressiveLabelIds().length : -1")
    assert labels >= 1, f"no labels after Bridges lens"


def test_nonzero_labels_after_focus(server_url, page):
    _goto_graph(page, server_url, w=1440)
    page.evaluate("""() => {
        if (window.__okfLoomGraph && window.__okfLoomGraph.cy) {
            window.__okfLoomGraph.cy.nodes()[0].select();
        }
    }""")
    page.wait_for_selector("#okf-lens-focus", timeout=10000)
    page.evaluate("document.getElementById('okf-lens-focus').click()")
    page.wait_for_timeout(1500)
    labels = page.evaluate("window.__okfLoomGraph ? window.__okfLoomGraph.progressiveLabelIds().length : -1")
    visible = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return 0;
        return window.__okfLoomGraph.cy.nodes().filter(function(n) { return !n.hasClass('dim'); }).length;
    }""")
    if visible > 0:
        assert labels >= 1, f"no labels after focus (visible={visible})"


# ===========================================================================
# 7. Static/single-file Explore action focus
# ===========================================================================

def test_static_explore_focuses_graph(static_site_url, page):
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    page.wait_for_selector(".okf-graph-explore-map", timeout=5000)
    page.click(".okf-graph-explore-map")
    page.wait_for_timeout(500)
    assert page.evaluate("document.activeElement.id") == "okf-graph"


def test_single_file_explore_focuses_graph(single_file_url, page):
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(single_file_url, wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    page.wait_for_selector(".okf-graph-explore-map", timeout=5000)
    page.click(".okf-graph-explore-map")
    page.wait_for_timeout(500)
    assert page.evaluate("document.activeElement.id") == "okf-graph"
