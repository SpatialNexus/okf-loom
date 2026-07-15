"""Mermaid theme contrast: verify line/border variables yield >=3:1 against
diagram background and text >=4.5:1 in all four themes + Soft Contrast.
"""
from __future__ import annotations
import socket, subprocess, sys, time, urllib.request, os, math
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


def _lum(r, g, b):
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

def _ratio(rgb1, rgb2):
    l1, l2 = _lum(*rgb1), _lum(*rgb2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


CONTRAST_JS = """(theme) => {
    var cs = getComputedStyle(document.documentElement);
    var cv = document.createElement('canvas'); cv.width=2; cv.height=2; var cx=cv.getContext('2d');
    function toHex(cssVal) {
        cx.fillStyle = '#000'; cx.fillStyle = cssVal; cx.fillRect(0,0,1,1);
        var d = cx.getImageData(0,0,1,1).data;
        return '#' + [d[0],d[1],d[2]].map(function(c){return c.toString(16).padStart(2,'0');}).join('');
    }
    function v(n) { return cs.getPropertyValue(n).trim(); }
    var fg = toHex(v('--okf-fg'));
    var fgMuted = toHex(v('--okf-fg-muted'));
    var bgElev = toHex(v('--okf-bg-elev'));
    var bg = toHex(v('--okf-bg'));
    var accent = toHex(v('--okf-accent'));
    var accentBg = toHex(v('--okf-accent-bg'));
    return {
        lineColor: fgMuted,
        primaryBorderColor: fgMuted,
        actorBorder: fgMuted,
        activationBorderColor: fgMuted,
        actorLineColor: fgMuted,
        primaryColor: bgElev,
        background: bg,
        actorBkg: bgElev,
        noteBkgColor: bgElev,
        noteBorderColor: accent,
        primaryTextColor: fg,
        signalTextColor: fg,
        noteTextColor: fg,
        secondaryTextColor: fg,
        tertiaryTextColor: fg,
    };
}"""


@pytest.mark.parametrize("theme", ["swiss-light", "swiss-dark", "technical-light", "technical-dark"])
def test_mermaid_line_contrast_gte_3_1(server_url, page, theme):
    """Mermaid line/border colors (mapped to --okf-fg-muted) yield >=3:1
    against diagram background in all four themes."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.evaluate(f"localStorage.setItem('okf-theme-family','{theme.split('-')[0]}');localStorage.setItem('okf-theme-mode','{theme.split('-')[1]}');")
    page.reload(wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    vals = page.evaluate(CONTRAST_JS, theme)
    bg_rgb = _hex_to_rgb(vals["background"])
    bgElev_rgb = _hex_to_rgb(vals["primaryColor"])
    accentBg_rgb = _hex_to_rgb(vals["noteBkgColor"])
    # Line color against diagram background (flowchart arrows/lines).
    line_rgb = _hex_to_rgb(vals["lineColor"])
    r = _ratio(line_rgb, bg_rgb)
    assert r >= 3.0, f"{theme} line/bg: {r:.3f} < 3.0"
    # Node borders against node fill (bg-elev).
    border_rgb = _hex_to_rgb(vals["primaryBorderColor"])
    r2 = _ratio(border_rgb, bgElev_rgb)
    assert r2 >= 3.0, f"{theme} border/bgElev: {r2:.3f} < 3.0"
    # Actor borders against actor background.
    actor_border = _hex_to_rgb(vals["actorBorder"])
    r3 = _ratio(actor_border, bgElev_rgb)
    assert r3 >= 3.0, f"{theme} actorBorder/actorBkg: {r3:.3f} < 3.0"
    # Note borders against note background.
    note_border = _hex_to_rgb(vals["noteBorderColor"])
    r4 = _ratio(note_border, accentBg_rgb)
    assert r4 >= 3.0, f"{theme} noteBorder/noteBkg: {r4:.3f} < 3.0"


@pytest.mark.parametrize("theme", ["swiss-light", "swiss-dark", "technical-light", "technical-dark"])
def test_mermaid_text_contrast_gte_4_5(server_url, page, theme):
    """Mermaid text colors (mapped to --okf-fg) yield >=4.5:1 against their
    respective backgrounds in all four themes."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.evaluate(f"localStorage.setItem('okf-theme-family','{theme.split('-')[0]}');localStorage.setItem('okf-theme-mode','{theme.split('-')[1]}');")
    page.reload(wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    vals = page.evaluate(CONTRAST_JS, theme)
    fg_rgb = _hex_to_rgb(vals["primaryTextColor"])
    bgElev_rgb = _hex_to_rgb(vals["primaryColor"])
    accentBg_rgb = _hex_to_rgb(vals["noteBkgColor"])
    bg_rgb = _hex_to_rgb(vals["background"])
    # Primary text on node fill.
    r = _ratio(fg_rgb, bgElev_rgb)
    assert r >= 4.5, f"{theme} text/bgElev: {r:.3f} < 4.5"
    # Signal text on diagram background.
    r2 = _ratio(fg_rgb, bg_rgb)
    assert r2 >= 4.5, f"{theme} signalText/bg: {r2:.3f} < 4.5"
    # Note text on note background.
    r3 = _ratio(fg_rgb, accentBg_rgb)
    assert r3 >= 4.5, f"{theme} noteText/noteBkg: {r3:.3f} < 4.5"


@pytest.mark.parametrize("theme", ["swiss-light", "technical-dark"])
def test_mermaid_soft_contrast_line_and_text(server_url, page, theme):
    """Soft Contrast modifier: lines still >=3:1, text still >=4.5:1."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.evaluate(f"localStorage.setItem('okf-theme-family','{theme.split('-')[0]}');localStorage.setItem('okf-theme-mode','{theme.split('-')[1]}');")
    page.reload(wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("document.documentElement.setAttribute('data-okf-contrast','soft')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-contrast') === 'soft'")
    vals = page.evaluate(CONTRAST_JS, theme)
    bg_rgb = _hex_to_rgb(vals["background"])
    bgElev_rgb = _hex_to_rgb(vals["primaryColor"])
    line_rgb = _hex_to_rgb(vals["lineColor"])
    r = _ratio(line_rgb, bg_rgb)
    assert r >= 3.0, f"SOFT {theme} line/bg: {r:.3f} < 3.0"
    fg_rgb = _hex_to_rgb(vals["primaryTextColor"])
    r2 = _ratio(fg_rgb, bgElev_rgb)
    assert r2 >= 4.5, f"SOFT {theme} text/bgElev: {r2:.3f} < 4.5"
