"""Contract-parity proofs for the live ``/__data/doc`` response."""
from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from okf_loom import Bundle
from okf_loom.server import OKFWikiHandler


_CSP = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://cdn.jsdelivr.net; "
    "connect-src 'self' https://cdn.jsdelivr.net; "
    "font-src 'self' https://cdn.jsdelivr.net; object-src 'none'; "
    "base-uri 'self'; form-action 'self'"
)


class _BodyHeadings(HTMLParser):
    """Collect heading tags and IDs inside the rendered concept body."""

    def __init__(self, *, body_only: bool) -> None:
        super().__init__()
        self.body_only = body_only
        self.body_depth = 0
        self.headings: list[tuple[str, str | None]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "div" and "okf-page__body" in (attr_map.get("class") or "").split():
            self.body_depth = 1
            return
        if self.body_depth:
            self.body_depth += 1
        if (self.body_depth or not self.body_only) and tag in {f"h{n}" for n in range(1, 7)}:
            self.headings.append((tag, attr_map.get("id")))

    def handle_endtag(self, tag: str) -> None:
        if self.body_depth:
            self.body_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.body_depth or not self.body_only:
            self.text.append(data)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(bundle: Bundle):
    server = ThreadingHTTPServer(("127.0.0.1", _free_port()), OKFWikiHandler)
    server.bundle = bundle  # type: ignore[attr-defined]
    server.config = {}  # type: ignore[attr-defined]
    server.name = bundle.name  # type: ignore[attr-defined]
    server.plugin = None  # type: ignore[attr-defined]
    server._state_lock = threading.Lock()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}"


def _heading_bundle(tmp_path: Path) -> Bundle:
    (tmp_path / "index.md").write_text("Bundle intro\n", encoding="utf-8")
    (tmp_path / "topic.md").write_text(
        """---
type: guide
title: Heading contract
description: Heading parity fixture
---
# Top

## Section

### Nested detail

Body text.
""",
        encoding="utf-8",
    )
    return Bundle.load(tmp_path)


def _headings(html: str, *, body_only: bool) -> list[tuple[str, str | None]]:
    parser = _BodyHeadings(body_only=body_only)
    parser.feed(html)
    return parser.headings


def _body_text(html: str, *, body_only: bool) -> str:
    parser = _BodyHeadings(body_only=body_only)
    parser.feed(html)
    return "".join(parser.text)


def _assert_json_security_headers(response) -> None:
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-XSS-Protection"] == "0"
    assert response.headers["Content-Security-Policy"] == _CSP


def test_data_doc_body_matches_initial_page_heading_contract(tmp_path: Path) -> None:
    """Initial and live HTML expose identical demoted heading tags and IDs."""
    server, thread, base = _start_server(_heading_bundle(tmp_path))
    try:
        with urllib.request.urlopen(f"{base}/topic", timeout=5) as response:
            page_html = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base}/__data/doc?id=topic", timeout=5) as response:
            payload = json.load(response)

        expected = [("h2", "top"), ("h3", "section"), ("h4", "nested-detail")]
        assert _headings(page_html, body_only=True) == expected
        assert _headings(payload["html"], body_only=False) == expected
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_data_doc_preserves_response_fields_and_security_headers(tmp_path: Path) -> None:
    """Body parity does not alter the endpoint envelope or HTTP protections."""
    server, thread, base = _start_server(_heading_bundle(tmp_path))
    try:
        with urllib.request.urlopen(f"{base}/__data/doc?id=topic", timeout=5) as response:
            payload = json.load(response)
            _assert_json_security_headers(response)
        assert set(payload) == {
            "id", "rev", "title", "type", "html", "raw", "frontmatter",
            "headings", "backlinks", "outgoing",
        }
        assert payload["raw"].startswith("# Top")
        assert payload["headings"] == [
            {"level": 1, "text": "Top"},
            {"level": 2, "text": "Section"},
            {"level": 3, "text": "Nested detail"},
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    ("query", "status", "envelope"),
    [
        ("", 400, {"error": "id required"}),
        ("?id=bad%20id", 404, {"error": "bad concept id: bad id"}),
        ("?id=missing%2Ftopic", 404, {"error": "unknown concept: missing/topic"}),
    ],
    ids=["missing-id", "malformed-id", "unknown-id"],
)
def test_data_doc_rejects_invalid_identity_with_stable_json_contract(
    tmp_path: Path,
    query: str,
    status: int,
    envelope: dict[str, str],
) -> None:
    """Identity failures retain exact status, envelope, type, and protections."""
    server, thread, base = _start_server(_heading_bundle(tmp_path))
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base}/__data/doc{query}", timeout=5)
        response = exc_info.value
        assert response.code == status
        _assert_json_security_headers(response)
        assert json.load(response) == envelope
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_data_doc_reads_one_fresh_active_bundle_snapshot(tmp_path: Path) -> None:
    """A bundle swap updates rev, source, rendered HTML, and metadata together."""
    topic_path = tmp_path / "topic.md"
    server, thread, base = _start_server(_heading_bundle(tmp_path))
    try:
        with urllib.request.urlopen(f"{base}/__data/doc?id=topic", timeout=5) as response:
            before = json.load(response)

        updated_source = """---
type: guide
title: Updated heading contract
description: Fresh snapshot fixture
---
# Fresh top

## Fresh nested

Updated body text.
"""
        topic_path.write_text(updated_source, encoding="utf-8")
        reloaded = Bundle.load(tmp_path)
        with server._state_lock:  # type: ignore[attr-defined]
            server.bundle = reloaded  # type: ignore[attr-defined]

        with urllib.request.urlopen(f"{base}/__data/doc?id=topic", timeout=5) as response:
            after = json.load(response)

        assert after["rev"] != before["rev"]
        assert after["title"] == "Updated heading contract"
        assert after["raw"] == reloaded.concepts[("topic",)].body
        assert "Updated body text." in after["html"]
        assert "Body text." not in after["html"]
        assert _headings(after["html"], body_only=False) == [
            ("h2", "fresh-top"),
            ("h3", "fresh-nested"),
        ]
        assert after["headings"] == [
            {"level": 1, "text": "Fresh top"},
            {"level": 2, "text": "Fresh nested"},
        ]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_data_doc_and_page_strip_duplicate_body_citations_before_demotion(
    tmp_path: Path,
) -> None:
    """Both render paths suppress body Citations and demote surviving headings."""
    (tmp_path / "index.md").write_text("Bundle intro\n", encoding="utf-8")
    (tmp_path / "topic.md").write_text(
        """---
type: guide
title: Citations contract
citations:
  - id: "1"
    text: Frontmatter citation
---
# Before

Kept before.

# Citations

- Duplicate body citation.

# After

Kept after.
""",
        encoding="utf-8",
    )
    server, thread, base = _start_server(Bundle.load(tmp_path))
    try:
        with urllib.request.urlopen(f"{base}/topic", timeout=5) as response:
            page_html = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base}/__data/doc?id=topic", timeout=5) as response:
            payload = json.load(response)

        expected = [("h2", "before"), ("h2", "after")]
        assert _headings(page_html, body_only=True) == expected
        assert _headings(payload["html"], body_only=False) == expected
        assert "Duplicate body citation." not in _body_text(page_html, body_only=True)
        assert "Duplicate body citation." not in _body_text(
            payload["html"], body_only=False
        )
        assert "Frontmatter citation" in page_html
        assert payload["frontmatter"]["citations"] == [
            {"id": "1", "text": "Frontmatter citation"}
        ]
        assert "Kept before." in payload["html"]
        assert "Kept after." in payload["html"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
