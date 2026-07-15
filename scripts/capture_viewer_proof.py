#!/usr/bin/env python3
"""Lightweight dated live/static browser smoke proof for the OKF viewer.

This is the small recurring viewer proof, not the stable curated media set
(``capture_readme_media.py``) or the comprehensive Editorial Workbench parity
matrix (``capture_final_workbench_proof.py``).

Renders the demo bundle BOTH live (``scripts/okf-loom serve``) AND as a static build
(``scripts/okf-loom build --target static``), then captures full-page screenshots of:

* the full-page Cytoscape graph view,
* a concept page (``tables/orders``),
* the search results page (query ``orders`` on the live server; the
  static build has no search backend, so we capture the empty-results
  page that documents the degraded state),

writing them under ``docs/screenshots/<YYYY-MM-DD>-viewer/``.

Requires explicit Playwright browser-proof dependencies + Chromium::

    python -m pip install playwright
    playwright install chromium
    python scripts/capture_viewer_proof.py [--bundle samples/demo_bundle] \\
        [--out-dir docs/screenshots]

Chrome's sandbox remains enabled by default. A constrained root container may
explicitly set ``OKF_CAPTURE_NO_SANDBOX=1`` when its sandbox cannot initialize.

Design notes
------------
* Import-safe: Playwright is imported lazily inside :func:`main`, so the
  module has no side effects on import (mirrors the pattern in
  ``scripts/build_skill_archive.py``).
* The live server is started on an ephemeral port via ``subprocess`` and
  is always torn down in a ``finally`` block (SIGTERM, then SIGKILL).
* The static build is served from a tmp dir via the stdlib
  ``http.server.ThreadingHTTPServer`` so the script does not depend on
  ``scripts/okf-loom serve`` for static artefacts.
* Readiness is polled, not slept on (no ``time.sleep`` busy-waits past
  the poll interval); the script exits non-zero if Playwright or the
  Chromium binary is unavailable, or if either server fails to start.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import http.server
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

try:  # Supports direct script execution and import through the repo namespace.
    from scripts.capture_support import (
        display_path,
        launch_chromium,
        wait_for_http_ok,
        wait_for_capture_ready,
        write_capture_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - direct invocation path
    from capture_support import (
        display_path,
        launch_chromium,
        wait_for_http_ok,
        wait_for_capture_ready,
        write_capture_manifest,
    )

__all__ = ["main"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Resolved repo root (the directory containing pyproject.toml). Lets the
# script run from any CWD.
_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPT_DIR.parent
SCRIPT_PATH = REPO_ROOT / "scripts"
DEFAULT_BUNDLE = REPO_ROOT / "samples" / "demo_bundle"
DEFAULT_OUT_DIR = REPO_ROOT / "docs" / "screenshots"

# Live-server readiness budget (seconds). The OKF server boots in well
# under a second; this covers slow runners.
_SERVER_STARTUP_TIMEOUT = 20.0
# Per-shot navigation + settle budget for Playwright.
_PAGE_LOAD_TIMEOUT_MS = 15_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Reserve and immediately release an ephemeral port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _log(msg: str) -> None:
    print(f"[capture_viewer_proof] {msg}", file=sys.stderr)


def _script_env() -> dict[str, str]:
    """Return an environment that can import checkout-local scripts."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{SCRIPT_PATH}{os.pathsep}{existing}" if existing else str(SCRIPT_PATH)
    )
    return env


# ---------------------------------------------------------------------------
# Live server (scripts/okf-loom serve)
# ---------------------------------------------------------------------------


class _LiveServer:
    """Context manager that runs ``scripts/okf-loom serve <bundle>`` on an ephemeral port."""

    def __init__(self, bundle: Path) -> None:
        self.bundle = bundle
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> str:
        self._proc = subprocess.Popen(
            [
                str(REPO_ROOT / "scripts" / "okf-loom"), "serve", str(self.bundle),
                "--host", "127.0.0.1", "--port", str(self.port),
                "--no-watch", "--no-open",
            ],
            cwd=str(REPO_ROOT),
            env=_script_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not wait_for_http_ok(
            self.base, timeout=_SERVER_STARTUP_TIMEOUT, proc=self._proc
        ):
            raise RuntimeError(
                f"scripts/okf-loom serve did not become ready at {self.base} within "
                f"{_SERVER_STARTUP_TIMEOUT:g}s"
            )
        _log(f"live server ready at {self.base}")
        return self.base

    def __exit__(self, *exc) -> None:
        proc = self._proc
        if proc is None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        self._proc = None


# ---------------------------------------------------------------------------
# Static-build server (stdlib http.server)
# ---------------------------------------------------------------------------


class _StaticServer:
    """Context manager that serves a static build dir on an ephemeral port."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> str:
        handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(  # noqa: E731
            *a, directory=str(self.root), **kw
        )
        self._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", self.port), handler
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()
        if not wait_for_http_ok(self.base, timeout=_SERVER_STARTUP_TIMEOUT):
            raise RuntimeError(
                f"static-build server did not become ready at {self.base} "
                f"within {_SERVER_STARTUP_TIMEOUT:g}s"
            )
        _log(f"static server ready at {self.base} (root={self.root})")
        return self.base

    def __exit__(self, *exc) -> None:
        srv = self._server
        if srv is not None:
            srv.shutdown()
            srv.server_close()
        self._server = None
        self._thread = None


# ---------------------------------------------------------------------------
# Static build (scripts/okf-loom build --target static)
# ---------------------------------------------------------------------------


def _build_static_site(bundle: Path, out_dir: Path) -> None:
    """Run ``scripts/okf-loom build <bundle> --out <out_dir> --target static``.

    Raises ``RuntimeError`` on non-zero exit so callers can surface a
    clear diagnostic.

    Note: the CLI's ``build`` subcommand takes the output path via
    ``--out`` (see ``scripts/okf_loom/cli.py``), not positionally.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            str(REPO_ROOT / "scripts" / "okf-loom"), "build", str(bundle),
            "--out", str(out_dir), "--target", "static",
        ],
        cwd=str(REPO_ROOT),
        env=_script_env(),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"scripts/okf-loom build failed (rc={proc.returncode}):\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    _log(f"static site built at {out_dir}")


# ---------------------------------------------------------------------------
# Screenshot capture
# ---------------------------------------------------------------------------


def _capture_targets(
    base: str, page, *, label: str, out_dir: Path, records: list[dict]
) -> list[Path]:
    """Capture the three browser-proof pages from ``base``; return the file paths.

    ``label`` is "live" or "static" and is folded into each filename so a
    single dated output directory can hold both sets side by side.
    """
    shots: list[Path] = []

    # 1. Graph page. Live server route: /__graph. Static file: /__graph.html.
    graph_url = f"{base}/__graph.html" if label == "static" else f"{base}/__graph"
    page.goto(graph_url, wait_until="load", timeout=_PAGE_LOAD_TIMEOUT_MS)
    ready = wait_for_capture_ready(page, "graph", timeout_ms=_PAGE_LOAD_TIMEOUT_MS)
    p = out_dir / f"{label}-graph.png"
    page.screenshot(path=str(p), full_page=True)
    shots.append(p)
    records.append({"file": p.name, "source": label,
                    "route": "/__graph" if label == "live" else "/__graph.html",
                    "theme": "swiss-light", "viewport": {"width": 1280, "height": 900},
                    "device_scale_factor": 2, "readiness": ready})

    # 2. Concept page (tables/orders).
    concept_url = (
        f"{base}/tables/orders.html" if label == "static" else f"{base}/tables/orders"
    )
    page.goto(concept_url, wait_until="load", timeout=_PAGE_LOAD_TIMEOUT_MS)
    ready = wait_for_capture_ready(page, "concept", timeout_ms=_PAGE_LOAD_TIMEOUT_MS)
    p = out_dir / f"{label}-concept-orders.png"
    page.screenshot(path=str(p), full_page=True)
    shots.append(p)
    records.append({"file": p.name, "source": label,
                    "route": "/tables/orders" if label == "live" else "/tables/orders.html",
                    "theme": "swiss-light", "viewport": {"width": 1280, "height": 900},
                    "device_scale_factor": 2, "readiness": ready})

    # 3. Search page. Live server: /__search?q=orders. Static build has no
    # search backend; the static search page renders with zero results,
    # which is itself the documented degraded-state artefact.
    search_url = (
        f"{base}/__search.html" if label == "static" else f"{base}/__search?q=orders"
    )
    page.goto(search_url, wait_until="load", timeout=_PAGE_LOAD_TIMEOUT_MS)
    ready = wait_for_capture_ready(page, "search", timeout_ms=_PAGE_LOAD_TIMEOUT_MS)
    p = out_dir / f"{label}-search.png"
    page.screenshot(path=str(p), full_page=True)
    shots.append(p)
    records.append({"file": p.name, "source": label,
                    "route": "/__search?q=orders" if label == "live" else "/__search.html",
                    "theme": "swiss-light", "viewport": {"width": 1280, "height": 900},
                    "device_scale_factor": 2, "readiness": ready})

    return shots


def _run_captures(
    bundle: Path, out_dir: Path, *, chrome_path: str | None = None
) -> tuple[list[Path], list[dict], str]:
    """Drive Playwright once for both live + static sources."""
    # Lazy import: this module stays import-safe (no top-level playwright
    # import) so tests / tooling can introspect it without the extra.
    from playwright.sync_api import sync_playwright

    captured: list[Path] = []
    records: list[dict] = []

    with sync_playwright() as p:
        # Launch once and reuse the resolved managed/system browser.
        launched = launch_chromium(p, chrome_path)
        browser = launched.browser
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                device_scale_factor=2,  # crisper screenshots for docs
            )
            context.add_init_script(
                "try { localStorage.setItem('okf-theme', 'swiss-light'); } catch (e) {}"
            )
            page = context.new_page()

            # --- live server ---
            with _LiveServer(bundle) as base:
                captured.extend(_capture_targets(
                    base, page, label="live", out_dir=out_dir, records=records
                ))

            # --- static build + stdlib http server ---
            static_dir = out_dir.parent / f"{out_dir.name}-static-src"
            _build_static_site(bundle, static_dir)
            with _StaticServer(static_dir) as base:
                captured.extend(
                    _capture_targets(
                        base, page, label="static", out_dir=out_dir, records=records
                    )
                )

            context.close()
        finally:
            browser.close()

    return captured, records, launched.source


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="capture_viewer_proof.py",
        description=(
            "Capture a lightweight dated live/static smoke proof of the OKF viewer for the demo "
            "bundle, both live (scripts/okf-loom serve) and static (scripts/okf-loom build --target "
            "static), under docs/screenshots/<date>-viewer/ "
            "(current spec §17); this is not the final parity matrix."
        ),
    )
    p.add_argument(
        "--bundle",
        type=Path,
        default=DEFAULT_BUNDLE,
        help=f"OKF bundle to render (default: {DEFAULT_BUNDLE})",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=(
            "parent output directory; a dated subdirectory "
            "<YYYY-MM-DD>-viewer/ is created inside it "
            f"(default: {DEFAULT_OUT_DIR})"
        ),
    )
    p.add_argument(
        "--chrome",
        default=None,
        help="path to Chrome/Chromium (then OKF_CHROME, AIC path, managed, system)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    # Parse argv FIRST so --help / --version exit cleanly without requiring
    # the optional browser-proof dependencies. Only then probe for Playwright.
    args = _build_arg_parser().parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print(
            "ERROR: playwright is not installed.\n"
            "  python -m pip install playwright\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        return 1

    bundle = args.bundle.resolve()
    out_parent = args.out_dir.resolve()

    if not bundle.is_dir():
        print(f"ERROR: bundle directory not found: {bundle}", file=sys.stderr)
        return 1

    today = _dt.date.today().isoformat()
    out_dir = out_parent / f"{today}-viewer"
    out_dir.mkdir(parents=True, exist_ok=True)

    _log(f"bundle={bundle}")
    _log(f"out_dir={out_dir}")

    try:
        captured, records, browser_source = _run_captures(
            bundle, out_dir, chrome_path=args.chrome
        )
    except (RuntimeError, SystemExit) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    manifest = write_capture_manifest(
        out_dir, records, repo_root=REPO_ROOT, browser_source=browser_source
    )

    print(f"# wrote {len(captured)} screenshots and manifest to {out_dir}")
    for path in [*captured, manifest]:
        rel = display_path(path, out_parent.parent)
        size = path.stat().st_size if path.exists() else 0
        print(f"  {rel}  ({size} bytes)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
