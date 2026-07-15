#!/usr/bin/env python3
"""Capture visual proof of the graph tuning controls (now the lens bar's "Advanced" disclosure in the right pane; formerly the Signal-controls panel).

Stands up ``scripts/okf-loom serve samples/demo_bundle`` on an ephemeral port, drives the
full-page ``/__graph`` view through several Signal-controls states with
Playwright using the shared managed/system Chrome resolver, and writes PNGs
under ``docs/screenshots/graph-signal-controls/``. Chrome's sandbox remains
enabled unless a constrained root container explicitly sets
``OKF_CAPTURE_NO_SANDBOX=1``.

Run from okf-loom/:  python scripts/capture_signal_controls.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    from scripts.capture_support import launch_chromium
except ModuleNotFoundError:  # pragma: no cover - direct invocation path
    from capture_support import launch_chromium

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "samples" / "demo_bundle"
OUT = ROOT / "docs" / "screenshots" / "graph-signal-controls"
OUT.mkdir(parents=True, exist_ok=True)


def script_env() -> dict[str, str]:
    env = dict(os.environ)
    scripts = str(ROOT / "scripts")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{scripts}{os.pathsep}{existing}" if existing else scripts
    return env


def free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_ready(base: str, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"scripts/okf-loom serve exited rc={proc.returncode}")
        try:
            with urllib.request.urlopen(f"{base}/", timeout=1.0) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.15)
    raise SystemExit("server never became ready")


def launch_browser(p):
    return launch_chromium(p).browser


def wait_graph_ready(page) -> None:
    """Wait for the diagnostic hook + the initial layout to settle and be
    applied (readiness assertion on the exact applied sequence, not a sleep)."""
    page.locator("#okf-graph canvas").first.wait_for(state="visible")
    page.wait_for_function(
        "() => window.__okfLoomGraph && window.__okfLoomGraph.cy "
        "&& window.__okfLoomGraph.cy.nodes().length > 0 "
        "&& window.__okfLoomGraph.layoutStats.lastAppliedSeq >= 1",
        timeout=10000,
    )


def preset(page, name: str) -> None:
    """Apply a preset and WAIT on a real readiness signal — a NEW layout
    sequence settling and being applied (lastAppliedSeq advances) — rather than
    a fixed sleep."""
    prev = page.evaluate("() => window.__okfLoomGraph.layoutStats.lastAppliedSeq")
    page.click(f'label[for="okf-lens-{name}"]')
    page.wait_for_function(
        "prev => window.__okfLoomGraph.layoutStats.lastAppliedSeq > prev", arg=prev, timeout=9000
    )
    page.wait_for_timeout(300)  # brief paint settle after the layout applies


def set_range(page, aria_label: str, value: int) -> None:
    """Drive a Signal range slider and WAIT on a real applied-layout signal
    (lastAppliedSeq advances) rather than a fixed sleep."""
    prev = page.evaluate("() => window.__okfLoomGraph.layoutStats.lastAppliedSeq")
    page.evaluate(
        """([label, val]) => {
          const inp = Array.from(document.querySelectorAll('.okf-signal input[type=range]'))
            .find(i => (i.getAttribute('aria-label')||'') === label);
          inp.value = String(val); inp.dispatchEvent(new Event('input', {bubbles:true})); }""",
        [aria_label, value],
    )
    page.wait_for_function(
        "prev => window.__okfLoomGraph.layoutStats.lastAppliedSeq > prev", arg=prev, timeout=9000
    )
    page.wait_for_timeout(300)


def shot(page, name: str) -> None:
    path = OUT / name
    page.locator("#okf-graph").screenshot(path=str(path))
    print("wrote", path)


def range_valuetext(page) -> list:
    """The accessible high-end labels currently exposed by the three spacing
    ranges (aria-valuetext) — proves the controls reached their maxima."""
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.okf-signal input[type=range]'))
             .filter(i => ['Node spacing','Cluster separation','Group strength']
               .includes(i.getAttribute('aria-label')||''))
             .map(i => (i.getAttribute('aria-label'))+': '+(i.getAttribute('aria-valuetext')))"""
    )


def strip_metrics(page) -> dict:
    """On-screen graph-strip metrics for the mobile open-drawer P1 check: how much
    of the viewport the Signal drawer eats, the uncovered graph-strip height, and
    how many node centres land inside that strip."""
    return page.evaluate(
        "() => {\n"
        "  const vh = window.innerHeight;\n"
        "  const panel = document.querySelector('.okf-signal');\n"
        "  const graph = document.getElementById('okf-graph');\n"
        "  const pr = panel.getBoundingClientRect();\n"
        "  const gr = graph.getBoundingClientRect();\n"
        "  const stripTop = Math.max(pr.bottom, gr.top);\n"
        "  const stripBottom = Math.min(gr.bottom, vh);\n"
        "  const strip = Math.max(0, stripBottom - stripTop);\n"
        "  const cy = (graph._cyreg && graph._cyreg.cy) || (window.__okfLoomGraph && window.__okfLoomGraph.cy);\n"
        "  let visNodes = 0;\n"
        "  if (cy) cy.nodes().forEach(n => { const bb = n.renderedBoundingBox(); const my = (bb.y1+bb.y2)/2 + gr.top; if (my > stripTop && my < stripBottom) visNodes++; });\n"
        "  return { vh, drawerVh: +(pr.height/vh*100).toFixed(1), stripPx: Math.round(strip), stripVh: +(strip/vh*100).toFixed(1), visNodes, totNodes: cy ? cy.nodes().length : 0 };\n"
        "}"
    )


def main() -> None:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "okf_loom", "serve", str(BUNDLE),
         "--host", "127.0.0.1", "--port", str(port), "--no-watch", "--no-open"],
        cwd=str(ROOT), env=script_env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_ready(base, proc)
        with sync_playwright() as p:
            browser = launch_browser(p)

            # --- Desktop ---
            ctx = browser.new_context(viewport={"width": 1366, "height": 900})
            page = ctx.new_page()
            page.goto(f"{base}/__graph", wait_until="domcontentloaded")
            page.locator(".okf-signal").wait_for(state="visible")
            wait_graph_ready(page)        # readiness assertion, not a blind sleep
            page.wait_for_timeout(400)    # brief paint settle
            shot(page, "01-overview-light.png")

            # Sanity: controls are real + wired (count + a live-status string).
            n_rows = page.locator(".okf-signal__row, .okf-signal__seg-item").count()
            status = page.locator(".okf-signal__status").inner_text()
            print("control rows:", n_rows, "| status:", status)

            preset(page, "themes")
            shot(page, "02-hubs-importance.png")
            print("hubs status:", page.locator(".okf-signal__status").inner_text())

            preset(page, "bridges")
            shot(page, "03-bridges-grouped.png")
            print("bridges status:", page.locator(".okf-signal__status").inner_text())

            preset(page, "flow")
            shot(page, "04-relations-typed.png")

            # Focus: re-select highest-degree node already selected on load,
            # then enable the Focus preset so its neighbourhood is highlighted.
            preset(page, "focus")
            shot(page, "05-focus-neighbourhood.png")
            print("focus status:", page.locator(".okf-signal__status").inner_text())

            # Detail panel relationship explanation proof.
            explain = page.locator("#okf-detail-signals")
            if explain.count():
                print("detail explain:", explain.inner_text().replace("\n", " | "))

            # Widened range proof: push Node spacing / Cluster separation /
            # Group strength to their new maxima (Vast / Expanse / Magnetic) so
            # the screenshot shows the far-apart, tightly-grouped spread the
            # 3-step range could not reach.
            preset(page, "map")
            set_range(page, "Node spacing", 4)        # Vast
            set_range(page, "Cluster separation", 4)  # Expanse
            set_range(page, "Group strength", 4)      # Magnetic
            shot(page, "09-vast-spread.png")
            print("max-range aria-valuetext:", range_valuetext(page))

            # Dark mode (Overview again for parity).
            preset(page, "map")
            page.click("#okf-theme")
            page.wait_for_timeout(600)
            page.locator("body").screenshot(path=str(OUT / "06-overview-dark-fullpage.png"))
            print("wrote", OUT / "06-overview-dark-fullpage.png")
            ctx.close()

            # --- Mobile ---
            # Capture the VIEWPORT (390×844), not the full scroll height, so the
            # shots show exactly what a phone user sees — the relevant frame for
            # the "graph occupies ≥35% of viewport while controls are open" check.
            mctx = browser.new_context(viewport={"width": 390, "height": 844})
            mpage = mctx.new_page()
            mpage.goto(f"{base}/__graph", wait_until="domcontentloaded")
            wait_graph_ready(mpage)       # readiness assertion, not a blind sleep
            mpage.wait_for_timeout(400)
            mpage.screenshot(path=str(OUT / "07-mobile-collapsed.png"))
            print("wrote", OUT / "07-mobile-collapsed.png")
            # Expand the (collapsed-on-mobile) Signal drawer.
            mpage.click(".okf-signal > summary")
            mpage.wait_for_timeout(500)
            mpage.screenshot(path=str(OUT / "08-mobile-open.png"))
            print("wrote", OUT / "08-mobile-open.png")
            # Report the actual on-screen graph strip metrics for the P1 check
            # (08 is the DEFAULT Balanced/Clear baseline kept for comparison).
            print("MOBILE-OPEN metrics (default):", strip_metrics(mpage))

            # Max-range on mobile (P1 #4): drive the three spacing sliders to
            # their maxima WHILE the Signal drawer is open, then capture — direct
            # vast-spread proof for the phone tune-and-view workflow that the
            # default 08 shot could not show. set_range() waits on a real
            # applied-layout signal (lastAppliedSeq), so this is semantic
            # readiness, not a blind sleep.
            set_range(mpage, "Node spacing", 4)        # Vast
            set_range(mpage, "Cluster separation", 4)  # Expanse
            set_range(mpage, "Group strength", 4)      # Magnetic
            mpage.screenshot(path=str(OUT / "10-mobile-vast-open.png"))
            print("wrote", OUT / "10-mobile-vast-open.png")
            print("MOBILE-VAST-OPEN metrics:", strip_metrics(mpage))
            print("mobile max-range aria-valuetext:", range_valuetext(mpage))
            mctx.close()

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
