"""Browser proof for the canonical frontend theme-state contract.

Covers the hardening-plan Phase 2 acceptance transitions on real pages:

  * configured default survives first boot (and is never copied to storage);
  * family and mode persist independently (Technical + Auto survives
    reload and navigation between wiki and graph);
  * explicit light/dark persists and ignores the OS;
  * every surface follows TWO consecutive ``prefers-color-scheme`` changes
    while Auto without persisting the resolved value;
  * legacy ``okf-theme`` values migrate once through the canonical resolver;
  * storage denial disables persistence only — never resolution;
  * ``okf-loom:themeChanged`` fires once per ACTUAL change;
  * the studio command palette drives the same resolver;
  * static-build, SPA, and single-file outputs boot the same contract;
  * partial/failed persistence stays correct: write-only storage keeps the
    parsed legacy preference in memory, boot reconciles the compatibility
    mirror from canonical state only, corrupt keys fall back per dimension
    without re-admitting the mirror as authority, and modifiers self-heal;
  * configured-source precedence: viewer JSON data-theme > studio YAML
    bootstrap theme > Swiss Auto/OS (studio ``auto`` = no preference).

Same three-way gating as tests/test_viewer_browser.py: module skip without
playwright, ``browser`` marker, per-test skip without a Chromium binary.
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

_SERVER_STARTUP_TIMEOUT = 15.0
_SERVER_POLL_INTERVAL = 0.15
_POLL_HTTP_TIMEOUT = 1.0


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_http(proc: subprocess.Popen, base: str, path: str = "/") -> None:
    deadline = time.monotonic() + _SERVER_STARTUP_TIMEOUT
    last_error: Exception | None = None
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


def _terminate(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _start_okf_serve(bundle: Path) -> tuple[subprocess.Popen, str]:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        okf_module_argv(
            "serve", str(bundle), "--host", "127.0.0.1", "--port", str(port),
            "--no-watch", "--no-open",
        ),
        cwd=str(TOOLKIT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=okf_subprocess_env(),
    )
    _wait_for_http(proc, base)
    return proc, base


@pytest.fixture(scope="session")
def server_url():
    """``okf serve`` over the UNCONFIGURED demo bundle (no viewer theme)."""
    if not DEMO_BUNDLE.is_dir():
        pytest.skip(f"demo bundle not found at {DEMO_BUNDLE}")
    proc, base = _start_okf_serve(DEMO_BUNDLE)
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def configured_server_url(tmp_path_factory):
    """``okf serve`` over a demo-bundle copy configured with technical-dark."""
    if not DEMO_BUNDLE.is_dir():
        pytest.skip(f"demo bundle not found at {DEMO_BUNDLE}")
    bundle = tmp_path_factory.mktemp("configured") / "bundle"
    shutil.copytree(DEMO_BUNDLE, bundle)
    cfg_dir = bundle / ".okf-loom" / "viewer"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"theme": "technical-dark"}), encoding="utf-8"
    )
    proc, base = _start_okf_serve(bundle)
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def studio_theme_server_url(tmp_path_factory):
    """``okf serve`` over a copy whose okf-loom.config.yaml sets a CONCRETE
    ``studio.theme`` while the viewer JSON surface stays unconfigured."""
    if not DEMO_BUNDLE.is_dir():
        pytest.skip(f"demo bundle not found at {DEMO_BUNDLE}")
    bundle = tmp_path_factory.mktemp("studiotheme") / "bundle"
    shutil.copytree(DEMO_BUNDLE, bundle)
    (bundle / "okf-loom.config.yaml").write_text(
        "studio:\n  theme: technical-dark\n", encoding="utf-8"
    )
    proc, base = _start_okf_serve(bundle)
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def conflicting_config_server_url(tmp_path_factory):
    """Both configured sources set, conflicting: studio YAML swiss-light vs
    viewer JSON technical-dark. The viewer JSON (server-painted) must win."""
    if not DEMO_BUNDLE.is_dir():
        pytest.skip(f"demo bundle not found at {DEMO_BUNDLE}")
    bundle = tmp_path_factory.mktemp("conflictcfg") / "bundle"
    shutil.copytree(DEMO_BUNDLE, bundle)
    (bundle / "okf-loom.config.yaml").write_text(
        "studio:\n  theme: swiss-light\n", encoding="utf-8"
    )
    cfg_dir = bundle / ".okf-loom" / "viewer"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps({"theme": "technical-dark"}), encoding="utf-8"
    )
    proc, base = _start_okf_serve(bundle)
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def static_site_url(tmp_path_factory):
    """Static build of the demo bundle served over plain HTTP."""
    if not DEMO_BUNDLE.is_dir():
        pytest.skip(f"demo bundle not found at {DEMO_BUNDLE}")
    out = tmp_path_factory.mktemp("staticsite") / "site"
    build = subprocess.run(
        okf_module_argv(
            "build", str(DEMO_BUNDLE), "--target", "static", "--out", str(out),
        ),
        cwd=str(TOOLKIT_ROOT),
        capture_output=True,
        text=True,
        env=okf_subprocess_env(),
    )
    if build.returncode != 0:
        pytest.skip(f"static build failed: {build.stderr[-500:]}")
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(out),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_http(proc, base, "/index.html")
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def spa_site_url(tmp_path_factory):
    """SPA build of the demo bundle served over plain HTTP from the site
    root (the spa target links assets at absolute /__static paths)."""
    if not DEMO_BUNDLE.is_dir():
        pytest.skip(f"demo bundle not found at {DEMO_BUNDLE}")
    out = tmp_path_factory.mktemp("spasite") / "site"
    build = subprocess.run(
        okf_module_argv(
            "build", str(DEMO_BUNDLE), "--target", "spa", "--out", str(out),
        ),
        cwd=str(TOOLKIT_ROOT),
        capture_output=True,
        text=True,
        env=okf_subprocess_env(),
    )
    if build.returncode != 0:
        pytest.skip(f"spa build failed: {build.stderr[-500:]}")
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(out),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_http(proc, base, "/index.html")
    try:
        yield base
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def single_file_url(tmp_path_factory):
    """Rendered single-file viewer opened via file:// (fully client-side)."""
    if not DEMO_BUNDLE.is_dir():
        pytest.skip(f"demo bundle not found at {DEMO_BUNDLE}")
    out = tmp_path_factory.mktemp("singlefile") / "viz.html"
    render = subprocess.run(
        okf_module_argv("render", str(DEMO_BUNDLE), "--out", str(out)),
        cwd=str(TOOLKIT_ROOT),
        capture_output=True,
        text=True,
        env=okf_subprocess_env(),
    )
    if render.returncode != 0 or not out.is_file():
        pytest.skip(f"single-file render failed: {render.stderr[-500:]}")
    return out.as_uri()


@pytest.fixture
def page():
    """Fresh Playwright Page per test (same launch fallbacks as the viewer
    browser suite: $AIC_PLAYWRIGHT_CHROME_PATH → chrome channel → chromium)."""
    chrome_path = os.environ.get("AIC_PLAYWRIGHT_CHROME_PATH") or ""
    attempts: list[dict] = []
    if chrome_path:
        attempts.append({"executable_path": chrome_path, "args": ["--no-sandbox"]})
    attempts.append({"channel": "chrome"})
    attempts.append({})
    with sync_playwright() as p:
        browser = None
        last_exc: Exception | None = None
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
                f"run `playwright install chromium`. ({last_exc})"
            )
        try:
            context = browser.new_context(color_scheme="light")
            pg = context.new_page()
            yield pg
            context.close()
        finally:
            browser.close()


def _theme(page) -> str:
    return page.evaluate("document.documentElement.getAttribute('data-theme')")


def _stored(page, key: str):
    return page.evaluate(f"localStorage.getItem('{key}')")


def _wait_theme(page, expected: str) -> None:
    page.wait_for_function(
        "t => document.documentElement.getAttribute('data-theme') === t",
        arg=expected,
        timeout=5000,
    )


# ---------------------------------------------------------------------------
# Configured default
# ---------------------------------------------------------------------------


def test_configured_default_survives_first_boot(configured_server_url, page):
    """No saved preference: the validated configured theme governs — and the
    boot never copies it into storage (config stays config)."""
    page.goto(f"{configured_server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-dark"
    assert _stored(page, "okf-theme-family") is None
    assert _stored(page, "okf-theme-mode") is None
    assert _stored(page, "okf-theme") is None
    # The popover reflects the configured state, not a hardcoded default.
    page.click("#okf-theme")
    assert page.get_attribute(
        '.okf-appearance__opt[data-okf-set="family"][data-okf-val="technical"]',
        "aria-checked") == "true"
    assert page.get_attribute(
        '.okf-appearance__opt[data-okf-set="mode"][data-okf-val="dark"]',
        "aria-checked") == "true"


def test_saved_preference_outranks_configured(configured_server_url, page):
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-family','swiss');"
        "localStorage.setItem('okf-theme-mode','light');}catch(e){}"
    )
    page.goto(f"{configured_server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-light"


def test_explicit_auto_outranks_configured_mode(configured_server_url, page):
    """A chosen Auto beats the configured dark default: with a light OS the
    page resolves light, keeping the configured technical family."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-mode','auto');}catch(e){}"
    )
    page.goto(f"{configured_server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-light"  # family from config, mode auto+light OS


# ---------------------------------------------------------------------------
# Family/mode orthogonality + OS following
# ---------------------------------------------------------------------------


def test_technical_plus_auto_survives_navigation_and_follows_os(server_url, page):
    """The Round-2 defect matrix: pick Technical while Auto → family persists
    independently, navigation keeps it, and TWO consecutive OS changes are
    followed without persisting the resolved theme."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-light"  # Swiss Auto/OS fallback, light OS

    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="family"][data-okf-val="technical"]')
    assert _theme(page) == "technical-light"
    assert _stored(page, "okf-theme-family") == "technical"
    assert _stored(page, "okf-theme-mode") is None      # mode untouched: still Auto
    assert _stored(page, "okf-theme") is None           # no concrete mirror while Auto

    # Navigation (wiki → graph) keeps Technical + Auto.
    page.goto(f"{server_url}/__graph", wait_until="load")
    assert _theme(page) == "technical-light"

    # Two consecutive OS changes are both honoured...
    page.emulate_media(color_scheme="dark")
    _wait_theme(page, "technical-dark")
    page.emulate_media(color_scheme="light")
    _wait_theme(page, "technical-light")
    # ...and the resolved value was never frozen into storage.
    assert _stored(page, "okf-theme-mode") is None
    assert _stored(page, "okf-theme") is None


def test_wiki_page_follows_two_os_changes_while_auto(server_url, page):
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-light"
    page.emulate_media(color_scheme="dark")
    _wait_theme(page, "swiss-dark")
    page.emulate_media(color_scheme="light")
    _wait_theme(page, "swiss-light")
    assert _stored(page, "okf-theme") is None


def test_explicit_dark_persists_across_reload_and_ignores_os(server_url, page):
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="mode"][data-okf-val="dark"]')
    assert _theme(page) == "swiss-dark"
    assert _stored(page, "okf-theme-mode") == "dark"
    # Explicit choice IS mirrored to the legacy key for old same-origin pages.
    assert _stored(page, "okf-theme") == "swiss-dark"

    page.reload(wait_until="load")
    assert _theme(page) == "swiss-dark"
    page.emulate_media(color_scheme="light")
    page.wait_for_timeout(150)  # allow any (wrong) scheme handler to run
    assert _theme(page) == "swiss-dark", "explicit mode must ignore the OS"


def test_returning_to_auto_clears_mirror_and_follows_os(server_url, page):
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-family','technical');"
        "localStorage.setItem('okf-theme-mode','dark');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-dark"
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="mode"][data-okf-val="auto"]')
    _wait_theme(page, "technical-light")  # light OS; family kept
    assert _stored(page, "okf-theme-mode") == "auto"
    assert _stored(page, "okf-theme") is None  # mirror removed while Auto


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("legacy", "family", "mode", "theme"),
    [
        ("pastel", "swiss", "light", "swiss-light"),
        ("midnight", "technical", "dark", "technical-dark"),
        ("swiss-dark", "swiss", "dark", "swiss-dark"),
    ],
)
def test_legacy_okf_theme_migrates_once(server_url, page, legacy, family, mode, theme):
    """Retired names and old concrete pins migrate into the canonical keys
    through the same resolver; the mirror is normalized."""
    page.context.add_init_script(
        f"try{{localStorage.setItem('okf-theme','{legacy}');}}catch(e){{}}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == theme
    assert _stored(page, "okf-theme-family") == family
    assert _stored(page, "okf-theme-mode") == mode
    assert _stored(page, "okf-theme") == theme


def test_family_only_pref_with_stale_mirror_removes_mirror_at_boot(server_url, page):
    """Invariant: a valid family-only preference must NOT leave a stale
    concrete legacy mirror in place — boot removes it. Configured/fallback
    dimensions are never synthesized into a mirror."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme','technical-dark');"
        "localStorage.setItem('okf-theme-family','technical');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-light"  # family=technical, no mode → Auto+light OS
    assert _stored(page, "okf-theme-family") == "technical"
    assert _stored(page, "okf-theme-mode") is None
    assert _stored(page, "okf-theme") is None  # stale mirror removed; no synthesized mirror


def test_mode_only_pref_with_stale_mirror_removes_mirror_at_boot(server_url, page):
    """Invariant: a valid mode-only preference must NOT leave a stale concrete
    legacy mirror — boot removes it (fallback family is never synthesized)."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme','technical-dark');"
        "localStorage.setItem('okf-theme-mode','dark');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-dark"  # family fallback swiss, explicit dark
    assert _stored(page, "okf-theme-family") is None
    assert _stored(page, "okf-theme-mode") == "dark"
    assert _stored(page, "okf-theme") is None  # stale mirror removed


def test_corrupt_family_with_stale_mirror_falls_back_and_removes_mirror(server_url, page):
    """Corrupt family value: that dimension falls back, the stale mirror is
    removed at boot, and the corrupt key is retained (its presence keeps the
    legacy migration gate closed so the mirror cannot be re-read)."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme','technical-dark');"
        "localStorage.setItem('okf-theme-family','banana');"
        "localStorage.setItem('okf-theme-mode','dark');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-dark"  # corrupt family → swiss fallback; explicit dark
    assert _stored(page, "okf-theme-family") == "banana"  # retained: migration gate
    assert _stored(page, "okf-theme-mode") == "dark"
    assert _stored(page, "okf-theme") is None  # stale mirror removed, not re-admitted


def test_corrupt_mode_with_stale_mirror_falls_back_and_removes_mirror(server_url, page):
    """Corrupt mode value behaves as Auto: family kept, mode Auto, stale mirror
    removed at boot."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme','technical-dark');"
        "localStorage.setItem('okf-theme-family','technical');"
        "localStorage.setItem('okf-theme-mode','sideways');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-light"  # family kept, corrupt mode → Auto + light OS
    assert _stored(page, "okf-theme-family") == "technical"
    assert _stored(page, "okf-theme-mode") == "sideways"  # retained: migration gate
    assert _stored(page, "okf-theme") is None


def test_partial_preference_never_synthesizes_mirror_from_configured_fallback(
    configured_server_url, page,
):
    """On a configured server (technical-dark), a family-only user preference
    plus a stale concrete mirror: boot removes the stale mirror and does NOT
    synthesize a replacement from the configured dark mode. The configured
    mode influences resolution (swiss family + configured dark → swiss-dark)
    but is neither persisted as a user mode nor written to the legacy key."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-family','swiss');"
        "localStorage.setItem('okf-theme','technical-dark');}catch(e){}"
    )
    page.goto(f"{configured_server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-dark"  # swiss family + configured dark mode
    assert _stored(page, "okf-theme-family") == "swiss"
    assert _stored(page, "okf-theme-mode") is None  # configured dark NOT persisted
    assert _stored(page, "okf-theme") is None  # stale mirror removed; nothing synthesized


def test_canonical_keys_outrank_stale_legacy_mirror(server_url, page):
    """Once the canonical keys exist the legacy key is never re-read: a
    stale/conflicting mirror cannot become a second authority."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme','technical-dark');"
        "localStorage.setItem('okf-theme-family','swiss');"
        "localStorage.setItem('okf-theme-mode','light');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-light"


# ---------------------------------------------------------------------------
# Storage denial
# ---------------------------------------------------------------------------


def test_storage_denied_keeps_resolution_and_in_page_switching(server_url, page):
    """A throwing localStorage disables persistence only: boot resolves the
    normal fallback and the Appearance controls still switch in-session."""
    page.context.add_init_script(
        "Object.defineProperty(window, 'localStorage', {"
        "  get() { throw new DOMException('denied', 'SecurityError'); }"
        "});"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-light"  # not forced to some other theme
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="family"][data-okf-val="technical"]')
    assert _theme(page) == "technical-light"  # in-page switching still works
    page.emulate_media(color_scheme="dark")
    _wait_theme(page, "technical-dark")  # Auto still follows the OS


# ---------------------------------------------------------------------------
# Change event
# ---------------------------------------------------------------------------


def test_theme_changed_event_fires_once_per_actual_change(server_url, page):
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.evaluate(
        "window.__events = [];"
        "window.addEventListener('okf-loom:themeChanged',"
        "  e => window.__events.push(e.detail));"
    )
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="mode"][data-okf-val="dark"]')
    page.click('.okf-appearance__opt[data-okf-set="mode"][data-okf-val="dark"]')  # no-op
    page.click('.okf-appearance__opt[data-okf-set="family"][data-okf-val="technical"]')
    events = page.evaluate("window.__events")
    assert len(events) == 2, f"expected 2 events (no-op suppressed), got {events}"
    assert events[0]["theme"] == "swiss-dark"
    assert events[0]["previousTheme"] == "swiss-light"
    assert events[0]["resolvedMode"] == "dark"
    assert events[0]["previousResolvedMode"] == "light"
    assert events[1]["theme"] == "technical-dark"
    assert events[1]["resolvedMode"] == "dark"  # family-only: mode unchanged
    assert events[1]["previousResolvedMode"] == "dark"


def _cy_palette_probe(page) -> dict:
    """Read the LIVE Cytoscape node/edge style through the window.__okfLoomGraph
    diagnostic hook (durable canvas-state proof, not a DOM/root proxy)."""
    return page.evaluate(
        """() => {
            const cy = window.__okfLoomGraph && window.__okfLoomGraph.cy;
            if (!cy || !cy.nodes().length) return null;
            return {
              nodeText: cy.nodes().first().style('color'),
              edgeLine: cy.edges().length ? cy.edges().first().style('line-color') : null,
            };
        }"""
    )


def _rgb(css: str) -> tuple:
    import re as _re
    return tuple(int(x) for x in _re.findall(r"\d+(?:\.\d+)?", css or "")[:3])


def test_graph_canvas_recolors_on_auto_os_transitions(server_url, page):
    """Direct consumer proof: across an ACTUAL Auto OS transition the
    Cytoscape stylesheet re-syncs to the resolved theme's palette (GRAPH_COLORS
    nodeText/edge mirror wiki.css --okf-fg / --okf-border-strong). Asserting
    only the root data-theme would not catch a dead okf-loom:themeChanged
    listener."""
    SWISS_LIGHT_FG = (17, 20, 24)     # #111418 — GRAPH_COLORS["swiss-light"]
    SWISS_DARK_FG = (240, 242, 244)   # #f0f2f4 — GRAPH_COLORS["swiss-dark"]
    page.goto(f"{server_url}/__graph", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.wait_for_function(
        "() => window.__okfLoomGraph && window.__okfLoomGraph.cy"
        " && window.__okfLoomGraph.cy.nodes().length > 0", timeout=15000)

    assert _theme(page) == "swiss-light"
    probe = _cy_palette_probe(page)
    assert _rgb(probe["nodeText"]) == SWISS_LIGHT_FG
    assert _rgb(probe["edgeLine"]) == SWISS_LIGHT_FG  # swiss edge = fg (hairline grid)

    # First OS flip while Auto: canvas follows.
    page.emulate_media(color_scheme="dark")
    _wait_theme(page, "swiss-dark")
    probe = _cy_palette_probe(page)
    assert _rgb(probe["nodeText"]) == SWISS_DARK_FG, "canvas did not re-sync on OS dark"
    assert _rgb(probe["edgeLine"]) == SWISS_DARK_FG

    # Second consecutive flip: Auto was not frozen (nothing was persisted).
    page.emulate_media(color_scheme="light")
    _wait_theme(page, "swiss-light")
    probe = _cy_palette_probe(page)
    assert _rgb(probe["nodeText"]) == SWISS_LIGHT_FG, "canvas froze after first OS change"
    assert _stored(page, "okf-theme") is None
    assert _stored(page, "okf-theme-mode") is None


def test_graph_explicit_dark_survives_os_change(server_url, page):
    page.goto(f"{server_url}/__graph", wait_until="load")
    page.wait_for_selector("#okf-graph canvas", timeout=15000)
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="mode"][data-okf-val="dark"]')
    assert _theme(page) == "swiss-dark"
    page.emulate_media(color_scheme="light")
    page.wait_for_timeout(150)
    assert _theme(page) == "swiss-dark", "explicit dark must survive OS change on graph"


# ---------------------------------------------------------------------------
# Studio integration
# ---------------------------------------------------------------------------


def test_studio_palette_theme_commands_drive_shared_resolver(server_url, page):
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.wait_for_function("() => window.okfLoomStudio", timeout=15000)

    def run_command(label: str) -> None:
        page.keyboard.press("Control+k")
        box = page.wait_for_selector(".okf-palette__input", state="visible")
        box.fill(label)
        item = page.wait_for_selector(
            f'.okf-palette__item:has-text("{label}")', state="visible")
        item.click()

    run_command("Theme: Technical Dark")
    assert _theme(page) == "technical-dark"
    assert _stored(page, "okf-theme-family") == "technical"
    assert _stored(page, "okf-theme-mode") == "dark"
    assert _stored(page, "okf-theme") == "technical-dark"

    # "Auto" switches mode only — the chosen family survives.
    run_command("Theme: Auto (follow OS)")
    _wait_theme(page, "technical-light")  # light OS
    assert _stored(page, "okf-theme-family") == "technical"
    assert _stored(page, "okf-theme-mode") == "auto"
    assert _stored(page, "okf-theme") is None


# ---------------------------------------------------------------------------
# Static + single-file outputs
# ---------------------------------------------------------------------------


def test_static_build_boots_contract_and_persists_across_pages(static_site_url, page):
    page.goto(f"{static_site_url}/index.html", wait_until="load")
    assert _theme(page) == "swiss-light"
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="family"][data-okf-val="technical"]')
    assert _theme(page) == "technical-light"
    # Same-origin static page navigation keeps the preference.
    page.goto(f"{static_site_url}/__graph.html", wait_until="load")
    assert _theme(page) == "technical-light"
    page.emulate_media(color_scheme="dark")
    _wait_theme(page, "technical-dark")
    page.emulate_media(color_scheme="light")
    _wait_theme(page, "technical-light")


def test_single_file_boots_contract_and_follows_os(single_file_url, page):
    page.goto(single_file_url, wait_until="load")
    assert _theme(page) == "swiss-light"
    page.emulate_media(color_scheme="dark")
    _wait_theme(page, "swiss-dark")
    page.emulate_media(color_scheme="light")
    _wait_theme(page, "swiss-light")
    # Appearance popover works in the fully offline artifact too.
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="family"][data-okf-val="technical"]')
    assert _theme(page) == "technical-light"

# ---------------------------------------------------------------------------
# Partial/failed persistence + mirror reconciliation (review findings)
# ---------------------------------------------------------------------------

_WRITE_ONLY_DENIAL = (
    "Storage.prototype.setItem = function () {"
    "  throw new DOMException('write denied', 'SecurityError'); };"
    "Storage.prototype.removeItem = function () {"
    "  throw new DOMException('write denied', 'SecurityError'); };"
)


def test_legacy_preference_survives_write_only_storage(server_url, page):
    """Reads succeed, writes throw: the parsed legacy preference must stay in
    module memory so THIS page still resolves it, even though the canonical
    keys cannot be written."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme','technical-dark');}catch(e){}"
        + _WRITE_ONLY_DENIAL
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-dark", "legacy preference lost under write-only storage"
    # The migration writes failed silently — nothing new was persisted.
    assert _stored(page, "okf-theme-family") is None
    assert _stored(page, "okf-theme-mode") is None
    assert _stored(page, "okf-theme") == "technical-dark"


def test_boot_removes_stale_mirror_when_canonical_auto(server_url, page):
    """Canonical Auto + a stale concrete mirror (e.g. left by an older build):
    boot reconciliation removes the mirror so old pages follow the OS again."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-family','technical');"
        "localStorage.setItem('okf-theme-mode','auto');"
        "localStorage.setItem('okf-theme','technical-dark');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-light"  # auto + light OS
    assert _stored(page, "okf-theme") is None, "stale concrete mirror not removed"


def test_boot_corrects_conflicting_mirror_when_fully_explicit(server_url, page):
    """Canonical explicit family+mode outrank a conflicting mirror; boot
    rewrites the mirror to the user's actual preference."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-family','swiss');"
        "localStorage.setItem('okf-theme-mode','dark');"
        "localStorage.setItem('okf-theme','technical-dark');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-dark"
    assert _stored(page, "okf-theme") == "swiss-dark", "conflicting mirror not corrected"


def test_partial_preference_never_bakes_configured_family_into_storage(
    configured_server_url, page
):
    """User saved only mode=dark; family comes from the configured default at
    RESOLVE time. Reconciliation must not write a mirror (or family key) that
    would freeze the configured family into user storage."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-mode','dark');}catch(e){}"
    )
    page.goto(f"{configured_server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-dark"  # family from config, mode from user
    assert _stored(page, "okf-theme-family") is None
    assert _stored(page, "okf-theme") is None, "configured family baked into the mirror"


# ---------------------------------------------------------------------------
# Corrupt / partial canonical keys (per-dimension fallback)
# ---------------------------------------------------------------------------


def test_corrupt_family_falls_back_per_dimension_and_gates_legacy(server_url, page):
    """A corrupt family value is ignored (that dimension falls back) but its
    raw presence still gates migration: the stale legacy mirror must NOT be
    re-read as authority, and the corrupt key is retained to keep that gate
    closed on future boots."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-family','banana');"
        "localStorage.setItem('okf-theme-mode','dark');"
        "localStorage.setItem('okf-theme','technical-dark');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "swiss-dark", "corrupt family must fall back, not adopt the mirror"
    assert _stored(page, "okf-theme-family") == "banana"  # retained: migration gate
    # Corrupt canonical state (family invalid): not a fully explicit theme,
    # so the stale concrete mirror is REMOVED at boot — never re-read as
    # authority. The corrupt key itself stays to keep the migration gate closed.
    assert _stored(page, "okf-theme") is None


def test_corrupt_mode_falls_back_to_auto(server_url, page):
    page.context.add_init_script(
        "try{localStorage.setItem('okf-theme-family','technical');"
        "localStorage.setItem('okf-theme-mode','sideways');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert _theme(page) == "technical-light"  # family kept; mode → Auto + light OS
    page.emulate_media(color_scheme="dark")
    _wait_theme(page, "technical-dark")  # corrupt mode behaves as Auto (follows OS)
    assert _stored(page, "okf-theme-mode") == "sideways"  # retained, ignored


# ---------------------------------------------------------------------------
# Modifiers (contrast / border)
# ---------------------------------------------------------------------------


def test_modifiers_persist_navigate_reload_and_reset(server_url, page):
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="contrast"][data-okf-val="soft"]')
    page.click('.okf-appearance__opt[data-okf-set="border"][data-okf-val="muted"]')
    assert _stored(page, "okf-contrast") == "soft"
    assert _stored(page, "okf-border") == "muted"

    page.goto(f"{server_url}/__graph", wait_until="load")  # navigation
    assert page.evaluate("document.documentElement.getAttribute('data-okf-contrast')") == "soft"
    assert page.evaluate("document.documentElement.getAttribute('data-okf-border')") == "muted"
    page.reload(wait_until="load")
    assert page.evaluate("document.documentElement.getAttribute('data-okf-contrast')") == "soft"

    # Reset to defaults removes both attribute and key.
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="contrast"][data-okf-val="high"]')
    page.click('.okf-appearance__opt[data-okf-set="border"][data-okf-val="on"]')
    assert page.evaluate("document.documentElement.getAttribute('data-okf-contrast')") is None
    assert page.evaluate("document.documentElement.getAttribute('data-okf-border')") is None
    assert _stored(page, "okf-contrast") is None
    assert _stored(page, "okf-border") is None


def test_corrupt_modifier_values_are_removed_and_default_applies(server_url, page):
    """Modifiers self-heal (documented asymmetry with the canonical theme
    keys, whose raw presence gates migration): a corrupt stored value is
    deleted at boot and the default applies."""
    page.context.add_init_script(
        "try{localStorage.setItem('okf-contrast','purple');"
        "localStorage.setItem('okf-border','dotted');}catch(e){}"
    )
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    assert page.evaluate("document.documentElement.getAttribute('data-okf-contrast')") is None
    assert page.evaluate("document.documentElement.getAttribute('data-okf-border')") is None
    assert _stored(page, "okf-contrast") is None, "corrupt contrast value not removed"
    assert _stored(page, "okf-border") is None, "corrupt border value not removed"


def test_modifier_switching_survives_denied_writes(server_url, page):
    page.context.add_init_script(_WRITE_ONLY_DENIAL)
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="contrast"][data-okf-val="soft"]')
    assert page.evaluate("document.documentElement.getAttribute('data-okf-contrast')") == "soft"
    assert _stored(page, "okf-contrast") is None  # write failed silently; session state intact
    assert page.get_attribute(
        '.okf-appearance__opt[data-okf-set="contrast"][data-okf-val="soft"]',
        "aria-checked") == "true"


# ---------------------------------------------------------------------------
# Configured-source precedence (viewer JSON vs studio YAML)
# ---------------------------------------------------------------------------


def test_studio_yaml_auto_carries_no_preference(server_url, page):
    """The default studio.theme=auto is delivered in the bootstrap but must
    register no configured preference: Swiss Auto/OS fallback governs."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    boot_theme = page.evaluate(
        "JSON.parse(document.getElementById('okf-studio-bootstrap').textContent).theme")
    assert boot_theme == "auto"
    assert _theme(page) == "swiss-light"
    state = page.evaluate("window.OKFLoomTheme.getState()")
    assert state["configuredFamily"] is None and state["configuredMode"] is None


def test_studio_yaml_concrete_theme_applies_when_viewer_unconfigured(
    studio_theme_server_url, page
):
    page.goto(f"{studio_theme_server_url}/tables/orders", wait_until="load")
    boot_theme = page.evaluate(
        "JSON.parse(document.getElementById('okf-studio-bootstrap').textContent).theme")
    assert boot_theme == "technical-dark"
    assert _theme(page) == "technical-dark"
    # Configured, not saved: nothing lands in storage.
    assert _stored(page, "okf-theme-family") is None
    assert _stored(page, "okf-theme-mode") is None
    assert _stored(page, "okf-theme") is None


def test_viewer_json_outranks_studio_yaml_on_conflict(
    conflicting_config_server_url, page
):
    """One unambiguous authority: the server-painted viewer JSON theme wins
    over a conflicting studio.theme (spec §9 precedence)."""
    page.goto(f"{conflicting_config_server_url}/tables/orders", wait_until="load")
    boot_theme = page.evaluate(
        "JSON.parse(document.getElementById('okf-studio-bootstrap').textContent).theme")
    assert boot_theme == "swiss-light"  # the conflict genuinely exists...
    assert _theme(page) == "technical-dark"  # ...and viewer JSON wins
    state = page.evaluate("window.OKFLoomTheme.getState()")
    assert state["configuredFamily"] == "technical"
    assert state["configuredMode"] == "dark"


# ---------------------------------------------------------------------------
# SPA output
# ---------------------------------------------------------------------------


def test_spa_build_boots_contract_and_persists_across_pages(spa_site_url, page):
    page.goto(f"{spa_site_url}/index.html", wait_until="load")
    assert _theme(page) == "swiss-light"
    page.click("#okf-theme")
    page.click('.okf-appearance__opt[data-okf-set="family"][data-okf-val="technical"]')
    assert _theme(page) == "technical-light"
    page.goto(f"{spa_site_url}/__graph.html", wait_until="load")
    assert _theme(page) == "technical-light"
    page.emulate_media(color_scheme="dark")
    _wait_theme(page, "technical-dark")
    page.emulate_media(color_scheme="light")
    _wait_theme(page, "technical-light")
    assert _stored(page, "okf-theme") is None
