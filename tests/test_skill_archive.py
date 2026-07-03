"""Tests for ``scripts/build_skill_archive.py`` (current skill archive hygiene contract).

These pin the skill-archive builder's secret-scrubbing invariants:

* Building the real repo yields a zip with no denylisted entries.
* A planted ``secret.txt`` is excluded by the builder.
* The post-build verification gate catches a *forced* inclusion (re-opens
  the archive on disk and fails closed).
* ``__pycache__`` / ``*.pyc`` / virtualenvs / dotenv files / private keys
  are all excluded.
* Entry ordering is deterministic.

Tests import the builder module directly from disk (it lives under
``scripts/``, not under ``src/``, so it is not on ``sys.path`` by default).
"""
from __future__ import annotations

import stat
import sys
import zipfile
from pathlib import Path

import pytest

# Import the builder script as a module. It lives under scripts/, which is
# not a package; load it directly from disk so the tests work no matter the
# caller's CWD.
_TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _TOOLKIT_ROOT / "scripts" / "build_skill_archive.py"

if str(_SCRIPT_PATH.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_PATH.parent))

import build_skill_archive as bpz  # type: ignore[import-not-found]  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str = "x", *, mode: int | None = None) -> Path:
    """Create a small file (and parents). Returns the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)
    return path


def _make_tree(tmp_path: Path, name: str = "pkg") -> Path:
    """A clean source tree with a couple of innocuous files."""
    root = tmp_path / name
    root.mkdir()
    _write(root / "README.md", "# demo\n")
    _write(root / "src" / "demo" / "__init__.py", "")
    _write(root / "src" / "demo" / "mod.py", "x = 1\n")
    return root


def _arcnames_of(out: Path) -> list[str]:
    with zipfile.ZipFile(out, "r") as zf:
        return sorted(zf.namelist())


# ---------------------------------------------------------------------------
# Unit-level denylist predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel_path",
    [
        # caches / bytecode
        "pkg/foo/__pycache__/m.pyc",
        "pkg/.pytest_cache/v/cache/lastfailed",
        "pkg/mod.pyc",
        "pkg/.mypy_cache/index.json",
        # virtualenvs
        "pkg/.venv/bin/python",
        "pkg/venv/Lib/python.dll",
        "pkg/env/bin/activate",
        # build / packaging state
        "pkg/build/lib/x.py",
        "pkg/dist/pkg-1.0.tar.gz",
        "pkg/src/pkg.egg-info/PKG-INFO",
        # dotenv
        "pkg/.env",
        "pkg/.env.local",
        "pkg/.env.production",
        "pkg/.envrc",
        # private keys
        "pkg/server.pem",
        "pkg/tls/client.key",
        "pkg/ssh/id_rsa",
        "pkg/ssh/id_rsa.pub",  # the .pub variant also starts with id_rsa
        "pkg/cert.p12",
        "pkg/cert.pfx",
        # credential/secret denylist (case-insensitive)
        "pkg/secret.txt",
        "pkg/SECRET.TXT",
        "pkg/credentials.json",
        "pkg/MyCredentials.yaml",
        "pkg/api_token.txt",
        "pkg/.api_key",
        "pkg/passwords.lst",
        "PKG/private.key",
        # P2-56: GPG / PGP armored & binary keyring suffixes
        "pkg/pubring.gpg",
        "pkg/secring.gpg",
        "pkg/keys/secret.asc",
        "pkg/message.asc",
        # P2-56: kubeconfig basenames (exact and <name>.kubeconfig)
        "pkg/.kubeconfig",
        "pkg/prod.kubeconfig",
        # P2-56: explicit secret-bearing YAML names (redundant with the
        # ``secret`` substring rule but pinned for clarity + future-proofing)
        "pkg/secrets.yml",
        "pkg/secrets.yaml",
        "pkg/config/secrets.yaml",
        # P2-56: <name>.htpasswd glob variants
        "pkg/basic.htpasswd",
        "pkg/htpasswd/basic.htpasswd",
    ],
)
def test_is_path_denied_catches_every_category(rel_path: str) -> None:
    """Every denylisted path shape must be flagged by ``is_path_denied``."""
    assert bpz.is_path_denied(rel_path), rel_path


@pytest.mark.parametrize(
    "rel_path",
    [
        "pkg/README.md",
        "pkg/src/demo/__init__.py",
        "pkg/src/demo/mod.py",
        "pkg/docs/architecture.md",
        "pkg/tests/test_foo.py",  # no denylist substring in 'test_foo.py'
        "pkg/samples/demo_bundle/tables/users.md",
        # 'tokenize.py' contains the substring 'token' — that is the cost of
        # the spec-mandated ``*token*`` rule. The library has no such file
        # today; if one is ever added, it must be renamed or explicitly
        # allow-listed. We do NOT carve out an exception here.
    ],
)
def test_is_path_denied_leaves_benign_paths_alone(rel_path: str) -> None:
    assert not bpz.is_path_denied(rel_path), rel_path


# ---------------------------------------------------------------------------
# Building a clean tree: builder excludes, ordering deterministic, manifest
# ---------------------------------------------------------------------------


def test_builder_excludes_planted_secret_txt(tmp_path: Path) -> None:
    """Spec acceptance: a planted ``secret.txt`` is excluded by the builder."""
    root = _make_tree(tmp_path, "pkg")
    _write(root / "config" / "secret.txt", "supersecret\n")
    _write(root / "src" / "demo" / "normal.txt", "ok\n")

    out = tmp_path / "pkg.zip"
    manifest = bpz.build_skill_archive(root, out)

    joined = "\n".join(manifest)
    assert "secret.txt" not in joined
    assert "config" not in joined  # whole subdir under a secret file is fine
    assert any(m.endswith("normal.txt") for m in manifest)


def test_excludes_pycache_and_pyc(tmp_path: Path) -> None:
    """``__pycache__`` and ``*.pyc`` are never shipped."""
    root = _make_tree(tmp_path, "pkg")
    _write(root / "src" / "demo" / "__pycache__" / "mod.cpython-312.pyc", "\0")
    _write(root / "src" / "demo" / "mod.cpython-312.pyc", "\0")  # stray at module root

    manifest = bpz.build_skill_archive(root, tmp_path / "out.zip")

    assert not any("__pycache__" in m for m in manifest)
    assert not any(m.endswith(".pyc") for m in manifest)
    # but the real source file is still there
    assert any(m.endswith("demo/mod.py") for m in manifest)


def test_excludes_venv_and_pytest_cache(tmp_path: Path) -> None:
    """Virtualenvs and pytest cache dirs are pruned wholesale."""
    root = _make_tree(tmp_path, "pkg")
    _write(root / ".venv" / "bin" / "python", "\0")
    _write(root / ".venv" / "lib" / "site-packages" / "x.py", "x = 1\n")
    _write(root / "venv" / "lib" / "x.py", "x = 1\n")
    _write(root / ".pytest_cache" / "v" / "cache" / "lastfailed", "")
    _write(root / ".mypy_cache" / "index.json", "{}")

    manifest = bpz.build_skill_archive(root, tmp_path / "out.zip")
    joined = "\n".join(manifest)

    assert ".venv" not in joined
    assert "/venv/" not in joined
    assert ".pytest_cache" not in joined
    assert ".mypy_cache" not in joined


def test_excludes_env_files(tmp_path: Path) -> None:
    """Dotenv family (``.env``, ``.env.*``, ``.envrc``) is excluded."""
    root = _make_tree(tmp_path, "pkg")
    _write(root / ".env", "API_KEY=hunter2\n")
    _write(root / ".env.local", "DB=prod\n")
    _write(root / ".env.production", "DB=prod\n")
    _write(root / ".envrc", "export FOO=1\n")
    # sanity: a normal file named 'environment.md' is fine
    _write(root / "docs" / "environment.md", "# env\n")

    manifest = bpz.build_skill_archive(root, tmp_path / "out.zip")
    joined = "\n".join(manifest)

    assert "/.env\n" not in joined + "\n"
    assert ".env.local" not in joined
    assert ".env.production" not in joined
    assert ".envrc" not in joined
    assert "environment.md" in joined  # benign name kept


def test_excludes_private_keys_and_ssh(tmp_path: Path) -> None:
    """Private-key suffixes and ``id_rsa*`` basenames are excluded."""
    root = _make_tree(tmp_path, "pkg")
    _write(root / "tls" / "server.pem", "-----BEGIN PRIVATE KEY-----\n")
    _write(root / "tls" / "client.key", "-----BEGIN RSA PRIVATE KEY-----\n")
    _write(root / "ssh" / "id_rsa", "-----BEGIN OPENSSH PRIVATE KEY-----\n")
    _write(root / "ssh" / "id_ed25519", "-----BEGIN OPENSSH PRIVATE KEY-----\n")
    _write(root / "certs" / "client.p12", "\0")
    _write(root / "certs" / "server.pfx", "\0")

    manifest = bpz.build_skill_archive(root, tmp_path / "out.zip")
    joined = "\n".join(manifest)

    for needle in [".pem", ".key", "id_rsa", "id_ed25519", ".p12", ".pfx"]:
        assert needle not in joined, f"denylisted key {needle!r} shipped"


def test_excludes_credential_token_names_case_insensitive(tmp_path: Path) -> None:
    """``*credential*`` / ``*token*`` / ``*secret*`` match regardless of case."""
    root = _make_tree(tmp_path, "pkg")
    _write(root / "creds" / "MyCredentials.json", "{}")
    _write(root / "creds" / "API_TOKEN.env", "x=y")  # also .env but substring first
    _write(root / "creds" / "secret", "s")
    _write(root / "creds" / "PASSWORDS.txt", "")

    manifest = bpz.build_skill_archive(root, tmp_path / "out.zip")
    joined = "\n".join(manifest).lower()

    for needle in ["credential", "token", "secret", "password"]:
        assert needle not in joined, f"denylisted substring {needle!r} shipped"


def test_build_is_deterministic_ordering(tmp_path: Path) -> None:
    """Two builds of the same tree produce identical sorted arcname lists.

    The returned manifest is always sorted (independent of filesystem walk
    order), and the on-disk archive is byte-identical across runs because
    every entry carries a fixed timestamp.
    """
    root_a = _make_tree(tmp_path, "pkgA")
    root_b = _make_tree(tmp_path, "pkgB")  # identical shape, different top-level name

    out_a = tmp_path / "a.zip"
    out_b = tmp_path / "b.zip"
    m_a = bpz.build_skill_archive(root_a, out_a)
    m_b = bpz.build_skill_archive(root_b, out_b)

    # The returned manifest is always sorted ascending.
    assert m_a == sorted(m_a)
    assert m_b == sorted(m_b)

    # Stripping the top-level prefix, identical tree shapes produce identical
    # arcname lists in identical order.
    strip = lambda lst: [n.split("/", 1)[1] if "/" in n else n for n in lst]
    assert strip(m_a) == strip(m_b)

    # Byte-deterministic: building the SAME tree twice yields identical bytes
    # (fixed timestamp + sorted order + deterministic compression).
    out_a2 = tmp_path / "a2.zip"
    bpz.build_skill_archive(root_a, out_a2)
    assert out_a.read_bytes() == out_a2.read_bytes()

    # Scrambling filesystem creation order does not change manifest order.
    root_c = _make_tree(tmp_path, "pkgC")
    _write(root_c / "zzz.md", "")
    _write(root_c / "aaa.md", "")
    out_c1 = tmp_path / "c1.zip"
    out_c2 = tmp_path / "c2.zip"
    m_c1 = bpz.build_skill_archive(root_c, out_c1)
    m_c2 = bpz.build_skill_archive(root_c, out_c2)
    assert m_c1 == m_c2 == sorted(m_c1)


def test_build_preserves_executable_bit(tmp_path: Path) -> None:
    """Executable scripts keep their mode bit after a build/unzip round-trip."""
    root = _make_tree(tmp_path, "pkg")
    script = _write(root / "scripts" / "run.sh", "#!/bin/sh\necho hi\n")
    script.chmod(0o755)

    out = tmp_path / "out.zip"
    bpz.build_skill_archive(root, out)

    with zipfile.ZipFile(out, "r") as zf:
        zi = next(i for i in zf.infolist() if i.filename.endswith("run.sh"))
    mode = (zi.external_attr >> 16) & 0o7777
    assert stat.S_ISREG((zi.external_attr >> 16) & 0o170000)
    assert mode & stat.S_IXUSR, f"expected executable bit; got mode={oct(mode)}"


def test_build_refuses_to_zip_output_into_itself(tmp_path: Path) -> None:
    """A prior ``out`` file inside ``source`` is excluded from the next walk."""
    root = _make_tree(tmp_path, "pkg")
    out = root / "pkg.zip"  # inside source!
    bpz.build_skill_archive(root, out)
    assert out.is_file()
    first = _arcnames_of(out)
    assert not any(n.endswith("pkg.zip") for n in first)

    # Second run should not pick up the previously written zip.
    bpz.build_skill_archive(root, out)
    second = _arcnames_of(out)
    assert first == second


# ---------------------------------------------------------------------------
# Post-build verification gate (fail-closed)
# ---------------------------------------------------------------------------


def test_post_build_verification_catches_forced_inclusion(tmp_path: Path) -> None:
    """Spec acceptance: post-build verify catches a forced denylisted entry.

    Builds a clean archive, then appends a ``secret.txt`` entry to it (the
    way a buggy writer or an attacker could), and asserts that ``verify_zip``
    re-opens the on-disk archive and fails closed.
    """
    root = _make_tree(tmp_path, "pkg")
    out = tmp_path / "out.zip"
    bpz.build_skill_archive(root, out)
    # Sanity: it was clean.
    bpz.verify_zip(out)

    # Force a denylisted entry into the archive on disk.
    with zipfile.ZipFile(out, "a") as zf:
        zf.writestr("pkg/leaked/secret.txt", "hunter2\n")

    with pytest.raises(bpz.SecretScrubError) as ei:
        bpz.verify_zip(out)
    assert "secret.txt" in str(ei.value)


def test_build_fails_when_source_missing(tmp_path: Path) -> None:
    """A missing source directory fails closed with SecretScrubError."""
    with pytest.raises(bpz.SecretScrubError):
        bpz.build_skill_archive(tmp_path / "does-not-exist", tmp_path / "out.zip")


# ---------------------------------------------------------------------------
# Real-repo smoke: building the actual toolkit yields a clean zip
# ---------------------------------------------------------------------------


def test_build_repo_zip_has_no_denylisted_entries(tmp_path: Path) -> None:
    """Spec acceptance: building the repo yields a zip with no denylisted entries.

    Builds the real ``okf-loom/`` tree (which currently contains
    ``__pycache__``, ``.pytest_cache``, and a ``*.egg-info`` dir from local
    dev) and asserts the resulting archive is clean per ``verify_zip`` and
    per direct substring spot-checks for every spec-listed category.
    """
    out = tmp_path / "okf-loom.zip"
    manifest = bpz.build_skill_archive(_TOOLKIT_ROOT, out)

    # Independent verify (build_skill_archive already did one; do another to
    # be explicit about the contract).
    again = bpz.verify_zip(out)
    assert again == sorted(again) == manifest

    joined = "\n".join(manifest).lower()
    for needle in [
        "__pycache__",
        ".pytest_cache",
        "/.okf-loom/",
        ".mypy_cache",
        ".pyc",
        ".venv",
        "/venv/",
        "egg-info",
        "/build/",
        "/dist/",
        ".env",
        ".envrc",
        ".pem",
        ".key",
        "id_rsa",
        ".p12",
        ".pfx",
        "secret",
        "credential",
        "token",
        "password",
        "private",
    ]:
        assert needle not in joined, f"denylisted pattern {needle!r} shipped"

    # Spot-check that real source files DID make it in (so the denylist
    # didn't over-prune).
    assert any(n.endswith("scripts/okf_loom/__init__.py") for n in manifest)
    assert any(n.endswith("pyproject.toml") for n in manifest)
    assert any(n.endswith("README.md") for n in manifest)


def test_cli_smoke_against_real_repo(tmp_path: Path) -> None:
    """``main`` builds the real repo to a temp zip and returns 0."""
    out = tmp_path / "okf-loom.zip"
    rc = bpz.main(["--source", str(_TOOLKIT_ROOT), "--out", str(out)])
    assert rc == 0
    assert out.is_file()
    assert out.stat().st_size > 0
    manifest = bpz.verify_zip(out)
    assert manifest == sorted(manifest)
    assert len(manifest) > 20  # the real skill checkout has well over 20 files


# ---------------------------------------------------------------------------
# Cleanup: make sure we don't leave build artefacts in the repo
# ---------------------------------------------------------------------------


def test_default_out_path_is_outside_source(tmp_path: Path) -> None:
    """Default ``--out`` lives OUTSIDE the source tree (no self-zip recursion)."""
    parser = bpz._build_arg_parser()
    args_default = parser.parse_args([])
    args_default_source = args_default.source.resolve()
    args_default_out = args_default.out.resolve()
    # out must not be inside source.
    assert args_default_out != args_default_source
    assert args_default_source not in args_default_out.parents


# ---------------------------------------------------------------------------
# P2-56: content-scan second layer (catches a key saved with a benign name)
# ---------------------------------------------------------------------------

# A realistic PEM private-key block (header + base64 body + footer). Small
# but valid-shaped; the body is base64 of the string "okf-test-key-material".
_FAKE_PEM_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "b2tmLXRlc3Qta2V5LW1hdGVyaWFsAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
    "-----END RSA PRIVATE KEY-----\n"
)


def test_verify_zip_content_scan_catches_pem_key_with_benign_name(
    tmp_path: Path,
) -> None:
    """A PEM key block saved as ``notes.txt`` is caught by the content scan.

    P2-56 second layer: the name denylist cannot catch a key renamed to a
    benign filename; the verify-time content scan re-reads each entry and
    fails closed when a full PEM private-key block is present.
    """
    root = _make_tree(tmp_path, "pkg")
    # Plant a real-shaped PEM block under a benign name. The name is NOT on
    # the denylist (so only the content scan catches it).
    assert not bpz.is_path_denied("pkg/notes.txt")
    _write(root / "notes.txt", _FAKE_PEM_KEY)

    out = tmp_path / "out.zip"
    with pytest.raises(bpz.SecretScrubError) as ei:
        bpz.build_skill_archive(root, out)
    assert "content scan failed" in str(ei.value)
    assert "notes.txt" in str(ei.value)


def test_verify_zip_content_scan_can_be_disabled(tmp_path: Path) -> None:
    """``scan_contents=False`` opts out of the content scan (large-tree escape)."""
    root = _make_tree(tmp_path, "pkg")
    _write(root / "notes.txt", _FAKE_PEM_KEY)
    out = tmp_path / "out.zip"
    # Build with the scan disabled — the benign-named key slips through, but
    # the name denylist still runs (a denylisted NAME would still fail).
    # build_skill_archive calls verify_zip(out) with default scan=True, so to
    # test the disabled path we build the zip manually then verify with
    # scan_contents=False.
    import zipfile
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc, path in bpz.collect_files(root):
            zf.write(path, arc)
    manifest = bpz.verify_zip(out, scan_contents=False)
    assert any(m.endswith("notes.txt") for m in manifest)


def test_content_scan_ignores_bare_pem_header_in_test_or_doc_files(
    tmp_path: Path,
) -> None:
    """A bare header string (no footer/body) must NOT trip the scan.

    This is the false-positive avoidance contract: source/doc/test files
    that merely *mention* ``-----BEGIN PRIVATE KEY-----`` as a string
    literal (e.g. this very test file, and tests/test_package.py's planted
    fixtures) must pass the content scan. Only a full PEM block matches.
    """
    root = _make_tree(tmp_path, "pkg")
    # Header only — no base64 body, no footer.
    _write(root / "docs" / "key-format.md", "# Key format\n\nUses `-----BEGIN PRIVATE KEY-----`.\n")
    out = tmp_path / "out.zip"
    manifest = bpz.build_skill_archive(root, out)
    assert any(m.endswith("key-format.md") for m in manifest)
    # Direct scan helper returns no offenders.
    assert bpz.scan_archive_contents(out) == []
