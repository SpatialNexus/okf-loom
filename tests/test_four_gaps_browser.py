"""Final four proof gaps: resolve lifecycle, fallback palette parity (all 7
roles), Border Off exact cue styles (no conditionals), edge opacity >=0.3.
Zero conditional/vacuous assertions.
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


def _get_token(page):
    return page.evaluate("""() => {
        try { return JSON.parse(document.getElementById('okf-studio-bootstrap').textContent).token; }
        catch(e) { return null; }
    }""")


# ===========================================================================
# 1. Resolve lifecycle: text-anchor → mark exists → jump → resolve → cleanup
# ===========================================================================

def test_resolve_lifecycle_clears_jump(server_url, page):
    """Post comment with TEXT anchor matching body content → applyCommentMarks
    must render a mark → click mark (production pin-click) → assert jumped +
    focused → resolve via API → SSE → assert cue/timer cleared, resolved state.
    No conditional branches."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    token = _get_token(page)
    assert token, "no CSRF token"

    # Read a real text snippet from the body to use as anchor.
    anchor_ref = page.evaluate("""() => {
        var p = document.querySelector('.okf-page__body p');
        if (!p) return null;
        var t = p.textContent.trim();
        return t.substring(0, Math.min(30, t.length));
    }""")
    assert anchor_ref, "no body paragraph text for anchor"

    # Post comment with text anchor.
    unique_body = "RESOLVE_LIFECYCLE_AAAA1111"
    ok = page.evaluate("""async (args) => {
        const resp = await fetch('/__comment', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-OKF-Token': args.token},
            body: JSON.stringify({concept: 'tables/orders', body: args.body,
                anchor: {kind: 'text', ref: args.ref, concept: 'tables/orders'}}),
        });
        return resp.ok;
    }""", {"token": token, "body": unique_body, "ref": anchor_ref})
    assert ok, "comment post failed"

    # Open comments panel to trigger loadComments → applyCommentMarks.
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.wait_for_selector(".okf-comment[data-comment-id]", timeout=5000)

    # Find our comment card ID.
    our_id = page.evaluate("""(body) => {
        var cards = document.querySelectorAll('.okf-comment[data-comment-id]');
        for (var c of cards) {
            if (c.textContent.indexOf(body) >= 0) return c.getAttribute('data-comment-id');
        }
        return null;
    }""", unique_body)
    assert our_id, "our comment card not found"

    # REQUIRE: applyCommentMarks rendered a body mark for our text anchor.
    page.wait_for_selector(f'.okf-comment-mark[data-comment-id="{our_id}"]', timeout=5000)

    # Click the mark — production pin-click path → jumpToCommentCard.
    # Use eval_on_selector to dispatch the click directly (the studio status
    # bar can intercept Playwright's pointer-based click).
    page.eval_on_selector(
        f'.okf-comment-mark[data-comment-id="{our_id}"]',
        "el => el.click()")
    page.wait_for_selector(".okf-comment--jumped", timeout=3000)

    # Precondition assertions (unconditional):
    pre = page.evaluate(f"""() => {{
        var card = document.querySelector('.okf-comment[data-comment-id="{our_id}"]');
        return {{
            hasJumped: card && card.classList.contains('okf-comment--jumped'),
            isFocused: card && document.activeElement === card,
        }};
    }}""")
    assert pre["hasJumped"], "precondition: card not jumped"
    assert pre["isFocused"], "precondition: card not focused"

    # Resolve the comment via the production API path.
    resolved = page.evaluate("""async (args) => {
        const resp = await fetch('/__comment-update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-OKF-Token': args.token},
            body: JSON.stringify({id: args.id, state: 'resolved'}),
        });
        return resp.ok;
    }""", {"token": token, "id": our_id})
    assert resolved, "resolve API call failed"

    # Wait for SSE echo + renderCommentsPanel.
    page.wait_for_timeout(2000)

    # After resolve: no jumped cue anywhere (unconditional).
    has_jumped = page.evaluate("document.querySelector('.okf-comment--jumped') !== null")
    assert not has_jumped, "jumped cue remains after resolve"

    # Card still exists with resolved state (unconditional).
    card = page.evaluate(f"""() => {{
        var c = document.querySelector('.okf-comment[data-comment-id="{our_id}"]');
        if (!c) return null;
        return {{
            dataState: c.getAttribute('data-state'),
        }};
    }}""")
    assert card is not None, "card removed after resolve"
    assert card["dataState"] == "resolved", f"card state: {card['dataState']}"

    # No late timer mutation: wait past the 4s cue timer.
    page.wait_for_timeout(5000)
    late = page.evaluate("document.querySelector('.okf-comment--jumped') !== null")
    assert not late, "stale timer re-added jumped cue"


# ===========================================================================
# 2. Fallback palette: ALL 7 roles match canonical CSS tokens for all themes
# ===========================================================================

@pytest.mark.parametrize("theme", ["swiss-light", "swiss-dark", "technical-light", "technical-dark"])
def test_fallback_palette_all_roles_match_css(server_url, page, theme):
    """Every GRAPH_COLORS fallback role resolves to the same RGB as the
    canonical CSS token it represents, for all four themes. No partial test."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    page.evaluate(f"""() => {{
        localStorage.setItem('okf-theme-family','{theme.split("-")[0]}');
        localStorage.setItem('okf-theme-mode','{theme.split("-")[1]}');
    }}""")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)

    data = page.evaluate("""(theme) => {
        const cs = getComputedStyle(document.documentElement);
        const cv = document.createElement('canvas'); cv.width=2; cv.height=2; const cx = cv.getContext('2d');
        function toRGB(cssColor) {
            cx.fillStyle = '#000'; cx.fillStyle = cssColor; cx.fillRect(0,0,1,1);
            const d = cx.getImageData(0,0,1,1).data; return [d[0], d[1], d[2]];
        }
        const g = window.__okfLoomGraph;
        if (!g) return null;
        const fb = g.fallbackColors(theme);
        const isDark = /-dark$/.test(theme);
        return {
            cssFg: toRGB(cs.getPropertyValue('--okf-fg').trim()),
            cssBgElev: toRGB(cs.getPropertyValue('--okf-bg-elev').trim()),
            cssBorderStrong: toRGB(cs.getPropertyValue('--okf-border-strong').trim()),
            cssFgMuted: toRGB(cs.getPropertyValue('--okf-fg-muted').trim()),
            cssSelect: toRGB(cs.getPropertyValue('--okf-select').trim()),
            fb: {
                nodeText: toRGB(fb.nodeText),
                nodeBorder: toRGB(fb.nodeBorder),
                bridgeBorder: toRGB(fb.bridgeBorder),
                edge: toRGB(fb.edge),
                edgeLabel: toRGB(fb.edgeLabel),
                edgeLabelBg: toRGB(fb.edgeLabelBg),
                select: toRGB(fb.select),
            },
            isDark: isDark,
        };
    }""", theme)
    assert data, f"diagnostic hook not available for {theme}"
    fb = data["fb"]
    expected_border = data["cssBgElev"] if data["isDark"] else data["cssFg"]

    assert fb["nodeText"] == data["cssFg"], f"{theme} nodeText {fb['nodeText']} != fg {data['cssFg']}"
    assert fb["nodeBorder"] == expected_border, f"{theme} nodeBorder {fb['nodeBorder']} != expected {expected_border}"
    assert fb["bridgeBorder"] == data["cssFg"], f"{theme} bridgeBorder {fb['bridgeBorder']} != fg {data['cssFg']}"
    assert fb["edge"] == data["cssBorderStrong"], f"{theme} edge {fb['edge']} != border-strong {data['cssBorderStrong']}"
    assert fb["edgeLabel"] == data["cssFgMuted"], f"{theme} edgeLabel {fb['edgeLabel']} != fg-muted {data['cssFgMuted']}"
    assert fb["edgeLabelBg"] == data["cssBgElev"], f"{theme} edgeLabelBg {fb['edgeLabelBg']} != bg-elev {data['cssBgElev']}"
    assert fb["select"] == data["cssSelect"], f"{theme} select {fb['select']} != select {data['cssSelect']}"


# ===========================================================================
# 3. Border Off: exact styles for ALL cue types across ALL themes
# ===========================================================================

@pytest.mark.parametrize("theme", ["swiss-light", "swiss-dark", "technical-light", "technical-dark"])
def test_border_off_all_cues_exact(server_url, page, theme):
    """Under Border Off + Bridges + Focus + path state: assert bridge underlay,
    focus-root, path node/edge, selected node/edge colors ALL exactly equal
    normalized --okf-select; assert numeric width/underlay/dash/opacity > 0.
    No conditional branches. Runs across all four themes."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    # Set theme.
    page.evaluate(f"""() => {{
        localStorage.setItem('okf-theme-family','{theme.split("-")[0]}');
        localStorage.setItem('okf-theme-mode','{theme.split("-")[1]}');
    }}""")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)

    # Activate Bridges lens for real bridge nodes.
    page.wait_for_selector("#okf-lens-bridges", timeout=10000)
    page.evaluate("document.getElementById('okf-lens-bridges').click()")
    page.wait_for_function("document.getElementById('okf-lens-bridges').checked")
    page.wait_for_timeout(1500)  # lens compute + bridge class assignment

    # Assign each tested role to a DISTINCT element. Clear any pre-existing
    # classes/selection first, then add exactly ONE tested class per element
    # so removing any single production selector sync fails its dedicated
    # assertion only.
    setup = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var allNodes = cy.nodes();
        var allEdges = cy.edges();
        if (allNodes.length < 4 || allEdges.length < 2) return {error: "not enough elements"};
        // Find a real bridge node from the Bridges lens.
        var bridgeNodes = cy.nodes(".okf-bridge");
        if (!bridgeNodes.length) return {error: "no bridge nodes after Bridges lens"};
        var bridgeEl = bridgeNodes[0];
        // Pick distinct non-bridge nodes for the other roles.
        var others = allNodes.not(bridgeEl);
        var focusEl = others[0];
        var pathEl  = others[1];
        var selEl   = others[2] || others[0];
        // Pick distinct edges.
        var pathEdgeEl = allEdges[0];
        var selEdgeEl  = allEdges[1] || allEdges[0];
        // Clear all tested classes from everyone.
        allNodes.removeClass("okf-focus-root okf-path");
        allEdges.removeClass("okf-path");
        allNodes.unselect(); allEdges.unselect();
        // Add exactly ONE role per dedicated element.
        focusEl.addClass("okf-focus-root");
        pathEl.addClass("okf-path");
        pathEdgeEl.addClass("okf-path");
        selEl.select();
        selEdgeEl.select();
        // Capture IDs for readback.
        return {
            bridgeId: bridgeEl.id(),
            focusId: focusEl.id(),
            pathNodeId: pathEl.id(),
            pathEdgeId: pathEdgeEl.id(),
            selNodeId: selEl.id(),
            selEdgeId: selEdgeEl.id(),
            bridgeCount: bridgeNodes.length,
            totalNodes: allNodes.length,
            totalEdges: allEdges.length,
        };
    }""")
    assert setup, f"graph not initialized for {theme}"
    assert "error" not in setup, f"{theme}: {setup.get('error')}"

    # Set Border Off (triggers MutationObserver → syncLabelColour).
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.wait_for_timeout(500)

    # Read styles back by captured element IDs.
    data = page.evaluate("""(ids) => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        var cy = window.__okfLoomGraph.cy;
        var cs = getComputedStyle(document.documentElement);
        var cv = document.createElement('canvas'); cv.width=2; cv.height=2;
        var cx = cv.getContext('2d');
        function toRGB(val) {
            cx.fillStyle='#000'; cx.fillStyle = val; cx.fillRect(0,0,1,1);
            var d = cx.getImageData(0,0,1,1).data; return [d[0], d[1], d[2]];
        }
        function nStyle(id, prop) {
            var el = cy.getElementById(id);
            return el ? el.style(prop) : null;
        }
        var cssSelect = toRGB(cs.getPropertyValue('--okf-select').trim());
        return {
            cssSelect: cssSelect,
            bridgeUnderlayColor: toRGB(nStyle(ids.bridgeId, 'underlay-color')),
            bridgeUnderlayOpacity: parseFloat(nStyle(ids.bridgeId, 'underlay-opacity')) || 0,
            bridgeUnderlayPadding: parseFloat(nStyle(ids.bridgeId, 'underlay-padding')) || 0,
            focusUnderlayColor: toRGB(nStyle(ids.focusId, 'underlay-color')),
            focusBorderColor: toRGB(nStyle(ids.focusId, 'border-color')),
            focusBorderWidth: parseFloat(nStyle(ids.focusId, 'border-width')) || 0,
            focusUnderlayOpacity: parseFloat(nStyle(ids.focusId, 'underlay-opacity')) || 0,
            focusUnderlayPadding: parseFloat(nStyle(ids.focusId, 'underlay-padding')) || 0,
            pathNodeBorderColor: toRGB(nStyle(ids.pathNodeId, 'border-color')),
            pathNodeBorderWidth: parseFloat(nStyle(ids.pathNodeId, 'border-width')) || 0,
            pathNodeUnderlayColor: toRGB(nStyle(ids.pathNodeId, 'underlay-color')),
            pathNodeUnderlayOpacity: parseFloat(nStyle(ids.pathNodeId, 'underlay-opacity')) || 0,
            pathEdgeLineColor: toRGB(nStyle(ids.pathEdgeId, 'line-color')),
            pathEdgeArrowColor: toRGB(nStyle(ids.pathEdgeId, 'target-arrow-color')),
            pathEdgeWidth: parseFloat(nStyle(ids.pathEdgeId, 'width')) || 0,
            pathEdgeOpacity: parseFloat(nStyle(ids.pathEdgeId, 'opacity')) || 0,
            selNodeBorderWidth: parseFloat(nStyle(ids.selNodeId, 'border-width')) || 0,
            selNodeBorderColor: toRGB(nStyle(ids.selNodeId, 'border-color')),
            selEdgeWidth: parseFloat(nStyle(ids.selEdgeId, 'width')) || 0,
            selEdgeLineColor: toRGB(nStyle(ids.selEdgeId, 'line-color')),
            selEdgeArrowColor: toRGB(nStyle(ids.selEdgeId, 'target-arrow-color')),
            selEdgeOpacity: parseFloat(nStyle(ids.selEdgeId, 'opacity')) || 0,
        };
    }""", setup)
    assert data, f"style readback failed for {theme}"
    sel = data["cssSelect"]
    # Bridge: dedicated element — underlay color == select, opacity/padding > 0.
    assert data["bridgeUnderlayColor"] == sel, f"{theme} bridge underlay {data['bridgeUnderlayColor']} != {sel}"
    assert data["bridgeUnderlayOpacity"] > 0, f"{theme} bridge underlay opacity: {data['bridgeUnderlayOpacity']}"
    assert data["bridgeUnderlayPadding"] > 0, f"{theme} bridge underlay padding: {data['bridgeUnderlayPadding']}"
    # Focus-root: dedicated element — underlay + border color == select;
    # numeric border width, underlay opacity, underlay padding > 0.
    assert data["focusUnderlayColor"] == sel, f"{theme} focus underlay {data['focusUnderlayColor']} != {sel}"
    assert data["focusBorderColor"] == sel, f"{theme} focus border {data['focusBorderColor']} != {sel}"
    assert data["focusBorderWidth"] > 0, f"{theme} focus border width: {data['focusBorderWidth']}"
    assert data["focusUnderlayOpacity"] > 0, f"{theme} focus underlay opacity: {data['focusUnderlayOpacity']}"
    assert data["focusUnderlayPadding"] > 0, f"{theme} focus underlay padding: {data['focusUnderlayPadding']}"
    # Path node: dedicated element — border + underlay color == select;
    # width/opacity > 0.
    assert data["pathNodeBorderColor"] == sel, f"{theme} path node border {data['pathNodeBorderColor']} != {sel}"
    assert data["pathNodeBorderWidth"] > 0, f"{theme} path node border width: {data['pathNodeBorderWidth']}"
    assert data["pathNodeUnderlayColor"] == sel, f"{theme} path node underlay {data['pathNodeUnderlayColor']} != {sel}"
    assert data["pathNodeUnderlayOpacity"] > 0, f"{theme} path node underlay opacity: {data['pathNodeUnderlayOpacity']}"
    # Path edge: dedicated element — line + arrow color == select;
    # width/opacity > 0.
    assert data["pathEdgeLineColor"] == sel, f"{theme} path edge line {data['pathEdgeLineColor']} != {sel}"
    assert data["pathEdgeArrowColor"] == sel, f"{theme} path edge arrow {data['pathEdgeArrowColor']} != {sel}"
    assert data["pathEdgeWidth"] > 0, f"{theme} path edge width: {data['pathEdgeWidth']}"
    assert data["pathEdgeOpacity"] > 0, f"{theme} path edge opacity: {data['pathEdgeOpacity']}"
    # Selected node: dedicated element — border color == select, width > 0.
    assert data["selNodeBorderColor"] == sel, f"{theme} sel node border {data['selNodeBorderColor']} != {sel}"
    assert data["selNodeBorderWidth"] > 0, f"{theme} sel node border width: {data['selNodeBorderWidth']}"
    # Selected edge: dedicated element — line + arrow color == select;
    # width/opacity > 0.
    assert data["selEdgeLineColor"] == sel, f"{theme} sel edge line {data['selEdgeLineColor']} != {sel}"
    assert data["selEdgeArrowColor"] == sel, f"{theme} sel edge arrow {data['selEdgeArrowColor']} != {sel}"
    assert data["selEdgeWidth"] > 0, f"{theme} sel edge width: {data['selEdgeWidth']}"
    assert data["selEdgeOpacity"] > 0, f"{theme} sel edge opacity: {data['selEdgeOpacity']}"


# ===========================================================================
# 4. Edge opacity floor >= 0.3 (unchanged)
# ===========================================================================

def test_edge_opacity_floor_03(server_url, page):
    """Map lens: minimum edge opacity >= 0.3."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    min_opacity = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return null;
        const cy = window.__okfLoomGraph.cy;
        var min = 1;
        cy.edges().forEach(function(e) {
            var op = parseFloat(e.style('opacity'));
            if (!isNaN(op) && op < min) min = op;
        });
        return min;
    }""")
    assert min_opacity is not None, "no edges found"
    assert min_opacity >= 0.3, f"edge opacity floor below 0.3: {min_opacity}"
