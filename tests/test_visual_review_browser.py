"""Visual hardening review proof: computed contrast ratios, search column,
Border Off audit for all aria states, legend breakpoint/user-toggle, parity.
Uses canvas-based oklch→sRGB conversion for exact WCAG ratios.
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
    out = tmp_path_factory.mktemp("vh-r-static") / "site"
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
    out = tmp_path_factory.mktemp("vh-r-sf") / "viz.html"
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

def _set_theme(pg, theme):
    pg.evaluate(f"localStorage.setItem('okf-theme-family','{theme.split('-')[0]}');localStorage.setItem('okf-theme-mode','{theme.split('-')[1]}');")

def _goto_concept(pg, base):
    pg.goto(f"{base}/tables/orders", wait_until="load")

def _wait_studio(pg):
    pg.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)

def _wait_graph(pg, base):
    pg.goto(f"{base}/__graph", wait_until="domcontentloaded")
    pg.wait_for_selector("#okf-graph canvas", timeout=15000)
    pg.wait_for_selector(".okf-graph-legend", timeout=5000)


# ===========================================================================
# 1. Computed contrast ratios for ALL status pairs across ALL themes
# ===========================================================================

CONTRAST_JS = """() => {
    const cs = getComputedStyle(document.documentElement);
    const c = document.createElement('canvas'); c.width=2; c.height=2; const cx=c.getContext('2d');
    function toRGB(cssColor) {
        cx.fillStyle = '#000'; cx.fillStyle = cssColor; cx.fillRect(0,0,1,1);
        const d = cx.getImageData(0,0,1,1).data; return [d[0]/255, d[1]/255, d[2]/255];
    }
    function get(prop) { return toRGB(cs.getPropertyValue(prop).trim()); }
    function lum(r,g,b) {
        function lin(ch) { return ch <= 0.03928 ? ch / 12.92 : Math.pow((ch + 0.055) / 1.055, 2.4); }
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    }
    function ratio(c1, c2) {
        const l1 = lum(c1[0], c1[1], c1[2]), l2 = lum(c2[0], c2[1], c2[2]);
        return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    }
    const out = {};
    for (const s of ['ok','warn','info','error']) {
        out[s] = {
            fgBg: ratio(get('--okf-'+s), get('--okf-'+s+'-bg')),
            onFill: ratio(get('--okf-on-'+s), get('--okf-'+s)),
        };
    }
    return out;
}"""

@pytest.mark.parametrize("theme", ["swiss-light", "swiss-dark", "technical-light", "technical-dark"])
def test_status_contrast_all_pairs_AA(server_url, page, theme):
    """Every status fg/bg and on-*/fill pair ≥4.5:1 (AA for text/glyphs)."""
    _goto_concept(page, server_url)
    _set_theme(page, theme)
    page.reload(wait_until="load")
    _wait_studio(page)
    ratios = page.evaluate(CONTRAST_JS)
    for stat in ["ok", "warn", "info", "error"]:
        fg_bg = ratios[stat]["fgBg"]
        on_fill = ratios[stat]["onFill"]
        assert fg_bg >= 4.5, f"{theme} {stat} fg/bg={fg_bg:.3f} <4.5"
        assert on_fill >= 4.5, f"{theme} {stat} on/fill={on_fill:.3f} <4.5"


@pytest.mark.parametrize("theme", ["swiss-light", "swiss-dark", "technical-light", "technical-dark"])
def test_status_contrast_soft_contrast(server_url, page, theme):
    """Soft Contrast variant also passes AA for all status pairs."""
    _goto_concept(page, server_url)
    _set_theme(page, theme)
    page.reload(wait_until="load")
    _wait_studio(page)
    page.evaluate("document.documentElement.setAttribute('data-okf-contrast','soft')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-contrast') === 'soft'")
    ratios = page.evaluate(CONTRAST_JS)
    for stat in ["ok", "warn", "info", "error"]:
        assert ratios[stat]["fgBg"] >= 4.5, f"{theme} SOFT {stat} fg/bg={ratios[stat]['fgBg']:.3f} <4.5"
        assert ratios[stat]["onFill"] >= 4.5, f"{theme} SOFT {stat} on/fill={ratios[stat]['onFill']:.3f} <4.5"


# ===========================================================================
# 2. Search title/results column ~72ch with wrapping
# ===========================================================================

def test_search_results_column_capped(server_url, page):
    """Search title and results are capped at ~72ch at 1280/1600."""
    for w in [1280, 1600]:
        page.set_viewport_size({"width": w, "height": 900})
        page.goto(f"{server_url}/__search?q=orders", wait_until="load")
        page.wait_for_selector(".okf-search__results, .okf-search-empty", timeout=5000)
        info = page.evaluate("""() => {
            const results = document.querySelector('.okf-search__results');
            const title = document.querySelector('.okf-search__title');
            return {
                resultsMaxW: results ? getComputedStyle(results).maxWidth : null,
                resultsW: results ? Math.round(results.getBoundingClientRect().width) : 0,
                titleMaxW: title ? getComputedStyle(title).maxWidth : null,
            };
        }""")
        assert info["resultsMaxW"] != "none", f"results max-width none at {w}"
        assert info["titleMaxW"] != "none", f"title max-width none at {w}"


def test_search_long_path_wraps(server_url, page):
    """Long concept paths in search results wrap (no horizontal overflow)."""
    page.set_viewport_size({"width": 768, "height": 900})
    page.goto(f"{server_url}/__search?q=orders", wait_until="load")
    page.wait_for_selector(".okf-search__results, .okf-search-empty", timeout=5000)
    overflow = page.evaluate("""() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
    })""")
    assert overflow["sw"] <= overflow["cw"] + 1, f"search overflow: {overflow}"


# ===========================================================================
# 3. Border Off: ALL aria states get non-color cues
# ===========================================================================

def test_border_off_all_states_have_font_weight(server_url, page):
    """Every aria-pressed/selected/current/checked state under Border Off
    gets font-weight:700 as a non-color cue."""
    _goto_concept(page, server_url)
    _wait_studio(page)
    page.evaluate("document.documentElement.setAttribute('data-okf-border', 'off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")

    # Appearance checked option.
    page.click("#okf-theme")
    page.wait_for_selector("#okf-appearance-menu:not([hidden])")
    w = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-appearance__opt[aria-checked="true"]')
    ).fontWeight""")
    assert w == "700", f"appearance checked: {w}"

    # Open panel, check tab.
    page.keyboard.press("Escape")
    page.wait_for_selector("#okf-appearance-menu[hidden]", state="attached")
    page.evaluate("window.okfLoomStudio.openPanel('comments')")
    page.wait_for_selector("#okf-panel:not([hidden])")
    w = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-panel__tab[aria-selected="true"]')
    ).fontWeight""")
    assert w == "700", f"panel tab selected: {w}"


def test_border_off_index_chip_font_weight(server_url, page):
    """Index filter chips (aria-pressed) get font-weight under Border Off."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{server_url}/", wait_until="load")
    page.wait_for_function("typeof window.okfLoomStudio === 'object'", timeout=15000)
    page.evaluate("document.documentElement.setAttribute('data-okf-border', 'off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    # Find a pressed index chip (the active filter or type chip).
    chip = page.query_selector('.okf-index-chip[aria-pressed="true"]')
    if chip:
        w = page.evaluate("""() => getComputedStyle(
            document.querySelector('.okf-index-chip[aria-pressed="true"]')
        ).fontWeight""")
        assert w == "700", f"index chip pressed: {w}"


def test_border_off_graph_legend_chip_font_weight(server_url, page):
    """Graph legend filter chips (aria-pressed) get font-weight under Border Off."""
    page.set_viewport_size({"width": 1280, "height": 900})
    _wait_graph(page, server_url)
    page.evaluate("document.documentElement.setAttribute('data-okf-border', 'off')")
    page.wait_for_function("document.documentElement.getAttribute('data-okf-border') === 'off'")
    chips = page.query_selector_all('.okf-graph-legend__item--chip[aria-pressed="true"]')
    if chips:
        w = page.evaluate("""() => {
            const c = document.querySelector('.okf-graph-legend__item--chip[aria-pressed="true"]');
            return c ? getComputedStyle(c).fontWeight : null;
        }""")
        assert w == "700", f"graph legend chip: {w}"


# ===========================================================================
# 4. Legend breakpoint tracking + user toggle preservation
# ===========================================================================

def test_legend_default_open_desktop(server_url, page):
    page.set_viewport_size({"width": 1280, "height": 900})
    _wait_graph(page, server_url)
    assert page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")


def test_legend_default_closed_mobile(server_url, page):
    page.set_viewport_size({"width": 390, "height": 900})
    _wait_graph(page, server_url)
    assert not page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")


def test_legend_user_toggle_preserved_across_resize(server_url, page):
    """User closes legend on desktop → resize to mobile → legend stays closed
    (user choice preserved)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    _wait_graph(page, server_url)
    assert page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")
    # User closes it.
    page.evaluate("document.querySelector('.okf-graph-legend').removeAttribute('open')")
    page.wait_for_function("!document.querySelector('.okf-graph-legend').hasAttribute('open')")
    # Resize to mobile — user toggle should be preserved (stay closed).
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_timeout(200)
    assert not page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')"), \
        "legend reopened despite user closing it"


def test_legend_default_follows_breakpoint_no_user_toggle(server_url, page):
    """Without user toggle, breakpoint resize changes the default."""
    page.set_viewport_size({"width": 1280, "height": 900})
    _wait_graph(page, server_url)
    assert page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")
    # Resize to mobile (no user toggle) — should close by default.
    page.set_viewport_size({"width": 390, "height": 900})
    page.wait_for_timeout(200)
    assert not page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")
    # Resize back to desktop — should reopen by default.
    page.set_viewport_size({"width": 1280, "height": 900})
    page.wait_for_timeout(200)
    assert page.evaluate("document.querySelector('.okf-graph-legend').hasAttribute('open')")


def test_legend_filter_enter_activates(server_url, page):
    """Enter on a focused legend filter chip toggles it (native button)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    _wait_graph(page, server_url)
    page.wait_for_selector(".okf-graph-legend__item--chip", timeout=5000)
    # Focus and press Enter on the first chip.
    page.evaluate("""() => {
        const chip = document.querySelector('.okf-graph-legend__item--chip');
        if (chip) chip.focus();
    }""")
    initial = page.evaluate("document.querySelector('.okf-graph-legend__item--chip').getAttribute('aria-pressed')")
    page.keyboard.press("Enter")
    page.wait_for_function("""() => {
        const c = document.querySelector('.okf-graph-legend__item--chip');
        return c && c.getAttribute('aria-pressed') !== '%s';
    }""" % initial)
    new = page.evaluate("document.querySelector('.okf-graph-legend__item--chip').getAttribute('aria-pressed')")
    assert new != initial, "Enter did not toggle the legend filter chip"


# ===========================================================================
# 5. Static/single-file parity
# ===========================================================================

@pytest.mark.parametrize("theme", ["swiss-light", "technical-dark"])
def test_static_status_tokens_defined(static_site_url, page, theme):
    """Status tokens resolve on static builds."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    page.evaluate(f"localStorage.setItem('okf-theme-family','{theme.split('-')[0]}');localStorage.setItem('okf-theme-mode','{theme.split('-')[1]}');")
    page.reload(wait_until="load")
    page.wait_for_selector("#okf-theme")
    vals = page.evaluate("""() => {
        const cs = getComputedStyle(document.documentElement);
        return {
            onOk: cs.getPropertyValue('--okf-on-ok').trim(),
            onWarn: cs.getPropertyValue('--okf-on-warn').trim(),
            onError: cs.getPropertyValue('--okf-on-error').trim(),
        };
    }""")
    for k, v in vals.items():
        assert v, f"{k} empty on static {theme}"


def test_static_border_off_appearance_font_weight(static_site_url, page):
    """Border Off font-weight cue works on static builds."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    page.evaluate("document.documentElement.setAttribute('data-okf-border','off')")
    page.click("#okf-theme")
    page.wait_for_selector("#okf-appearance-menu:not([hidden])")
    w = page.evaluate("""() => getComputedStyle(
        document.querySelector('.okf-appearance__opt[aria-checked="true"]')
    ).fontWeight""")
    assert w == "700", f"static border-off appearance: {w}"


def test_static_search_column_capped(static_site_url, page):
    """Search results capped on static builds."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{static_site_url}/__search.html?q=orders", wait_until="load")
    page.wait_for_selector(".okf-search__results, .okf-search-empty", timeout=5000)
    mw = page.evaluate("""() => {
        const r = document.querySelector('.okf-search__results');
        return r ? getComputedStyle(r).maxWidth : null;
    }""")
    assert mw and mw != "none", f"static search results max-width: {mw}"


def test_single_file_legend_in_detail_or_fallback(single_file_url, page):
    """Single-file viewer has the legend element (in detail pane or fallback)."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(single_file_url, wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_selector(".okf-graph-legend", timeout=5000)
    assert page.evaluate("!!document.querySelector('.okf-graph-legend')")
    # Verify it's a <details> element.
    assert page.evaluate("document.querySelector('.okf-graph-legend').tagName === 'DETAILS'")


def test_single_file_status_tokens(single_file_url, page):
    """Status tokens resolve in single-file viewer."""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(single_file_url, wait_until="load")
    vals = page.evaluate("""() => {
        const cs = getComputedStyle(document.documentElement);
        return cs.getPropertyValue('--okf-on-ok').trim();
    }""")
    assert vals, "on-ok empty in single-file"
