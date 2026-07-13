from __future__ import annotations

import json

import pytest

import capture_support
import capture_readme_media


class _FakeChromium:
    def __init__(self, successful_kwargs: dict):
        self.successful_kwargs = successful_kwargs
        self.calls: list[dict] = []

    def launch(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs == self.successful_kwargs:
            return "browser"
        raise RuntimeError(f"unavailable: {kwargs}")


class _FakePlaywright:
    def __init__(self, successful_kwargs: dict):
        self.chromium = _FakeChromium(successful_kwargs)


def test_browser_candidates_do_not_use_unsupported_chromium_channel(monkeypatch):
    monkeypatch.delenv("OKF_CHROME", raising=False)
    monkeypatch.delenv("AIC_PLAYWRIGHT_CHROME_PATH", raising=False)
    monkeypatch.setattr(capture_support.shutil, "which", lambda _command: None)

    sources = [source for source, _kwargs in capture_support._browser_candidates()]

    assert "system-channel:chrome" in sources
    assert "system-channel:chromium" not in sources


def test_browser_resolution_falls_back_from_managed_to_system_chrome(monkeypatch):
    monkeypatch.delenv("OKF_CHROME", raising=False)
    monkeypatch.delenv("AIC_PLAYWRIGHT_CHROME_PATH", raising=False)
    monkeypatch.delenv("OKF_CAPTURE_NO_SANDBOX", raising=False)
    monkeypatch.setattr(capture_support.shutil, "which", lambda _command: None)
    playwright = _FakePlaywright({"channel": "chrome"})

    launched = capture_support.launch_chromium(playwright)

    assert launched.browser == "browser"
    assert launched.source == "system-channel:chrome"
    assert playwright.chromium.calls[:2] == [{}, {"channel": "chrome"}]


def test_browser_resolution_keeps_fallback_when_explicit_path_is_bad(monkeypatch):
    monkeypatch.delenv("OKF_CHROME", raising=False)
    monkeypatch.delenv("AIC_PLAYWRIGHT_CHROME_PATH", raising=False)
    monkeypatch.delenv("OKF_CAPTURE_NO_SANDBOX", raising=False)
    monkeypatch.setattr(capture_support.shutil, "which", lambda _command: None)
    playwright = _FakePlaywright({})

    launched = capture_support.launch_chromium(playwright, "/missing/chrome")

    assert launched.source == "playwright-managed"
    assert playwright.chromium.calls == [
        {"executable_path": "/missing/chrome"},
        {},
    ]


def test_browser_resolution_adds_no_sandbox_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("OKF_CHROME", raising=False)
    monkeypatch.delenv("AIC_PLAYWRIGHT_CHROME_PATH", raising=False)
    monkeypatch.setenv("OKF_CAPTURE_NO_SANDBOX", "1")
    monkeypatch.setattr(capture_support.shutil, "which", lambda _command: None)
    playwright = _FakePlaywright({"args": ["--no-sandbox"]})

    launched = capture_support.launch_chromium(playwright)

    assert launched.source == "playwright-managed"
    assert playwright.chromium.calls == [{"args": ["--no-sandbox"]}]


def test_display_path_accepts_external_output_directory(tmp_path):
    repo = tmp_path / "repo"
    external = tmp_path / "captures" / "proof.png"

    assert capture_support.display_path(external, repo) == str(external)
    assert capture_support.display_path(repo / "docs" / "proof.png", repo) == "docs/proof.png"


def test_readme_capture_cycle_uses_swiss_first_canonical_theme_identifiers():
    assert capture_readme_media.THEMES == capture_support.CANONICAL_THEMES
    assert "light" not in capture_readme_media.THEMES
    assert "dark" not in capture_readme_media.THEMES


class _FakePage:
    def __init__(self, diagnostic: dict, *, fail_wait: bool = False):
        self.diagnostic = diagnostic
        self.fail_wait = fail_wait
        self.wait_calls: list[tuple] = []

    def wait_for_function(self, expression, *, arg, timeout):
        self.wait_calls.append((expression, arg, timeout))
        if self.fail_wait:
            raise TimeoutError("bounded timeout")

    def evaluate(self, expression, arg):
        assert arg == self.diagnostic["target"]
        return self.diagnostic


def test_semantic_readiness_returns_valid_uniform_without_treating_it_as_empty():
    diagnostic = {
        "target": "graph",
        "state": "valid",
        "uniform": True,
        "detail": "readable valid-uniform graph canvas",
        "url": "http://example.test/__graph",
    }
    page = _FakePage(diagnostic)

    assert capture_support.wait_for_capture_ready(page, "graph", timeout_ms=321) == diagnostic
    assert page.wait_calls[0][2] == 321


@pytest.mark.parametrize("state", ["hidden", "unreadable", "unavailable", "not-ready"])
def test_semantic_readiness_preserves_failure_state_in_timeout_diagnostic(state):
    diagnostic = {
        "target": "graph",
        "state": state,
        "detail": f"graph is {state}",
        "url": "http://example.test/__graph",
    }
    page = _FakePage(diagnostic, fail_wait=True)

    with pytest.raises(capture_support.CaptureReadinessError) as exc_info:
        capture_support.wait_for_capture_ready(page, "graph", timeout_ms=50)

    assert exc_info.value.diagnostic["state"] == state
    assert "after 50ms" in str(exc_info.value)
    assert state in str(exc_info.value)


def test_graph_layout_timeout_reports_sequence_and_semantic_state():
    diagnostic = {
        "target": "graph",
        "state": "not-ready",
        "detail": "graph data/layout has not been applied",
        "url": "http://example.test/__graph",
    }
    page = _FakePage(diagnostic, fail_wait=True)

    with pytest.raises(capture_support.CaptureReadinessError) as exc_info:
        capture_support.wait_for_graph_layout_after(page, 17, timeout_ms=75)

    assert exc_info.value.diagnostic["state"] == "not-ready"
    assert "did not advance beyond 17" in str(exc_info.value)
    assert "after 75ms" in str(exc_info.value)


def test_server_readiness_fails_early_when_owned_process_exits():
    class ExitedProcess:
        @staticmethod
        def poll():
            return 23

    with pytest.raises(RuntimeError, match=r"rc=23") as exc_info:
        capture_support.wait_for_http_ok(
            "http://127.0.0.1:9", timeout=10, proc=ExitedProcess()
        )

    assert "exited before" in str(exc_info.value)


def test_manifest_records_revision_browser_route_theme_and_viewport(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_support, "git_revision", lambda _root: "abc123")
    record = {
        "file": "live-graph.png",
        "source": "live",
        "route": "/__graph",
        "theme": "swiss-light",
        "viewport": {"width": 1280, "height": 900},
        "device_scale_factor": 2,
        "readiness": {"state": "valid", "detail": "visible"},
    }

    path = capture_support.write_capture_manifest(
        tmp_path, [record], repo_root=tmp_path, browser_source="system-channel:chrome"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["revision"] == "abc123"
    assert payload["browser_source"] == "system-channel:chrome"
    assert payload["captures"] == [{
        **record,
        "artifact_type": "still",
        "themes": ["swiss-light"],
        "variants": {},
    }]


def test_manifest_normalizes_gif_schema_and_keeps_readiness(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_support, "git_revision", lambda _root: "abc123")
    readiness = {"state": "valid", "detail": "all frames ready", "frames": []}
    record = {
        "file": "themes.gif",
        "source": "live",
        "route": "/demo/showcase",
        "themes": list(capture_support.CANONICAL_THEMES),
        "viewport": {"width": 1280, "height": 800},
        "device_scale_factor": 1,
        "readiness": readiness,
    }

    path = capture_support.write_capture_manifest(
        tmp_path, [record], repo_root=tmp_path, browser_source="playwright-managed"
    )
    capture = json.loads(path.read_text(encoding="utf-8"))["captures"][0]

    assert set(capture) == {
        "artifact_type", "device_scale_factor", "file", "readiness", "route",
        "source", "theme", "themes", "variants", "viewport",
    }
    assert capture["artifact_type"] == "animation"
    assert capture["theme"] is None
    assert capture["themes"] == list(capture_support.CANONICAL_THEMES)
    assert capture["readiness"] == readiness
