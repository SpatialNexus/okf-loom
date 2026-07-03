"""Bootstrap and import commands for creating new OKF bundles.

``okf bootstrap <dest>`` — scaffold an empty bundle with root index.md
declaring okf_version, plus an empty log.md.

``okf import <src_dir> <dest>`` — copy markdown files from src_dir into
dest, injecting minimal ``type:`` frontmatter heuristically (Reference
default, or guessed from filename/first heading). Existing frontmatter is
preserved. After import, the caller typically runs ``okf discover`` to
find what to curate next.

Both commands are designed for the common onboarding flow: "I have N
markdown files; turn them into an OKF bundle."
"""
from __future__ import annotations

import re
from pathlib import Path

from . import OKF_VERSION_KEY, SPEC_VERSION
from .io_utils import atomic_write_text
from .parse import parse_document, serialize_document

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_FILENAME_TYPE_HINTS: dict[str, str] = {
    "api": "API Endpoint",
    "endpoint": "API Endpoint",
    "table": "Table",
    "dataset": "Dataset",
    "service": "Service",
    "playbook": "Playbook",
    "runbook": "Playbook",
    "reference": "Reference",
    "metric": "Metric",
    "guide": "Guide",
    "tutorial": "Tutorial",
    "readme": "Reference",
}


def bootstrap_bundle(dest: str | Path, *, name: str | None = None) -> dict:
    """Scaffold an empty OKF bundle at ``dest``.

    Creates:
        - ``dest/`` directory (if absent)
        - ``dest/index.md`` with ``okf_version: "0.1"`` frontmatter
        - ``dest/log.md`` with a header and today's initialization entry

    Returns a dict: ``{"created": [paths], "dest": str}``.

    Raises:
        FileExistsError: if ``dest`` already exists and is non-empty
            (to avoid clobbering an existing bundle).
    """
    dest = Path(dest)
    # Guard: refuse if dest is a file (not a directory).
    if dest.exists() and not dest.is_dir():
        raise NotADirectoryError(
            f"Destination exists but is not a directory: {dest}"
        )
    # Guard: refuse to create a nested bundle (dest inside an existing
    # bundle would pollute the parent's rglob-based loader).
    _refuse_if_nested(dest)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(
            f"Destination directory is not empty: {dest}. "
            "Use `okf import` to add files to an existing bundle, or "
            "remove the destination first."
        )
    dest.mkdir(parents=True, exist_ok=True)
    bundle_name = name or dest.resolve().name
    # Note: bundle_name is a display name (shown in the viewer, log, etc.).
    # It is NOT used as a filesystem path segment, so spaces and unicode are
    # fine. The concept-id segment validation does NOT apply here.

    created: list[str] = []

    # Root index.md with okf_version declaration (SPEC §11).
    index_content = serialize_document(
        {OKF_VERSION_KEY: SPEC_VERSION},
        f"# {bundle_name}\n\nA new OKF bundle. Add concepts (markdown files with "
        "`type:` frontmatter) and run `okf discover` to find gaps.\n",
    )
    index_path = dest / "index.md"
    atomic_write_text(index_path, index_content)
    created.append(str(index_path.relative_to(dest)))

    # Log.md with initialization entry.
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    log_content = (
        f"# Update Log\n\n"
        f"## {today}\n"
        f"* **Initialization**: Created bundle `{bundle_name}`.\n"
    )
    log_path = dest / "log.md"
    atomic_write_text(log_path, log_content)
    created.append(str(log_path.relative_to(dest)))

    return {"created": created, "dest": str(dest), "name": bundle_name}


def import_directory(
    src_dir: str | Path,
    dest_dir: str | Path,
    *,
    default_type: str = "Reference",
    overwrite: bool = False,
) -> dict:
    """Import markdown files from ``src_dir`` into an OKF bundle at ``dest_dir``.

    For each ``.md`` file in ``src_dir`` (recursively):
        1. Read the content.
        2. Parse existing frontmatter. If ``type`` is present, preserve it.
           If not, inject ``type: <guessed>`` (heuristic: filename prefix,
           first heading, or ``default_type``).
        3. Write to ``dest_dir`` preserving the relative directory structure.
        4. Skip ``index.md`` / ``log.md`` (reserved filenames).

    If ``dest_dir`` does not exist, it is created (and bootstrapped with
    root ``index.md`` + ``log.md``). If it exists and is a valid bundle,
    files are added alongside existing content unless ``overwrite=False``
    and a file with the same relative path already exists (skipped).

    Returns a dict:
        ``{"imported": N, "skipped": N, "bootstrapped": bool,
          "guessed_types": {filename: type}, "dest": str}``
    """
    src_dir = Path(src_dir)
    dest_dir = Path(dest_dir)

    if not src_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {src_dir}")

    bootstrapped = False
    if not dest_dir.exists() or not any(dest_dir.glob("*.md")):
        bootstrap_bundle(dest_dir)
        bootstrapped = True

    imported = 0
    skipped = 0
    guessed_types: dict[str, str] = {}

    for md_path in sorted(src_dir.rglob("*.md")):
        # Skip symlinked files (defence against info leak: a symlink to
        # /etc/sensitive would copy target contents into the bundle).
        if md_path.is_symlink():
            skipped += 1
            continue
        rel = md_path.relative_to(src_dir)
        # Skip reserved filenames.
        if rel.name in ("index.md", "log.md"):
            skipped += 1
            continue

        target = dest_dir / rel
        if target.exists() and not overwrite:
            skipped += 1
            continue

        # Wrap the ENTIRE per-file pipeline (read + parse + inject + write)
        # in try/except so one bad file doesn't abort the whole import.
        try:
            raw = md_path.read_text(encoding="utf-8")
            fm, body = parse_document(raw)

            # Inject type if missing.
            if not fm.get("type"):
                guessed = _guess_type(rel, body)
                fm["type"] = guessed
                guessed_types[str(rel)] = guessed
                # Ensure title is present (fall back to filename stem).
                if not fm.get("title"):
                    fm["title"] = rel.stem.replace("_", " ").replace("-", " ").title()

            target.parent.mkdir(parents=True, exist_ok=True)
            content = serialize_document(fm, body)
            atomic_write_text(target, content)
            imported += 1
        except (OSError, UnicodeError, Exception) as e:
            # Per-file skip: don't let one bad file abort the whole import.
            # Catching Exception broadly is intentional here — import is a
            # best-effort bulk operation and partial success is better than
            # total failure.
            skipped += 1
            continue

    return {
        "imported": imported,
        "skipped": skipped,
        "bootstrapped": bootstrapped,
        "guessed_types": guessed_types,
        "dest": str(dest_dir),
    }


def _refuse_if_nested(dest: Path) -> None:
    """Raise ValueError if ``dest`` is inside an existing OKF bundle.

    Walks ancestors of ``dest`` looking for a directory containing an
    ``index.md`` with ``okf_version`` frontmatter. Nested bundles corrupt
    the parent bundle's ``rglob``-based loader (SPEC §3 forbids nesting).
    """
    from .parse import parse_document
    parent = dest.parent
    while parent != parent.parent:  # stop at filesystem root
        candidate = parent / "index.md"
        if candidate.exists():
            try:
                fm, _ = parse_document(candidate.read_text(encoding="utf-8"))
                if fm.get("okf_version"):
                    raise ValueError(
                        f"Refusing to create nested bundle: {dest} is inside "
                        f"an existing OKF bundle at {parent}. SPEC §3 forbids "
                        f"nested bundles."
                    )
            except ValueError:
                raise  # Re-raise the refusal; don't swallow it.
            except Exception:
                pass  # Not a valid bundle root; continue walking.
        parent = parent.parent


def _guess_type(rel: Path, body: str) -> str:
    """Heuristically guess the concept type from filename and first heading."""
    # 1. Filename prefix (e.g. "api_users.md" -> "API Endpoint").
    stem_lower = rel.stem.lower()
    for prefix, type_name in _FILENAME_TYPE_HINTS.items():
        if stem_lower.startswith(prefix) or f"_{prefix}" in stem_lower:
            return type_name

    # 2. First heading text.
    m = _HEADING_RE.search(body)
    if m:
        heading = m.group(1).lower()
        for keyword, type_name in _FILENAME_TYPE_HINTS.items():
            if keyword in heading:
                return type_name

    # 3. Default.
    return "Reference"
