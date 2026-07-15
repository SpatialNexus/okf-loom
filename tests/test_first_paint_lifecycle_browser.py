"""First-paint lifecycle: wrong-theme flash, boot-banner flash, and desktop
recentering must NOT occur during native document navigation.

These are deterministic browser proofs for the three startup defects fixed
across the serve first-paint lifecycle:

  * THEME FOUC — with a dark OS and no saved preference, the resolved theme
    must be painted at first paint (parser-blocking theme.js), so a light
    fallback is never observed on the destination document.
  * BANNER FLASH — the JS fallback banner must NEVER be visible during a
    normal successful studio boot; it must appear only when the studio
    genuinely fails to boot (studio.js blocked, or boot() throws after
    module evaluation).
  * DESKTOP RECENTERING — the concept-page rail reserve (body padding-right)
    must be present from first paint so the centered page never recentres,
    and no padding-right transition fires on navigation. Mobile keeps no
    reserve.

Navigation is exercised both via ``page.goto`` and via a NATIVE internal
``<a href>`` click (no SPA/link interception) so Back/Forward and modifier
semantics stay the browser's own.

ASYNC_LIFECYCLE_MATRIX — theme/bootstrap/studio boot settlement
================================================================

The boot lifecycle has exactly three terminal states. Each is settled by a
single owner, on a single trigger, with no timer/retry/opacity masking.

Persisted-state policy: BROWSER-EPHEMERAL. The settlement classes
(``okf-studio-booted`` / ``okf-studio-unavailable``) live on
``document.documentElement`` for the lifetime of the current document only.
They are never written to localStorage, sessionStorage, cookies, or any
server-side store. A full document load (navigation, reload) re-derives the
settlement from scratch. The user's theme choice (``okf-theme-mode``) and
nav-collapse (``okf-nav-collapsed``) ARE persisted; the boot settlement is
NOT — it is a per-document, per-load derived fact.

Boot mutation phase: ``boot()`` performs a sequence of SYNCHRONOUS DOM
mutations (mountBar appends the studio bar, mountNavToggle toggles the
nav-collapse class, then view/sidebar/rail setup). The settlement is stamped
ONLY after this entire synchronous body returns (ready) or throws
(unavailable). The async tails dispatched during boot (loadGraph,
loadComments, tokenFetch, the 400ms rebuildMarginMarkers timer) are
fire-and-forget: they resolve/reject AFTER the synchronous settlement is
already terminal, and their own ``.then``/``.catch`` handlers never call
``_settleBoot`` or touch the settlement classes.

+-------------+---------------------------+--------------------------+----------------------------+----------------+--------------------------+--------+-------------------------------------------+
| State       | Owner                     | Trigger                  | Mutation (additive-only)   | Terminal state | Deadline / abort         | Retry  | Late result                               |
+=============+===========================+==========================+============================+================+==========================+========+===========================================+
| READY       | studio.js _runBoot()      | boot() returns normally  | html.okf-studio-booted     | Yes (one-way)  | Synchronous (no timer)   | None   | loadGraph/loadComments/tokenFetch are     |
|             |                           | (sync init complete)     |                            |                |                          |        | fire-and-forget; their own .catch() does  |
|             |                           |                          |                            |                |                          |        | not affect the ready settlement           |
+-------------+---------------------------+--------------------------+----------------------------+----------------+--------------------------+--------+-------------------------------------------+
| UNAVAILABLE | studio.js _runBoot()      | boot() throws AFTER at   | html.okf-studio-unavailable| Yes (one-way)  | Synchronous (no timer)   | None   | Already-dispatched async tails resolve/   |
| (boot fail) | catch                     | least one genuine DOM    |                            |                |                          |        | reject with their OWN handlers; they NEVER|
|             |                           | mutation (mountBar etc.) |                            |                |                          |        | call _settleBoot or touch the classes —   |
|             |                           |                          |                            |                |                          |        | unavailable persists (proved below)       |
+-------------+---------------------------+--------------------------+----------------------------+----------------+--------------------------+--------+-------------------------------------------+
| UNAVAILABLE | theme.js watchdog         | DOMContentLoaded fires   | html.okf-studio-unavailable| Yes (one-way)  | DOMContentLoaded event   | None   | N/A (event-driven, one-shot)              |
| (no module) | _settleStudioBanner()     | and okf-studio-booted    | (idempotent if already     |                | (no timer)               |        |                                           |
|             |                           | is still ABSENT          | set by catch path)         |                |                          |        |                                           |
+-------------+---------------------------+--------------------------+----------------------------+----------------+--------------------------+--------+-------------------------------------------+

Invariants:
  * Classes are ADDITIVE ONLY — neither is ever removed after stamping.
  * READY and UNAVAILABLE are mutually exclusive: boot() either returns
    (stamps booted) or throws (stamps unavailable), never both.
  * The watchdog adds unavailable only when booted is absent, so it can
    never overwrite a ready state.
  * No timer, no retry, no opacity transition, no overlay mask.
  * Late async tails (promises + timers dispatched during boot) cannot
    replace unavailable with booted or hide the failure banner: they have
    no code path to _settleBoot and the settlement classes are add-only.

Direct proofs in this file:
  * READY:              test_no_banner_flash_during_successful_boot
  * READY (rAF):        test_no_transient_banner_flash_during_successful_boot_rAF
  * UNAVAILABLE (throw): test_boot_failure_after_genuine_mutation
  * UNAVAILABLE (no module): test_module_evaluation_failure_watchdog
  * Late-tail safety:   test_late_async_tail_cannot_overwrite_unavailable
  * One-way invariant:  test_banner_settlement_is_one_way_no_overwrite

TABLE CONTAINMENT LIFECYCLE — reactive reclassification (not terminal)
======================================================================

Table fit/overflow classification is REACTIVE, not terminal: it re-derives
on viewport/column resize and live body replacement. The invariant is that
``--fit`` and ``--overflow`` are always mutually exclusive, and the ARIA
affordance (role/tabindex/aria-label/cue/edge-state) is added on overflow
and FULLY removed on fit — no stale affordance leaks across reclassification.

+-----------------+------------------------+--------------------------+----------------------------+----------------+--------------------------+--------+-------------------------------------------+
| Scenario        | Owner                  | Trigger                  | Mutation                   | Persisted state | Deadline / abort        | Retry  | Late result                               |
+=================+========================+==========================+============================+=================+==========================+========+===========================================+
| Prepaint theme  | theme.js (parser-      | <head> parse (before     | html[data-theme]           | localStorage    | Synchronous (parser-     | None   | N/A (synchronous, before paint)           |
|                 | blocking)              | first paint)             |                            | okf-theme-mode  | blocking, no timer)      |        |                                           |
+-----------------+------------------------+--------------------------+----------------------------+-----------------+--------------------------+--------+-------------------------------------------+
| Table initial   | renderers.js initTables| DOMContentLoaded /       | wrap table in .okf-       | BROWSER-        | Synchronous on init;     | None   | classifyTable is idempotent;              |
|                 | → classifyTable        | okf-loom:bodyPatched     | tablewrap; set --fit or   | EPHEMERAL       | ResizeObserver debounce  |        | re-running on the same table is a no-op   |
|                 |                        |                          | --overflow + ARIA/cue      | (DOM only)      | 150ms on resize          |        | (data-okfEnhanced guard)                  |
+-----------------+------------------------+--------------------------+----------------------------+-----------------+--------------------------+--------+-------------------------------------------+
| Table resize    | scheduleReclassify →   | window resize /          | Reclassify --fit ↔         | BROWSER-        | 150ms debounce timer     | None   | Latest resize wins; intermediate          |
|                 | updateTableFits →      | ResizeObserver (sidebar  | --overflow; add/remove     | EPHEMERAL       | (cleared + reset on each  |        | events are coalesced; classifyTable is    |
|                 | classifyTable          | toggle, focus, split)    | ARIA/cue atomically        | (DOM only)      | event)                   |        | always called after the debounce settles  |
+-----------------+------------------------+--------------------------+----------------------------+-----------------+--------------------------+--------+-------------------------------------------+
| Table body      | okf-loom:bodyPatched → | Live studio concept      | Old wrapper/table removed  | BROWSER-        | Synchronous on patch     | None   | Stale affordance is removed when the old  |
| patch           | initAll → initTables   | change (studio.js /      | with the old table; new    | EPHEMERAL       | event; classifyTable     |        | table is replaced; the new table gets a   |
|                 | + updateTableFits      | live.js dispatch)        | table enhanced fresh       | (DOM only)      | runs immediately after   |        | fresh wrapper with no inherited state     |
+-----------------+------------------------+--------------------------+----------------------------+-----------------+--------------------------+--------+-------------------------------------------+

Direct proofs in this file:
  * Table initial (overflow): test_live_patch_inserts_overflowing_table_with_affordance
  * Table body patch (fit replaces overflow): test_live_patch_replaces_overflow_with_fit_removes_affordance
  * Table resize (fit→overflow): test_responsive_keyboard_browser.py::test_table_resize_reclassifies_fit_to_overflow
  * No-JS table (no enhancer): test_nojs_mobile_table_no_enhancer_and_scrollable
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402

from conftest import TOOLKIT_ROOT, okf_module_argv, okf_subprocess_env  # noqa: E402

pytestmark = pytest.mark.browser
DEMO_BUNDLE = TOOLKIT_ROOT / "samples" / "demo_bundle"
CONCEPT = "/tables/orders"


# ---------------------------------------------------------------------------
# Server + page fixtures
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_http(proc: subprocess.Popen, base: str, path: str = "/") -> None:
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.skip("server exited")
        try:
            with urllib.request.urlopen(base + path, timeout=1) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(0.15)
    pytest.skip("server not ready")


def _terminate(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def server_url():
    if not DEMO_BUNDLE.is_dir():
        pytest.skip("no demo bundle")
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        okf_module_argv(
            "serve", str(DEMO_BUNDLE), "--host", "127.0.0.1", "--port", str(port),
            "--no-watch", "--no-open",
        ),
        cwd=str(TOOLKIT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=okf_subprocess_env(),
    )
    _wait_http(proc, base)
    try:
        yield base
    finally:
        _terminate(proc)


def _launch_browser():
    chrome = os.environ.get("AIC_PLAYWRIGHT_CHROME_PATH") or ""
    attempts = []
    if chrome:
        attempts.append({"executable_path": chrome, "args": ["--no-sandbox"]})
    attempts.append({"channel": "chrome"})
    attempts.append({})
    p = sync_playwright().start()
    browser = None
    last = None
    for kw in attempts:
        try:
            browser = p.chromium.launch(**kw)
            break
        except Exception as e:
            last = e
    if browser is None:
        p.stop()
        pytest.skip(f"no chrome ({last})")
    return p, browser


@pytest.fixture
def dark_page():
    """A Chromium page emulating a DARK OS, desktop width, no saved theme."""
    p, browser = _launch_browser()
    try:
        ctx = browser.new_context(
            color_scheme="dark", viewport={"width": 1280, "height": 900}
        )
        ctx.clear_cookies()  # fresh storage origin
        pg = ctx.new_page()
        yield pg
        ctx.close()
    finally:
        browser.close()
        p.stop()


@pytest.fixture
def light_page():
    p, browser = _launch_browser()
    try:
        ctx = browser.new_context(
            color_scheme="light", viewport={"width": 1280, "height": 900}
        )
        pg = ctx.new_page()
        yield pg
        ctx.close()
    finally:
        browser.close()
        p.stop()


@pytest.fixture
def mobile_page():
    p, browser = _launch_browser()
    try:
        ctx = browser.new_context(
            color_scheme="dark", viewport={"width": 414, "height": 900}
        )
        pg = ctx.new_page()
        yield pg
        ctx.close()
    finally:
        browser.close()
        p.stop()


@pytest.fixture
def page():
    """General-purpose JS-enabled desktop page with a settable viewport.

    Used by tests that need to resize the viewport mid-session (e.g. live
    table patch tests that drive the enhancer at a chosen mobile width)."""
    p, browser = _launch_browser()
    try:
        ctx = browser.new_context(
            color_scheme="light", viewport={"width": 1280, "height": 900}
        )
        pg = ctx.new_page()
        yield pg
        ctx.close()
    finally:
        browser.close()
        p.stop()


@pytest.fixture
def nojs_desktop_page():
    """Desktop page with JavaScript disabled (no rail can ever be built)."""
    p, browser = _launch_browser()
    try:
        ctx = browser.new_context(
            color_scheme="dark",
            viewport={"width": 1280, "height": 900},
            java_script_enabled=False,
        )
        pg = ctx.new_page()
        yield pg
        ctx.close()
    finally:
        browser.close()
        p.stop()


@pytest.fixture
def nojs_mobile_page():
    """Mobile-width page with JavaScript genuinely disabled.

    Used to prove the no-JS table containment path WITHOUT relying on a
    JS-enabled context (the old test_nojs_table_still_scrolls admitted it
    could not disable JS mid-session, so it only checked pre-enhancement
    CSS from a JS-enabled page — not a real no-JS proof)."""
    p, browser = _launch_browser()
    try:
        ctx = browser.new_context(
            color_scheme="dark",
            viewport={"width": 414, "height": 900},
            java_script_enabled=False,
        )
        pg = ctx.new_page()
        yield pg
        ctx.close()
    finally:
        browser.close()
        p.stop()


def _banner_display(page) -> str:
    return page.evaluate(
        """() => {
            var b = document.querySelector('.okf-studio-fallback-banner--js');
            return b ? getComputedStyle(b).display : 'absent';
        }"""
    )


def _count_visible_banners(page) -> int:
    return page.evaluate(
        """() => {
            var n = 0;
            document.querySelectorAll('.okf-studio-fallback-banner').forEach(function(b){
                if (getComputedStyle(b).display !== 'none') n++;
            });
            return n;
        }"""
    )


def _install_first_paint_theme_sampler(page):
    """Sample data-theme on the first few animation frames (≈ first paints).

    theme.js is parser-blocking, so by the first rendering opportunity data-theme
    is already resolved; every sample must be the resolved (dark) theme — never a
    light fallback — proving no wrong-theme paint at first paint."""
    page.add_init_script(
        """
        window.__okfFirstPaintThemes = [];
        (function loop(){
          (window.requestAnimationFrame || function(f){ setTimeout(f,16); })(function(){
            var el = document.documentElement;
            window.__okfFirstPaintThemes.push(el ? el.getAttribute('data-theme') : null);
            if (window.__okfFirstPaintThemes.length < 5) loop();
          });
        })();
        """
    )


def _install_banner_display_sampler(page):
    """Sample the --js fallback banner's computed display across rAF frames.

    This is a paint-crossing proof: instead of checking only the final settled
    state, it captures the banner's display value on each of the first ~10
    animation frames. A transient flash (banner visible for one frame before
    okf-studio-booted is stamped) would be caught here even if the final state
    is correct."""
    page.add_init_script(
        """
        window.__okfBannerSamples = [];
        (function loop(){
          (window.requestAnimationFrame || function(f){ setTimeout(f,16); })(function(){
            var b = document.querySelector('.okf-studio-fallback-banner--js');
            window.__okfBannerSamples.push(b ? getComputedStyle(b).display : 'absent');
            if (window.__okfBannerSamples.length < 10) loop();
          });
        })();
        """
    )


def _install_paddingright_transition_logger(page):
    """Record any 'padding-right' transitionend on <body> (animated recentering)."""
    page.add_init_script(
        """
        window.__okfPadTransitions = [];
        document.addEventListener('transitionend', function(e){
          if (e.target === document.body && e.propertyName === 'padding-right') {
            window.__okfPadTransitions.push(performance.now());
          }
        }, true);
        """
    )


def _install_frame_geometry_sampler(page):
    """Sample concept centerline + documentElement client/scroll width across
    rAF frames (paint-crossing geometry proof).

    Captures the horizontal center of ``.okf-page`` (or ``#okf-main``) and
    ``documentElement.clientWidth`` / ``scrollWidth`` on each of the first ~8
    animation frames. A desktop recentering (rail reserve applied late) would
    show the centerline or clientWidth shifting between frames; a mobile
    document overflow would show ``scrollWidth > clientWidth``. Both are
    caught here even if the final settled state is correct."""
    page.add_init_script(
        """
        window.__okfFrameGeo = [];
        (function loop(){
          (window.requestAnimationFrame || function(f){ setTimeout(f,16); })(function(){
            var el = document.querySelector('.okf-page') || document.getElementById('okf-main');
            var de = document.documentElement;
            var r = el ? el.getBoundingClientRect() : null;
            window.__okfFrameGeo.push({
              center: r ? Math.round(r.left + r.width / 2) : null,
              clientW: r ? el.clientWidth : null,
              deClientW: de ? de.clientWidth : null,
              deScrollW: de ? de.scrollWidth : null,
            });
            if (window.__okfFrameGeo.length < 8) loop();
          });
        })();
        """
    )


# ===========================================================================
# THEME FOUC — resolved theme painted at first paint (dark OS, no saved pref)
# ===========================================================================


def test_theme_js_is_parser_blocking_not_deferred(server_url):
    """The fix: theme.js is a blocking head script (no defer) so it resolves
    data-theme before first paint. Asserted from the served HTML."""
    import urllib.request as u
    html = u.urlopen(server_url + CONCEPT, timeout=3).read().decode("utf-8")
    # Find the theme.js tag.
    i = html.find("theme.js")
    assert i > 0, "theme.js script tag missing"
    # The tag should NOT carry defer (parser-blocking).
    tag_end = html.find(">", i)
    tag = html[i:tag_end]
    assert "defer" not in tag, f"theme.js must be parser-blocking (no defer): {tag!r}"


def test_resolved_theme_is_dark_before_load_on_dark_os(server_url, dark_page):
    """Dark OS, no saved preference → data-theme is already the resolved dark
    theme by DOMContentLoaded (theme.js ran during head parse, before paint)."""
    _install_first_paint_theme_sampler(dark_page)
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    theme = dark_page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert theme is not None and theme.endswith("-dark"), (
        f"expected a dark resolved theme at DOMContentLoaded, got {theme!r}"
    )
    # Strengthen: every first-paint sample (≈ first paints) is the resolved
    # dark theme — no light fallback was ever painted.
    dark_page.wait_for_timeout(150)  # let a few rAF samples accrue
    samples = dark_page.evaluate("window.__okfFirstPaintThemes")
    assert samples, "first-paint theme sampler did not run"
    light = [v for v in samples if v and v.endswith("-light")]
    assert not light, f"a light theme was painted during dark-OS load: {samples!r}"


def test_resolved_theme_dark_survives_native_link_navigation(server_url, dark_page):
    """Native internal <a> click (no interception): the destination paints the
    resolved dark theme with no light flash. Sampled via first-paint frames."""
    _install_first_paint_theme_sampler(dark_page)
    dark_page.goto(f"{server_url}/", wait_until="domcontentloaded")
    link = dark_page.query_selector(f'a[href="{CONCEPT}"]')
    if link is None:
        link = dark_page.query_selector('a[href^="/tables/"]')
    assert link is not None, "no native internal concept link found on the index"
    with dark_page.expect_navigation(wait_until="domcontentloaded"):
        link.click()
    theme = dark_page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert theme is not None and theme.endswith("-dark"), (
        f"native-link destination theme not dark: {theme!r}"
    )
    dark_page.wait_for_timeout(150)
    samples = dark_page.evaluate("window.__okfFirstPaintThemes")
    assert not [v for v in samples if v and v.endswith("-light")], (
        f"light theme painted during native navigation: {samples!r}"
    )


def test_theme_precedence_auto_dark_os(server_url, dark_page):
    """Explicit precedence: auto mode (no saved preference) + dark OS must
    paint the dark theme from the very first frame. This is the canonical
    FOUC guard: the OS preference drives resolution at parse time, so no
    light fallback is ever painted."""
    _install_first_paint_theme_sampler(dark_page)
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    # No saved preference → auto mode governs.
    assert dark_page.evaluate("localStorage.getItem('okf-theme-mode')") is None
    theme = dark_page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert theme is not None and theme.endswith("-dark"), (
        f"auto + dark OS should resolve dark at first paint, got {theme!r}"
    )
    dark_page.wait_for_timeout(150)
    samples = dark_page.evaluate("window.__okfFirstPaintThemes")
    assert samples, "first-paint theme sampler did not run"
    assert all(v and v.endswith("-dark") for v in samples), (
        f"a non-dark frame was painted during auto+dark-OS load: {samples!r}"
    )


def test_theme_precedence_saved_dark_on_light_os(server_url, light_page):
    """Explicit precedence: a saved dark preference must paint dark from the
    first frame even when the OS is light (saved preference > OS)."""
    light_page.add_init_script(
        "try{localStorage.setItem('okf-theme-mode','dark');}catch(e){}"
    )
    _install_first_paint_theme_sampler(light_page)
    light_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    theme = light_page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert theme is not None and theme.endswith("-dark"), (
        f"saved dark on light OS should resolve dark, got {theme!r}"
    )
    light_page.wait_for_timeout(150)
    samples = light_page.evaluate("window.__okfFirstPaintThemes")
    assert samples, "first-paint theme sampler did not run"
    assert all(v and v.endswith("-dark") for v in samples), (
        f"a non-dark frame was painted despite saved dark: {samples!r}"
    )


def test_theme_precedence_auto_light_os(server_url, light_page):
    """Explicit precedence: auto mode + light OS must paint light from the
    first frame (default Swiss family + auto + light OS = swiss-light)."""
    _install_first_paint_theme_sampler(light_page)
    light_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    assert light_page.evaluate("localStorage.getItem('okf-theme-mode')") is None
    theme = light_page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert theme == "swiss-light", (
        f"auto + light OS should resolve swiss-light, got {theme!r}"
    )
    light_page.wait_for_timeout(150)
    samples = light_page.evaluate("window.__okfFirstPaintThemes")
    assert samples, "first-paint theme sampler did not run"
    assert all(v == "swiss-light" for v in samples), (
        f"a non-swiss-light frame was painted during auto+light-OS load: {samples!r}"
    )


# ===========================================================================
# BANNER FLASH — never visible during successful boot; visible on failure
# ===========================================================================


def test_no_banner_flash_during_successful_boot(server_url, dark_page):
    """During a normal successful studio boot the JS fallback banner is NEVER
    visible — not even transiently. The reveal marker okf-studio-unavailable is
    only ever ADDED (never removed), so its absence at load proves it was never
    set (no flash) while okf-studio-booted is present."""
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    # By DOMContentLoaded the boot outcome is settled (modules ran first).
    has_booted = dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-booted')"
    )
    assert has_booted, "studio did not boot before DOMContentLoaded"
    assert _banner_display(dark_page) == "none", "fallback banner visible after boot"
    unavailable = dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-unavailable')"
    )
    assert not unavailable, "okf-studio-unavailable was set during a successful boot"


def test_no_transient_banner_flash_during_successful_boot_rAF(server_url, dark_page):
    """Paint-crossing proof: across multiple rAF frames during a normal
    successful boot, the --js banner is NEVER visible (not even for one frame).
    This catches a regression where the banner flashes before okf-studio-booted
    is stamped — the exact P1 defect (premature ready class hiding failures
    was the inverse, but a transient flash on the success path is the
    complementary symptom)."""
    _install_banner_display_sampler(dark_page)
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    dark_page.wait_for_timeout(200)  # let rAF sampler collect frames
    samples = dark_page.evaluate("window.__okfBannerSamples")
    assert samples, "banner sampler did not collect any frames"
    visible_frames = [i for i, d in enumerate(samples) if d == "block"]
    assert not visible_frames, (
        f"banner was visible in frames {visible_frames} during successful boot: {samples!r}"
    )
    # Final settled state is also correct.
    assert _banner_display(dark_page) == "none"


def test_no_banner_flash_on_native_link_navigation(server_url, dark_page):
    """Same guarantee across a native internal link navigation. Uses rAF
    banner sampling on the destination to prove no transient flash."""
    _install_banner_display_sampler(dark_page)
    dark_page.goto(f"{server_url}/", wait_until="domcontentloaded")
    link = dark_page.query_selector(f'a[href="{CONCEPT}"]') or dark_page.query_selector(
        'a[href^="/tables/"]'
    )
    assert link is not None, "no concept link"
    with dark_page.expect_navigation(wait_until="domcontentloaded"):
        link.click()
    dark_page.wait_for_function(
        "() => document.documentElement.classList.contains('okf-studio-booted')",
        timeout=10000,
    )
    assert _banner_display(dark_page) == "none"
    unavailable = dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-unavailable')"
    )
    assert not unavailable, "banner flashed during native navigation"
    dark_page.wait_for_timeout(200)
    samples = dark_page.evaluate("window.__okfBannerSamples")
    if samples:
        visible_frames = [i for i, d in enumerate(samples) if d == "block"]
        assert not visible_frames, (
            f"banner visible in frames {visible_frames} during native navigation: {samples!r}"
        )


def test_banner_visible_when_studio_blocked(server_url, light_page):
    """Genuine failure: blocking studio.js must still reveal the banner (the
    watchdog adds okf-studio-unavailable at DOMContentLoaded)."""

    def block_studio(route):
        if "studio.js" in route.request.url:
            route.abort()
        else:
            route.continue_()

    light_page.route("**/*", block_studio)
    light_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    light_page.wait_for_timeout(300)  # past DOMContentLoaded settlement
    assert _count_visible_banners(light_page) == 1, "failure banner did not appear"
    assert light_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-unavailable')"
    ), "watchdog did not mark studio unavailable"


def test_module_evaluation_failure_watchdog(server_url, dark_page):
    """Module-evaluation failure: studio.js loads and begins evaluating, but
    the module-scope code throws before _runBoot is reached (so boot() is
    never called and window.okfLoomStudio is never assigned). The theme.js
    watchdog must catch this — it adds okf-studio-unavailable at
    DOMContentLoaded because okf-studio-booted is absent.

    This is the "no module" watchdog path, NOT a boot() failure. Contrast
    with test_boot_failure_after_genuine_mutation below, which proves the
    distinct "boot() genuinely ran then threw" path.

    Mechanism: break the first Node.prototype.appendChild call. The bar is
    assembled at module-evaluation scope (before boot), so the throw crashes
    module evaluation. The override self-heals after one throw so other
    scripts are unaffected.
    """
    dark_page.add_init_script(
        """
        var _orig = Node.prototype.appendChild;
        Node.prototype.appendChild = function(child) {
            Node.prototype.appendChild = _orig;
            throw new Error("test: simulated module-eval failure");
        };
        """
    )
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    dark_page.wait_for_timeout(300)  # past DOMContentLoaded settlement

    # Module evaluation threw, so the studio API was never published.
    assert not dark_page.evaluate(
        "typeof window.okfLoomStudio === 'object'"
    ), "studio API should not exist when module eval threw"
    # The watchdog caught it: unavailable stamped, booted absent.
    assert dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-unavailable')"
    ), "watchdog did not mark studio unavailable after module-eval failure"
    assert not dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-booted')"
    ), "okf-studio-booted must never be stamped when module eval threw"
    # The failure banner is revealed.
    assert _banner_display(dark_page) == "block", (
        "failure banner not visible after module-eval failure"
    )
    assert _count_visible_banners(dark_page) == 1


def test_boot_failure_after_genuine_mutation(server_url, dark_page):
    """Direct boot() failure proof (P1 contract item 1, genuine-mutation case).

    studio.js loads and evaluates completely (window.okfLoomStudio IS
    assigned), boot() begins executing and performs genuine DOM mutations
    (mountBar appends the studio bar to document.body), THEN throws.

    This is the exact P1 scenario the _runBoot wrapper was built for: the OLD
    code stamped okf-studio-booted at module evaluation (before boot ran), so
    the theme.js watchdog saw the class at DOMContentLoaded and permanently
    hid the failure banner. After the fix, boot() throwing must stamp
    okf-studio-unavailable so the banner is revealed.

    Mechan: the inert test-only _bootProbe("post-mount") seam (see studio.js)
    fires AFTER mountBar() + mountNavToggle() completed — i.e. after at least
    one genuine boot() DOM mutation. The probe throws, boot() throws, and
    _runBoot's catch stamps unavailable.
    """
    dark_page.add_init_script(
        """
        window.__okfBootProbe = function(phase) {
            if (phase === 'post-mount') {
                throw new Error("test: simulated boot failure after genuine mutation");
            }
        };
        """
    )
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    dark_page.wait_for_timeout(300)  # past DOMContentLoaded settlement

    # The studio MODULE evaluated completely (this is the key distinction
    # from a module-evaluation failure).
    assert dark_page.evaluate(
        "typeof window.okfLoomStudio === 'object'"
    ), "studio module should have loaded (API published) before boot() threw"

    # boot() genuinely mutated the DOM before throwing: the studio bar was
    # appended to document.body by mountBar() (the probe fires AFTER that).
    assert dark_page.evaluate(
        "!!document.querySelector('.okf-studio-bar')"
    ), "studio bar should be in the DOM — boot() performed a genuine mutation"

    # boot() threw → unavailable stamped, booted absent.
    assert dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-unavailable')"
    ), "boot() threw after a genuine mutation but unavailable was not stamped"
    assert not dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-booted')"
    ), "okf-studio-booted must not be stamped when boot() threw"

    # The failure banner is revealed and stable.
    assert _banner_display(dark_page) == "block", (
        "failure banner not visible after boot() threw post-mutation"
    )
    assert _count_visible_banners(dark_page) == 1
    dark_page.wait_for_timeout(150)
    assert _banner_display(dark_page) == "block", "banner not stable after wait"


def test_late_async_tail_cannot_overwrite_unavailable(server_url, dark_page):
    """Late-tail safety proof (P1 contract item 1, late-result case).

    boot() runs all the way to the end — dispatching loadGraph,
    loadComments, tokenFetch promises and the 400ms rebuildMarginMarkers
    timer — THEN throws at the post-async-kick probe. _runBoot stamps
    unavailable. The in-flight async tails subsequently resolve/reject over
    the next several hundred milliseconds.

    Contract: those late tails MUST NOT replace okf-studio-unavailable with
    okf-studio-booted, MUST NOT remove the unavailable class, and MUST NOT
    hide the failure banner. The settlement is terminal and one-way; the
    async tails have no code path to _settleBoot.
    """
    dark_page.add_init_script(
        """
        window.__okfBootProbe = function(phase) {
            if (phase === 'post-async-kick') {
                throw new Error("test: boot threw after async tails dispatched");
            }
        };
        """
    )
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")

    # At DOMContentLoaded, boot() has already thrown and unavailable is stamped.
    assert dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-unavailable')"
    ), "unavailable should be stamped immediately after boot threw"

    # Snapshot the settlement state, then wait long enough for ALL late tails
    # to resolve: the 400ms rebuildMarginMarkers timer, plus loadGraph/
    # loadComments/tokenFetch fetch round-trips (typically <100ms locally).
    def settlement():
        return dark_page.evaluate("""() => ({
            booted: document.documentElement.classList.contains('okf-studio-booted'),
            unavailable: document.documentElement.classList.contains('okf-studio-unavailable'),
            banner: (() => {
                var b = document.querySelector('.okf-studio-fallback-banner--js');
                return b ? getComputedStyle(b).display : 'absent';
            })(),
        })""")

    s0 = settlement()
    assert s0["unavailable"] and not s0["booted"], (
        f"initial settlement wrong: {s0!r}"
    )
    assert s0["banner"] == "block", f"banner not visible initially: {s0!r}"

    # Wait well past the 400ms timer + fetch tails.
    dark_page.wait_for_timeout(900)

    s1 = settlement()
    assert s1["unavailable"], (
        "late async tail removed okf-studio-unavailable — settlement is NOT terminal"
    )
    assert not s1["booted"], (
        "late async tail stamped okf-studio-booted over unavailable — late-result leak"
    )
    assert s1["banner"] == "block", (
        "late async tail hid the failure banner — late-result leak"
    )


def test_banner_settlement_is_one_way_no_overwrite(server_url, dark_page):
    """One-way settlement invariant: once okf-studio-booted is stamped, it is
    never removed; okf-studio-unavailable is never added on top. This proves
    the settlement classes are additive-only (no race/overwrite)."""
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    dark_page.wait_for_timeout(300)
    has_booted = dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-booted')"
    )
    has_unavailable = dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-unavailable')"
    )
    assert has_booted, "studio should have booted successfully"
    assert not has_unavailable, (
        "okf-studio-unavailable must never coexist with okf-studio-booted"
    )
    # After additional time, the state must be unchanged (no late overwrite).
    dark_page.wait_for_timeout(300)
    has_booted_still = dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-booted')"
    )
    has_unavailable_still = dark_page.evaluate(
        "document.documentElement.classList.contains('okf-studio-unavailable')"
    )
    assert has_booted_still and not has_unavailable_still, (
        "boot settlement changed after settlement — not one-way"
    )


# ===========================================================================
# DESKTOP RECENTERING — rail reserve present at first paint, no animation
# ===========================================================================


def test_desktop_rail_reserve_present_before_load(server_url, dark_page):
    """The concept-page rail reserve (body padding-right) is present from the
    earliest measurable layout (DOMContentLoaded), not added after boot."""
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    pr = dark_page.evaluate("getComputedStyle(document.body).paddingRight")
    assert pr == "48px", f"desktop rail reserve not present at DOMContentLoaded: {pr!r}"


def test_no_paddingright_transition_on_navigation(server_url, dark_page):
    """No padding-right transitionend fires during navigation — the reserve is
    applied from first paint, so the centered page never animates/recentres."""
    _install_paddingright_transition_logger(dark_page)
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    dark_page.wait_for_timeout(500)  # well past any 0.2s transition window
    transitions = dark_page.evaluate("window.__okfPadTransitions")
    assert transitions == [], (
        f"a padding-right transition (recentering) fired during load: {transitions!r}"
    )


def test_concept_centerline_stable_across_load(server_url, dark_page):
    """The centered .okf-page's horizontal center AND client-width must not
    move between DOMContentLoaded and post-load (no desktop recentering).
    Client-width is checked alongside centerline so a content-box resize
    (e.g. the rail reserve kicking in late) is caught even if the centerline
    happens to stay put by coincidence."""
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")

    def geometry():
        return dark_page.evaluate(
            """() => {
                var el = document.querySelector('.okf-page') || document.getElementById('okf-main');
                if (!el) return null;
                var r = el.getBoundingClientRect();
                return {
                    center: Math.round(r.left + r.width / 2),
                    clientWidth: el.clientWidth,
                    left: Math.round(r.left),
                };
            }"""
        )

    g1 = geometry()
    assert g1 is not None, "no .okf-page / #okf-main to measure"
    dark_page.wait_for_timeout(500)
    g2 = geometry()
    assert g1["center"] == g2["center"], (
        f"concept centerline moved during load: {g1['center']} -> {g2['center']}"
    )
    assert g1["clientWidth"] == g2["clientWidth"], (
        f"concept client-width changed during load: {g1['clientWidth']} -> {g2['clientWidth']}"
    )


def test_mobile_has_no_rail_reserve(server_url, mobile_page):
    """At <=900px the concept page keeps no rail reserve (mobile layout)."""
    mobile_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    pr = mobile_page.evaluate("getComputedStyle(document.body).paddingRight")
    assert pr == "0px", f"mobile should have no rail reserve, got {pr!r}"


def test_nojs_desktop_has_no_rail_gutter(server_url, nojs_desktop_page):
    """With JS off the rail can never be built, so the reserve must NOT apply
    even on a wide concept page — no dead 48px gutter in the read-only view."""
    nojs_desktop_page.goto(f"{server_url}{CONCEPT}", wait_until="load")
    nojs_desktop_page.wait_for_timeout(200)
    pr = nojs_desktop_page.evaluate("getComputedStyle(document.body).paddingRight")
    assert pr == "0px", f"no-JS desktop should have no rail reserve, got {pr!r}"
    # And the no-JS fallback banner is still the single visible banner.
    assert _count_visible_banners(nojs_desktop_page) == 1


# ===========================================================================
# FRAME GEOMETRY — paint-crossing centerline + documentElement width
# (P1 contract item 3: frame-sampled geometry alongside theme/banner sampling)
# ===========================================================================


def test_desktop_frame_geometry_stable_across_first_paints(server_url, dark_page):
    """Paint-crossing proof: across the first ~8 rAF frames on a desktop
    concept page, the .okf-page centerline and documentElement client/scroll
    width never shift. This catches a late rail-reserve application that a
    settled-only check would miss — the recentering happens BETWEEN paints."""
    _install_frame_geometry_sampler(dark_page)
    dark_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    dark_page.wait_for_timeout(250)  # let the rAF sampler collect frames
    samples = dark_page.evaluate("window.__okfFrameGeo")
    assert samples and len(samples) >= 3, (
        f"frame geometry sampler did not collect enough frames: {samples!r}"
    )
    centers = [s["center"] for s in samples if s["center"] is not None]
    clientWs = [s["clientW"] for s in samples if s["clientW"] is not None]
    assert len(set(centers)) == 1, (
        f"centerline shifted across first paints: {centers!r}"
    )
    assert len(set(clientWs)) == 1, (
        f"clientWidth shifted across first paints: {clientWs!r}"
    )
    # No document-level horizontal overflow at desktop width.
    overflow = [s for s in samples if s["deScrollW"] > s["deClientW"] + 1]
    assert not overflow, f"document overflow in early frames: {overflow!r}"


def test_mobile_frame_geometry_stable_no_overflow(server_url, mobile_page):
    """Paint-crossing proof at mobile width: the concept centerline is stable
    across first paints AND documentElement never overflows horizontally
    (the table is locally contained, not document-wide)."""
    _install_frame_geometry_sampler(mobile_page)
    mobile_page.goto(f"{server_url}{CONCEPT}", wait_until="domcontentloaded")
    mobile_page.wait_for_timeout(250)
    samples = mobile_page.evaluate("window.__okfFrameGeo")
    assert samples and len(samples) >= 3, (
        f"frame geometry sampler did not collect enough frames: {samples!r}"
    )
    centers = [s["center"] for s in samples if s["center"] is not None]
    assert len(set(centers)) == 1, (
        f"mobile centerline shifted across first paints: {centers!r}"
    )
    overflow = [s for s in samples if s["deScrollW"] > s["deClientW"] + 1]
    assert not overflow, (
        f"mobile document overflow in early frames (table not contained): {overflow!r}"
    )


def test_frame_geometry_stable_via_native_link_navigation(server_url, dark_page):
    """Same frame-geometry stability proof, but reached via a native internal
    <a> click (no link interception). The destination must not recenter or
    overflow during its first paints."""
    _install_frame_geometry_sampler(dark_page)
    dark_page.goto(f"{server_url}/", wait_until="domcontentloaded")
    link = dark_page.query_selector(f'a[href="{CONCEPT}"]') or dark_page.query_selector(
        'a[href^="/tables/"]'
    )
    assert link is not None, "no concept link"
    with dark_page.expect_navigation(wait_until="domcontentloaded"):
        link.click()
    dark_page.wait_for_timeout(250)
    samples = dark_page.evaluate("window.__okfFrameGeo")
    assert samples and len(samples) >= 3, (
        f"frame sampler did not run on destination: {samples!r}"
    )
    centers = [s["center"] for s in samples if s["center"] is not None]
    clientWs = [s["clientW"] for s in samples if s["clientW"] is not None]
    assert len(set(centers)) == 1, (
        f"centerline shifted on native-link destination: {centers!r}"
    )
    assert len(set(clientWs)) == 1, (
        f"clientWidth shifted on native-link destination: {clientWs!r}"
    )


def test_nojs_desktop_geometry_no_overflow(server_url, nojs_desktop_page):
    """No-JS desktop: no rail gutter (JS never runs), no document overflow,
    and the concept content is reachable within the viewport width."""
    nojs_desktop_page.goto(f"{server_url}{CONCEPT}", wait_until="load")
    nojs_desktop_page.wait_for_timeout(200)
    geo = nojs_desktop_page.evaluate(
        """() => ({
            deSW: document.documentElement.scrollWidth,
            deCW: document.documentElement.clientWidth,
            paddingRight: getComputedStyle(document.body).paddingRight,
        })"""
    )
    assert geo["deSW"] <= geo["deCW"] + 1, (
        f"no-JS desktop document overflow: {geo!r}"
    )
    assert geo["paddingRight"] == "0px", (
        f"no-JS desktop should have no rail gutter: {geo!r}"
    )


# ===========================================================================
# Native navigation semantics preserved (no interception)
# ===========================================================================


def _find_concept_link(page):
    """Find a native internal concept link on the current page."""
    return page.query_selector(f'a[href="{CONCEPT}"]') or page.query_selector(
        'a[href^="/tables/"]'
    )


def test_native_back_forward_after_link_navigation(server_url, dark_page):
    """Native anchor navigation keeps working with the browser's own history:
    a real <a> click, then Back, returns to the origin document; then Forward
    returns to the destination (P1 contract item 4: Back AND Forward)."""
    dark_page.goto(f"{server_url}/", wait_until="domcontentloaded")
    origin = dark_page.url
    link = _find_concept_link(dark_page)
    assert link is not None, "no concept link"
    with dark_page.expect_navigation(wait_until="domcontentloaded"):
        link.click()
    assert dark_page.url.endswith(CONCEPT), dark_page.url
    # Browser-native Back.
    dark_page.go_back()
    dark_page.wait_for_load_state("domcontentloaded")
    assert dark_page.url.rstrip("/").endswith(origin.rstrip("/")) or dark_page.url == origin, (
        f"Back did not return to origin: {dark_page.url!r} vs {origin!r}"
    )
    # Browser-native Forward returns to the destination.
    dark_page.go_forward()
    dark_page.wait_for_load_state("domcontentloaded")
    assert dark_page.url.endswith(CONCEPT), (
        f"Forward did not return to destination: {dark_page.url!r}"
    )


def test_native_enter_key_navigates_focused_anchor(server_url, dark_page):
    """Keyboard navigation: focusing a real internal <a> and pressing Enter
    performs a native navigation (no link interception, no custom handler).
    This proves keyboard users can navigate via real anchors."""
    dark_page.goto(f"{server_url}/", wait_until="domcontentloaded")
    link = _find_concept_link(dark_page)
    assert link is not None, "no concept link"
    link.focus()
    with dark_page.expect_navigation(wait_until="domcontentloaded"):
        dark_page.keyboard.press("Enter")
    assert dark_page.url.endswith(CONCEPT), (
        f"Enter on focused anchor did not navigate: {dark_page.url!r}"
    )


def test_native_ctrl_click_opens_new_tab(server_url, dark_page):
    """Ctrl/Cmd-click on a real internal <a> opens a new tab (native browser
    behaviour), proving no click interceptor captures or preventDefaults the
    modifier-click. The studio does NOT intercept links into a SPA shell."""
    dark_page.goto(f"{server_url}/", wait_until="domcontentloaded")
    link = _find_concept_link(dark_page)
    assert link is not None, "no concept link"
    href = link.get_attribute("href")
    assert href, "concept link has no href"
    # Ctrl-click (meta on mac) opens a new context (tab). We assert a new
    # page event fires — the browser's own modifier semantics, not a JS
    # handler. No SPA interception means the browser handles it natively.
    with dark_page.context.expect_page(timeout=5000) as new_page_info:
        link.click(modifiers=["Control"])
    new_page = new_page_info.value
    try:
        # A popup first exists as about:blank, whose DOMContentLoaded state is
        # already satisfied. Wait for the destination URL rather than treating
        # that transient initial document as the new tab's final navigation.
        new_page.wait_for_url(f"**{href}", wait_until="domcontentloaded", timeout=5000)
        assert new_page.url.endswith(href), (
            f"Ctrl-click new tab URL mismatch: {new_page.url!r} vs {href!r}"
        )
    finally:
        new_page.close()
    # The original page must NOT have navigated (background-tab semantics).
    assert not dark_page.url.endswith(CONCEPT), (
        f"original page navigated on Ctrl-click (interceptor?): {dark_page.url!r}"
    )


# ===========================================================================
# NO-JS TABLE CONTAINEMENT — real java_script_enabled=False proof
# (P1 contract item 2: actual no-JS browser context at mobile width)
# ===========================================================================


def test_nojs_mobile_table_no_enhancer_and_scrollable(server_url, nojs_mobile_page):
    """Genuine no-JS proof at mobile width (P1 contract item 2).

    With ``java_script_enabled=False`` the renderers.js enhancer NEVER runs,
    so there must be NO ``.okf-tablewrap`` wrapper, NO ``--fit``/``--overflow``
    classes, NO role/tabindex/cue on a wrapper. The bare ``.okf-table``
    (``display: block; overflow-x: auto``) must still scroll horizontally so
    all columns are reachable, the document must not overflow horizontally,
    AND the table itself must be a keyboard-focusable scrollport: it carries
    the server-side fallback ``tabindex="0"`` + accessible name/instruction
    (``aria-label``) while keeping its implicit table role (no role override).

    This replaces the old ``test_nojs_table_still_scrolls`` which ran in a
    JS-ENABLED context and could only inspect pre-enhancement CSS — never a
    real no-JS proof."""
    pg = nojs_mobile_page
    pg.goto(f"{server_url}{CONCEPT}", wait_until="load")
    pg.wait_for_timeout(300)

    info = pg.evaluate(
        """() => {
            var de = document.documentElement;
            var table = document.querySelector('table.okf-table');
            var wrap = document.querySelector('.okf-tablewrap');
            return {
                hasWrapper: !!wrap,
                docSW: de.scrollWidth,
                docCW: de.clientWidth,
                tableOverX: table ? getComputedStyle(table).overflowX : null,
                tableDisplay: table ? getComputedStyle(table).display : null,
                tableSW: table ? table.scrollWidth : null,
                tableCW: table ? table.clientWidth : null,
                tableTabindex: table ? table.getAttribute('tabindex') : null,
                tableRole: table ? table.getAttribute('role') : null,
                tableAriaLabel: table ? table.getAttribute('aria-label') : null,
                tableFallback: table ? table.getAttribute('data-okf-fallback') : null,
                jsEnabled: typeof window.okfLoomStudio !== 'undefined',
            };
        }"""
    )
    # JavaScript genuinely did not run: no studio API, no enhancer wrapper.
    assert not info["jsEnabled"], "JS ran in a no-JS context — fixture broken"
    assert not info["hasWrapper"], (
        ".okf-tablewrap enhancer exists without JS — enhancer leaked into SSR"
    )
    # The bare table retains its scroll CSS so it is independently scrollable.
    assert info["tableOverX"] in ("auto", "scroll"), (
        f"bare table must retain overflow-x scroll CSS, got {info['tableOverX']!r}"
    )
    assert info["tableDisplay"] == "block", (
        f"no-JS table must use the static display:block scrollport, "
        f"got {info['tableDisplay']!r}"
    )
    assert info["tableSW"] > info["tableCW"], (
        f"bare table should overflow (scrollable) at mobile: SW={info['tableSW']} CW={info['tableCW']}"
    )
    # Document-level width containment: no horizontal page scrollbar.
    assert info["docSW"] <= info["docCW"] + 1, (
        f"no-JS mobile document overflow: docSW={info['docSW']} docCW={info['docCW']}"
    )
    # P1 no-JS keyboard focusability: the bare table is the scrollport, so it
    # MUST itself be a keyboard-focusable region with an accessible name +
    # instruction, while keeping native table semantics (no role override).
    assert info["tableTabindex"] == "0", (
        f"no-JS table must carry the server fallback tabindex=0, "
        f"got {info['tableTabindex']!r}"
    )
    assert info["tableRole"] is None, (
        "no-JS table must keep its implicit table role (no role override)"
    )
    assert info["tableFallback"] == "tabbable", (
        "no-JS table must carry the data-okf-fallback marker for transfer"
    )
    assert info["tableAriaLabel"], "no-JS table must have an accessible name"
    assert "table" in info["tableAriaLabel"].lower(), info["tableAriaLabel"]
    assert "scroll" in info["tableAriaLabel"].lower(), (
        f"accessible name must include the scroll instruction: {info['tableAriaLabel']!r}"
    )


def test_nojs_mobile_table_reachable_by_tab(server_url, nojs_mobile_page):
    """No-JS mobile: the bare table is keyboard-reachable AND keyboard-scrollable.

    Real ``java_script_enabled=False`` proof (P1 contract item 1): we drive the
    page ONLY with native keyboard input (no JS scrollLeft mutation) and observe
    the result via Playwright's isolated evaluate context.

      1. Tab forward from the freshly-loaded document until focus lands on the
         table — proves the server fallback ``tabindex="0"`` puts it in the tab
         order (the focus TARGET is the table element).
      2. Press ArrowRight on the focused table — ``scrollLeft`` must increase,
         proving a no-JS keyboard user can drive the horizontal scroll.
      3. Press End to jump to the far right — the last column header must land
         inside the table's visible client area, proving EVERY off-screen column
         is reachable by keyboard scroll with no JS enhancer.

    Without the server fallback this was impossible: a bare ``<table>`` is not
    focusable, so arrow keys did nothing and off-screen columns were unreachable.
    """
    pg = nojs_mobile_page
    pg.goto(f"{server_url}{CONCEPT}", wait_until="load")
    pg.wait_for_timeout(200)

    # (1) Keyboard-navigate to the table. Tab is a real keyboard event; the
    # loop only OBSERVES activeElement to detect arrival (no JS mutation).
    focused_table = False
    for _ in range(80):
        pg.keyboard.press("Tab")
        if pg.evaluate(
            "document.activeElement && document.activeElement.tagName === 'TABLE'"
        ):
            focused_table = True
            break
    assert focused_table, "Tab never reached the no-JS table — not in tab order"

    # The focus target is genuinely the bare table (not a wrapper: JS is off).
    active = pg.evaluate(
        """() => {
            var el = document.activeElement;
            return {
                tag: el ? el.tagName : null,
                cls: el ? el.className : null,
                tabindex: el ? el.getAttribute('tabindex') : null,
                hasWrapper: !!document.querySelector('.okf-tablewrap'),
            };
        }"""
    )
    assert active["tag"] == "TABLE", f"focus target is not the table: {active!r}"
    assert active["tabindex"] == "0", "focused table must carry tabindex=0"
    assert not active["hasWrapper"], "no enhancer wrapper may exist without JS"

    # (2) A real ArrowRight keypress must scroll the focused scrollport.
    # A short frame-settle yield lets the browser apply the keyboard-driven
    # scroll before observation (keyboard scroll lands on the next frame) —
    # this is a single deterministic yield, not a retry/poll.
    before = pg.evaluate("document.activeElement.scrollLeft")
    pg.keyboard.press("ArrowRight")
    pg.wait_for_timeout(60)
    after = pg.evaluate("document.activeElement.scrollLeft")
    assert after > before, (
        f"ArrowRight did not scroll the no-JS table: before={before} after={after}"
    )

    # (3) Reach the far right with repeated ArrowRight (the canonical
    # horizontal-scroll key — more portable than End, whose horizontal mapping
    # is browser-specific). Stop once scrollLeft stops advancing, then prove the
    # LAST column header is inside the table's visible client area: every
    # off-screen column is reachable by keyboard scroll with no JS enhancer.
    prev = -1
    for _ in range(80):
        pg.keyboard.press("ArrowRight")
        pg.wait_for_timeout(30)
        sl = pg.evaluate("document.activeElement.scrollLeft")
        if sl == prev:
            break
        prev = sl
    reached = pg.evaluate(
        """() => {
            var t = document.activeElement;
            var headers = t.querySelectorAll('th');
            var last = headers[headers.length - 1];
            var tr = last.getBoundingClientRect();
            var trect = t.getBoundingClientRect();
            return {
                scrollLeft: t.scrollLeft,
                maxScroll: t.scrollWidth - t.clientWidth,
                lastRight: Math.round(tr.right),
                tableLeft: Math.round(trect.left),
                tableCW: t.clientWidth,
                lastText: last.textContent.trim(),
            };
        }"""
    )
    assert reached["scrollLeft"] >= reached["maxScroll"] - 1, (
        f"keyboard scroll did not reach the far right: "
        f"scrollLeft={reached['scrollLeft']} maxScroll={reached['maxScroll']}"
    )
    # The last column's right edge is within the visible client area.
    visible_right = reached["tableLeft"] + reached["tableCW"]
    assert reached["lastRight"] <= visible_right + 1, (
        f"last column '{reached['lastText']}' not reachable by keyboard scroll: "
        f"lastRight={reached['lastRight']} visibleRight={visible_right}"
    )


# ===========================================================================
# NO-JS STATIC FIRST-LAYOUT GEOMETRY — durable earliest-available proof
# (P1 contract item 2: no delayed settled assertion, no JS frame sampler)
# ===========================================================================


def test_nojs_geometry_is_static_at_first_layout(server_url, nojs_mobile_page):
    """Durable no-JS earliest-available geometry proof (P1 contract item 2).

    Why rAF frame sampling is UNAVAILABLE here: the page is loaded with
    ``java_script_enabled=False``, so NO scripts execute and
    ``requestAnimationFrame`` callbacks never fire. A JS-driven frame sampler
    therefore cannot observe a transition timeline — and there is nothing to
    sample, because with JS off there is no async settlement. The durable
    proof is therefore a STATIC document/CSS invariant captured at the
    EARLIEST point geometry is available (the ``load`` event, after stylesheets
    are applied), with NO arbitrary sleep / retry / poll.

    Captured immediately on ``load``:
      * no settlement classes on <html> — proves no JS boot transition exists
        or is pending (there is no enhancer to settle the table either);
      * the table uses the static fallback CSS (``display:block;
        overflow-x:auto``) — geometry is driven by the stylesheet, not a
        runtime class swap, so it is final at first layout;
      * document width is contained (no horizontal page overflow);
      * a zero-delay re-read is byte-identical — proves no async drift (the
        no-JS document is immutable after ``load``).
    """
    pg = nojs_mobile_page
    # wait_until="load" is the deterministic earliest-available layout signal
    # (all CSS parsed + applied). No wait_for_timeout / retry is used as proof.
    pg.goto(f"{server_url}{CONCEPT}", wait_until="load")

    def _snapshot():
        return pg.evaluate(
            """() => {
                var de = document.documentElement;
                var html = de.classList.toString();
                var table = document.querySelector('table.okf-table');
                var cs = table ? getComputedStyle(table) : null;
                return {
                    docSW: de.scrollWidth,
                    docCW: de.clientWidth,
                    htmlClasses: html,
                    booted: de.classList.contains('okf-studio-booted'),
                    unavailable: de.classList.contains('okf-studio-unavailable'),
                    hasWrapper: !!document.querySelector('.okf-tablewrap'),
                    tableDisplay: cs ? cs.display : null,
                    tableOverX: cs ? cs.overflowX : null,
                    tableSW: table ? table.scrollWidth : null,
                    tableCW: table ? table.clientWidth : null,
                    jsEnabled: typeof window.okfLoomStudio !== 'undefined',
                };
            }"""
        )

    g1 = _snapshot()

    # JS is genuinely off: no studio API, no settlement classes, no enhancer.
    assert not g1["jsEnabled"], "JS ran in a no-JS context — fixture broken"
    assert not g1["booted"], "okf-studio-booted present without JS"
    assert not g1["unavailable"], "okf-studio-unavailable present without JS"
    assert g1["htmlClasses"] == "", (
        f"no-JS <html> must carry no settlement classes, got {g1['htmlClasses']!r}"
    )
    assert not g1["hasWrapper"], "enhancer wrapper present without JS"

    # Geometry is the static CSS fallback, final at first layout.
    assert g1["tableDisplay"] == "block", (
        f"static table display must be block (scrollport), got {g1['tableDisplay']!r}"
    )
    assert g1["tableOverX"] in ("auto", "scroll"), (
        f"static table overflow-x must be a scroll value, got {g1['tableOverX']!r}"
    )
    assert g1["docSW"] <= g1["docCW"] + 1, (
        f"no-JS document overflow at first layout: docSW={g1['docSW']} docCW={g1['docCW']}"
    )

    # Durable: a zero-delay re-read is identical — nothing settles in no-JS.
    g2 = _snapshot()
    assert g1 == g2, (
        f"no-JS geometry drifted between immediate reads (no async expected): "
        f"{g1!r} vs {g2!r}"
    )


# ===========================================================================
# LIVE TABLE PATCH LIFECYCLE — body patch via okf-loom:bodyPatched enhancer
# (P1 contract item 5: real insert/replace through the live enhancer path)
# ===========================================================================


_WIDE_TABLE_HTML = """
<table class="okf-table" tabindex="0"
  aria-label="Table. Scroll horizontally to view all columns."
  data-okf-fallback="tabbable">
<thead><tr><th>Col A</th><th>Col B</th><th>Col C</th><th>Col D</th><th>Col E</th>
<th>Col F</th><th>Col G</th><th>Col H</th><th>Col I</th><th>Col J</th></tr></thead>
<tbody>
<tr><td>alpha-001</td><td>beta-002</td><td>gamma-003</td><td>delta-004</td><td>epsilon-005</td>
<td>zeta-006</td><td>eta-007</td><td>theta-008</td><td>iota-009</td><td>kappa-010</td></tr>
<tr><td>alpha-011</td><td>beta-012</td><td>gamma-013</td><td>delta-014</td><td>epsilon-015</td>
<td>zeta-016</td><td>eta-017</td><td>theta-018</td><td>iota-019</td><td>kappa-020</td></tr>
<tr><td>alpha-021</td><td>beta-022</td><td>gamma-023</td><td>delta-024</td><td>epsilon-025</td>
<td>zeta-026</td><td>eta-027</td><td>theta-028</td><td>iota-029</td><td>kappa-030</td></tr>
</tbody>
</table>
"""

_FIT_TABLE_HTML = """
<table class="okf-table" tabindex="0"
  aria-label="Table. Scroll horizontally to view all columns."
  data-okf-fallback="tabbable">
<thead><tr><th>Name</th><th>Value</th></tr></thead>
<tbody><tr><td>alpha</td><td>1</td></tr></tbody>
</table>
"""


def _patch_body_table(page, html):
    """Simulate the live studio patch path: replace the body table with the
    given HTML, then dispatch the real ``okf-loom:bodyPatched`` event so
    renderers.js's initAll re-scans and enhances the fresh table — exactly
    what live.js/studio.js do after a server-side concept change."""
    page.evaluate(
        """(html) => {
            var body = document.querySelector('.okf-page__body');
            if (!body) return false;
            var old = body.querySelector('table.okf-table');
            if (old) {
                var wrap = old.closest('.okf-tablewrap');
                if (wrap) wrap.remove();
                else old.remove();
            }
            var tpl = document.createElement('div');
            tpl.innerHTML = html.trim();
            var newTable = tpl.firstElementChild;
            body.appendChild(newTable);
            window.dispatchEvent(new CustomEvent('okf-loom:bodyPatched'));
            return true;
        }""",
        html,
    )


def _table_wrap_info_live(page):
    """Table wrapper info for the LAST table on the page (the patched one)."""
    return page.evaluate(
        """() => {
            var html = document.documentElement;
            var wraps = document.querySelectorAll('.okf-tablewrap');
            var wrap = wraps[wraps.length - 1];
            if (!wrap) return null;
            var cue = wrap.querySelector('.okf-table-cue');
            var table = wrap.querySelector('table');
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
                rowCount: table ? table.rows.length : 0,
                // Inner-table fallback-affordance state (transfer proof).
                tableTabindex: table ? table.getAttribute('tabindex') : null,
                tableAriaLabel: table ? table.getAttribute('aria-label') : null,
                tableFallback: table ? table.getAttribute('data-okf-fallback') : null,
            };
        }"""
    )


def test_live_patch_inserts_overflowing_table_with_affordance(server_url, page):
    """Live body patch inserts an overflowing table at mobile width via the
    real ``okf-loom:bodyPatched`` enhancer path. The enhancer must wrap it,
    classify it as overflow, add the full accessibility affordance (role,
    tabindex, aria-label, cue, edge-state), keep keyboard scroll working,
    and contain the width locally (no document overflow)."""
    page.set_viewport_size({"width": 414, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_timeout(300)

    # Insert a wide (overflowing) table via the live patch path.
    _patch_body_table(page, _WIDE_TABLE_HTML)
    page.wait_for_timeout(500)  # past the 150ms debounce reclassify

    info = _table_wrap_info_live(page)
    assert info, "no table wrapper after live patch — enhancer did not re-run"
    assert info["rowCount"] >= 4, "patched table not enhanced (rows include header)"
    assert info["wrapOverflows"], (
        f"patched table should overflow at 414px: SW={info['wrapSW']} CW={info['wrapCW']}"
    )
    assert "okf-tablewrap--overflow" in info["cls"]
    assert "okf-tablewrap--fit" not in info["cls"], "fit+overflow must be mutually exclusive"
    assert info["role"] == "region", "wrapper must have role=region on overflow"
    assert info["tabindex"] == "0", "wrapper must be keyboard-focusable on overflow"
    assert info["ariaLabel"], "wrapper must have an accessible name on overflow"
    assert info["hasCue"], "visible scroll cue must be present on overflow"
    assert info["cueText"], "cue must have text"
    assert info["dataScroll"] in ("start", "middle", "end"), "edge state must be set"
    # Transfer proof: the patched table carried the no-JS fallback affordance
    # (data-okf-fallback="tabbable"); enhanceTable must have stripped it from
    # the table even though the wrapper re-acquires the affordance on overflow.
    assert info["tableFallback"] is None, (
        f"live-patched overflow table kept the data-okf-fallback marker, "
        f"got {info['tableFallback']!r}"
    )
    assert info["tableTabindex"] is None, (
        f"live-patched overflow table kept the no-JS fallback tabindex, "
        f"got {info['tableTabindex']!r}"
    )
    # Width containment: no document-level horizontal overflow.
    assert info["docSW"] <= info["docCW"] + 1, (
        f"live-patched table caused document overflow: docSW={info['docSW']} docCW={info['docCW']}"
    )

    # Keyboard scroll works on the live-enhanced overflow region.
    page.evaluate(
        """() => {
            var wraps = document.querySelectorAll('.okf-tablewrap');
            wraps[wraps.length - 1].focus();
        }"""
    )
    before = page.evaluate(
        """() => {
            var wraps = document.querySelectorAll('.okf-tablewrap');
            return wraps[wraps.length - 1].scrollLeft;
        }"""
    )
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(100)
    after = page.evaluate(
        """() => {
            var wraps = document.querySelectorAll('.okf-tablewrap');
            return wraps[wraps.length - 1].scrollLeft;
        }"""
    )
    assert after > before, (
        f"ArrowRight did not scroll the live-enhanced region: {before} -> {after}"
    )


def test_live_patch_replaces_overflow_with_fit_removes_affordance(server_url, page):
    """After the overflowing table is replaced with a fitting table via the
    live patch path, the stale overflow affordance (role, tabindex, cue,
    edge-state) must be REMOVED — the wrapper reclassifies to fit and reads
    as a plain table. This proves no stale ARIA/tab-stop leaks across live
    body patches."""
    page.set_viewport_size({"width": 414, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.wait_for_timeout(300)

    # Phase 1: insert overflowing table, confirm it is enhanced as overflow.
    _patch_body_table(page, _WIDE_TABLE_HTML)
    page.wait_for_timeout(500)
    info1 = _table_wrap_info_live(page)
    assert info1 and info1["wrapOverflows"], "precondition: first table should overflow"
    assert info1["hasCue"], "precondition: cue should be present on overflow"

    # Phase 2: replace with a narrow (fitting) table via the same live path.
    _patch_body_table(page, _FIT_TABLE_HTML)
    page.wait_for_timeout(500)

    info2 = _table_wrap_info_live(page)
    assert info2, "no table wrapper after replacing with fit table"
    assert not info2["wrapOverflows"], (
        f"narrow table should fit at 414px: SW={info2['wrapSW']} CW={info2['wrapCW']}"
    )
    assert "okf-tablewrap--fit" in info2["cls"], "wrapper should classify as fit"
    assert "okf-tablewrap--overflow" not in info2["cls"], (
        "stale --overflow class leaked after replacing with a fitting table"
    )
    assert info2["role"] is None, "stale role=region leaked on fit table"
    assert info2["tabindex"] is None, "stale tabindex leaked on fit table"
    assert info2["ariaLabel"] is None, "stale aria-label leaked on fit table"
    assert not info2["hasCue"], "stale scroll cue leaked on fit table"
    assert info2["dataScroll"] is None, "stale data-scroll leaked on fit table"
    # Transfer proof in the live patch path: the freshly-inserted table
    # carried the server fallback focus affordance (see _WIDE/_FIT_TABLE_HTML),
    # and the enhancer must have stripped it from the table so a fitting live
    # table is not an extra tab stop on the table element itself.
    assert info2["tableTabindex"] is None, (
        f"live-patched fit table kept the no-JS fallback tabindex, "
        f"got {info2['tableTabindex']!r}"
    )
    assert info2["tableAriaLabel"] is None, (
        f"live-patched fit table kept the no-JS fallback aria-label"
    )
    assert info2["tableFallback"] is None, (
        f"live-patched fit table kept the data-okf-fallback marker, "
        f"got {info2['tableFallback']!r}"
    )
    # Width containment holds.
    assert info2["docSW"] <= info2["docCW"] + 1, "document overflow after fit replace"
