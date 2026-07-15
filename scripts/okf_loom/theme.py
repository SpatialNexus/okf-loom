"""Shared backend contract for Editorial Workbench theme configuration."""
from __future__ import annotations

from typing import Final


# Concrete values emitted into ``data-theme`` and consumed by every renderer.
EXPLICIT_THEMES: Final[tuple[str, ...]] = (
    "swiss-light",
    "swiss-dark",
    "technical-light",
    "technical-dark",
)

# ``auto`` is a preference mode, not a concrete ``data-theme`` value.  The
# studio YAML surface supports it; the legacy viewer JSON surface configures a
# concrete build-time default and therefore intentionally does not.
CONFIGURABLE_THEMES: Final[frozenset[str]] = frozenset((*EXPLICIT_THEMES, "auto"))

# Returning browser preferences are migrated client-side. Configuration files
# reject these retired names and point authors at the same deterministic map.
LEGACY_THEME_MIGRATIONS: Final[dict[str, str]] = {
    "light": "technical-light",
    "dark": "technical-dark",
    "pastel": "swiss-light",
    "sepia": "swiss-light",
    "midnight": "technical-dark",
}


def legacy_theme_message(field_name: str, value: str) -> str | None:
    """Return contextual migration guidance for a retired theme, if any."""
    replacement = LEGACY_THEME_MIGRATIONS.get(value)
    if replacement is None:
        return None
    return (
        f"{field_name}: legacy theme {value!r} is not valid configuration; "
        f"replace it with {replacement!r}. Returning users' saved browser "
        "preferences are migrated automatically."
    )
