# Graph health

Graph health is advisory. A bundle can be valid OKF and still be hard to use
as a graph; do not turn these checks into hard conformance unless the user asks
for a producer policy.

## Quick loop

```bash
scripts/okf-loom validate <bundle>
scripts/okf-loom discover <bundle>
scripts/okf-loom graph-quality <bundle>
scripts/okf-loom serve <bundle> --no-open
```

Use `--format json` when another agent or harness will consume the report.

## What good looks like

- `type` names the kind of thing: `Table`, `Service`, `Runbook`, `Decision`,
  `Redmine Issue`, `Historical Wiki Revision`. Do not use it for broad source
  buckets such as `Wiki Page` when a more precise type is available.
- `title` names the instance. Duplicate titles should either be merged or made
  unambiguous.
- Links and `relations:` express real dependency, membership, reference, or
  provenance edges. For hierarchy, prefer relation types such as `part_of`,
  `contains`, or `belongs_to` when the relationship is semantically true.
- Imported or mixed-source bundles should carry source metadata such as
  `source_system` and, when helpful, `graph_cluster`. These are optional custom
  keys; consumers that do not understand them must still ignore them safely.
- Add `aliases`, `entities`, and `provenance` when they carry real information.
  Do not invent filler values just to satisfy a report.
- Prefer absolute bundle-relative Markdown links in generated or newly authored
  prose, for example `[Orders](/tables/orders.md)`. Relative links remain valid.

## Reading `graph-quality`

`graph-quality` reports common usability smells:

- generic type overuse;
- duplicate or near-duplicate titles;
- low optional metadata coverage;
- no explicit hierarchy signal in larger bundles;
- disconnected components and orphan concepts.

Treat findings as prompts for review. A deliberately separated bundle may have
multiple components; a small scratch bundle may have no aliases or provenance.

## Discovery noise

`discover` suppresses low-confidence unlinked-mention suggestions by default.
Use:

```bash
scripts/okf-loom discover <bundle> --include-low-confidence
```

when doing a broad import audit. Do not blindly apply mention suggestions whose
matched phrase is a common label such as `Users`, `Clients`, `Wiki`, or `Index`,
a common first name such as `David`, or a project/status label that appears
across many imported pages. High-frequency labels usually need source-aware
curation, not automatic linking.
