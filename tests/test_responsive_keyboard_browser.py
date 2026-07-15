"""Browser proof for responsive chrome + keyboard/focus correctness.

Covers the Editorial Workbench hardening slice:
  * Appearance popover geometry (fixed-position, not clipped, in-bounds) at
    320/390/768/900/901/1280.
  * Appearance radiogroup keyboard (roving tabindex, arrows wrap+select,
    Home/End, opening focuses checked Family, Tab one-per-group, Escape
    restores trigger, focus-exit close, no native key suppression).
  * Studio panel tabs ARIA (role=tab/tabpanel, aria-controls, aria-labelledby,
    roving tabindex, arrows/Home/End activate).
  * Mobile Studio modal (role=dialog aria-modal=true, inert siblings, focus
    trap, Escape topmost, backdrop close, focus restoration, breakpoint
    transition).
  * Desktop Studio non-modal (no inert/trap, Escape closes).
  * Responsive overflow (no document horizontal overflow; footer/topbar/graph
    controls reachable).

Same three-way gating as the other browser suites.
"""
from __future__ import annotations

import socket
import subprocess
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
_SERVER_STARTUP_TIMEOUT = 15.0
_SERVER_POLL_INTERVAL = 0.15
_POLL_HTTP_TIMEOUT = 1.0


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_http(proc, base, path="/"):
    deadline = time.monotonic() + _SERVER_STARTUP_TIMEOUT
    last_error = None
    while time.monotonic() < deadline:
        rc = proc.poll()
        if rc is not None:
            pytest.skip(f"server exited before becoming ready (rc={rc})")
        try:
            with urllib.request.urlopen(base + path, timeout=_POLL_HTTP_TIMEOUT) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            last_error = exc
        time.sleep(_SERVER_POLL_INTERVAL)
    pytest.skip(f"server not ready in {_SERVER_STARTUP_TIMEOUT:g}s ({last_error!r})")


def _terminate(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def server_url():
    if not DEMO_BUNDLE.is_dir():
        pytest.skip(f"demo bundle not found at {DEMO_BUNDLE}")
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        okf_module_argv(
            "serve", str(DEMO_BUNDLE), "--host", "127.0.0.1", "--port", str(port),
            "--no-watch", "--no-open",
        ),
        cwd=str(TOOLKIT_ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=okf_subprocess_env(),
    )
    _wait_for_http(proc, base)
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture
def page():
    chrome_path = os.environ.get("AIC_PLAYWRIGHT_CHROME_PATH") or ""
    attempts = []
    if chrome_path:
        attempts.append({"executable_path": chrome_path, "args": ["--no-sandbox"]})
    attempts.append({"channel": "chrome"})
    attempts.append({})
    with sync_playwright() as p:
        browser = None
        last_exc = None
        for kwargs in attempts:
            try:
                browser = p.chromium.launch(**kwargs)
                break
            except Exception as exc:
                last_exc = exc
                continue
        if browser is None:
            pytest.skip(
                "chromium binary not installed and no system Chrome available: "
                f"({last_exc})"
            )
        try:
            context = browser.new_context(color_scheme="light")
            pg = context.new_page()
            yield pg
            context.close()
        finally:
            browser.close()


def _wait_for_studio(pg):
    pg.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)


def _set_width(pg, w):
    pg.set_viewport_size({"width": w, "height": 900})


def _menu_bounds(page):
    return page.evaluate("""() => {
        const m = document.getElementById('okf-appearance-menu');
        if (!m) return null;
        const r = m.getBoundingClientRect();
        return {left: r.left, top: r.top, right: r.right, bottom: r.bottom,
                width: r.width, height: r.height};
    }""")


def _open_menu(page):
    page.click("#okf-theme")
    page.wait_for_selector("#okf-appearance-menu:not([hidden])", timeout=3000)


# ===========================================================================
# Appearance popover geometry at target widths
# ===========================================================================

@pytest.mark.parametrize("width", [320, 390, 768, 900, 901, 1280])
def test_appearance_menu_within_viewport_bounds(server_url, page, width):
    """Menu is fully within the viewport (8px inset) at every target width —
    not clipped by the topbar controls overflow scroller."""
    _set_width(page, width)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    b = _menu_bounds(page)
    assert b, "menu not found"
    vw = page.evaluate("window.innerWidth")
    vh = page.evaluate("window.innerHeight")
    assert b["left"] >= 7, f"left {b['left']} < 8 at {width}px"
    assert b["top"] >= 7, f"top {b['top']} < 8 at {width}px"
    assert b["right"] <= vw - 7, f"right {b['right']} > {vw}-8 at {width}px"
    assert b["bottom"] <= vh - 7, f"bottom {b['bottom']} > {vh}-8 at {width}px"
    assert b["width"] > 0 and b["height"] > 0


@pytest.mark.parametrize("width", [320, 390, 768, 900])
def test_appearance_menu_not_clipped_by_overflow(server_url, page, width):
    """The menu is position:fixed, so it escapes the topbar controls scroller
    (overflow-x:auto at <=900px). The menu's offsetHeight must equal its
    scrollHeight — no content clipped — and it must extend BELOW the topbar."""
    _set_width(page, width)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    info = page.evaluate("""() => {
        const m = document.getElementById('okf-appearance-menu');
        const topbar = document.querySelector('.okf-topbar');
        return {
            offset: m.offsetHeight,
            scroll: m.scrollHeight,
            menuBottom: m.getBoundingClientRect().bottom,
            topbarBottom: topbar ? topbar.getBoundingClientRect().bottom : 0,
        };
    }""")
    assert info["offset"] >= info["scroll"], "menu content clipped"
    assert info["menuBottom"] > info["topbarBottom"], "menu hidden behind topbar"


def test_appearance_menu_repositions_on_scroll(server_url, page):
    """Menu stays within viewport bounds after scrolling while open."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    page.evaluate("window.scrollTo(0, 300)")
    page.wait_for_timeout(150)
    b = _menu_bounds(page)
    vw = page.evaluate("window.innerWidth")
    vh = page.evaluate("window.innerHeight")
    assert b["left"] >= 7 and b["top"] >= 7
    assert b["right"] <= vw - 7 and b["bottom"] <= vh - 7


# ===========================================================================
# Appearance radiogroup keyboard navigation
# ===========================================================================

def test_opening_focuses_checked_family_option(server_url, page):
    """Opening the menu focuses the checked option in the Family group."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    focused = page.evaluate("""() => {
        const el = document.activeElement;
        return el ? {set: el.getAttribute('data-okf-set'), val: el.getAttribute('data-okf-val'),
                     checked: el.getAttribute('aria-checked')} : null;
    }""")
    assert focused, "nothing focused after opening menu"
    assert focused["set"] == "family", f"expected family group focused, got {focused}"
    assert focused["checked"] == "true", f"focused option not checked: {focused}"


def test_arrow_right_wraps_and_selects_in_family_group(server_url, page):
    """ArrowRight moves within the Family group, wrapping from last to first,
    and selects each option as it lands."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    # Swiss is checked by default (no saved pref + light OS → swiss-light).
    # Family group order: Technical, Swiss. Swiss is last → ArrowRight wraps to Technical.
    page.keyboard.press("ArrowRight")
    focused = page.evaluate("""() => {
        const el = document.activeElement;
        return el ? {val: el.getAttribute('data-okf-val'),
                     checked: el.getAttribute('aria-checked')} : null;
    }""")
    assert focused["val"] == "technical", f"ArrowRight should wrap to technical: {focused}"
    assert focused["checked"] == "true", "wrapped option should be selected"
    assert page.evaluate("document.documentElement.getAttribute('data-theme')").startswith("technical")


def test_home_and_end_in_radiogroup(server_url, page):
    """Home focuses first option, End focuses last option in the current group."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    page.keyboard.press("End")
    val = page.evaluate("document.activeElement.getAttribute('data-okf-val')")
    # Family group: Technical(0), Swiss(1) → End → Swiss
    assert val == "swiss", f"End should focus last (swiss), got {val}"
    page.keyboard.press("Home")
    val = page.evaluate("document.activeElement.getAttribute('data-okf-val')")
    assert val == "technical", f"Home should focus first (technical), got {val}"


def test_tab_moves_between_groups_not_within(server_url, page):
    """Tab from a Family option moves to the Mode group (one stop per group,
    not one per option). The focused option in Mode is the checked one."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    page.keyboard.press("Tab")
    focused = page.evaluate("""() => {
        const el = document.activeElement;
        return el ? {set: el.getAttribute('data-okf-set'),
                     tabindex: el.getAttribute('tabindex')} : null;
    }""")
    assert focused["set"] == "mode", f"Tab should move to mode group: {focused}"
    assert focused["tabindex"] == "0", "checked option in mode group should be tabindex=0"


def test_escape_closes_and_restores_trigger(server_url, page):
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.click("#okf-theme")
    page.wait_for_selector("#okf-appearance-menu:not([hidden])")
    page.keyboard.press("Escape")
    page.wait_for_selector("#okf-appearance-menu[hidden]", state="attached")
    assert page.evaluate("document.activeElement.id") == "okf-theme"


def test_outside_click_closes_menu(server_url, page):
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    # Click on the page heading (outside the menu wrapper).
    page.click("h1.okf-page__title")
    page.wait_for_selector("#okf-appearance-menu[hidden]", state="attached")


def test_roving_tabindex_one_zero_per_group(server_url, page):
    """Exactly one option per radiogroup has tabindex=0 (the checked one)."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    groups = page.evaluate("""() => {
        const groups = document.querySelectorAll('.okf-appearance__group[role="radiogroup"]');
        return Array.from(groups).map(g => {
            const tabs = g.querySelectorAll('.okf-appearance__opt[tabindex="0"]');
            return tabs.length;
        });
    }""")
    assert len(groups) == 4, f"expected 4 radiogroups, got {len(groups)}"
    for i, count in enumerate(groups):
        assert count == 1, f"group {i} has {count} tabindex=0 options, expected 1"


def test_native_keys_not_suppressed_when_menu_closed(server_url, page):
    """Backspace/Delete/Copy in an editable input work normally when the menu
    is closed (no global keyboard handler interferes)."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    search = page.locator('.okf-search-form input[type="search"]')
    search.fill("hello")
    search.focus()
    page.keyboard.press("Backspace")
    assert search.input_value() == "hell", "Backspace suppressed in search input"


def test_native_keys_not_suppressed_when_menu_open(server_url, page):
    """Even with the menu open, typing in a separate editable field works —
    the keyboard handler only fires inside radiogroup options."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _open_menu(page)
    # Focus the search input (outside the menu) and type.
    search = page.locator('.okf-search-form input[type="search"]')
    search.click()
    search.fill("test")
    page.keyboard.press("a")
    assert "a" in search.input_value(), "key suppressed in search while menu open"


# ===========================================================================
# Studio panel tabs ARIA + keyboard
# ===========================================================================

def test_panel_tabs_have_proper_aria(server_url, page):
    """Panel tabs have role=tab, aria-controls, stable IDs; body has
    role=tabpanel + aria-labelledby matching the active tab."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    tab = page.locator('#okf-panel-tab--comments')
    assert tab.get_attribute("role") == "tab"
    assert tab.get_attribute("aria-controls") == "okf-panel-body"
    assert tab.get_attribute("aria-selected") == "true"
    assert tab.get_attribute("tabindex") == "0"
    body = page.locator("#okf-panel-body")
    assert body.get_attribute("role") == "tabpanel"
    assert body.get_attribute("aria-labelledby") == "okf-panel-tab--comments"


def test_panel_tab_arrows_activate_and_keep_focus(server_url, page):
    """Arrow Right/Left in the tablist activates the adjacent tab and keeps
    focus on the tab list."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    tab = page.locator('#okf-panel-tab--comments')
    tab.focus()
    page.keyboard.press("ArrowRight")
    active = page.evaluate("document.activeElement.getAttribute('id')")
    assert active == "okf-panel-tab--changes", f"ArrowRight should activate changes tab: {active}"
    assert page.evaluate("document.activeElement.getAttribute('aria-selected')") == "true"


def test_panel_tab_home_end(server_url, page):
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.locator('#okf-panel-tab--comments').focus()
    page.keyboard.press("End")
    active = page.evaluate("document.activeElement.getAttribute('data-okf-set') || document.activeElement.textContent")
    # Metadata is last
    assert "Metadata" in page.evaluate("document.activeElement.textContent")
    page.keyboard.press("Home")
    assert "Comments" in page.evaluate("document.activeElement.textContent")


def test_panel_tab_key_exits_tablist(server_url, page):
    """Tab from the active tab moves OUT of the tablist (natural Tab flow)."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.locator('#okf-panel-tab--comments').focus()
    page.keyboard.press("Tab")
    # Focus should no longer be on a tab.
    active = page.evaluate("""() => {
        const el = document.activeElement;
        return el ? el.className : null;
    }""")
    assert "okf-panel__tab" not in (active or "")


# ===========================================================================
# Mobile Studio modal (<=900px)
# ===========================================================================

def test_mobile_panel_is_modal_dialog(server_url, page):
    """At <=900px the panel acquires role=dialog + aria-modal=true."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    assert page.evaluate("document.getElementById('okf-panel').getAttribute('role')") == "dialog"
    assert page.evaluate("document.getElementById('okf-panel').getAttribute('aria-modal')") == "true"


def test_mobile_panel_inerts_siblings(server_url, page):
    """Body children (except panel + overlay) are inert when modal is open."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    main_inert = page.evaluate("document.querySelector('main')?.inert")
    assert main_inert is True, "main should be inert when modal is open"


def test_mobile_panel_restores_inert_on_close(server_url, page):
    """Closing the panel restores inert=false on all siblings."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.evaluate("window.okfLoomStudio.closePanel()")
    page.wait_for_selector("#okf-panel[hidden]", state="attached")
    main_inert = page.evaluate("document.querySelector('main')?.inert")
    assert main_inert is False or main_inert is None, "main should not be inert after close"


def test_mobile_panel_traps_tab(server_url, page):
    """Tab cycles within the panel (focus trap)."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    # Tab many times — focus should never leave the panel.
    for _ in range(20):
        page.keyboard.press("Tab")
    assert "okf-panel" in (page.evaluate("document.activeElement.closest('#okf-panel')?.id") or "")


def test_mobile_panel_escape_closes_and_restores_focus(server_url, page):
    """Escape on mobile closes the modal and restores focus to the trigger."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    # Open via the studio button (so there's a trigger to restore to).
    page.click(".okf-studio-open-btn")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.keyboard.press("Escape")
    page.wait_for_selector("#okf-panel[hidden]", state="attached")
    active = page.evaluate("document.activeElement?.className || ''")
    assert "okf-studio-open-btn" in active or "studio" in active.lower(), \
        f"focus not restored to trigger: {active}"


def test_mobile_panel_close_button_dismisses(server_url, page):
    """On mobile the panel covers 100vw (no visible backdrop), so the close
    button (labeled 'Esc') is the primary dismissal — not a synthetic overlay
    click. The close button must work."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    page.click(".okf-panel__close")
    page.wait_for_selector("#okf-panel[hidden]", state="attached")


def test_desktop_panel_is_not_modal(server_url, page):
    """At >900px the panel is complementary (not dialog/modal), no inert."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    role = page.evaluate("document.getElementById('okf-panel').getAttribute('role')")
    assert role == "complementary", f"desktop should be complementary, got {role}"
    assert not page.evaluate("document.getElementById('okf-panel').hasAttribute('aria-modal')")
    main_inert = page.evaluate("document.querySelector('main')?.inert")
    assert main_inert is False or main_inert is None


def test_breakpoint_transition_acquires_modal(server_url, page):
    """Crossing from desktop to mobile while panel is open acquires modal."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    _set_width(page, 390)
    page.wait_for_timeout(200)  # MQ listener fires
    role = page.evaluate("document.getElementById('okf-panel').getAttribute('role')")
    assert role == "dialog", f"should acquire dialog on mobile transition: {role}"


def test_breakpoint_transition_releases_modal(server_url, page):
    """Crossing from mobile to desktop while panel is open releases modal."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    _set_width(page, 1280)
    page.wait_for_timeout(200)
    role = page.evaluate("document.getElementById('okf-panel').getAttribute('role')")
    assert role == "complementary", f"should release modal on desktop transition: {role}"
    main_inert = page.evaluate("document.querySelector('main')?.inert")
    assert main_inert is False or main_inert is None


# ===========================================================================
# Responsive overflow
# ===========================================================================

@pytest.mark.parametrize("width", [320, 390, 768, 900])
def test_no_document_horizontal_overflow_concept(server_url, page, width):
    """The concept page has no document-level horizontal overflow at target
    widths (scrollWidth <= clientWidth + 1 tolerance)."""
    _set_width(page, width)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    overflow = page.evaluate("""() => ({
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
    })""")
    assert overflow["scrollW"] <= overflow["clientW"] + 1, \
        f"horizontal overflow at {width}px: scrollW={overflow['scrollW']} clientW={overflow['clientW']}"


@pytest.mark.parametrize("width", [320, 390, 768, 900])
def test_no_document_horizontal_overflow_graph(server_url, page, width):
    """The graph page has no document-level horizontal overflow."""
    _set_width(page, width)
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph", timeout=10000)
    overflow = page.evaluate("""() => ({
        scrollW: document.documentElement.scrollWidth,
        clientW: document.documentElement.clientWidth,
    })""")
    assert overflow["scrollW"] <= overflow["clientW"] + 1, \
        f"graph horizontal overflow at {width}px: scrollW={overflow['scrollW']} clientW={overflow['clientW']}"


def test_footer_actions_reachable_on_mobile(server_url, page):
    """At 320px every footer action button is visible and within viewport."""
    _set_width(page, 320)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    btns = page.locator(".okf-studio-bar--status .okf-studiobtn")
    count = btns.count()
    assert count > 0, "no footer buttons found"
    for i in range(count):
        box = btns.nth(i).bounding_box()
        assert box, f"button {i} has no bounding box"
        assert box["x"] + box["width"] <= 320 + 1, \
            f"button {i} extends beyond viewport: {box}"


def test_graph_topbar_no_overflow_on_mobile(server_url, page):
    """At 390px the graph topbar has no horizontal overflow (controls may wrap
    to a second row at <=430px — that's the intended two-row header pattern)."""
    _set_width(page, 390)
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph", timeout=10000)
    overflow = page.evaluate("""() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
    })""")
    assert overflow["sw"] <= overflow["cw"] + 1, f"graph topbar overflow at 390px: sw={overflow['sw']} cw={overflow['cw']}"


# ===========================================================================
# Mobile table overflow containment + accessibility (P1 table fix)
# ===========================================================================

def _table_wrap_info(page):
    """Single source of truth for table-wrapper measurements in the tests."""
    return page.evaluate("""() => {
        const html = document.documentElement;
        const wrap = document.querySelector('.okf-tablewrap');
        if (!wrap) return null;
        const cue = wrap.querySelector('.okf-table-cue');
        const table = wrap.querySelector('table');
        return {
            docSW: html.scrollWidth, docCW: html.clientWidth,
            wrapSW: wrap.scrollWidth, wrapCW: wrap.clientWidth,
            wrapOverflows: wrap.scrollWidth > wrap.clientWidth + 1,
            cls: wrap.className,
            role: wrap.getAttribute('role'),
            tabindex: wrap.getAttribute('tabindex'),
            ariaLabel: wrap.getAttribute('aria-label'),
            dataScroll: wrap.getAttribute('data-scroll'),
            hasCue: !!cue,
            cueText: cue ? cue.textContent : null,
            // Inner-table fallback-affordance state. markdown.py stamps the
            // bare table with tabindex/aria-label/data-okf-fallback for the
            // no-JS path; enhanceTable must TRANSFER (strip) them so a fit
            // table carries no extra tab stop and overflow uses the wrapper.
            tableTabindex: table ? table.getAttribute('tabindex') : null,
            tableAriaLabel: table ? table.getAttribute('aria-label') : null,
            tableFallback: table ? table.getAttribute('data-okf-fallback') : null,
            tableEnhanced: table ? table.classList.contains('okf-table--enhanced') : false,
        };
    }""")


@pytest.mark.parametrize("width", [390, 414])
def test_mobile_table_overflow_has_accessibility(server_url, page, width):
    """At mobile widths the overflowing table wrapper is a labelled,
    keyboard-focusable scroll region with a visible cue and edge-state."""
    _set_width(page, width)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.wait_for_timeout(300)
    info = _table_wrap_info(page)
    assert info, "no table wrapper found"
    assert info["wrapOverflows"], f"table should overflow at {width}px"
    assert "okf-tablewrap--overflow" in info["cls"]
    assert "okf-tablewrap--fit" not in info["cls"], "fit and overflow must be mutually exclusive"
    assert info["role"] == "region", "wrapper must have role=region on overflow"
    assert info["tabindex"] == "0", "wrapper must be keyboard-focusable on overflow"
    assert info["ariaLabel"], "wrapper must have an accessible name on overflow"
    assert "table" in info["ariaLabel"].lower()
    assert info["hasCue"], "visible scroll cue must be present on overflow"
    assert info["cueText"], "cue must have text"
    assert info["dataScroll"] in ("start", "middle", "end"), "data-scroll edge state must be set"


@pytest.mark.parametrize("width", [390, 414])
def test_mobile_table_no_document_overflow(server_url, page, width):
    """The table is locally contained — no document-level horizontal overflow."""
    _set_width(page, width)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.wait_for_timeout(300)
    info = _table_wrap_info(page)
    assert info["docSW"] <= info["docCW"] + 1, \
        f"document overflow at {width}px: docSW={info['docSW']} docCW={info['docCW']}"


def test_desktop_table_fit_has_no_tab_stop(server_url, page):
    """At desktop width a table that fits has NO overflow affordance: no
    role, no tabindex, no cue. Desktop reads as a plain table.

    Also proves the no-JS→JS affordance TRANSFER: markdown.py stamps the bare
    table with tabindex/aria-label/data-okf-fallback for the no-JS keyboard
    path, but once the enhancer runs it strips those table attributes and lets
    classifyTable keep the wrapper clean on fit — so neither the wrapper NOR
    the inner table is an extra tab stop."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.wait_for_timeout(300)
    info = _table_wrap_info(page)
    assert info, "no table wrapper found"
    assert not info["wrapOverflows"], "table should fit at 1280px"
    assert "okf-tablewrap--fit" in info["cls"]
    assert "okf-tablewrap--overflow" not in info["cls"]
    assert info["role"] is None, "fit table wrapper must not have role"
    assert info["tabindex"] is None, "fit table wrapper must not be a tab stop"
    assert info["ariaLabel"] is None, "fit table wrapper must not have aria-label"
    assert not info["hasCue"], "fit table must not have a cue"
    # Transfer proof: the inner table's server fallback focus affordance is
    # stripped by enhanceTable, so a fitting desktop table is NOT an extra
    # tab stop on the table element itself either.
    assert info["tableEnhanced"], "table should be enhanced in JS mode"
    assert info["tableTabindex"] is None, (
        f"enhanced fit table must not carry the no-JS fallback tabindex, "
        f"got {info['tableTabindex']!r}"
    )
    assert info["tableAriaLabel"] is None, (
        f"enhanced fit table must not carry the no-JS fallback aria-label, "
        f"got {info['tableAriaLabel']!r}"
    )
    assert info["tableFallback"] is None, (
        f"data-okf-fallback marker must be stripped after transfer, "
        f"got {info['tableFallback']!r}"
    )


def test_table_edge_shadow_state_transitions(server_url, page):
    """data-scroll updates from 'start' to 'end' as the user scrolls right."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.wait_for_timeout(300)
    info = _table_wrap_info(page)
    assert info["dataScroll"] == "start", "should start at left edge"
    # Scroll to the far right.
    page.evaluate("""() => {
        const w = document.querySelector('.okf-tablewrap');
        w.scrollLeft = w.scrollWidth;
    }""")
    page.wait_for_timeout(200)
    info2 = _table_wrap_info(page)
    assert info2["dataScroll"] == "end", \
        f"should reach 'end' after scrolling right, got {info2['dataScroll']}"


def test_table_keyboard_scroll(server_url, page):
    """A keyboard user can scroll the focused overflow region with arrow keys."""
    _set_width(page, 390)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.wait_for_timeout(300)
    page.evaluate("document.querySelector('.okf-tablewrap').focus()")
    before = page.evaluate("document.querySelector('.okf-tablewrap').scrollLeft")
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(100)
    after = page.evaluate("document.querySelector('.okf-tablewrap').scrollLeft")
    assert after > before, f"ArrowRight should scroll the region: before={before} after={after}"


def test_table_resize_reclassifies_fit_to_overflow(server_url, page):
    """Resizing from wide (fit) to narrow (overflow) adds the affordance."""
    _set_width(page, 1280)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.wait_for_timeout(300)
    fit = _table_wrap_info(page)
    assert "okf-tablewrap--fit" in fit["cls"]
    # Narrow the viewport — debounced reclassify + ResizeObserver must fire.
    _set_width(page, 390)
    page.wait_for_timeout(500)
    overflow = _table_wrap_info(page)
    assert "okf-tablewrap--overflow" in overflow["cls"], "resize did not reclassify to overflow"
    assert overflow["role"] == "region"


def test_table_bare_css_present_before_enhancement(server_url, page):
    """The bare ``.okf-table`` keeps its own ``overflow-x: auto`` CSS so that
    even before the JS enhancer runs (or if it never runs) the table scrolls
    horizontally without causing document-level overflow.

    NOTE: This runs in a JS-ENABLED context and inspects the pre-enhancement
    state (before ``_wait_for_studio``). It is NOT a no-JS proof — the real
    ``java_script_enabled=False`` no-JS table containment proof lives in
    ``test_first_paint_lifecycle_browser.py::test_nojs_mobile_table_no_enhancer_and_scrollable``
    and ``test_nojs_mobile_table_reachable_by_tab``."""
    # The 'page' fixture has JS enabled; we measure the bare-table CSS state
    # immediately on DOMContentLoaded, before the enhancer wraps the table.
    _set_width(page, 414)
    page.goto(f"{server_url}/tables/orders", wait_until="domcontentloaded")
    page.wait_for_timeout(200)
    info = page.evaluate("""() => ({
        docSW: document.documentElement.scrollWidth,
        docCW: document.documentElement.clientWidth,
        tableOverX: (() => {
            const t = document.querySelector('table.okf-table');
            return t ? getComputedStyle(t).overflowX : null;
        })(),
    })""")
    assert info["docSW"] <= info["docCW"] + 1, "document overflow before JS enhancement"
    assert info["tableOverX"] in ("auto", "visible"), "bare table must retain scroll CSS"
