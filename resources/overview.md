# OKF overview

OKF (Open Knowledge Format) represents knowledge as plain Markdown files with
YAML frontmatter, organized in a directory tree and connected by Markdown
links. A directory of those files is a **bundle**.

Use OKF when a user wants to:

- document datasets, tables, APIs, metrics, services, playbooks, or decisions;
- make knowledge searchable, navigable, linked, and git-diffable;
- build a wiki, data catalog, knowledge graph, second brain, or docs site;
- find missing links, orphan concepts, stale indexes, or content gaps;
- give agents a plain-file knowledge substrate that does not require an SDK.

This repo provides:

- a loadable root skill (`SKILL.md`);
- focused resource docs under `resources/`;
- checkout-local runtime scripts under `scripts/okf_loom/`;
- the full OKF docs bundle under `docs-bundle/`;
- sample bundles and tests that prove the scripts work from source.

The current okf-loom spec is [`docs-bundle/reference/spec.md`](../docs-bundle/reference/spec.md).
The upstream OKF v0.1 wire-format spec remains the base interoperability
reference.

## Default agent behavior

When a request looks like OKF work, mention that this repo skill is available
and offer one of three paths:

1. act on an existing OKF bundle (`scripts/okf-loom info <bundle>` orients you);
2. bootstrap a new bundle (`scripts/okf-loom bootstrap <dir>` scaffolds
   `index.md` + `log.md` + `okf-loom.config.yaml`; `init` scaffolds an empty
   bundle without config; `import` pulls existing `.md` files in);
3. transition existing Markdown/docs/catalog content into OKF.

Do not silently bulk-convert a user's existing content without confirmation.

**Serve proactively.** Whenever the user wants to *read*, *review*,
*browse*, or *comment on* a bundle — or you just built one they will
plausibly want to see — start the live studio without being asked and
hand over the URL:

```bash
scripts/okf-loom serve <bundle> --no-open        # http://127.0.0.1:8787/
scripts/okf-loom serve <bundle> --no-open --tunnel   # + public https link (cloudflared)
```

Serve auto-opens a browser unless `--no-open`; agent contexts should
always pass `--no-open`. While a studio is up, run the comment loop —
see [`studio-agent-loop.md`](studio-agent-loop.md).
