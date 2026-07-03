# How-to guides

Recipe-style guides for a specific real-world goal.
Each one assumes you already know the basics and want the steps to a concrete outcome.

Skim the list, find your task, follow the numbered steps.

## Validation and CI

* [Validate a bundle in CI](/how-to/validate_in_ci.md) — pick a profile, wire GitHub Actions / GitLab CI, use exit codes and JSON output.
* [Migrate across spec versions](/how-to/migrate_spec_version.md) — declare `okf_version`, preview and apply idempotent migrations.

## Curation and authoring

* [Find and fix bundle gaps](/how-to/discover_and_fix_gaps.md) — run discovery, triage suggestions, apply via mutators or plans.
* [Author concepts via CLI verbs](/how-to/author_with_verbs.md) — `write-concept`, `set-frontmatter`, `link-add`, `entity-add` without JSON plans.

## Shipping and embedding

* [Build a static site](/how-to/build_static_site.md) — render a bundle to a portable SPA, static, or single-file site.
* [Embed the viewer in an agent harness](/how-to/embed_in_harness.md) — CLI, library, and long-running server integration shapes.
* [Archive and resolve comment threads](/how-to/archive_threads.md) — the separate archive track, the root-only rule, unarchive and auto-unarchive.

## Where to start if you are new

If any of the commands above are unfamiliar, the walk-throughs in the
[/tutorials/](/tutorials/index.md) quadrant take you through them one step at a time.

For the why behind each command, see the
[/explanation/](/explanation/index.md) quadrant, and for the neutral command and flag listings see the
[/reference/](/reference/index.md) quadrant.
