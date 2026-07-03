---
okf_version: '0.1'
okf_extensions:
  - okf.cap.typed_relations
  - okf.cap.entities
  - okf.cap.aliases
generated: true
---

# okf-loom Documentation

okf-loom is a GitHub-cloneable, vendor-neutral,
harness-agnostic skill repository with a documentation bundle, focused
resources, and checkout-local scripts. It **validates**, **searches**, **discovers gaps in**, **updates**,
and **renders a navigable wiki + graph viewer for** any Open Knowledge Format
bundle. See the [current okf-loom specification](reference/spec.md); upstream
OKF SPEC v0.1 remains the base wire-format reference.

**See it in action:** the [Rendering & Feature Showcase](demo/showcase.md)
packs every renderer (Mermaid, KaTeX, syntax highlighting, tables) and
live feature onto one page.

This bundle IS okf-loom's own documentation, organised in the
[Diátaxis](https://diataxis.fr/) framework: each concept belongs to one of
four content types, and the type tells you how to read it.

# Demo

* [Rendering & Feature Showcase](demo/showcase.md) — every renderer
  (Mermaid, KaTeX, syntax highlighting, tables) and every governed key
  on one page. Open it first when evaluating the viewer.

# Four kinds of documentation

## Learning

Walk-throughs written for someone new to okf-loom. Read top to bottom;
reproduce every step.

* [Use okf-loom from a clone](tutorials/install.md) — clone, load `SKILL.md` and resources, verify, first `scripts/okf-loom validate`.
* [Author your first bundle](tutorials/first_bundle.md) — scaffold, write, validate.
* [Use the live studio](tutorials/live_studio_basics.md) — serve, navigate, comment.
* [Direct the agent loop](tutorials/author_with_agent.md) — wait → claim → write → resolve.

See [tutorials/](tutorials/index.md) for the full list.

## How-to

Recipe-style guides for a specific goal. Skim the list, find your task,
follow the steps.

* [Validate a bundle in CI](how-to/validate_in_ci.md)
* [Find and fix bundle gaps](how-to/discover_and_fix_gaps.md)
* [Author concepts via CLI verbs](how-to/author_with_verbs.md)
* [Build a static site](how-to/build_static_site.md)
* [Archive and resolve comment threads](how-to/archive_threads.md)
* [Embed the viewer in an agent harness](how-to/embed_in_harness.md)
* [Migrate across spec versions](how-to/migrate_spec_version.md)

See [how-to/](how-to/index.md) for the full list.

## Reference

Technical descriptions of the machinery. Read topically; not sequential.

* [CLI command reference](reference/cli.md)
* [Current okf-loom specification](reference/spec.md)
* [Frontmatter contract](reference/frontmatter.md)
* [Link forms](reference/links.md)
* [Capability registry](reference/capabilities.md)
* [Search modes](reference/search_modes.md)
* [HTTP server routes](reference/http_routes.md)
* [Comment lifecycle and archive rules](reference/comment_lifecycle.md)
* [okf-loom.config.yaml reference](reference/config_yaml.md)

### Deep design docs (imported)

These are the long-form authoritative sources for design rationale and
binding specs. They live in the bundle so search/graph/indexes reach them.

* [okf-loom architecture](reference/architecture.md) — module-by-module developer reference.
* [Embedding guide](reference/embedding_guide.md) — harness-specific wiring recipes (opencode, Claude Code, Codex, LangGraph, MCP, custom).

See [reference/](reference/index.md) for the full list.

## Understanding

Discussion-oriented pieces that clarify the why behind the design.

* [What OKF is for](explanation/what_is_okf.md)
* [okf-loom architecture (concise)](explanation/architecture.md)
* [Why the live studio exists](explanation/live_studio_design.md)
* [Dependency-light philosophy](explanation/zero_dependencies.md)
* [Why this bundle uses Diátaxis](explanation/diataxis.md)
* [Original requirements brief](explanation/requirements.md) — the user-stated goals + traceability matrix.
* [Best-of-breed research](explanation/research.md) — comparative analysis of Obsidian, Quartz, MkDocs, etc.

See [explanation/](explanation/index.md) for the full list.

# Outside the bundle

These stay in `okf-loom/docs/` because they are retained proof artifacts
rather than user-facing docs:

* [docs/screenshots/](../docs/screenshots/) — viewer capture proof PNGs.
