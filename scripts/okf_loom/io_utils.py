"""Atomic-write helpers shared across okf-loom.

All mutating operations (``update``, ``index``, ``log``, ``render``) go
through these helpers. The pattern is:

    1. Create a tmp file via ``tempfile.mkstemp`` in the *same directory*
       as the target (so ``os.replace`` is atomic on POSIX — same
       filesystem). The tmp file is created mode 0600 by ``mkstemp``, so
       it is private even on shared hosts.
    2. Write the content via ``os.fdopen``.
    3. ``os.replace(tmp, path)`` to swap into place atomically.
    4. On ANY exception during write or replace, ``os.unlink`` the tmp
       file in a ``finally`` block — no orphans left behind.

This addresses:
    - Symlink-race attacks (predictable tmp names → victim file clobber).
    - World-readable tmp files (default umask on Linux is often 0644).
    - Tmp-file orphaning on disk-full / permission errors mid-write.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


SELF_IGNORE = """# Auto-written by okf-loom: this directory holds ephemeral working
# state (live-session feed, undo history, per-session auth token, or
# derived caches) and must never be committed. The `*` makes the
# directory self-ignoring in ANY repository, with no parent .gitignore
# cooperation required. Safe to edit; okf-loom never overwrites it.
*
"""


def ensure_self_ignored(dirpath: str | Path) -> None:
    """Make ``dirpath`` self-ignoring: write ``dirpath/.gitignore``
    containing ``*`` (idempotent; never overwrites an existing file so
    user edits stick). The standard pattern for tool-owned state dirs —
    pytest writes ``.pytest_cache/.gitignore``, Cargo writes
    ``target/.gitignore``, virtualenv self-ignores the venv dir: works
    wherever the bundle lives, and is immune to the directory being
    renamed or configured elsewhere.
    Viewer overrides are deliberately NOT self-ignored — they are
    hand-authored customization worth versioning.
    """
    dirpath = Path(dirpath)
    gi = dirpath / ".gitignore"
    if gi.exists():
        return
    try:
        dirpath.mkdir(parents=True, exist_ok=True)
        atomic_write_text(gi, SELF_IGNORE)
    except OSError:
        pass  # best-effort: a read-only checkout must not break serving


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path`` (tmp + os.replace).

    The tmp file is created in the same directory as ``path`` (so the
    rename is atomic on POSIX) with mode 0600 via ``mkstemp``. Parents
    are created if missing. On any exception, the tmp file is unlinked.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".okf-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        # BaseException so we also clean up on KeyboardInterrupt.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """Atomically write ``data`` to ``path`` (binary). See ``atomic_write_text``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".okf-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_replace_tree(src: str | Path, dst: str | Path) -> None:
    """Atomically replace ``dst`` directory with the contents of ``src``.

    Strategy (POSIX, same-filesystem):
        1. If ``dst`` exists, rename it to ``dst.old`` (atomic).
        2. Rename ``src`` to ``dst`` (atomic).
        3. Recursively delete ``dst.old``.

    If step 2 fails after step 1, we attempt to rename ``dst.old`` back
    to ``dst`` to roll back. The window of inconsistency is the brief
    moment between step 1 and step 2 when ``dst`` does not exist; readers
    may see a missing directory. This is acceptable for build outputs.

    Caller must ensure ``src`` and ``dst`` are on the same filesystem.
    """
    src = Path(src)
    dst = Path(dst)
    if not src.is_dir():
        raise NotADirectoryError(f"src is not a directory: {src}")
    backup: Path | None = None
    if dst.exists():
        backup = dst.with_name(dst.name + ".old")
        # Remove any stale backup from a previous interrupted run.
        if backup.exists():
            _rmtree(backup)
        os.rename(dst, backup)
    try:
        os.rename(src, dst)
    except OSError:
        if backup is not None and backup.exists():
            try:
                os.rename(backup, dst)
            except OSError:
                pass
        raise
    if backup is not None and backup.exists():
        _rmtree(backup)


def _rmtree(path: Path) -> None:
    """Recursively delete a directory tree (symlink-safe).

    Refuses to delete a top-level symlink (which would follow the link
    target and delete its contents rather than the link itself).
    """
    # Guard: if path itself is a symlink, unlink the link, not its target.
    if path.is_symlink():
        try:
            path.unlink()
        except OSError:
            pass
        return
    # Use os.walk top-down so we don't follow symlinks; unlink files and
    # the directory itself.
    for root, dirs, files in os.walk(path, topdown=False, followlinks=False):
        for name in files:
            try:
                (Path(root) / name).unlink()
            except OSError:
                pass
        for name in dirs:
            p = Path(root) / name
            if p.is_symlink():
                try:
                    p.unlink()
                except OSError:
                    pass
            else:
                try:
                    p.rmdir()
                except OSError:
                    pass
    try:
        path.rmdir()
    except OSError:
        pass
