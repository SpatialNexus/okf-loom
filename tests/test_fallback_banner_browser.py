"""Fallback banner visibility: no-JS, JS failure, studio success, static.
Verifies exactly one banner visible per state across all template surfaces.
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
    out = tmp_path_factory.mktemp("fb-static") / "site"
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
    """Page context with JavaScript disabled."""
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


def _count_visible_banners(page):
    return page.evaluate("""() => {
        var banners = document.querySelectorAll('.okf-studio-fallback-banner');
        var visible = 0;
        banners.forEach(function(b) {
            if (getComputedStyle(b).display !== 'none') visible++;
        });
        return visible;
    }""")


# ===========================================================================
# No-JS: only the <noscript> banner visible
# ===========================================================================

def test_nojs_concept_one_banner(nojs_page, server_url):
    """With JS off, exactly one fallback banner visible (the noscript one)."""
    nojs_page.goto(f"{server_url}/tables/orders", wait_until="load")
    nojs_page.wait_for_timeout(500)
    count = _count_visible_banners(nojs_page)
    assert count == 1, f"no-JS concept: {count} banners (expected 1)"


def test_nojs_graph_one_banner(nojs_page, server_url):
    nojs_page.goto(f"{server_url}/__graph", wait_until="load")
    nojs_page.wait_for_timeout(500)
    count = _count_visible_banners(nojs_page)
    assert count == 1, f"no-JS graph: {count} banners (expected 1)"


def test_nojs_index_one_banner(nojs_page, server_url):
    nojs_page.goto(f"{server_url}/", wait_until="load")
    nojs_page.wait_for_timeout(500)
    count = _count_visible_banners(nojs_page)
    assert count == 1, f"no-JS index: {count} banners (expected 1)"


# ===========================================================================
# JS on, studio booted: zero banners
# ===========================================================================

def test_js_studio_booted_zero_banners(server_url, page):
    """With JS on and studio booted, zero banners visible."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_timeout(500)
    count = _count_visible_banners(page)
    assert count == 0, f"JS booted: {count} banners (expected 0)"


def test_js_studio_booted_graph_zero_banners(server_url, page):
    page.goto(f"{server_url}/__graph", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_timeout(500)
    count = _count_visible_banners(page)
    assert count == 0, f"JS booted graph: {count} banners (expected 0)"


# ===========================================================================
# JS on, studio failure: exactly one --js banner
# ===========================================================================

def test_js_studio_failure_one_banner(server_url, page):
    """With JS on but studio.js blocked, exactly one --js banner visible."""
    # Block studio.js via route interception.
    def block_studio(route):
        if "studio.js" in route.request.url:
            route.abort()
        else:
            route.continue_()
    page.route("**/*", block_studio)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_timeout(2000)  # allow theme.js to run + add okf-js-enabled
    count = _count_visible_banners(page)
    assert count == 1, f"JS failure: {count} banners (expected 1)"
    # Verify it's the --js variant, not the noscript.
    is_js = page.evaluate("""() => {
        var banners = document.querySelectorAll('.okf-studio-fallback-banner');
        var vis = [];
        banners.forEach(function(b) {
            if (getComputedStyle(b).display !== 'none') vis.push(b);
        });
        return vis.length > 0 && vis[0].classList.contains('okf-studio-fallback-banner--js');
    }""")
    assert is_js, "visible banner is not the --js variant"


# ===========================================================================
# Static: zero banners
# ===========================================================================

def test_static_concept_zero_banners(static_site_url, page):
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    page.wait_for_timeout(500)
    count = _count_visible_banners(page)
    assert count == 0, f"static: {count} banners (expected 0)"


def test_static_graph_zero_banners(static_site_url, page):
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    page.wait_for_timeout(500)
    count = _count_visible_banners(page)
    assert count == 0, f"static graph: {count} banners (expected 0)"
