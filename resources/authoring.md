# OKF authoring

One file should answer one question well: **one file = one concept = one graph
identity**. Split files that describe unrelated assets; merge duplicate or stub
concepts.

## New concept default

When you create a concept, dress it fully by default — every key below
that carries real information should be present (only `type` is hard-
required, but sparse frontmatter wastes the graph/search/entity
features the user is here for):

```markdown
---
type: Table                      # kind of thing (Table, Service, Playbook, Decision…)
title: Customer Orders           # instance name
description: One row per completed order, denormalised for analytics.
tags: [orders, analytics]
timestamp: "2026-07-02T00:00:00Z"   # quote it; validate warns when missing
aliases: [orders fact table]     # renders as the page subtitle
entities:                        # things this concept is about
  - label: Order
    kind: business_entity
relations:                       # typed edges (colour-coded on the graph)
  - type: depends_on
    target: /tables/customers.md
provenance:
  - source: https://example.com/upstream-doc
    note: Where this knowledge came from.
citations:
  - id: src1
    text: "External source. https://example.com"
---

# Overview
…body: headings, tables, fenced code, mermaid/math blocks all render.
```

Placement: one directory per type family (`tables/`, `services/`,
`playbooks/`, …); the file name becomes the concept id
(`tables/orders.md` → `tables/orders`). Link targets use the absolute
bundle form (`/tables/customers.md`).

[`docs-bundle/demo/showcase.md`](../docs-bundle/demo/showcase.md) is the
worked example — every governed key plus every renderer on one page;
open it in the studio to see what each key buys.

**After every batch of writes:**

```bash
scripts/okf-loom validate <bundle>            # fix findings; --strict in CI
scripts/okf-loom discover <bundle>            # missing links/indexes/descriptions
scripts/okf-loom index <bundle>               # regenerate marker-safe index blocks
```

`index` only rewrites between `okf:generated:index` markers — hand-
authored index prose without markers gets REPLACED, so check `git diff`
after running it against a curated index.

## Good concepts

- Use `type` for the kind of thing (`Table`, `API Endpoint`, `Playbook`).
- Use `title` for the instance name (`Customer Orders`).
- Keep `description` as a single useful sentence.
- Put structured detail in headings, tables, lists, and fenced code blocks.
- Cross-link every dependency, join, implementation, citation, and related
  concept.

## Body conventions

Use conventional headings when they fit:

- `# Schema` for fields/columns.
- `# Examples` for queries, commands, payloads, or concrete usage.
- `# Citations` for external sources.

Other headings are welcome: `# Overview`, `# Joins`, `# Runbook`,
`# Limitations`, `# Decisions`, and so on.

## Images and media

Store screenshots/diagrams inside the bundle (an `assets/` dir next to the
concepts that use them) and reference them like any markdown image:

```markdown
![Login flow](/research/xero/assets/login-flow.png)
```

The studio serves bundle-local media directly (images, `.mp4`/`.webm`,
`.pdf`), and static builds copy the same files, so both render what editors
and GitHub render. Three deliberate limits: files in gitignored/pruned
directories won't serve (same §5 visibility as concepts — `bundle.include`
revives), remote hot-linked images are CSP-blocked, and `data:` URIs are
sanitized away — keep media as bundle-local files. `validate` flags an
image whose target file is missing (`asset.missing`) or outside the bundle
root (`asset.out_of_bundle`).

## Index and log files

- `index.md` lists a directory's contents. Only the root `index.md` may have
  frontmatter.
- `log.md` is optional update history, newest first, date-grouped.
- Generated index regions must use `<!-- okf:generated:index begin/end -->`
  markers unless the root index opts into full generation.

## Authoring verbs

```bash
scripts/okf-loom write-concept --bundle path/to/bundle \
  --id tables/orders --type Table --title Orders \
  --description "One row per completed order."

scripts/okf-loom set-frontmatter --bundle path/to/bundle \
  --id tables/orders --key owner --value team-checkout

scripts/okf-loom link-add --bundle path/to/bundle \
  --source tables/orders --target tables/customers --relation depends_on

scripts/okf-loom entity-add --bundle path/to/bundle \
  --id tables/orders --label Order --kind business_entity
```

All mutators parse, modify, serialize, and atomically rename. They preserve
unknown frontmatter keys and are idempotent where repeated application should
be safe.
