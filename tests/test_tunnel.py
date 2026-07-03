"""``okf serve --tunnel`` — quick-tunnel plumbing.

Covers the pure URL parser, the CLI flag wiring, and the fail-closed
behaviour when cloudflared is absent. The actual cloudflared subprocess
is never started (network-free suite).
"""
from __future__ import annotations

import pytest

from okf_loom.server import parse_quick_tunnel_url, start_quick_tunnel


# ---------------------------------------------------------------------------
# parse_quick_tunnel_url — pure parser
# ---------------------------------------------------------------------------

def test_parse_extracts_url_from_cloudflared_banner_line() -> None:
    line = (
        "2026-07-02T10:00:00Z INF |  https://hired-henderson-visual-endorsed"
        ".trycloudflare.com                                        |"
    )
    assert parse_quick_tunnel_url(line) == (
        "https://hired-henderson-visual-endorsed.trycloudflare.com"
    )


def test_parse_returns_none_for_noise_lines() -> None:
    for line in (
        "2026-07-02T10:00:00Z INF Requesting new quick Tunnel on trycloudflare.com...",
        "https://developers.cloudflare.com/cloudflare-one/",  # docs link, not a tunnel
        "",
    ):
        assert parse_quick_tunnel_url(line) is None


def test_parse_handles_none_input() -> None:
    assert parse_quick_tunnel_url(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# start_quick_tunnel — fail-closed without cloudflared
# ---------------------------------------------------------------------------

def test_start_quick_tunnel_missing_binary_raises_actionable_error(monkeypatch) -> None:
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(RuntimeError) as exc:
        start_quick_tunnel(8787)
    assert "cloudflared" in str(exc.value)


# ---------------------------------------------------------------------------
# CLI wiring — the flag exists and defaults off
# ---------------------------------------------------------------------------

def test_serve_parser_accepts_tunnel_flag() -> None:
    from okf_loom.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["serve", "some-bundle", "--tunnel", "--no-open"])
    assert args.tunnel is True
    args2 = parser.parse_args(["serve", "some-bundle"])
    assert args2.tunnel is False
