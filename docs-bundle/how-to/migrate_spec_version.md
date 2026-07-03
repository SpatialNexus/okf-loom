---
type: How-to
title: Migrate across spec versions
description: Migrate an OKF bundle across OKF spec versions by declaring okf_version in the root index, previewing with upgrade checks, and applying idempotent migrations.
resource: /how-to/migrate_spec_version.md
tags: [migration, upgrade, spec-version, forward-compat]
timestamp: "2026-06-29T00:00:00Z"
---

# Migrate across spec versions

This guide walks you through moving a bundle across OKF spec versions
safely, with preview, idempotent application, and no hand-editing of
files.

You already have a bundle and have run validation against it.
If you do not, [Author your first bundle](/tutorials/first_bundle.md)
covers the basics.

# Step 1: Declare the bundle's spec version

The bundle declares its spec version in the **root** `index.md`
frontmatter, and only there (SPEC §6, §11).

```yaml
---
okf_version: "0.1"
okf_extensions:
  - okf.cap.typed_relations
  - okf.cap.entities
generated: true
---
```

Quote the version string so YAML keeps it as a string rather than parsing
it as a float — the same rule that applies to `timestamp`.

If the declared version differs from okf-loom's `SPEC_VERSION`, the
validator emits a warning and okf-loom does best-effort consumption
(SPEC §11 mandate).

Non-root `index.md` files MUST NOT carry frontmatter (see
[Frontmatter contract](/reference/frontmatter.md)).

# Step 2: Preview pending migrations

`upgrade --check` prints the migrations that would run against the
bundle, without writing anything.

```bash
scripts/okf-loom upgrade --check path/to/bundle
```

Read the preview before applying.
Each migration is an idempotent transformer that reuses the same
`parse_document` → modify → `serialize_document` pipeline as the
authoring verbs, so frontmatter key order and unknown keys are preserved.

# Step 3: Apply the migrations

`upgrade --apply` runs every pending migration in order.

```bash
scripts/okf-loom upgrade --apply path/to/bundle
```

Re-running it is a no-op: migrations are idempotent and skip work they
have already done.

# Step 4: Target a specific spec version

Pass `--to-spec` to migrate toward a specific spec version rather than
the latest okf-loom knows.

```bash
scripts/okf-loom upgrade --check --to-spec "NEXT_SPEC" path/to/bundle
scripts/okf-loom upgrade --apply  --to-spec "NEXT_SPEC" path/to/bundle
```

Quote the version string so the shell does not interpret it as a flag.

# Step 5: Re-validate after the migration

Run the validator to confirm the bundle still conforms after the
migration.

```bash
scripts/okf-loom validate path/to/bundle --strict --profile producer
```

Commit the migration as one change so the diff reads as a clean version
bump.
If anything looks wrong, `git revert` brings the bundle back to its
pre-migration state; the migration itself never destroys hand-curated
content.

See [Validate a bundle in CI](/how-to/validate_in_ci.md) for wiring that
re-validation into CI.

# Step 6: Know what v0.1 migrations exist

Today, **no migrations are defined for spec v0.1** — it is the baseline.

`upgrade --check` on a v0.1 bundle therefore reports nothing to do.
The command and flags above are forward-looking: when a future spec
version ships migrations, the same workflow applies them.

This is by design.
okf-loom features such as typed relations, entities, the live studio, and
archive tracks are optional capability-gated or config-gated additions; the
wire format remains SPEC v0.1, so a v0.1 bundle needs no migration to use
them.

See [Capability registry](/reference/capabilities.md) for how optional
features activate without a spec bump.

# End state

You now have a workflow that:

- Declares the bundle's spec version in the root index.
- Previews migrations before applying them.
- Applies them idempotently and re-validates after.

# See also

* [Validate a bundle in CI](/how-to/validate_in_ci.md) — gate migrations behind strict validation.
* [Capability registry](/reference/capabilities.md) — how optional features activate without a spec bump.
* [CLI command reference](/reference/cli.md) — every flag on `upgrade`.
* [Frontmatter contract](/reference/frontmatter.md) — required vs recommended keys, including `okf_version`.
* [Dependency-light philosophy](/explanation/zero_dependencies.md) — why the wire format and runtime setup stay minimal.

Return to [How-to guides](/how-to/index.md).
