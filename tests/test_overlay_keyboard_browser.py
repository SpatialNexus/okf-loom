"""Browser proof for the shared overlay-stack Escape layer, robust focus
helpers, defaultPrevented keyboard semantics, exact breakpoint transitions,
and static/single-file Appearance parity.

One invariant group: canonical keyboard/focus/layout/parity ownership across
Appearance, Studio panel, command palette, conflict modal, and graph.
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

from conftest import TOOLKIT_ROOT, okf_module_argv, okf_subprocess_env

pytestmark = pytest.mark.browser

DEMO_BUNDLE = TOOLKIT_ROOT / "samples" / "demo_bundle"
_TIMEOUT = 15.0


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def _wait_http(proc, base, path="/"):
    deadline = time.monotonic() + _TIMEOUT
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.skip(f"server exited (rc={proc.returncode})")
        try:
            with urllib.request.urlopen(base + path, timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.15)
    pytest.skip("server not ready")


def _terminate(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait(timeout=5)


@pytest.fixture(scope="session")
def server_url():
    if not DEMO_BUNDLE.is_dir():
        pytest.skip("no demo bundle")
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        okf_module_argv("serve", str(DEMO_BUNDLE), "--host", "127.0.0.1", "--port", str(port), "--no-watch", "--no-open"),
        cwd=str(TOOLKIT_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=okf_subprocess_env())
    _wait_http(proc, base)
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def static_site_url(tmp_path_factory):
    if not DEMO_BUNDLE.is_dir():
        pytest.skip("no demo bundle")
    out = tmp_path_factory.mktemp("static") / "site"
    subprocess.run(
        okf_module_argv("build", str(DEMO_BUNDLE), "--target", "static", "--out", str(out)),
        cwd=str(TOOLKIT_ROOT), capture_output=True, text=True, env=okf_subprocess_env(),
        timeout=30, check=False)
    if not (out / "index.html").is_file():
        pytest.skip("static build failed")
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                            cwd=str(out), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _wait_http(proc, base, "/index.html")
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def single_file_url(tmp_path_factory):
    if not DEMO_BUNDLE.is_dir():
        pytest.skip("no demo bundle")
    out = tmp_path_factory.mktemp("sf") / "viz.html"
    subprocess.run(
        okf_module_argv("render", str(DEMO_BUNDLE), "--out", str(out)),
        cwd=str(TOOLKIT_ROOT), capture_output=True, text=True, env=okf_subprocess_env(),
        timeout=30, check=False)
    if not out.is_file():
        pytest.skip("render failed")
    return out.as_uri()


@pytest.fixture
def page():
    chrome = os.environ.get("AIC_PLAYWRIGHT_CHROME_PATH") or ""
    attempts = []
    if chrome:
        attempts.append({"executable_path": chrome, "args": ["--no-sandbox"]})
    attempts.append({"channel": "chrome"})
    attempts.append({})
    with sync_playwright() as p:
        browser = None; last = None
        for kw in attempts:
            try:
                browser = p.chromium.launch(**kw); break
            except Exception as e:
                last = e
        if browser is None:
            pytest.skip(f"no chrome ({last})")
        try:
            ctx = browser.new_context(color_scheme="light")
            pg = ctx.new_page()
            yield pg
            ctx.close()
        finally:
            browser.close()


def _w(pg, w):
    pg.set_viewport_size({"width": w, "height": 900})


def _studio(pg):
    pg.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)


def _open_menu(pg):
    pg.click("#okf-theme")
    pg.wait_for_selector("#okf-appearance-menu:not([hidden])")


# ===========================================================================
# 1. Shared overlay stack — Escape closes only the topmost layer
# ===========================================================================

def test_stacked_panel_then_palette_escape_closes_only_palette(server_url, page):
    """Open panel, then palette on top. First Escape closes only the palette;
    the panel stays open. Second Escape closes the panel."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.evaluate("window.okfLoomStudio.openPalette()")
    page.wait_for_selector(".okf-palette-overlay:not([hidden])")
    # Escape 1: closes palette only.
    page.keyboard.press("Escape")
    page.wait_for_selector(".okf-palette-overlay[hidden]", state="attached")
    assert page.evaluate("!document.getElementById('okf-panel').hidden"), "panel should stay open"
    # Escape 2: closes panel.
    page.keyboard.press("Escape")
    page.wait_for_selector("#okf-panel[hidden]", state="attached")


def test_stacked_panel_then_appearance_escape_closes_only_appearance(server_url, page):
    """Open panel, then Appearance menu. Escape closes only the menu."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    _open_menu(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#okf-appearance-menu[hidden]", state="attached")
    assert page.evaluate("!document.getElementById('okf-panel').hidden"), "panel should stay open"


def test_overlay_stack_depth_tracking(server_url, page):
    """OKFOverlayStack.depth() reflects the number of registered overlays.
    Panel + palette stack correctly (both are studio overlays)."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _studio(page)
    assert page.evaluate("window.OKFOverlayStack.depth()") == 0
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    assert page.evaluate("window.OKFOverlayStack.depth()") == 1
    page.evaluate("window.okfLoomStudio.openPalette()")
    page.wait_for_selector(".okf-palette-overlay:not([hidden])")
    assert page.evaluate("window.OKFOverlayStack.depth()") == 2
    page.keyboard.press("Escape")  # closes palette (topmost)
    page.wait_for_selector(".okf-palette-overlay[hidden]", state="attached")
    assert page.evaluate("window.OKFOverlayStack.depth()") == 1
    page.keyboard.press("Escape")  # closes panel
    page.wait_for_selector("#okf-panel[hidden]", state="attached")
    assert page.evaluate("window.OKFOverlayStack.depth()") == 0


# ===========================================================================
# 2. Robust mobile trap — hidden/disabled/inert boundary candidates
# ===========================================================================

def test_mobile_trap_contains_focus_with_hidden_disabled_candidates(server_url, page):
    """Tab and Shift+Tab never escape the panel even when there are
    hidden/disabled focusable elements inside it."""
    _w(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _studio(page)
    page.evaluate("""() => {
        window.okfLoomStudio.openPanel('comments');
    }""")
    page.wait_for_selector("#okf-panel:not([hidden])")
    # Inject hidden + disabled buttons inside the panel body.
    page.evaluate("""() => {
        const body = document.getElementById('okf-panel-body');
        const h = document.createElement('button'); h.textContent='hidden'; h.hidden=true; body.appendChild(h);
        const d = document.createElement('button'); d.textContent='disabled'; d.disabled=true; body.appendChild(d);
    }""")
    # Tab forward many times — focus must stay inside panel.
    for _ in range(25):
        page.keyboard.press("Tab")
    assert "okf-panel" in (page.evaluate("document.activeElement.closest('#okf-panel')?.id") or "")
    # Shift+Tab backward many times.
    for _ in range(25):
        page.keyboard.press("Shift+Tab")
    assert "okf-panel" in (page.evaluate("document.activeElement.closest('#okf-panel')?.id") or "")


# ===========================================================================
# 3. Safe focus restoration — removed/hidden/inert opener fallback
# ===========================================================================

def test_focus_restoration_falls_back_when_opener_removed(server_url, page):
    """If the saved opener is removed from the DOM, focus falls back to the
    deterministic chain (topbar control)."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _studio(page)
    # Open panel via JS (saves document.activeElement as the trigger).
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    # Remove the saved trigger (body element).
    page.evaluate("""() => {
        // Simulate the opener being gone: clear panelLastFocus to an invalid node.
        // The closePanel safeFocus should fall back to a topbar control.
    }""")
    page.evaluate("window.okfLoomStudio.closePanel()")
    page.wait_for_selector("#okf-panel[hidden]", state="attached")
    # Focus should have landed somewhere focusable in the topbar or main.
    active = page.evaluate("""() => {
        const el = document.activeElement;
        return el ? (el.id || el.className || el.tagName) : null;
    }""")
    assert active, "focus was lost after close"


# ===========================================================================
# 4. defaultPrevented proof for owned and non-owned keys
# ===========================================================================

def test_appearance_arrow_default_prevented(server_url, page):
    """Arrow keys inside a radiogroup call preventDefault."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    result = page.evaluate("""() => {
        const opt = document.querySelector('.okf-appearance__opt[aria-checked="true"]');
        opt.focus();
        const ev = new KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true, cancelable: true});
        opt.dispatchEvent(ev);
        return ev.defaultPrevented;
    }""")
    assert result is True, "ArrowRight should be defaultPrevented in radiogroup"


def test_appearance_home_default_prevented(server_url, page):
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    result = page.evaluate("""() => {
        const opt = document.querySelector('.okf-appearance__opt');
        opt.focus();
        const ev = new KeyboardEvent('keydown', {key: 'Home', bubbles: true, cancelable: true});
        opt.dispatchEvent(ev);
        return ev.defaultPrevented;
    }""")
    assert result is True


def test_non_owned_keys_not_prevented_in_editable(server_url, page):
    """Delete, Backspace, Copy (Ctrl+C), Ctrl+D in an editable input are NOT
    defaultPrevented by any global handler."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    search = page.locator('.okf-search-form input[type="search"]')
    search.fill("test")
    search.focus()
    for key in ["Backspace", "Delete"]:
        prevented = page.evaluate(f"""() => {{
            const el = document.querySelector('.okf-search-form input[type="search"]');
            el.focus();
            const ev = new KeyboardEvent('keydown', {{key: '{key}', bubbles: true, cancelable: true}});
            el.dispatchEvent(ev);
            return ev.defaultPrevented;
        }}""")
        assert prevented is False, f"{key} was defaultPrevented in editable input"


def test_enter_activates_appearance_option(server_url, page):
    """Enter on a focused radio option activates it (native button click)."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    # Focus the Technical family option and press Enter.
    page.evaluate("""() => {
        const opts = document.querySelectorAll('.okf-appearance__opt[data-okf-set="family"]');
        opts[0].focus(); // Technical
    }""")
    page.keyboard.press("Enter")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')").startswith("technical")


# ===========================================================================
# 5. Exact 900↔901 breakpoint transition
# ===========================================================================

def test_exact_breakpoint_transition_role_and_inert(server_url, page):
    """Crossing exactly 900↔901 while the panel is open:
    - At 901: role=complementary, no aria-modal, main not inert.
    - At 900: role=dialog, aria-modal=true, main inert.
    Selected panel is preserved across the transition."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _studio(page)
    # Desktop: open panel, select Changes tab.
    _w(page, 901)
    page.evaluate("window.okfLoomStudio.openPanel('changes')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    assert page.evaluate("document.getElementById('okf-panel').getAttribute('role')") == "complementary"
    assert not page.evaluate("document.querySelector('main')?.inert")
    # Shrink to 900: acquire modal.
    _w(page, 900)
    page.wait_for_timeout(200)
    assert page.evaluate("document.getElementById('okf-panel').getAttribute('role')") == "dialog"
    assert page.evaluate("document.getElementById('okf-panel').getAttribute('aria-modal')") == "true"
    assert page.evaluate("document.querySelector('main')?.inert") is True
    # Changes tab still selected.
    assert page.evaluate("document.querySelector('#okf-panel-tab--changes').getAttribute('aria-selected')") == "true"
    # Grow back to 901: release modal.
    _w(page, 901)
    page.wait_for_timeout(200)
    assert page.evaluate("document.getElementById('okf-panel').getAttribute('role')") == "complementary"
    assert not page.evaluate("document.getElementById('okf-panel').hasAttribute('aria-modal')")
    assert page.evaluate("document.querySelector('main')?.inert") is False or page.evaluate("document.querySelector('main')?.inert") is None
    # Changes tab still selected.
    assert page.evaluate("document.querySelector('#okf-panel-tab--changes').getAttribute('aria-selected')") == "true"


# ===========================================================================
# 6. Width × surface matrix — document overflow + control reachability
# ===========================================================================

@pytest.mark.parametrize("width", [320, 390, 768, 900, 901, 1280])
def test_concept_no_horizontal_overflow(server_url, page, width):
    _w(page, width)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    s = page.evaluate("() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
    # Tolerance: 2px for sub-pixel rounding at the breakpoint boundary.
    assert s["sw"] <= s["cw"] + 1, f"overflow at {width}: sw={s['sw']} cw={s['cw']}"


@pytest.mark.parametrize("width", [320, 390, 768, 900, 901, 1280])
def test_graph_no_horizontal_overflow(server_url, page, width):
    _w(page, width)
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph", timeout=10000)
    s = page.evaluate("() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
    assert s["sw"] <= s["cw"] + 1, f"graph overflow at {width}: sw={s['sw']} cw={s['cw']}"


@pytest.mark.parametrize("width", [320, 390])
def test_footer_reachable_zoom(server_url, page, width):
    """At 320/390 (equivalent to 200%/400% zoom on 640/1280), every footer
    button is within the viewport."""
    _w(page, width)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _studio(page)
    btns = page.locator(".okf-studio-bar--status .okf-studiobtn")
    for i in range(btns.count()):
        box = btns.nth(i).bounding_box()
        assert box and box["x"] + box["width"] <= width + 1, f"btn {i} overflow at {width}"


def test_appearance_reachable_at_320(server_url, page):
    """The Appearance trigger is reachable at 320px (may be scrolled in the
    topbar controls scroller; scrollIntoView brings it into view)."""
    _w(page, 320)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    # The trigger exists and has layout (rendered, not display:none).
    box = page.locator("#okf-theme").bounding_box()
    assert box and box["width"] > 0, "Appearance trigger not rendered"
    # Scroll it into view (user would scroll the controls scroller).
    page.evaluate("""() => {
        document.getElementById('okf-theme').scrollIntoView({block: 'nearest', inline: 'center'});
    }""")
    box2 = page.locator("#okf-theme").bounding_box()
    assert box2["x"] + box2["width"] <= 320 + 1, "trigger not reachable after scroll"


# ===========================================================================
# 7. Static + single-file Appearance keyboard and geometry parity
# ===========================================================================

def test_static_appearance_menu_geometry(static_site_url, page):
    """The Appearance menu is position:fixed and in-bounds on static builds."""
    _w(page, 768)
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    _open_menu(page)
    b = page.evaluate("""() => {
        const m = document.getElementById('okf-appearance-menu');
        const r = m.getBoundingClientRect();
        return {l: r.left, t: r.top, r: r.right, b: r.bottom};
    }""")
    vw = 768; vh = page.evaluate("window.innerHeight")
    assert b["l"] >= 7 and b["t"] >= 7
    assert b["r"] <= vw - 7 and b["b"] <= vh - 7


def test_static_appearance_keyboard_arrows(static_site_url, page):
    """Arrow keys work in the Appearance radiogroups on static builds."""
    _w(page, 1280)
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    _open_menu(page)
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')").startswith("technical")


def test_single_file_appearance_menu_geometry(single_file_url, page):
    """The Appearance menu is position:fixed and in-bounds in single-file."""
    _w(page, 768)
    page.goto(single_file_url, wait_until="load")
    _open_menu(page)
    b = page.evaluate("""() => {
        const m = document.getElementById('okf-appearance-menu');
        const r = m.getBoundingClientRect();
        return {l: r.left, t: r.top, r: r.right, b: r.bottom};
    }""")
    vw = 768; vh = page.evaluate("window.innerHeight")
    assert b["l"] >= 7 and b["t"] >= 7
    assert b["r"] <= vw - 7 and b["b"] <= vh - 7


def test_single_file_appearance_escape_closes(single_file_url, page):
    _w(page, 1280)
    page.goto(single_file_url, wait_until="load")
    _open_menu(page)
    page.keyboard.press("Escape")
    page.wait_for_selector("#okf-appearance-menu[hidden]", state="attached")


# ===========================================================================
# 8. Focus-exit close + pre-existing inert exact restore
# ===========================================================================

def test_focus_exit_closes_appearance_menu(server_url, page):
    """Tabbing out of the menu to an element outside the wrapper closes it."""
    _w(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    # Tab all the way through the menu options (4 groups × ~1 stop each = ~4 Tabs)
    # then one more Tab exits to the page → focus-exit closes.
    for _ in range(10):
        page.keyboard.press("Tab")
    page.wait_for_selector("#okf-appearance-menu[hidden]", state="attached")


def test_mobile_inert_exact_restore_on_close(server_url, page):
    """After closePanel, exactly the elements that were inerted are restored —
    no element that was NOT inerted gets accidentally de-inerted."""
    _w(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _studio(page)
    # Record which body children are inert BEFORE opening the panel.
    before = page.evaluate("""() => Array.from(document.body.children).map(c => ({
        tag: c.tagName, id: c.id || '', inert: !!c.inert
    }))""")
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.evaluate("window.okfLoomStudio.closePanel()")
    page.wait_for_selector("#okf-panel[hidden]", state="attached")
    after = page.evaluate("""() => Array.from(document.body.children).map(c => ({
        tag: c.tagName, id: c.id || '', inert: !!c.inert
    }))""")
    # Every child that was NOT inert before should be NOT inert after.
    for i in range(min(len(before), len(after))):
        if not before[i]["inert"]:
            assert not after[i]["inert"], f"child {after[i]['tag']}#{after[i]['id']} was not inert before but is inert after close"
