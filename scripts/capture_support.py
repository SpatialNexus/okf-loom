"""Shared, import-safe support for Playwright capture scripts.

The helpers in this module deliberately do not import Playwright.  Capture
scripts remain useful for ``--help`` and unit tests when that optional
dependency is absent.

Chrome's sandbox remains enabled by default.  Root-only containers that cannot
provide a working sandbox may explicitly set ``OKF_CAPTURE_NO_SANDBOX=1``;
the opt-out is shared by every capture script that uses :func:`launch_chromium`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

CANONICAL_THEMES = (
    "swiss-light",
    "swiss-dark",
    "technical-light",
    "technical-dark",
)


@dataclass(frozen=True)
class BrowserLaunch:
    browser: Any
    source: str


class CaptureReadinessError(RuntimeError):
    """A capture target did not reach a semantically valid state in time."""

    def __init__(self, target: str, diagnostic: Mapping[str, Any], timeout_ms: int):
        self.target = target
        self.diagnostic = dict(diagnostic)
        self.timeout_ms = timeout_ms
        state = self.diagnostic.get("state", "not-ready")
        detail = self.diagnostic.get("detail", "no diagnostic detail")
        url = self.diagnostic.get("url", "unknown URL")
        super().__init__(
            f"capture target {target!r} is {state} after {timeout_ms}ms at "
            f"{url}: {detail}"
        )


def _browser_candidates(explicit_path: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    """Return ordered, de-duplicated Chromium launch strategies."""
    candidates: list[tuple[str, dict[str, Any]]] = []
    seen_paths: set[str] = set()

    def add_path(source: str, value: str | None) -> None:
        if not value:
            return
        resolved = str(Path(value).expanduser())
        if resolved not in seen_paths:
            seen_paths.add(resolved)
            candidates.append((source, {"executable_path": resolved}))

    add_path("--chrome", explicit_path)
    add_path("OKF_CHROME", os.environ.get("OKF_CHROME"))
    add_path("AIC_PLAYWRIGHT_CHROME_PATH", os.environ.get("AIC_PLAYWRIGHT_CHROME_PATH"))
    candidates.append(("playwright-managed", {}))
    candidates.append(("system-channel:chrome", {"channel": "chrome"}))
    for command in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        add_path(f"system-path:{command}", shutil.which(command))
    return candidates


def _sandbox_launch_args() -> list[str]:
    """Return an explicit sandbox opt-out for constrained root containers."""
    value = os.environ.get("OKF_CAPTURE_NO_SANDBOX")
    if value is None or value.strip().lower() in {"", "0", "false", "no", "off"}:
        return []
    if value.strip().lower() in {"1", "true", "yes", "on"}:
        return ["--no-sandbox"]
    raise SystemExit(
        "ERROR: OKF_CAPTURE_NO_SANDBOX must be one of "
        "1/true/yes/on or 0/false/no/off"
    )


def launch_chromium(playwright: Any, explicit_path: str | None = None) -> BrowserLaunch:
    """Launch the first available managed or system Chromium-family browser.

    An invalid explicit/environment path is diagnostic but does not prevent a
    managed or other installed browser from being selected.  The sandbox is
    disabled only when ``OKF_CAPTURE_NO_SANDBOX`` is explicitly true.
    """
    failures: list[str] = []
    launch_args = _sandbox_launch_args()
    for source, kwargs in _browser_candidates(explicit_path):
        launch_kwargs = dict(kwargs)
        if launch_args:
            launch_kwargs["args"] = launch_args
        try:
            return BrowserLaunch(playwright.chromium.launch(**launch_kwargs), source)
        except Exception as exc:  # Playwright has several environment-specific errors.
            failures.append(f"{source}: {type(exc).__name__}: {exc}")
    summary = "\n".join(f"  - {line}" for line in failures)
    raise SystemExit(
        "ERROR: no Chromium-family browser is available. Pass --chrome PATH, "
        "set OKF_CHROME/AIC_PLAYWRIGHT_CHROME_PATH, install system Chrome, or "
        "run `playwright install chromium`. Attempts:\n" + summary
    )


def wait_for_http_ok(
    base: str,
    *,
    timeout: float = 20.0,
    poll_interval: float = 0.15,
    http_timeout: float = 1.0,
    proc: Any | None = None,
) -> bool:
    """Poll ``base/`` and fail early when an owned server process exits."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None:
            returncode = proc.poll()
            if returncode is not None:
                raise RuntimeError(
                    f"server process exited before {base} became ready "
                    f"(rc={returncode})"
                )
        try:
            with urllib.request.urlopen(f"{base}/", timeout=http_timeout) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(poll_interval)
    return False


_INSPECT_TARGET_JS = r"""(target) => {
  const visible = (el) => {
    if (!el) return false;
    const style = getComputedStyle(el), rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
      Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
  };
  const selectors = {
    index: '#okf-main.okf-index',
    concept: '#okf-main.okf-page',
    rendering: '#okf-main.okf-page',
    search: '#okf-main.okf-search',
    studio: '.okf-panel:not([hidden])',
    graph: '#okf-graph'
  };
  const selector = selectors[target], root = selector && document.querySelector(selector);
  const base = {target, url: location.href, title: document.title};
  if (!selector) return {...base, state: 'unavailable', detail: 'unknown target kind'};
  if (!root) return {...base, state: 'unavailable', detail: `missing ${selector}`};
  if (!visible(root)) return {...base, state: 'hidden', detail: `${selector} is not visible`};
  if (target === 'rendering') {
    const diagrams = [...root.querySelectorAll('.mermaid')];
    if (diagrams.length && diagrams.some((el) => !el.querySelector('svg'))) {
      return {...base, state: 'not-ready', detail: 'Mermaid diagram has not rendered'};
    }
  }
  if (target !== 'graph') {
    if (!(root.textContent || '').trim()) {
      return {...base, state: 'not-ready', detail: `${selector} has no rendered content`};
    }
    return {...base, state: 'valid', detail: 'visible rendered content'};
  }
  const canvases = [...root.querySelectorAll('canvas')];
  if (!canvases.length) return {...base, state: 'not-ready', detail: 'graph canvas is absent'};
  if (!canvases.some(visible)) return {...base, state: 'hidden', detail: 'graph canvases are not visible'};
  const hook = window.__okfLoomGraph;
  if (!hook || !hook.cy || !hook.layoutStats || hook.cy.nodes().length < 1 ||
      hook.layoutStats.lastAppliedSeq < 1) {
    return {...base, state: 'not-ready', detail: 'graph data/layout has not been applied'};
  }
  let nonUniform = false;
  try {
    for (const canvas of canvases.filter(visible)) {
      const ctx = canvas.getContext('2d');
      if (!ctx) continue;
      const width = Math.min(canvas.width, 32), height = Math.min(canvas.height, 32);
      if (!width || !height) continue;
      const data = ctx.getImageData(0, 0, width, height).data;
      for (let i = 4; i < data.length; i += 4) {
        if (data[i] !== data[0] || data[i+1] !== data[1] ||
            data[i+2] !== data[2] || data[i+3] !== data[3]) {
          nonUniform = true; break;
        }
      }
    }
  } catch (error) {
    return {...base, state: 'unreadable', detail: String(error)};
  }
  return {...base, state: 'valid', uniform: !nonUniform,
    detail: nonUniform ? 'readable graph canvas' : 'readable valid-uniform graph canvas'};
}"""


def inspect_capture_target(page: Any, target: str) -> dict[str, Any]:
    """Return one of unavailable/hidden/unreadable/not-ready/valid."""
    result = page.evaluate(_INSPECT_TARGET_JS, target)
    return dict(result)


def wait_for_capture_ready(page: Any, target: str, timeout_ms: int = 10_000) -> dict[str, Any]:
    """Wait for semantic target readiness and emit bounded state diagnostics."""
    try:
        page.wait_for_function(
            f"target => ({_INSPECT_TARGET_JS})(target).state === 'valid'",
            arg=target,
            timeout=timeout_ms,
        )
    except Exception as exc:
        try:
            diagnostic = inspect_capture_target(page, target)
        except Exception as diagnostic_exc:
            diagnostic = {
                "state": "unavailable",
                "detail": f"diagnostic evaluation failed: {diagnostic_exc}",
                "url": getattr(page, "url", "unknown URL"),
            }
        raise CaptureReadinessError(target, diagnostic, timeout_ms) from exc
    return inspect_capture_target(page, target)


def wait_for_graph_layout_after(page: Any, previous_sequence: int, timeout_ms: int = 10_000) -> None:
    """Wait for a newly applied graph layout, with graph-state diagnostics."""
    try:
        page.wait_for_function(
            "previous => window.__okfLoomGraph && window.__okfLoomGraph.layoutStats "
            "&& window.__okfLoomGraph.layoutStats.lastAppliedSeq > previous",
            arg=previous_sequence,
            timeout=timeout_ms,
        )
    except Exception as exc:
        diagnostic = inspect_capture_target(page, "graph")
        diagnostic["detail"] = (
            f"layout sequence did not advance beyond {previous_sequence}; "
            + str(diagnostic.get("detail", ""))
        )
        raise CaptureReadinessError("graph", diagnostic, timeout_ms) from exc


def display_path(path: Path, relative_to: Path) -> str:
    """Display a repo-relative path when possible, otherwise an absolute path."""
    try:
        return str(path.relative_to(relative_to))
    except ValueError:
        return str(path)


def git_revision(repo_root: Path) -> str:
    """Return the checked-out revision, or ``unknown`` outside a git checkout."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def write_capture_manifest(
    out_dir: Path,
    records: Iterable[Mapping[str, Any]],
    *,
    repo_root: Path,
    browser_source: str,
) -> Path:
    """Write normalized capture provenance beside generated artifacts."""
    normalized = []
    for source_record in records:
        record = dict(source_record)
        theme = record.get("theme")
        normalized.append(
            {
                "file": str(record["file"]),
                "artifact_type": record.get(
                    "artifact_type",
                    "animation" if str(record["file"]).lower().endswith(".gif") else "still",
                ),
                "source": str(record["source"]),
                "route": str(record["route"]),
                "theme": theme,
                "themes": list(record.get("themes") or ([theme] if theme else [])),
                "modifiers": dict(record.get("modifiers") or {}),
                "viewport": dict(record["viewport"]),
                "device_scale_factor": int(record["device_scale_factor"]),
                "readiness": dict(
                    record.get("readiness")
                    or {"state": "not-recorded", "detail": "no readiness record"}
                ),
                "environment": dict(record.get("environment") or {}),
                "variants": dict(record.get("variants") or {}),
            }
        )
    payload = {
        "schema": "okf-loom-capture-manifest-v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "revision": git_revision(repo_root),
        "browser_source": browser_source,
        "captures": normalized,
    }
    path = out_dir / "capture-manifest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
