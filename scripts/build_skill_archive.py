#!/usr/bin/env python3
"""Skill archive builder with secret scrubbing.

Builds a deterministic zip of the okf-loom skill checkout while
**excluding** caches, virtualenvs, local build state, environment files,
private keys, and any file whose name matches a credential/secret denylist.
After writing, the archive is **re-opened and asserted clean** — if any
denylisted entry slipped in (or was forced in), the build fails closed.

Pure stdlib (``zipfile``, ``os``, ``fnmatch``, ``pathlib``, ``argparse``).
Runnable standalone::

    python scripts/build_skill_archive.py [--source DIR] [--out FILE]

Design notes
------------
* The script is import-safe so tests can call ``build_skill_archive`` and
  ``verify_zip`` directly without parsing argv.
* Output is written via tmp + atomic rename (AGENTS.md hard rule).
* ``verify_zip`` performs an *independent* re-read of the archive on disk
  (not just a re-check of the in-memory file list) — that is what catches
  forced inclusions and writer bugs.
* ZipInfo entries carry a fixed timestamp (1980-01-01, the zipfile minimum)
  so two builds of the same tree produce byte-identical archives; entry
  ordering is sorted by arcname.
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
import zipfile
from pathlib import Path

__all__ = [
    "SecretScrubError",
    "is_path_denied",
    "name_matches_denylist",
    "collect_files",
    "build_skill_archive",
    "verify_zip",
    "scan_archive_contents",
    "main",
]


class SecretScrubError(Exception):
    """Raised when a denylisted file pattern is found in the built archive.

    The post-build verification gate raises this so the build fails closed
    instead of silently shipping a secret-bearing artifact.
    """


# ---------------------------------------------------------------------------
# Denylist
# ---------------------------------------------------------------------------

# Directory names (any depth) that are excluded wholesale. Compared
# case-insensitively so ``.VENV`` / ``Venv`` are also caught.
_DENY_DIR_NAMES: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "venv",
        "env",
        ".env",
        ".eggs",
        ".idea",
        ".vscode",
        ".git",
        ".hg",
        ".svn",
        ".cache",
        ".config",  # never ship local tool config
        "node_modules",
        "build",
        "dist",
        "_site",
        "okf-site",
        "htmlcov",
        ".aic",  # agent scratch state (this workspace's job memory, etc.)
        ".okf-loom",  # generated/session bundle state; regenerate from shipped .md files
        # Credential store directories
        ".aws",
        ".kube",
        ".gnupg",
        ".docker",
        ".ansible",
        ".terraform.d",
    }
)
_DENY_DIR_NAMES_LOWER: frozenset[str] = frozenset(d.lower() for d in _DENY_DIR_NAMES)

# Basename glob patterns (fnmatch, case-insensitive). Files (and dir-like
# artifacts such as ``*.egg-info``) whose basename matches are excluded.
_DENY_NAME_GLOBS: tuple[str, ...] = (
    # Python bytecode
    "*.pyc",
    "*.pyo",
    "*.pyd",
    # Editor / OS noise
    "*.swp",
    "*.swo",
    "*~",
    ".ds_store",
    "thumbs.db",
    # Coverage / cache artefacts
    ".coverage",
    ".coverage.*",
    "htmlcov",
    # Build / packaging artefacts
    "*.egg-info",
    "*.egg",
    # Environment files (dotenv family)
    ".env",
    ".env.*",
    ".envrc",
    # Private-key suffixes
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
    "*.jks",
    # GPG / PGP armored & binary keyrings (P2-56)
    "*.gpg",
    "*.asc",
    # SSH / well-known private key basenames
    "id_rsa",
    "id_rsa.*",
    "id_dsa",
    "id_dsa.*",
    "id_ecdsa",
    "id_ecdsa.*",
    "id_ed25519",
    "id_ed25519.*",
    # Credential store files
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    ".htpasswd",
    "*.htpasswd",  # P2-56: also catch <name>.htpasswd variants
    ".kubeconfig",  # P2-56: kubeconfig basenames
    "*.kubeconfig",  # P2-56: <name>.kubeconfig variants
    "*.kdbx",
    "*.ppk",
    "*.ovpn",
    # Explicit secret-bearing YAML names (P2-56: redundant with the
    # ``secret`` substring rule below, but listed explicitly for clarity
    # and so a future narrowing of the substring rule does not silently
    # re-allow these).
    "secrets.yml",
    "secrets.yaml",
    # Service account / key files
    "service_account*.json",
    "*serviceaccount*.json",
)

# Case-insensitive substrings that mark a basename as credential/secret-ish
# (spec: ``*secret*``, ``*credential*``, ``*token*``, ``*.p12``, "etc.").
_DENY_NAME_SUBSTRINGS: tuple[str, ...] = (
    "secret",
    "credential",
    "token",
    "password",
    "passwd",
    "apikey",
    "api_key",
    "private",
)


def name_matches_denylist(name: str) -> bool:
    """True if a basename matches any denylist glob or secret substring."""
    low = name.lower()
    for sub in _DENY_NAME_SUBSTRINGS:
        if sub in low:
            return True
    for pat in _DENY_NAME_GLOBS:
        pat_l = pat.lower()
        if fnmatch.fnmatch(low, pat_l):
            return True
    return False


def is_path_denied(rel_path: str) -> bool:
    """True if any path component or basename of ``rel_path`` is denylisted.

    ``rel_path`` may be POSIX- or Windows-style and may include a leading
    top-level skill-archive prefix (e.g. ``okf-loom/scripts/...``); every
    non-empty component is checked, so directory-level exclusions apply
    no matter where they appear in the path.
    """
    parts = rel_path.replace("\\", "/").split("/")
    for part in parts:
        if not part:
            continue
        if part.lower() in _DENY_DIR_NAMES_LOWER:
            return True
        if name_matches_denylist(part):
            return True
    return False


# ---------------------------------------------------------------------------
# File collection + zip build
# ---------------------------------------------------------------------------

# Fixed ZipInfo timestamp — the zipfile format minimum. Used for every entry
# so two builds of the same tree produce byte-identical archives.
_FIXED_TIMESTAMP: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)


def collect_files(
    source: Path,
    *,
    exclude: set[Path] | None = None,
) -> list[tuple[str, Path]]:
    """Walk ``source`` and return sorted ``[(arcname, abs_path), ...]``.

    Denied directories are pruned in-place during the walk (so we never
    descend into them); each surviving file is also re-checked against the
    denylist as belt-and-suspenders. ``exclude`` is a set of absolute paths
    to skip even when they otherwise pass the denylist (used to keep the
    output zip itself out of the next run's archive).
    """
    source = source.resolve()
    top = source.name
    exclude_resolved = {p.resolve() for p in (exclude or ())}
    files: list[tuple[str, Path]] = []

    for root, dirnames, filenames in os.walk(source):
        # Prune denied directories in-place (and keep walk order deterministic).
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d.lower() not in _DENY_DIR_NAMES_LOWER
            and not name_matches_denylist(d)
        )
        root_path = Path(root)
        for fn in sorted(filenames):
            abs_path = (root_path / fn).resolve()
            if abs_path in exclude_resolved:
                continue
            rel = abs_path.relative_to(source).as_posix()
            arc = f"{top}/{rel}"
            if is_path_denied(arc):
                continue
            files.append((arc, abs_path))

    files.sort(key=lambda t: t[0])
    return files


def build_skill_archive(
    source: Path | str,
    out: Path | str,
    *,
    fixed_time: tuple[int, int, int, int, int, int] = _FIXED_TIMESTAMP,
) -> list[str]:
    """Build a deterministic skill-checkout zip of ``source`` at ``out``.

    Writes to ``<out>.tmp`` and atomically renames into place, then
    independently re-opens the final archive and asserts it is clean.
    Returns the sorted list of arcnames actually present in the archive.

    Raises:
        SecretScrubError: if ``source`` is not a directory or the post-build
            verification pass finds any denylisted entry.
    """
    source = Path(source).resolve()
    out = Path(out).resolve()
    if not source.is_dir():
        raise SecretScrubError(f"source directory not found: {source}")

    out.parent.mkdir(parents=True, exist_ok=True)
    files = collect_files(source, exclude={out})

    tmp_out = out.with_suffix(out.suffix + ".tmp")
    if tmp_out.exists():
        tmp_out.unlink()
    try:
        with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for arc, path in files:
                st = path.stat()
                zi = zipfile.ZipInfo(arc, date_time=fixed_time)
                # Preserve unix mode (top 16 bits of external_attr) so
                # executable scripts stay executable after unzip.
                zi.external_attr = (st.st_mode & 0xFFFF) << 16
                zi.compress_type = zipfile.ZIP_DEFLATED
                with open(path, "rb") as fh:
                    zf.writestr(zi, fh.read())
        os.replace(tmp_out, out)
    finally:
        if tmp_out.exists():
            tmp_out.unlink()

    # Independent re-read of the on-disk archive — catches writer bugs and
    # forced inclusions the in-memory walk could miss.
    return verify_zip(out)


# ---------------------------------------------------------------------------
# Content scanning (P2-56, second layer)
# ---------------------------------------------------------------------------
#
# A denylist by name cannot catch a private key saved as ``notes.txt``. As a
# second layer, ``scan_archive_contents`` re-opens the finished archive and
# looks for a PEM private-key block inside each entry. This is O(total
# archive bytes) but runs only at verify time (once per build); for the OKF
# Toolkit (a few hundred small source files) the cost is negligible. For a
# much larger source tree the scan can be disabled via
# ``verify_zip(..., scan_contents=False)``.
#
# We scan only the first ``_PEM_SCAN_HEAD_BYTES`` of each entry: PEM blocks
# start at (or near) the beginning of a key file.
#
# False-positive avoidance: the regex requires BOTH a ``-----BEGIN ... PRIVATE
# KEY-----`` header AND a matching ``-----END ... PRIVATE KEY-----`` footer
# within the scanned head, with base64 body bytes between. A real private
# key always has all three; a source/doc/test file that merely *mentions*
# the marker as a string literal (e.g. a unit test planting
# ``"-----BEGIN PRIVATE KEY-----\n"``) does NOT match because it lacks the
# footer + body. This is the reported cost tradeoff: a naive header-only
# scan would flag legitimate source files; the block scan flags real keys.
_PEM_SCAN_HEAD_BYTES: int = 8 * 1024
_PEM_PRIVATE_KEY_RE = re.compile(
    rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"
    rb"[A-Za-z0-9+/=\s]{8,8000}"  # base64 body (newlines + padding)
    rb"-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----"
)


def scan_archive_contents(out: Path | str) -> list[str]:
    """Scan every entry in ``out`` for a PEM private-key block.

    Returns the sorted list of arcnames whose content matched a full PEM
    block (header + base64 body + footer). Does NOT raise; callers
    (``verify_zip``) raise ``SecretScrubError`` when the list is non-empty.
    Binary-safe: reads bytes and matches the byte regex. Only the first
    ``_PEM_SCAN_HEAD_BYTES`` of each entry are read.
    """
    out = Path(out)
    offenders: list[str] = []
    with zipfile.ZipFile(out, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            try:
                with zf.open(info, "r") as fh:
                    head = fh.read(_PEM_SCAN_HEAD_BYTES)
            except (RuntimeError, zipfile.BadZipFile, OSError):
                # Unreadable entry → skip; verify_zip's name check is the
                # primary gate, and a corrupt entry will fail at unzip time.
                continue
            if _PEM_PRIVATE_KEY_RE.search(head):
                offenders.append(info.filename)
    return sorted(set(offenders))


def verify_zip(
    out: Path | str,
    *,
    scan_contents: bool = True,
) -> list[str]:
    """Re-open ``out`` on disk and assert no entry is denylisted.

    Returns the sorted list of arcnames. Raises ``SecretScrubError`` listing
    the offending entries when any denylisted pattern is present.

    Two layers (P2-56):

    1. **Name denylist** (``is_path_denied``): every arcname component is
       checked against the glob + substring denylist. Catches the common
       cases (``.env``, ``id_rsa``, ``*.pem``, ``secrets.yml``, …).
    2. **Content scan** (``scan_archive_contents``): re-reads each entry's
       first bytes and looks for a PEM ``-----BEGIN ... PRIVATE KEY-----``
       header. Catches a key saved with a benign filename. Disable with
       ``scan_contents=False`` for very large trees where the O(N) read is
       too costly (the name denylist still runs).
    """
    out = Path(out)
    with zipfile.ZipFile(out, "r") as zf:
        infos = zf.infolist()
        offenders = [i.filename for i in infos if is_path_denied(i.filename)]
        arcnames = [i.filename for i in infos]
    if offenders:
        raise SecretScrubError(
            "post-build verification failed; denylisted entries present in "
            f"archive {out}:\n  " + "\n  ".join(sorted(set(offenders)))
        )
    if scan_contents:
        content_offenders = scan_archive_contents(out)
        if content_offenders:
            raise SecretScrubError(
                "post-build content scan failed; entries containing a PEM "
                f"private-key header present in archive {out}:\n  "
                + "\n  ".join(content_offenders)
            )
    return sorted(arcnames)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    here = Path(__file__).resolve().parent
    repo_root = here.parent  # scripts/ -> okf-loom/
    default_out = repo_root.parent / "okf-loom.zip"

    p = argparse.ArgumentParser(
        prog="build_skill_archive.py",
        description=(
            "Build a deterministic zip of the okf-loom skill checkout "
            "with cache/secret scrubbing and post-build verification."
        ),
    )
    p.add_argument(
        "--source",
        type=Path,
        default=repo_root,
        help="skill checkout root to zip (default: the okf-loom/ this script ships in)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=default_out,
        help="output zip path (default: <source>/../okf-loom.zip)",
    )
    return p


def print_manifest(arcnames: list[str], *, source: Path, out: Path) -> None:
    """Print the build manifest (sorted arcnames) to stdout."""
    print(f"# okf-loom skill archive")
    print(f"#   source: {source}")
    print(f"#   out:    {out}")
    print(f"#   files:  {len(arcnames)}")
    for arc in arcnames:
        print(f"  {arc}")


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    source = args.source.resolve()
    out = args.out.resolve()

    try:
        manifest = build_skill_archive(source, out)
    except SecretScrubError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print_manifest(manifest, source=source, out=out)
    print(f"\n# wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
