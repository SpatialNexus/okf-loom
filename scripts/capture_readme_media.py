#!/usr/bin/env python3
"""Capture the curated README media set (docs/media/) from the live studio.

Unlike ``capture_viewer_proof.py`` (dated proof artefacts for spec §17),
this script regenerates the STABLE, hand-picked set of images the README
links to. Filenames are fixed so the README never needs updating when the
media is refreshed:

* ``studio-home.png``        — dashboard index, Swiss Light
* ``showcase-rendering.png`` — Mermaid/KaTeX section of demo/showcase
* ``comment-composer.png``   — select-to-comment affordance + composer
* ``graph-map.png``          — full-page graph, Map lens, Swiss Light
* ``graph-bridges-dark.png`` — Bridges lens, Swiss Dark
* ``search.png``             — live search results
* ``themes.gif``             — demo/showcase cycling all four canonical themes
* ``graph-lenses.gif``       — the graph cycling Map→Themes→Flow→Bridges→Recent
* ``social-preview.png``     — 1280×640 Swiss Light graph preview
* ``comment-loop.mp4``       — deterministic semantic comment-composer sequence

Requires Playwright plus a Chromium-family browser::

    python -m pip install playwright pillow   # pillow only for the GIFs
    playwright install chromium               # OR have Google Chrome installed
    PYTHONPATH=scripts python scripts/capture_readme_media.py

Browser resolution order: ``--chrome PATH`` flag, ``OKF_CHROME`` and
``AIC_PLAYWRIGHT_CHROME_PATH`` env vars, Playwright's managed Chromium, then
system Chrome/Chromium channels and discovered executable paths.
Chrome's sandbox stays enabled unless a constrained root container explicitly
sets ``OKF_CAPTURE_NO_SANDBOX=1``.
Without Pillow the two GIFs are skipped with a warning; the PNGs still
capture. Stills are DPR-2 for crispness; GIF frames are DPR-1 to keep the
files README-friendly. GIFs autoplay exactly once, omit the infinite-loop
extension, and remain on their final semantic frame (WCAG 2.2.2).
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # Supports both direct script execution and import via the repo namespace.
    from scripts.capture_support import (
        display_path,
        launch_chromium,
        wait_for_http_ok,
        wait_for_capture_ready,
        wait_for_graph_layout_after,
        write_capture_manifest,
    )
except ModuleNotFoundError:  # pragma: no cover - direct invocation path
    from capture_support import (
        display_path,
        launch_chromium,
        wait_for_http_ok,
        wait_for_capture_ready,
        wait_for_graph_layout_after,
        write_capture_manifest,
    )

__all__ = ["main"]

_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPT_DIR.parent
DEFAULT_BUNDLE = REPO_ROOT / "docs-bundle"
DEFAULT_OUT_DIR = REPO_ROOT / "docs" / "media"

_SERVER_STARTUP_TIMEOUT = 20.0
_PAGE_LOAD_TIMEOUT_MS = 20_000
_CAPTURE_READY_TIMEOUT_MS = 12_000

STILL_VIEWPORT = {"width": 1440, "height": 900}
GIF_VIEWPORT = {"width": 1280, "height": 800}
GIF_FRAME_MS = 1_600
GIF_FINAL_FRAME_MS = 2_400
THEMES = ("swiss-light", "swiss-dark", "technical-light", "technical-dark")
LENSES = ("Map", "Themes", "Flow", "Bridges", "Recent")


def _log(msg: str) -> None:
    print(f"[capture_readme_media] {msg}", file=sys.stderr)


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _script_env() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{_SCRIPT_DIR}{os.pathsep}{existing}" if existing else str(_SCRIPT_DIR)
    )
    return env


class _LiveServer:
    """Run ``scripts/okf-loom serve <bundle>`` on an ephemeral port."""

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
                f"scripts/okf-loom serve did not become ready at {self.base} "
                f"within {_SERVER_STARTUP_TIMEOUT:g}s"
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
# Browser helpers
# ---------------------------------------------------------------------------


def _launch_browser(p, chrome_path: str | None):
    """Resolve a Chromium-family browser (see module docstring for order)."""
    return launch_chromium(p, chrome_path)


def _new_page(browser, *, viewport: dict, dpr: int, theme: str | None = None):
    """Context+page with the graph tour pre-dismissed and an optional theme."""
    ctx = browser.new_context(viewport=viewport, device_scale_factor=dpr)
    boot = "try{localStorage.setItem('okfGraphTourDone','1');"
    if theme:
        family, mode = theme.rsplit("-", 1)
        boot += (
            f"localStorage.setItem('okf-theme-family','{family}');"
            f"localStorage.setItem('okf-theme-mode','{mode}');"
            "localStorage.removeItem('okf-theme');"
        )
    boot += "}catch(e){}"
    ctx.add_init_script(boot)
    return ctx, ctx.new_page()


def _goto(page, url: str, target: str) -> dict:
    page.goto(url, wait_until="load", timeout=_PAGE_LOAD_TIMEOUT_MS)
    return wait_for_capture_ready(page, target, timeout_ms=_CAPTURE_READY_TIMEOUT_MS)


def _click_lens(page, lens: str) -> dict:
    """Select a graph lens chip by its accessible name."""
    previous = page.evaluate("() => window.__okfLoomGraph.layoutStats.lastAppliedSeq")
    page.get_by_role("radio", name=lens).click(timeout=5_000)
    wait_for_graph_layout_after(page, previous, timeout_ms=_CAPTURE_READY_TIMEOUT_MS)
    return wait_for_capture_ready(page, "graph", timeout_ms=_CAPTURE_READY_TIMEOUT_MS)


# ---------------------------------------------------------------------------
# Captures
# ---------------------------------------------------------------------------


def _capture_stills(
    browser, base: str, out_dir: Path, records: list[dict]
) -> list[Path]:
    shots: list[Path] = []

    def still(name: str, route: str, theme: str, readiness: dict) -> Path:
        p = out_dir / name
        shots.append(p)
        records.append({
            "file": name,
            "source": "live",
            "route": route,
            "theme": theme,
            "viewport": STILL_VIEWPORT,
            "device_scale_factor": 2,
            "readiness": readiness,
        })
        return p

    # Dashboard index.
    ctx, page = _new_page(browser, viewport=STILL_VIEWPORT, dpr=2, theme="swiss-light")
    ready = _goto(page, f"{base}/", "index")
    page.screenshot(path=str(still("studio-home.png", "/", "swiss-light", ready)))

    # Showcase concept, scrolled to the Mermaid/KaTeX stretch.
    ready = _goto(page, f"{base}/demo/showcase", "rendering")
    page.evaluate(
        """() => {
            const h = [...document.querySelectorAll('h2,h3')]
                .find(x => /Diagrams/i.test(x.textContent));
            if (h) h.scrollIntoView({block: 'start'});
            window.scrollBy(0, -16);
        }"""
    )
    page.screenshot(path=str(still(
        "showcase-rendering.png", "/demo/showcase", "swiss-light", ready
    )))

    # Select-to-comment: stage a real selection so the affordance appears,
    # open the composer, and type a representative ask for the agent.
    page.evaluate("window.scrollTo(0, 0)")
    page.evaluate(
        """() => {
            const body = document.querySelector('.okf-page__body');
            const para = body &&
                [...body.querySelectorAll('p')].find(p => p.textContent.length > 80);
            if (!para) return;
            para.scrollIntoView({block: 'center'});
            const r = document.createRange();
            r.selectNodeContents(para);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(r);
        }"""
    )
    page.locator(".okf-comment-afford button").wait_for(
        state="visible", timeout=_CAPTURE_READY_TIMEOUT_MS
    )
    page.click(".okf-comment-afford button", timeout=5_000)
    page.locator('textarea[aria-label="Comment for agent"]').wait_for(
        state="visible", timeout=_CAPTURE_READY_TIMEOUT_MS
    )
    page.fill(
        'textarea[aria-label="Comment for agent"]',
        "Tighten this intro and cross-link it to the graph lenses explanation.",
    )
    page.screenshot(path=str(still(
        "comment-composer.png", "/demo/showcase", "swiss-light", ready
    )))
    ctx.close()

    # Graph: Map lens (light) and Bridges lens (dark).
    ctx, page = _new_page(browser, viewport=STILL_VIEWPORT, dpr=2, theme="swiss-light")
    ready = _goto(page, f"{base}/__graph", "graph")
    page.screenshot(path=str(still("graph-map.png", "/__graph", "swiss-light", ready)))
    ctx.close()

    ctx, page = _new_page(browser, viewport=STILL_VIEWPORT, dpr=2, theme="swiss-dark")
    ready = _goto(page, f"{base}/__graph", "graph")
    ready = _click_lens(page, "Bridges")
    page.screenshot(path=str(still(
        "graph-bridges-dark.png", "/__graph?lens=bridges", "swiss-dark", ready
    )))
    ctx.close()

    # Live search.
    ctx, page = _new_page(browser, viewport=STILL_VIEWPORT, dpr=2, theme="swiss-light")
    ready = _goto(page, f"{base}/__search?q=studio", "search")
    page.screenshot(path=str(still(
        "search.png", "/__search?q=studio", "swiss-light", ready
    )))
    ctx.close()

    return shots


def _assemble_gif(frames: list, out_path: Path) -> None:
    """Stitch PNG bytes into a finite one-cycle GIF ending on the last frame.

    Deliberately omit Pillow's ``loop`` argument: ``loop=0`` writes the
    Netscape infinite-loop extension, while no extension means one autoplay
    cycle and a retained static final frame.
    """
    import io

    from PIL import Image

    images = [Image.open(io.BytesIO(f)).convert("RGB") for f in frames]
    images = [im.quantize(colors=255, dither=Image.Dither.NONE) for im in images]
    images[0].save(
        out_path,
        save_all=True,
        append_images=images[1:],
        duration=[GIF_FRAME_MS] * (len(images) - 1) + [GIF_FINAL_FRAME_MS],
        optimize=True,
    )


def _gif_playback_metadata(frame_count: int, final_frame: str) -> dict:
    """Manifest contract for finite GIF playback."""
    return {
        "autoplay": "finite-one-cycle",
        "loop_count": 1,
        "infinite_loop": False,
        "loop_extension": False,
        "frame_count": frame_count,
        "frame_duration_ms": GIF_FRAME_MS,
        "final_frame": final_frame,
        "final_frame_duration_ms": GIF_FINAL_FRAME_MS,
        "final_frame_retained": True,
    }


def _capture_gifs(browser, base: str, out_dir: Path, records: list[dict]) -> list[Path]:
    try:
        import PIL  # noqa: F401
    except ImportError:
        _log("WARNING: pillow not installed - skipping themes.gif and "
             "graph-lenses.gif (python -m pip install pillow)")
        return []

    shots: list[Path] = []

    # Theme cycle on the showcase page. One context per theme: renderers
    # (Mermaid/hljs) pick their skin at render time, so a reload per theme
    # is the honest capture.
    frames = []
    frame_readiness = []
    for theme in THEMES:
        ctx, page = _new_page(browser, viewport=GIF_VIEWPORT, dpr=1, theme=theme)
        frame_readiness.append(_goto(page, f"{base}/demo/showcase", "rendering"))
        frames.append(page.screenshot())
        ctx.close()
    path = out_dir / "themes.gif"
    _assemble_gif(frames, path)
    shots.append(path)
    records.append({"file": path.name, "source": "live", "route": "/demo/showcase",
                    "themes": list(THEMES), "viewport": GIF_VIEWPORT,
                    "device_scale_factor": 1,
                    "readiness": {"state": "valid", "detail": "all frames ready",
                                  "frames": frame_readiness},
                    "variants": {"playback": _gif_playback_metadata(
                        len(THEMES), THEMES[-1]
                    )}})
    _log("themes.gif assembled")

    # Lens cycle on the graph page (Focus is omitted: it needs a chosen node).
    frames = []
    ctx, page = _new_page(browser, viewport=GIF_VIEWPORT, dpr=1, theme="swiss-light")
    frame_readiness = [_goto(page, f"{base}/__graph", "graph")]
    frames.append(page.screenshot())  # Map is the boot lens
    for lens in LENSES[1:]:
        frame_readiness.append(_click_lens(page, lens))
        frames.append(page.screenshot())
    ctx.close()
    path = out_dir / "graph-lenses.gif"
    _assemble_gif(frames, path)
    shots.append(path)
    records.append({"file": path.name, "source": "live", "route": "/__graph",
                    "theme": "swiss-light", "variants": {
                        "lenses": list(LENSES),
                        "playback": _gif_playback_metadata(len(LENSES), LENSES[-1]),
                    },
                    "viewport": GIF_VIEWPORT, "device_scale_factor": 1,
                    "readiness": {"state": "valid", "detail": "all frames ready",
                                  "frames": frame_readiness}})
    _log("graph-lenses.gif assembled")

    return shots


def _capture_social_preview(browser, base: str, out_dir: Path, records: list[dict]) -> Path:
    viewport = {"width": 1280, "height": 640}
    ctx, page = _new_page(browser, viewport=viewport, dpr=1, theme="swiss-light")
    try:
        ready = _goto(page, f"{base}/__graph", "graph")
        path = out_dir / "social-preview.png"
        page.screenshot(path=str(path), full_page=False)
        records.append({
            "file": path.name, "artifact_type": "still", "source": "live",
            "route": "/__graph", "theme": "swiss-light", "viewport": viewport,
            "device_scale_factor": 1, "readiness": ready,
            "variants": {"state": "social-preview", "surface": "graph-map"},
        })
        return path
    finally:
        ctx.close()


def _capture_comment_video(browser, base: str, out_dir: Path, records: list[dict]) -> Path:
    """Build an MP4 from semantically ready interaction frames via ffmpeg."""
    viewport = {"width": 1280, "height": 720}
    ctx, page = _new_page(browser, viewport=viewport, dpr=1, theme="swiss-light")
    frame_readiness: list[dict] = []
    try:
        frame_readiness.append(_goto(page, f"{base}/demo/showcase", "rendering"))
        with tempfile.TemporaryDirectory(prefix="okf-comment-video-") as tmp:
            tmp_dir = Path(tmp)
            frames = [tmp_dir / f"frame-{index}.png" for index in range(3)]
            page.screenshot(path=str(frames[0]))
            page.evaluate("""() => {
              const body = document.querySelector('.okf-page__body');
              const para = body && [...body.querySelectorAll('p')]
                .find(p => p.textContent.length > 80);
              if (!para) return;
              para.scrollIntoView({block: 'center'});
              const range = document.createRange(); range.selectNodeContents(para);
              const selection = window.getSelection(); selection.removeAllRanges();
              selection.addRange(range);
            }""")
            page.locator(".okf-comment-afford button").wait_for(
                state="visible", timeout=_CAPTURE_READY_TIMEOUT_MS
            )
            page.screenshot(path=str(frames[1]))
            page.locator(".okf-comment-afford button").click()
            textarea = page.locator('textarea[aria-label="Comment for agent"]')
            textarea.wait_for(state="visible", timeout=_CAPTURE_READY_TIMEOUT_MS)
            textarea.fill("Cross-link this explanation to the graph lenses guide.")
            page.screenshot(path=str(frames[2]))

            concat = tmp_dir / "frames.txt"
            concat.write_text(
                "".join(
                    f"file '{frame}'\nduration {duration}\n"
                    for frame, duration in zip(frames, (1.5, 1.25, 2.5), strict=True)
                ) + f"file '{frames[-1]}'\n",
                encoding="utf-8",
            )
            path = out_dir / "comment-loop.mp4"
            proc = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                 "-i", str(concat), "-vf", "format=yuv420p", "-r", "30",
                 "-c:v", "libx264", "-movflags", "+faststart", "-map_metadata", "-1",
                 str(path)],
                capture_output=True, text=True,
            )
            if proc.returncode or not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(
                    f"ffmpeg could not generate {path} (rc={proc.returncode}): "
                    f"{proc.stderr.strip()}"
                )
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True,
            )
            if probe.returncode:
                raise RuntimeError(
                    f"ffprobe could not verify {path} (rc={probe.returncode}): "
                    f"{probe.stderr.strip()}"
                )
            duration_seconds = round(float(probe.stdout.strip()), 3)
        records.append({
            "file": path.name, "artifact_type": "video", "source": "live",
            "route": "/demo/showcase", "theme": "swiss-light", "viewport": viewport,
            "device_scale_factor": 1,
            "readiness": {"state": "valid", "detail": "all interaction frames ready",
                          "frames": frame_readiness},
            "variants": {"state": "comment-loop", "format": "h264-yuv420p",
                         "duration_seconds": duration_seconds, "semantic_frames": 3},
        })
        return path
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg and ffprobe are required to regenerate comment-loop.mp4"
        ) from exc
    finally:
        ctx.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="capture_readme_media.py",
        description=(
            "Regenerate the curated README media set under docs/media/ "
            "from a live studio serving the docs bundle."
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
        help=f"output directory for the media files (default: {DEFAULT_OUT_DIR})",
    )
    p.add_argument(
        "--chrome",
        default=None,
        help="path to Chrome/Chromium (then OKF_CHROME, AIC path, managed, system)",
    )
    p.add_argument(
        "--skip-gifs",
        action="store_true",
        help="skip the two GIF animations; still capture PNGs and comment-loop.mp4",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "ERROR: playwright is not installed.\n"
            "  python -m pip install playwright pillow\n"
            "  playwright install chromium",
            file=sys.stderr,
        )
        return 1

    bundle = args.bundle.resolve()
    out_dir = args.out_dir.resolve()
    if not bundle.is_dir():
        print(f"ERROR: bundle directory not found: {bundle}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    _log(f"bundle={bundle}")
    _log(f"out_dir={out_dir}")

    captured: list[Path] = []
    records: list[dict] = []
    browser_source = "unknown"
    try:
        with sync_playwright() as p:
            launched = _launch_browser(p, args.chrome)
            browser = launched.browser
            browser_source = launched.source
            try:
                with _LiveServer(bundle) as base:
                    captured.extend(_capture_stills(browser, base, out_dir, records))
                    if not args.skip_gifs:
                        captured.extend(_capture_gifs(browser, base, out_dir, records))
                    captured.append(_capture_social_preview(browser, base, out_dir, records))
                    captured.append(_capture_comment_video(browser, base, out_dir, records))
            finally:
                browser.close()
    except (RuntimeError, SystemExit) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    manifest = write_capture_manifest(
        out_dir, records, repo_root=REPO_ROOT, browser_source=browser_source
    )

    print(f"# wrote {len(captured)} media files and manifest to {out_dir}")
    for path in [*captured, manifest]:
        size = path.stat().st_size if path.exists() else 0
        print(f"  {display_path(path, REPO_ROOT)}  ({size / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
