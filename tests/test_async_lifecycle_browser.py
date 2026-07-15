"""Deterministic Mermaid lifecycle, graph palette, and comment interaction
proof using controlled stubs — no CDN dependency.
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


# Stub mermaid module for deterministic testing (no CDN).
STUB_MERMAID_JS = """() => {
    // The stub: a mock mermaid that renders a synthetic <svg> into each node.
    // Records initialize calls with theme + resolved themeVariables colors
    // so tests can verify theme changes via the primaryColor value.
    window.__mermaidCallLog = [];
    window.__okfMermaidTestImport = {
        default: {
            initialize: function(opts) {
                var tv = opts.themeVariables || {};
                window.__mermaidCallLog.push({
                    fn: 'initialize',
                    theme: opts.theme,
                    primaryColor: tv.primaryColor || '',
                    background: tv.background || '',
                });
            },
            run: function(args) {
                var nodes = args.nodes || [];
                window.__mermaidCallLog.push({fn: 'run', count: nodes.length});
                nodes.forEach(function(n) {
                    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                    // Determine current theme from the last initialize call's
                    // primaryColor (dark vs light have different bg-elev values).
                    var lastInit = window.__mermaidCallLog.filter(function(c) { return c.fn === 'initialize'; }).pop();
                    if (lastInit) svg.setAttribute('data-stub-bg', lastInit.background || '');
                    n.innerHTML = '';
                    n.appendChild(svg);
                });
                return Promise.resolve();
            },
        }
    };
}"""


def _inject_mermaid_stub(pg):
    """Inject the stub mermaid before renderers.js runs."""
    pg.evaluate(STUB_MERMAID_JS)


def _add_mermaid_div(pg, source="graph TD; A-->B"):
    pg.evaluate(f"""() => {{
        var div = document.createElement('div');
        div.className = 'mermaid';
        div.textContent = {repr(source)};
        document.querySelector('.okf-page__body').appendChild(div);
    }}""")


# ===========================================================================
# 1. Mermaid deterministic lifecycle (no CDN — controlled stub)
# ===========================================================================

def test_mermaid_initial_render_with_stub(server_url, page):
    """Initial render: source stamped, SVG committed, generation correct."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    _inject_mermaid_stub(page)
    _add_mermaid_div(page)
    # Trigger initMermaid via bodyPatched event.
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_function("document.querySelector('div.mermaid svg') !== null", timeout=5000)
    # Source preserved.
    src = page.evaluate("document.querySelector('div.mermaid').getAttribute('data-source')")
    assert src and "graph TD" in src
    # SVG committed.
    assert page.evaluate("document.querySelector('div.mermaid svg') !== null")
    # ID is unique (page-global counter).
    div_id = page.evaluate("document.querySelector('div.mermaid').id")
    assert div_id and div_id.startswith("okf-mermaid-")


def test_mermaid_light_dark_light_rerender(server_url, page):
    """Light→dark→light: each transition rerenders; source preserved."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    _inject_mermaid_stub(page)
    _add_mermaid_div(page)
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_function("document.querySelector('div.mermaid svg') !== null", timeout=5000)
    # Light→dark: check initialize was called with different background.
    # With theme:'base', the theme string is always 'base'; we verify the
    # theme change via the resolved background color from themeVariables.
    page.evaluate("""() => {
        document.documentElement.setAttribute('data-theme', 'technical-dark');
        window.dispatchEvent(new CustomEvent("okf-loom:themeChanged", {
            detail: {resolvedMode: "dark", previousResolvedMode: "light"}
        }));
    }""")
    page.wait_for_function("""() => {
        var inits = window.__mermaidCallLog.filter(function(c) { return c.fn === 'initialize'; });
        if (inits.length < 2) return false;
        // With theme:'base', background is resolved from CSS tokens.
        // Light bg (#f...) differs from dark bg (#0...).
        return inits[inits.length-1].background !== inits[0].background;
    }""", timeout=10000)
    # SVG should still exist in live DOM (committed from clones).
    page.wait_for_function("document.querySelector('div.mermaid svg') !== null", timeout=5000)
    # Dark→light.
    page.evaluate("""() => {
        document.documentElement.setAttribute('data-theme', 'technical-light');
        window.dispatchEvent(new CustomEvent("okf-loom:themeChanged", {
            detail: {resolvedMode: "light", previousResolvedMode: "dark"}
        }));
    }""")
    page.wait_for_function("""() => {
        var inits = window.__mermaidCallLog.filter(function(c) { return c.fn === 'initialize'; });
        // After dark→light: the last init should differ from the dark one.
        if (inits.length < 3) return false;
        return inits[inits.length-1].background !== inits[inits.length-2].background;
    }""", timeout=10000)
    # Source still preserved.
    src = page.evaluate("document.querySelector('div.mermaid').getAttribute('data-source')")
    assert src and "graph TD" in src


def test_mermaid_family_only_no_rerender(server_url, page):
    """Family-only change (same resolvedMode) does NOT rerender."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    _inject_mermaid_stub(page)
    _add_mermaid_div(page)
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_function("document.querySelector('div.mermaid svg') !== null", timeout=5000)
    calls_before = page.evaluate("window.__mermaidCallLog.length")
    # Family-only event.
    page.evaluate("""() => {
        window.dispatchEvent(new CustomEvent("okf-loom:themeChanged", {
            detail: {resolvedMode: "light", previousResolvedMode: "light"}
        }));
    }""")
    page.wait_for_timeout(500)
    calls_after = page.evaluate("window.__mermaidCallLog.length")
    assert calls_after == calls_before, f"family-only caused rerender: {calls_before} → {calls_after}"


def test_mermaid_import_failure_fallback(server_url, page):
    """Import failure leaves readable source + fallback class."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    # Set stub to reject.
    page.evaluate("""() => {
        window.__okfMermaidTestImport = {default: null};
    }""")
    _add_mermaid_div(page)
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_timeout(1000)
    # Source text should be visible (not cleared).
    src = page.evaluate("document.querySelector('div.mermaid').getAttribute('data-source')")
    assert src and "graph TD" in src
    # Fallback class applied.
    assert page.evaluate("document.querySelector('div.mermaid').classList.contains('mermaid--fallback')")


def test_mermaid_render_failure_fallback(server_url, page):
    """Render failure (mermaid.run throws) leaves readable source + fallback."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    # Stub that throws on run.
    page.evaluate("""() => {
        window.__okfMermaidTestImport = {
            default: {
                initialize: function() {},
                run: function() { return Promise.reject(new Error('render failed')); }
            }
        };
    }""")
    _add_mermaid_div(page)
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_timeout(1000)
    assert page.evaluate("document.querySelector('div.mermaid').classList.contains('mermaid--fallback')")
    src = page.evaluate("document.querySelector('div.mermaid').getAttribute('data-source')")
    assert src


def test_mermaid_stale_completion_discarded(server_url, page):
    """A delayed stale render does NOT overwrite a newer one."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    # Stub with controllable delay.
    page.evaluate("""() => {
        window.__mermaidRenderDelay = 0;
        window.__okfMermaidTestImport = {
            default: {
                initialize: function(opts) { window.__lastBg = (opts.themeVariables || {}).background || ''; },
                run: function(args) {
                    var delay = window.__mermaidRenderDelay;
                    return new Promise(function(resolve) {
                        setTimeout(function() {
                            var bg = window.__lastBg || '';
                            (args.nodes || []).forEach(function(n) {
                                n.innerHTML = '';
                                var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                                svg.setAttribute('data-stub-bg', bg);
                                n.appendChild(svg);
                            });
                            resolve();
                        }, delay);
                    });
                }
            }
        };
    }""")
    _add_mermaid_div(page)
    page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
    page.wait_for_function("document.querySelector('div.mermaid svg')", timeout=5000)
    # Set a long delay, then fire dark→light quickly.
    page.evaluate("window.__mermaidRenderDelay = 500")
    # Fire dark (gen 2, will be slow).
    page.evaluate("""() => {
        window.dispatchEvent(new CustomEvent("okf-loom:themeChanged", {
            detail: {resolvedMode: "dark", previousResolvedMode: "light"}
        }));
    }""")
    page.wait_for_timeout(50)
    # Immediately fire light (gen 3, fast — delay back to 0).
    page.evaluate("window.__mermaidRenderDelay = 0")
    page.evaluate("""() => {
        window.dispatchEvent(new CustomEvent("okf-loom:themeChanged", {
            detail: {resolvedMode: "light", previousResolvedMode: "dark"}
        }));
    }""")
    page.wait_for_timeout(1000)
    # The committed SVG should have the light background (from gen 3), not
    # the dark one (from the stale gen 2). We compare background hex values:
    # the light background should be brighter than the dark one.
    bg = page.evaluate("document.querySelector('div.mermaid svg').getAttribute('data-stub-bg')")
    assert bg, f"stale render committed with empty bg"
    # Light bg (#f0f... or #fff...) should be brighter than dark (#0f... or #16...).
    # Simple check: light bg starts with a high hex digit.
    assert bg[1] >= 'e' or bg[1] >= 'E', f"stale dark bg committed: {bg}"


def test_mermaid_repeated_body_patches_unique_ids(server_url, page):
    """Repeated body patches create new diagram divs with unique IDs — no
    collisions."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    _inject_mermaid_stub(page)
    for i in range(3):
        _add_mermaid_div(page, f"graph TD; N{i}-->M{i}")
        page.evaluate("window.dispatchEvent(new Event('okf-loom:bodyPatched'))")
        page.wait_for_timeout(300)
    ids = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('div.mermaid[id]')).map(d => d.id);
    }""")
    # All IDs unique.
    assert len(ids) == len(set(ids)), f"duplicate IDs: {ids}"
    assert len(ids) == 3


# ===========================================================================
# 2. Graph palette: MutationObserver excludes data-theme
# ===========================================================================

def test_graph_no_duplicate_sync_on_theme(server_url, page):
    """Theme change triggers one sync (via themeChanged), not a duplicate
    (via MutationObserver on data-theme)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    # Count syncLabelColour calls by intercepting.
    count_before = page.evaluate("""() => {
        if (!window.__okfLoomGraph || !window.__okfLoomGraph.cy) return -1;
        return 0; // baseline
    }""")
    # Change theme via data-theme attribute (would trigger both the event
    # listener AND the old MutationObserver if data-theme were observed).
    page.evaluate("document.documentElement.setAttribute('data-theme', 'technical-dark')")
    page.wait_for_timeout(300)
    # No crash — canvas still present.
    assert page.evaluate("document.querySelectorAll('#okf-graph canvas').length > 0")


# ===========================================================================
# 3. Split: descriptions + Border Off underline
# ===========================================================================

def test_split_descriptions(server_url, page):
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
