"""Deterministic viewer-asset cache-busting / versioning (Phase 6 polish).

Pinned contract (``okf_loom.viewer.assets.asset_version`` /
``versioned_asset_url``):

* The version is the first 16 hex chars of the SHA-256 of the *resolved*
  asset content (builtin or effective bundle override) — a pure function of
  the bytes, so it is identical across runs, machines, and the live/SPA/static
  emit paths (single digest contract).
* Same content ⇒ same version; any content change ⇒ a different version.
* External asset URLs emitted into live/SPA/static HTML carry ``?v=<version>``;
  the single-file output inlines assets and carries NO version query.
* The live router ignores the query (it routes on ``urlparse().path``), so a
  versioned URL resolves to the same bytes as the plain URL.
* CSP ``default-src 'self'`` is unaffected (same-origin URL + query).

Mutable-override freshness (no stale-cache race):
* Only process-constant BUILTIN digests are memoized. Bundle-ROOT override
  digests are recomputed from the current bytes on EVERY call and are NEVER
  cached, so an override edit is reflected with no watcher/manual cache clear
  and a stale value can never be restored by a concurrent completion.

Single explicit override-name scope (``STATIC_ASSET_NAMES``):
* Only built-in viewer asset names may be loaded, served, overridden, or
  hashed; unknown names are rejected at the loader/server/hasher boundary.

These tests do not depend on real upstream bundles.
"""
from __future__ import annotations

import hashlib
import re
import socket
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from okf_loom import Bundle
from okf_loom.render import (
    _render_concept_page,
    _render_graph_page,
    _render_index_page,
    build_site,
    render_single_file,
)
from okf_loom.viewer import assets as viewer_assets
from okf_loom.viewer.assets import (
    STATIC_ASSET_NAMES,
    _resolve_static,
    asset_version,
    is_known_static_asset,
    load_static,
    versioned_asset_url,
)

from conftest import TOOLKIT_ROOT

_VERSION_RE = r"\?v=[0-9a-f]{16}"


def _external_asset_urls(html: str) -> list[str]:
    """All ``src``/``href`` values that reference a ``__static`` asset URL."""
    return re.findall(r'(?:src|href)="([^"]*__static/[^"]*)"', html)


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _enable_operator_consent(monkeypatch) -> None:
    """Open the effective active-code gate for override tests."""
    monkeypatch.setenv(viewer_assets.OPERATOR_CONSENT_ENV, "1")
    viewer_assets._operator_consent_override = None
    viewer_assets.clear_overrides_cache()


def _override_bundle(tiny_good_bundle: Path) -> Bundle:
    """A bundle whose config opts into active code (gate opened by the caller)."""
    (tiny_good_bundle / "okf-loom.config.yaml").write_text(
        "viewer:\n  allow_active_code: true\n", encoding="utf-8"
    )
    return Bundle.load(tiny_good_bundle)


def _override_dir(bundle: Bundle) -> Path:
    d = bundle.root / ".okf-loom" / "viewer" / "static"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Digest contract
# ---------------------------------------------------------------------------


def test_static_asset_names_matches_on_disk_builtins() -> None:
    """The scope frozenset is exactly the on-disk built-in asset set."""
    on_disk = {
        p.name for p in
        (TOOLKIT_ROOT / "scripts" / "okf_loom" / "viewer" / "static").iterdir()
        if p.is_file()
    }
    assert set(STATIC_ASSET_NAMES) == on_disk
    assert sorted(STATIC_ASSET_NAMES) == sorted(STATIC_ASSET_NAMES)


def test_is_known_static_asset_scope() -> None:
    assert is_known_static_asset("wiki.css") is True
    assert is_known_static_asset("evil.exe") is False
    assert is_known_static_asset("") is False
    assert is_known_static_asset("../wiki.css") is False


def test_asset_version_matches_manual_sha256_of_resolved_content() -> None:
    for name in STATIC_ASSET_NAMES:
        content, _is_override = _resolve_static(name)
        assert asset_version(name) == _digest(content), f"{name}: diverged from sha256"


def test_asset_version_is_stable_across_calls() -> None:
    assert asset_version("wiki.css") == asset_version("wiki.css") == asset_version("wiki.css", None)


def test_versioned_asset_url_preserves_prefix_and_appends_query() -> None:
    assert versioned_asset_url("wiki.css", "/__static") == (
        f"/__static/wiki.css?v={asset_version('wiki.css')}"
    )
    assert versioned_asset_url("wiki.js", "__static") == (
        f"__static/wiki.js?v={asset_version('wiki.js')}"
    )
    assert versioned_asset_url("theme.js", "../../__static") == (
        f"../../__static/theme.js?v={asset_version('theme.js')}"
    )


def test_versioned_asset_url_omits_query_only_for_unknown_name() -> None:
    """Graceful plain URL is contract-allowed ONLY for unknown/out-of-scope names."""
    assert versioned_asset_url("no-such-file.css", "/__static") == "/__static/no-such-file.css"


# ---------------------------------------------------------------------------
# Mutable-override freshness — NO manual cache clear, NO watcher dependency
# ---------------------------------------------------------------------------


def test_override_version_reflects_current_bytes_without_manual_clear(
    tiny_good_bundle: Path, monkeypatch
) -> None:
    """Editing an override changes its version on the very next call, with no
    ``clear_overrides_cache`` and no watcher reload — override digests are
    computed fresh every call."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)
    odir = _override_dir(b)
    override = odir / "wiki.css"

    builtin_v = asset_version("wiki.css")
    override.write_text("/* override v1 */\n", encoding="utf-8")
    v1 = asset_version("wiki.css", b)
    assert v1 != builtin_v
    assert v1 == _digest("/* override v1 */\n")

    override.write_text("/* override v2 — changed */\n", encoding="utf-8")
    v2 = asset_version("wiki.css", b)
    assert v2 != v1 == _digest("/* override v1 */\n")
    assert v2 == _digest("/* override v2 — changed */\n")

    # Builtin version unaffected, and the builtin-keyed cache entry was NOT
    # overwritten by the override computations.
    assert asset_version("wiki.css") == builtin_v
    assert viewer_assets._ASSET_VERSION_CACHE.get("wiki.css") == builtin_v


@pytest.mark.parametrize("name", sorted(STATIC_ASSET_NAMES))
def test_every_supported_override_is_fresh_and_served(
    tiny_good_bundle: Path, monkeypatch, name: str
) -> None:
    """For EVERY supported override name: writing an override (no manual clear)
    changes the version to match the new content's digest, and the live server
    serves the override bytes at the versioned URL."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)
    override = _override_dir(b) / name

    builtin_v = asset_version(name)
    c1 = f"/* override A for {name} */\n"
    override.write_text(c1, encoding="utf-8")
    v1 = asset_version(name, b)
    assert v1 != builtin_v, f"{name}: override version did not differ from builtin"
    assert v1 == _digest(c1), f"{name}: version does not match override digest"

    # Served bytes at the versioned URL match the override content.
    base, _ = _start_server(b)
    try:
        r = urllib.request.urlopen(f"{base}/__static/{name}?v={v1}", timeout=3)
        assert r.status == 200
        assert r.read().decode("utf-8") == c1, f"{name}: served bytes != override content"
    finally:
        _stop_server()

    # A second edit (again no manual clear) produces a new digest.
    c2 = f"/* override B for {name} — different bytes */\n"
    override.write_text(c2, encoding="utf-8")
    v2 = asset_version(name, b)
    assert v2 != v1, f"{name}: second override edit did not change the version"
    assert v2 == _digest(c2)


def test_live_html_version_changes_after_override_edit_without_clear(
    tiny_good_bundle: Path, monkeypatch
) -> None:
    """Production path: after editing an override (no manual clear), the next
    rendered live page carries the NEW version in its wiki.css URL."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)
    g = b.graph()
    concept = next(iter(b.concepts.values()))

    def wiki_css_version(html: str) -> str:
        m = re.search(r'href="[^"]*__static/wiki\.css\?v=([0-9a-f]{16})"', html)
        assert m, "wiki.css versioned URL not found in rendered page"
        return m.group(1)

    html0 = _render_concept_page(concept, b, g, mode="serve", name=b.name, palette={}, config={})
    v0 = wiki_css_version(html0)
    assert v0 == asset_version("wiki.css")  # no override yet -> builtin

    (_override_dir(b) / "wiki.css").write_text("/* live HTML freshness */\n", encoding="utf-8")
    html1 = _render_concept_page(concept, b, g, mode="serve", name=b.name, palette={}, config={})
    v1 = wiki_css_version(html1)
    assert v1 != v0, "live HTML version did not change after override edit"
    assert v1 == asset_version("wiki.css", b)


def test_repeated_static_and_spa_builds_pick_up_new_override_digest(
    tiny_good_bundle: Path, monkeypatch, tmp_path: Path
) -> None:
    """In ONE process: build, edit an override, build again — the second build's
    emitted HTML carries the new digest (override digests are not memoized)."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)

    def wiki_css_v(out_dir: Path) -> str:
        html = (out_dir / "index.html").read_text(encoding="utf-8")
        m = re.search(r'href="[^"]*__static/wiki\.css\?v=([0-9a-f]{16})"', html)
        assert m, "wiki.css versioned URL missing from built index"
        return m.group(1)

    out1 = tmp_path / "static1"
    build_site(b, out1, target="static")
    v1 = wiki_css_v(out1)

    (_override_dir(b) / "wiki.css").write_text("/* between-builds edit */\n", encoding="utf-8")

    out2 = tmp_path / "static2"
    build_site(b, out2, target="static")
    v2 = wiki_css_v(out2)
    assert v2 != v1, "repeated static build did not pick up new override digest"

    out3 = tmp_path / "spa1"
    build_site(b, out3, target="spa")
    v3 = wiki_css_v(out3)
    assert v3 == v2, "SPA build digest diverged from static build digest (single contract)"


def test_concurrent_readers_never_restore_stale_override_digest(
    tiny_good_bundle: Path, monkeypatch
) -> None:
    """Structurally impossible to restore a stale override digest: override
    digests are never stored in the cache, so every reader computes from the
    file's current bytes. Proves (1) the cache never holds an override digest,
    and (2) once the override is settled, reads are deterministic."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)
    override = _override_dir(b) / "wiki.css"
    override.write_text("/* X */\n", encoding="utf-8")
    digest_x = _digest("/* X */\n")
    digest_y = _digest("/* Y */\n")

    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            asset_version("wiki.css", b)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in range(8):
            pool.submit(reader)
        # Flip content a few times while readers spin.
        for body in ("/* X */\n", "/* Y */\n", "/* X */\n", "/* Y */\n"):
            override.write_text(body, encoding="utf-8")
            threading.Event().wait(0.02)
        stop.set()

    # (1) Structural proof: the version cache holds ONLY builtin digests — the
    # override digests digest_x/digest_y were never stored, so there is no
    # cached value a concurrent reader could restore as stale.
    for k, v in list(viewer_assets._ASSET_VERSION_CACHE.items()):
        assert v == _digest(load_static(k)), (
            f"version cache holds a non-builtin digest for {k!r}: {v}"
        )
    assert digest_x not in viewer_assets._ASSET_VERSION_CACHE.values()
    assert digest_y not in viewer_assets._ASSET_VERSION_CACHE.values()

    # (2) Once settled on Y, the digest is deterministically Y for every read.
    override.write_text("/* Y */\n", encoding="utf-8")
    assert all(asset_version("wiki.css", b) == digest_y for _ in range(50))


# ---------------------------------------------------------------------------
# Gate semantics
# ---------------------------------------------------------------------------


def test_changed_asset_changes_only_its_own_version(
    tiny_good_bundle: Path, monkeypatch
) -> None:
    """Overriding wiki.css changes only wiki.css's version; theme.js (not
    overridden) keeps the builtin version. No manual cache clear."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)
    (_override_dir(b) / "wiki.css").write_text("/* only wiki override */\n", encoding="utf-8")
    builtin_wiki = asset_version("wiki.css")
    builtin_theme = asset_version("theme.js")
    assert asset_version("wiki.css", b) != builtin_wiki
    assert asset_version("theme.js", b) == builtin_theme


def test_gate_closed_falls_back_to_builtin_version(
    tiny_good_bundle: Path, monkeypatch
) -> None:
    """Gate CLOSED → override ignored, version is the builtin's (override
    content never reaches the URL). A later gate-open re-resolves fresh."""
    monkeypatch.delenv(viewer_assets.OPERATOR_CONSENT_ENV, raising=False)
    viewer_assets._operator_consent_override = None
    viewer_assets.clear_overrides_cache()
    b = _override_bundle(tiny_good_bundle)
    (_override_dir(b) / "wiki.css").write_text("/* ignored override */\n", encoding="utf-8")
    builtin_v = asset_version("wiki.css")
    assert asset_version("wiki.css", b) == builtin_v  # gate closed

    # Flip gate open -> same process, no manual version-cache clear.
    _enable_operator_consent(monkeypatch)
    assert asset_version("wiki.css", b) != builtin_v  # override now honoured
    assert asset_version("wiki.css", b) == _digest("/* ignored override */\n")


# ---------------------------------------------------------------------------
# Single explicit scope — load / serve / hash reject unknown names
# ---------------------------------------------------------------------------


def test_load_static_rejects_unknown_name() -> None:
    with pytest.raises(FileNotFoundError):
        load_static("definitely-not-a-viewer-asset.js")


def test_resolve_static_rejects_unknown_name() -> None:
    with pytest.raises(FileNotFoundError):
        _resolve_static("evil.exe")


def test_asset_version_unknown_name_returns_empty() -> None:
    assert asset_version("evil.exe") == ""


def test_serve_rejects_unknown_override_name(
    tiny_good_bundle: Path, monkeypatch
) -> None:
    """An override for a name NOT in the built-in scope is not served (404),
    even with the gate open. The scope is enforced at the handler boundary."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)
    (_override_dir(b) / "malicious-extra.js").write_text(
        "/* should never be served */", encoding="utf-8"
    )
    base, _ = _start_server(b)
    try:
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(f"{base}/__static/malicious-extra.js", timeout=3)
        assert ei.value.code == 404
    finally:
        _stop_server()


def test_serve_rejects_traversal_and_nul(tiny_good_bundle: Path) -> None:
    """Path-traversal / NUL payloads cannot escape the static dir, and the
    ``?v=`` mechanism cannot be used to smuggle one (the query is ignored)."""
    b = Bundle.load(tiny_good_bundle)
    base, _ = _start_server(b)
    bad = [
        "/__static/../config.py",
        "/__static/..%2f..%2fconfig.py?v=x",
        "/__static/wiki.css/../../config.py",
    ]
    try:
        for url in bad:
            with pytest.raises(urllib.error.HTTPError) as ei:
                urllib.request.urlopen(base + url, timeout=3)
            assert ei.value.code == 404, f"{url} did not 404"
    finally:
        _stop_server()


def test_symlinked_override_escape_is_rejected_and_not_versioned(
    tiny_good_bundle: Path, monkeypatch, tmp_path: Path
) -> None:
    """A symlinked override that escapes the bundle root is not honoured by
    load/hash/serve (P1-4): the hash falls back to the builtin digest, and the
    server 404s the escaped override so the host secret is never served."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)
    secret = tmp_path.parent / "asset_symlink_secret.txt"
    secret.write_text("HOST-SECRET-SYMLINK-ESCAPE", encoding="utf-8")
    link = _override_dir(b) / "wiki.css"
    try:
        os = pytest.importorskip("os")
        try:
            os.symlink(secret, link)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks not supported on this platform")
        builtin_v = asset_version("wiki.css")
        # Hash falls back to builtin (escape rejected at resolution).
        assert asset_version("wiki.css", b) == builtin_v
        # Serve 404s the escaped override (existing P2-54 contract: the escape
        # is contained; it does not silently fall through to the builtin).
        base, _ = _start_server(b)
        try:
            with pytest.raises(urllib.error.HTTPError) as ei:
                urllib.request.urlopen(f"{base}/__static/wiki.css", timeout=3)
            assert ei.value.code == 404
            body = ei.value.read().decode("utf-8", errors="replace")
            assert "HOST-SECRET-SYMLINK-ESCAPE" not in body
        finally:
            _stop_server()
    finally:
        try:
            secret.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# All emitted external URLs carry the version (live / SPA / static)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["serve", "spa", "static"])
def test_every_external_asset_url_on_concept_page_carries_version(
    tiny_good_bundle: Path, mode: str
) -> None:
    b = Bundle.load(tiny_good_bundle)
    g = b.graph()
    concept = next(iter(b.concepts.values()))
    html = _render_concept_page(concept, b, g, mode=mode, name=b.name, palette={}, config={})
    urls = _external_asset_urls(html)
    assert urls, f"{mode}: no __static asset URLs found in concept page"
    for url in urls:
        assert re.search(_VERSION_RE, url), f"{mode}: unversioned asset URL: {url!r}"
        name = re.search(r"__static/([^?]+)", url).group(1)
        assert f"v={asset_version(name)}" in url
    # theme.js still precedes wiki.js (regression guard for the _theme_js_link change).
    assert html.find("theme.js") < html.find("wiki.js")


@pytest.mark.parametrize("mode", ["serve", "spa", "static"])
def test_graph_page_external_asset_urls_carry_version(
    tiny_good_bundle: Path, mode: str
) -> None:
    b = Bundle.load(tiny_good_bundle)
    html = _render_graph_page(b, mode=mode, name=b.name, config={})
    urls = _external_asset_urls(html)
    assert urls
    for url in urls:
        assert re.search(_VERSION_RE, url), f"{mode}: unversioned graph asset URL: {url!r}"


def test_index_page_external_asset_urls_carry_version(tiny_good_bundle: Path) -> None:
    b = Bundle.load(tiny_good_bundle)
    html = _render_index_page(
        b, mode="serve", name=b.name, palette={}, config={}, sub="", index_file=None,
    )
    urls = _external_asset_urls(html)
    assert urls
    for url in urls:
        assert re.search(_VERSION_RE, url), f"unversioned URL: {url!r}"


def test_version_is_identical_across_serve_and_static(tiny_good_bundle: Path) -> None:
    """Single digest contract: the version for a given asset is the same in
    every emit mode."""
    b = Bundle.load(tiny_good_bundle)
    g = b.graph()
    concept = next(iter(b.concepts.values()))
    by_mode = {}
    for mode in ("serve", "spa", "static"):
        html = _render_concept_page(concept, b, g, mode=mode, name=b.name, palette={}, config={})
        m = re.search(r'href="[^"]*__static/wiki\.css\?v=([0-9a-f]{16})"', html)
        assert m, f"{mode}: wiki.css version not found"
        by_mode[mode] = m.group(1)
    assert by_mode["serve"] == by_mode["spa"] == by_mode["static"] == asset_version("wiki.css")


# ---------------------------------------------------------------------------
# Built-site output: files keep plain names; HTML references carry ?v=
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("target", ["static", "spa"])
def test_build_emits_plain_named_files_but_versioned_html_refs(
    tiny_good_bundle: Path, target: str
) -> None:
    out = tiny_good_bundle / f"_site_{target}_ver"
    b = Bundle.load(tiny_good_bundle)
    build_site(b, out, target=target)
    static_dir = out / "__static"
    assert static_dir.is_dir()
    plain_names = {p.name for p in static_dir.iterdir() if p.is_file()}
    assert plain_names == set(STATIC_ASSET_NAMES), "on-disk asset names drifted from scope"


# ---------------------------------------------------------------------------
# Single-file output stays self-contained
# ---------------------------------------------------------------------------


def test_single_file_has_no_version_queries(tiny_good_bundle: Path) -> None:
    b = Bundle.load(tiny_good_bundle)
    out = tiny_good_bundle / "viz_ver.html"
    render_single_file(b, out)
    html = out.read_text(encoding="utf-8")
    assert "?v=" not in html
    assert _external_asset_urls(html) == []


# ---------------------------------------------------------------------------
# CSP + invalid-encoding + error behaviour
# ---------------------------------------------------------------------------


def test_versioned_urls_are_csp_safe_and_page_csp_unchanged(tiny_good_bundle: Path) -> None:
    """Every emitted versioned URL is same-origin host-relative, the version is
    pure hex (no spaces/quotes/scheme injection), and the page CSP meta tag is
    unchanged by versioning (still ``default-src 'self'``)."""
    b = Bundle.load(tiny_good_bundle)
    g = b.graph()
    concept = next(iter(b.concepts.values()))
    for mode in ("serve", "spa", "static"):
        html = _render_concept_page(concept, b, g, mode=mode, name=b.name, palette={}, config={})
        urls = _external_asset_urls(html)
        assert urls, f"{mode}: no asset URLs"
        for url in urls:
            # No scheme/host (same-origin), no whitespace/quotes.
            assert "://" not in url, f"{mode}: URL has a scheme/host: {url!r}"
            assert not any(c in url for c in (' ', '"', "'", "<", ">")), f"{mode}: unsafe char: {url!r}"
            m = re.search(r"\?v=([0-9a-f]{16})$", url)
            assert m, f"{mode}: version not pure 16-hex at end: {url!r}"
        # The page CSP meta is unchanged by the versioning feature.
        assert "default-src 'self'" in html
        assert "script-src 'self' https://cdn.jsdelivr.net" in html


def test_version_query_with_non_hex_value_is_ignored_for_routing(
    tiny_good_bundle: Path,
) -> None:
    """A malformed/invalid version query must NOT change routing or break the
    response — the server ignores the query entirely."""
    b = Bundle.load(tiny_good_bundle)
    base, _ = _start_server(b)
    expected = load_static("wiki.css").encode("utf-8")
    try:
        for q in ("?v=STALE", "?v=", "?v=!!!", "?v=" + "g" * 16, "?x=1&v=zzz"):
            r = urllib.request.urlopen(f"{base}/__static/wiki.css{q}", timeout=3)
            assert r.status == 200, f"query {q!r} did not resolve"
            assert r.read() == expected
    finally:
        _stop_server()


def test_asset_version_propagates_read_error_for_known_asset(
    tiny_good_bundle: Path, monkeypatch
) -> None:
    """Graceful plain-URL applies ONLY to unknown names. A read error on a
    KNOWN resolved asset is a real failure and propagates (no silent stale
    fallback), mirroring ``load_static`` semantics."""
    _enable_operator_consent(monkeypatch)
    b = _override_bundle(tiny_good_bundle)
    override = _override_dir(b) / "wiki.css"
    override.write_text("/* real override */\n", encoding="utf-8")

    real_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        if self == override:
            raise PermissionError("simulated unreadable override")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)
    # Both the loader and the hasher surface the read error (defined behaviour).
    with pytest.raises(OSError):
        asset_version("wiki.css", b)
    with pytest.raises(OSError):
        load_static("wiki.css", b)


# ---------------------------------------------------------------------------
# Query URLs resolve through the live server
# ---------------------------------------------------------------------------


def test_versioned_query_url_resolves_through_live_server(tiny_good_bundle: Path) -> None:
    """``/__static/wiki.css?v=<anything>`` is served identically to the plain
    URL — the router ignores the query (``urlparse().path``)."""
    b = Bundle.load(tiny_good_bundle)
    base, _ = _start_server(b)
    expected = load_static("wiki.css").encode("utf-8")
    real_v = asset_version("wiki.css")
    try:
        r = urllib.request.urlopen(f"{base}/__static/wiki.css?v={real_v}", timeout=3)
        assert r.status == 200 and r.read() == expected
        r2 = urllib.request.urlopen(f"{base}/__static/wiki.css?v=stale-cache-key", timeout=3)
        assert r2.status == 200 and r2.read() == expected
        r3 = urllib.request.urlopen(f"{base}/__static/wiki.css", timeout=3)
        assert r3.status == 200 and r3.read() == expected
    finally:
        _stop_server()


def test_live_page_external_asset_urls_carry_version(tiny_good_bundle: Path) -> None:
    b = Bundle.load(tiny_good_bundle)
    base, _ = _start_server(b)
    try:
        html = urllib.request.urlopen(base + "/", timeout=3).read().decode("utf-8")
    finally:
        _stop_server()
    urls = _external_asset_urls(html)
    assert urls, "served index page has no __static asset URLs"
    for url in urls:
        assert re.search(_VERSION_RE, url), f"served page: unversioned URL: {url!r}"


def test_studio_bootstrap_assets_carry_version(tiny_good_bundle: Path) -> None:
    """The studio bootstrap injected by the live server (studio.css/live.js/
    studio.js) carries the same version contract as rendered-page assets."""
    import secrets

    from okf_loom.server import OKFWikiHandler
    from okf_loom.studio import Studio

    bundle = Bundle.load(tiny_good_bundle)
    base, server, thread = _start_server_raw(bundle, with_studio=True)
    try:
        html = urllib.request.urlopen(base + "/", timeout=3).read().decode("utf-8")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
    for name in ("studio.css", "live.js", "studio.js"):
        assert f"__static/{name}?v=" in html, f"studio bootstrap missing versioned {name}"
        assert f"v={asset_version(name, bundle)}" in html, f"{name}: version mismatch"


# ---------------------------------------------------------------------------
# Test-server harness helpers
# ---------------------------------------------------------------------------


_SERVER_HOLDER: dict = {}


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_server_raw(bundle: Bundle, *, with_studio: bool = False):
    from okf_loom.server import OKFWikiHandler

    server = ThreadingHTTPServer(("127.0.0.1", _free_port()), OKFWikiHandler)
    server.bundle = bundle
    server.config = {}
    server.name = bundle.name
    server.plugin = None
    server._state_lock = threading.Lock()
    server._reload_error = None
    server.csrf_token = ""
    server.allowed_hosts = ("127.0.0.1", "localhost")
    server.max_sse_clients = 32
    if with_studio:
        import secrets as _s

        from okf_loom.studio import Studio

        studio = Studio.for_bundle(bundle.root, bundle_name=bundle.name)
        studio.ensure_session()
        server.studio = studio
        server.csrf_token = _s.token_hex(16)
        server.studio_live = True
        server.studio_edit = True
        server.studio_theme = "auto"
    else:
        server.studio = None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_address[1]}", server, thread


def _start_server(bundle: Bundle):
    """Context-style start; pair with _stop_server (single active server)."""
    base, server, thread = _start_server_raw(bundle, with_studio=False)
    _SERVER_HOLDER["server"] = server
    _SERVER_HOLDER["thread"] = thread
    return base, server


def _stop_server() -> None:
    server = _SERVER_HOLDER.pop("server", None)
    thread = _SERVER_HOLDER.pop("thread", None)
    if server is not None:
        server.shutdown()
        server.server_close()
    if thread is not None:
        thread.join(timeout=3)
