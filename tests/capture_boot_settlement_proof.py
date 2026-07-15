"""Capture fresh proof screenshots for the first-paint boot-settlement slice.

Stands up ``okf serve samples/demo_bundle`` (studio on), drives Chrome to the
concept page in each terminal state, and writes PNGs under
``docs/screenshots/boot-settlement/``. Also writes a provenance manifest
mapping each screenshot to its scenario, viewport, command, and terminal state.

Run:  python3 tests/capture_boot_settlement_proof.py
"""
from __future__ import annotations

import json
import os
import platform
import shlex
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

TK = Path(__file__).resolve().parent.parent
DEMO = TK / "samples" / "demo_bundle"
OUT = TK / "docs" / "screenshots" / "boot-settlement"
OUT.mkdir(parents=True, exist_ok=True)
CONCEPT = "/tables/orders"
DEVICE_SCALE_FACTOR = 1


def okf_env():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(TK / "scripts") + (os.pathsep + existing if existing else "")
    return env


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_up(base):
    dl = time.monotonic() + 15
    while time.monotonic() < dl:
        try:
            urllib.request.urlopen(base + "/", timeout=1)
            return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError("server not ready")


def git_identity():
    """Return the HEAD identity captured before the browser/server starts.

    Revision identifies the committed HEAD only; it deliberately does not
    imply that the working tree was clean when the screenshots were made.
    """
    def git_value(*args):
        try:
            return subprocess.run(
                ["git", *args], cwd=str(TK), check=True, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ).stdout.strip(), None
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", None)
            return None, (detail.strip() if detail else str(exc))

    revision, revision_error = git_value("rev-parse", "HEAD")
    branch, branch_error = git_value("symbolic-ref", "--short", "HEAD")
    return {
        "revision": revision,
        "revision_source": "git rev-parse HEAD",
        "revision_fallback": revision_error,
        "revision_scope": "HEAD commit only; working-tree modifications are not represented",
        "branch": branch,
        "branch_source": "git symbolic-ref --short HEAD",
        "branch_fallback": branch_error,
    }


def launch(p):
    chrome = os.environ.get("AIC_PLAYWRIGHT_CHROME_PATH") or ""
    attempts = []
    if chrome:
        attempts.append((
            {"executable_path": chrome, "args": ["--no-sandbox"]},
            "AIC_PLAYWRIGHT_CHROME_PATH",
            shlex.join([chrome, "--no-sandbox"]),
            chrome,
        ))
    attempts.append((
        {"channel": "chrome"}, "system channel: chrome",
        "playwright.chromium.launch(channel='chrome')", None,
    ))
    attempts.append((
        {}, "Playwright-managed Chromium",
        "playwright.chromium.launch()", None,
    ))
    for kw, selection, command, executable in attempts:
        try:
            browser = p.chromium.launch(**kw)
            return browser, {
                "engine": "chromium",
                "version": browser.version,
                "selection": selection,
                "executable": executable,
                "command": command,
                "launch_flags": list(kw.get("args", [])),
            }
        except Exception:
            continue
    raise RuntimeError("no chrome available")


def banner_display(pg):
    return pg.evaluate(
        """() => {
            var b = document.querySelector('.okf-studio-fallback-banner--js');
            return b ? getComputedStyle(b).display : 'absent';
        }"""
    )


# P1 contract item 2 — durable no-JS static first-layout geometry. With
# java_script_enabled=False NO scripts execute, so requestAnimationFrame
# callbacks never fire and a JS frame sampler CANNOT observe a transition
# timeline (and nothing settles — there is no async boot). The durable proof
# is therefore a STATIC document/CSS invariant captured at the EARLIEST point
# geometry is available (the ``load`` event), with no timer / retry / poll.
NOJS_STATIC_PROOF = (
    "Durable no-JS earliest-available geometry: captured at the deterministic "
    "`load` event (all CSS parsed + applied), immediately, with NO sleep/retry. "
    "Because java_script_enabled=False, no scripts run, requestAnimationFrame "
    "never fires, and a JS frame sampler is UNAVAILABLE — there is also no "
    "async settlement to sample. The proof is the static DOM/CSS invariant: "
    "<html> carries no settlement classes, the table uses the static fallback "
    "CSS (display:block; overflow-x:auto) with the server tabindex=\"0\" + "
    "aria-label no-JS keyboard affordance, and document width is contained."
)


def nojs_geometry(pg):
    """Static first-layout invariants that prove there is no JS-driven
    transition and the no-JS table is a keyboard-focusable scrollport.
    Captured immediately on `load` (caller guarantees wait_until='load' and
    NO intervening wait_for_timeout)."""
    return pg.evaluate(
        """() => {
            var de = document.documentElement;
            var table = document.querySelector('table.okf-table');
            var cs = table ? getComputedStyle(table) : null;
            return {
                jsEnabled: typeof window.okfLoomStudio !== 'undefined',
                htmlClasses: de.classList.toString(),
                docSW: de.scrollWidth,
                docCW: de.clientWidth,
                docContained: de.scrollWidth <= de.clientWidth + 1,
                hasWrapper: !!document.querySelector('.okf-tablewrap'),
                tableDisplay: cs ? cs.display : null,
                tableOverX: cs ? cs.overflowX : null,
                tableSW: table ? table.scrollWidth : null,
                tableCW: table ? table.clientWidth : null,
                tableOverflows: table ? table.scrollWidth > table.clientWidth + 1 : null,
                tableTabindex: table ? table.getAttribute('tabindex') : null,
                tableRole: table ? table.getAttribute('role') : null,
                tableAriaLabel: table ? table.getAttribute('aria-label') : null,
            };
        }"""
    )


def main():
    repository = git_identity()
    invocation_argv = [sys.executable, *sys.argv]
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "okf_loom", "serve", str(DEMO),
         "--host", "127.0.0.1", "--port", str(port), "--no-watch", "--no-open"],
        cwd=str(TK), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=okf_env(),
    )
    manifest = {}
    try:
        wait_up(base)
        with sync_playwright() as p:
            browser, browser_metadata = launch(p)

            # 01 — Desktop successful boot (dark OS): no banner.
            ctx = browser.new_context(color_scheme="dark",
                                      viewport={"width": 1280, "height": 900},
                                      device_scale_factor=DEVICE_SCALE_FACTOR)
            pg = ctx.new_page()
            pg.goto(f"{base}{CONCEPT}", wait_until="domcontentloaded")
            pg.wait_for_function(
                "document.documentElement.classList.contains('okf-studio-booted')",
                timeout=10000,
            )
            pg.wait_for_timeout(300)
            assert banner_display(pg) == "none", "banner visible on successful boot"
            pg.screenshot(path=str(OUT / "01-successful-boot-no-banner.png"))
            manifest["01-successful-boot-no-banner.png"] = {
                "scenario": "Successful studio boot — JS fallback banner hidden",
                "viewport": "1280x900 desktop, dark OS",
                "command": "okf serve samples/demo_bundle (HEAD recorded in top-level revision)",
                "test": "test_first_paint_lifecycle_browser.py::test_no_banner_flash_during_successful_boot",
                "terminal_state": "html.okf-studio-booted (banner display:none)",
            }
            ctx.close()

            # 02 — Boot failure AFTER genuine mutation (dark OS): banner visible.
            ctx = browser.new_context(color_scheme="dark",
                                      viewport={"width": 1280, "height": 900},
                                      device_scale_factor=DEVICE_SCALE_FACTOR)
            pg = ctx.new_page()
            pg.add_init_script(
                """window.__okfBootProbe = function(phase) {
                    if (phase === 'post-mount') throw new Error('capture: boot fail');
                };"""
            )
            pg.goto(f"{base}{CONCEPT}", wait_until="domcontentloaded")
            pg.wait_for_timeout(300)
            assert pg.evaluate(
                "document.documentElement.classList.contains('okf-studio-unavailable')"
            ), "unavailable not stamped"
            assert banner_display(pg) == "block", "banner not visible on boot failure"
            pg.screenshot(path=str(OUT / "02-boot-failure-banner-visible.png"))
            manifest["02-boot-failure-banner-visible.png"] = {
                "scenario": "Boot failure AFTER genuine DOM mutation — banner revealed",
                "viewport": "1280x900 desktop, dark OS",
                "command": "okf serve samples/demo_bundle; __okfBootProbe post-mount throws",
                "test": "test_first_paint_lifecycle_browser.py::test_boot_failure_after_genuine_mutation",
                "terminal_state": "html.okf-studio-unavailable (banner display:block)",
            }
            ctx.close()

            # 03 — Studio.js blocked (light OS): banner visible via watchdog.
            ctx = browser.new_context(color_scheme="light",
                                      viewport={"width": 1280, "height": 900},
                                      device_scale_factor=DEVICE_SCALE_FACTOR)
            pg = ctx.new_page()

            def block_studio(route):
                if "studio.js" in route.request.url:
                    route.abort()
                else:
                    route.continue_()

            pg.route("**/*", block_studio)
            pg.goto(f"{base}{CONCEPT}", wait_until="domcontentloaded")
            pg.wait_for_timeout(300)
            assert banner_display(pg) == "block", "banner not visible when studio blocked"
            pg.screenshot(path=str(OUT / "03-studio-blocked-banner-visible.png"))
            manifest["03-studio-blocked-banner-visible.png"] = {
                "scenario": "studio.js blocked/missing — watchdog reveals banner at DOMContentLoaded",
                "viewport": "1280x900 desktop, light OS",
                "command": "okf serve samples/demo_bundle; studio.js route aborted",
                "test": "test_first_paint_lifecycle_browser.py::test_banner_visible_when_studio_blocked",
                "terminal_state": "html.okf-studio-unavailable (banner display:block)",
            }
            ctx.close()

            # 04 — No-JS (dark OS): noscript banner visible + static first-layout geometry.
            ctx = browser.new_context(color_scheme="dark",
                                      viewport={"width": 1280, "height": 900},
                                      device_scale_factor=DEVICE_SCALE_FACTOR,
                                      java_script_enabled=False)
            pg = ctx.new_page()
            # wait_until="load" is the deterministic earliest-available layout
            # signal (all CSS applied). NO wait_for_timeout: in no-JS there is
            # nothing to settle, so this IS the durable earliest proof.
            pg.goto(f"{base}{CONCEPT}", wait_until="load")
            count = pg.evaluate(
                """() => {
                    var n = 0;
                    document.querySelectorAll('.okf-studio-fallback-banner').forEach(function(b){
                        if (getComputedStyle(b).display !== 'none') n++;
                    });
                    return n;
                }"""
            )
            assert count == 1, f"no-JS banner count {count}"
            geo = nojs_geometry(pg)
            assert not geo["jsEnabled"], "JS ran in a no-JS context"
            assert geo["htmlClasses"] == "", "no-JS <html> must have no settlement classes"
            assert geo["docContained"], f"no-JS desktop doc overflow: {geo!r}"
            assert geo["tableDisplay"] == "block", geo
            assert geo["tableTabindex"] == "0", geo
            assert geo["tableRole"] is None, geo
            pg.screenshot(path=str(OUT / "04-nojs-banner-visible.png"))
            manifest["04-nojs-banner-visible.png"] = {
                "scenario": "JavaScript disabled — noscript fallback banner only",
                "viewport": "1280x900 desktop, dark OS, java_script_enabled=False",
                "command": "okf serve samples/demo_bundle; Playwright java_script_enabled=False",
                "test": "test_first_paint_lifecycle_browser.py::test_nojs_desktop_geometry_no_overflow",
                "terminal_state": "no settlement classes (JS off); noscript banner visible",
                "capture_timing": "immediate at wait_until=load (no sleep/retry)",
                "nojs_static_geometry": geo,
                "nojs_static_proof": NOJS_STATIC_PROOF,
            }
            ctx.close()

            # 05 — Mobile successful boot (dark OS, 414px): no banner, table contained.
            ctx = browser.new_context(color_scheme="dark",
                                      viewport={"width": 414, "height": 900},
                                      device_scale_factor=DEVICE_SCALE_FACTOR)
            pg = ctx.new_page()
            pg.goto(f"{base}{CONCEPT}", wait_until="domcontentloaded")
            pg.wait_for_function(
                "document.documentElement.classList.contains('okf-studio-booted')",
                timeout=10000,
            )
            pg.wait_for_timeout(300)
            assert banner_display(pg) == "none", "mobile banner visible on boot"
            pg.screenshot(path=str(OUT / "05-mobile-successful-boot.png"))
            manifest["05-mobile-successful-boot.png"] = {
                "scenario": "Mobile successful boot — table contained, no banner",
                "viewport": "414x900 mobile, dark OS",
                "command": "okf serve samples/demo_bundle (HEAD recorded in top-level revision)",
                "test": "test_first_paint_lifecycle_browser.py::test_mobile_frame_geometry_stable_no_overflow",
                "terminal_state": "html.okf-studio-booted; table locally contained (no doc overflow)",
            }
            ctx.close()

            # 06 — Mobile no-JS table: bare table is a keyboard-focusable
            # scrollport (server tabindex + aria-label), scrolls natively, no
            # enhancer wrapper. Captured at the earliest-available layout point.
            ctx = browser.new_context(color_scheme="dark",
                                      viewport={"width": 414, "height": 900},
                                      device_scale_factor=DEVICE_SCALE_FACTOR,
                                      java_script_enabled=False)
            pg = ctx.new_page()
            # wait_until="load": earliest durable geometry; no JS to settle.
            pg.goto(f"{base}{CONCEPT}", wait_until="load")
            geo = nojs_geometry(pg)
            assert not geo["jsEnabled"], "JS ran in a no-JS context"
            assert not geo["hasWrapper"], "enhancer wrapper exists without JS"
            assert geo["htmlClasses"] == "", "no-JS <html> must have no settlement classes"
            assert geo["docContained"], f"no-JS mobile doc overflow: {geo!r}"
            assert geo["tableDisplay"] == "block", geo
            assert geo["tableOverX"] in ("auto", "scroll"), geo
            assert geo["tableOverflows"], (
                f"mobile table should overflow at 414px: {geo!r}"
            )
            # P1 keyboard-focusable scrollport: server fallback affordance.
            assert geo["tableTabindex"] == "0", geo
            assert geo["tableRole"] is None, geo
            assert geo["tableAriaLabel"], geo
            pg.screenshot(path=str(OUT / "06-mobile-nojs-table-scrollable.png"))
            manifest["06-mobile-nojs-table-scrollable.png"] = {
                "scenario": "Mobile no-JS — bare table is a keyboard-focusable "
                            "scrollport (tabindex+aria-label), scrolls natively, "
                            "no enhancer wrapper",
                "viewport": "414x900 mobile, dark OS, java_script_enabled=False",
                "command": "okf serve samples/demo_bundle; Playwright java_script_enabled=False",
                "test": "test_first_paint_lifecycle_browser.py::test_nojs_mobile_table_no_enhancer_and_scrollable "
                        "+ test_nojs_mobile_table_reachable_by_tab + test_nojs_geometry_is_static_at_first_layout",
                "terminal_state": "no settlement classes (JS off); bare table "
                                  "display:block overflow-x:auto tabindex=0, no wrapper",
                "capture_timing": "immediate at wait_until=load (no sleep/retry)",
                "nojs_static_geometry": geo,
                "nojs_static_proof": NOJS_STATIC_PROOF,
            }
            ctx.close()

            # 07 — Mobile no-JS table KEYBOARD-FOCUSED: visible focus
            # treatment on the bare table (the user-visible affordance for the
            # server tabindex="0"). Tab to the table, then screenshot the
            # focus-visible outline. Proves a no-JS keyboard user gets a
            # visible, named, scrollable focus target with no JS enhancer.
            ctx = browser.new_context(color_scheme="dark",
                                      viewport={"width": 414, "height": 900},
                                      device_scale_factor=DEVICE_SCALE_FACTOR,
                                      java_script_enabled=False)
            pg = ctx.new_page()
            pg.goto(f"{base}{CONCEPT}", wait_until="load")
            focused = False
            for _ in range(80):
                pg.keyboard.press("Tab")
                if pg.evaluate(
                    "document.activeElement && document.activeElement.tagName === 'TABLE'"
                ):
                    focused = True
                    break
            assert focused, "Tab never reached the no-JS table in capture"
            pg.screenshot(path=str(OUT / "07-mobile-nojs-table-keyboard-focus.png"))
            manifest["07-mobile-nojs-table-keyboard-focus.png"] = {
                "scenario": "Mobile no-JS — bare table keyboard-focused (Tab), "
                            "showing the visible :focus-visible outline on the "
                            "server-side tabindex=0 scrollport",
                "viewport": "414x900 mobile, dark OS, java_script_enabled=False",
                "command": "okf serve samples/demo_bundle; Playwright java_script_enabled=False; Tab to table",
                "test": "test_first_paint_lifecycle_browser.py::test_nojs_mobile_table_reachable_by_tab",
                "terminal_state": "table focused via real Tab keypress; "
                                  ":focus-visible outline rendered",
                "capture_timing": "immediate after Tab focus (no sleep/retry)",
            }
            ctx.close()

            browser.close()

        manifest_path = OUT / "provenance.json"
        with open(manifest_path, "w") as f:
            json.dump({
                "schema": "okf-loom-boot-settlement-provenance-v2",
                "description": "Fresh current-branch proof screenshots for the "
                               "first-paint boot-settlement + table-containment slice.",
                **repository,
                "captured_by": "tests/capture_boot_settlement_proof.py",
                "capture_invocation": shlex.join(invocation_argv),
                "capture_invocation_argv": invocation_argv,
                "capture_date": time.strftime("%Y-%m-%d", time.gmtime()),
                "capture_timezone": "UTC",
                "capture_timezone_fallback": None,
                "server": "python -m okf_loom serve samples/demo_bundle --no-watch --no-open",
                "environment": {
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                    "browser": browser_metadata,
                    "device_scale_factor": DEVICE_SCALE_FACTOR,
                    "automation": "Playwright synchronous Python API",
                },
                "screenshots": manifest,
            }, f, indent=2)
            f.write("\n")
        print(f"captured {len(manifest)} screenshots + provenance.json to {OUT}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
