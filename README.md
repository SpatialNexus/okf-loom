# okf-loom Skill

okf-loom v1.0 is an Apache-2.0 open-source OKF toolkit and loadable agent
skill.

This repository is a loadable, repo-local skill for working with
[Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
bundles. It includes:

- `SKILL.md` — the primary skill entrypoint for agents;
- `resources/` — small Markdown guides referenced by the skill;
- `scripts/okf_loom/` — checkout-local runtime scripts;
- `docs-bundle/` — the full OKF documentation bundle;
- `samples/` and `tests/` — examples and executable proofs.

The distribution unit is this git repo layout. Do not install or publish it as
a Python package to use it; run the scripts directly from the checkout.

## If you're a human: point your agent here

That's the whole setup. Clone the repo and tell your agent to work in it —
[`CLAUDE.md`](CLAUDE.md) (Claude Code), [`AGENTS.md`](AGENTS.md) (opencode &
friends), and [`SKILL.md`](SKILL.md) (skill loaders) all route the agent to
the same orientation, including the standing **default behaviours**: author
docs as OKF bundles, validate after writing, start the live studio
proactively when you want to read or comment, and work your comments via the
studio loop. Requirements: Python 3.11+; nothing to install (PyYAML is used
when present, with a built-in fallback otherwise); session state and its
auth token are auto-gitignored.

## Agent quickstart

1. Clone or open this repo.
2. Load [`SKILL.md`](SKILL.md) — start with its **Default behaviours**.
3. Read the resource file that matches the task.
4. Run commands with the checked-in `scripts/okf-loom` helper.

```bash
scripts/okf-loom --version
# okf-loom 1.0.0 (SPEC v0.1)
scripts/okf-loom validate docs-bundle --strict
```

From a parent workspace where the checkout is named `okf-loom/`:

```bash
okf-loom/scripts/okf-loom validate okf-loom/docs-bundle --strict
```

## What OKF does

OKF represents knowledge — metadata, context, schemas, relationships, and
curated insight — as plain Markdown files with YAML frontmatter, organized in a
directory tree and cross-linked into a graph. This skill gives agents and
humans scripts to validate, search, discover, update, render, and serve those
bundles.

## Common commands

```bash
# Validate and inspect.
scripts/okf-loom validate samples/demo_bundle --strict
scripts/okf-loom info samples/demo_bundle

# Search and discover.
scripts/okf-loom search docs-bundle "current spec" --mode hybrid
scripts/okf-loom discover samples/demo_bundle --out /tmp/okf-suggestions.json

# Serve the live studio (wiki + graph lenses + commenting), or build.
scripts/okf-loom serve samples/demo_bundle --no-open           # http://127.0.0.1:8787/
scripts/okf-loom serve samples/demo_bundle --no-open --tunnel  # + public https link
scripts/okf-loom build docs-bundle --target static --out /tmp/okf-docs-site
```

Security note: `serve` is loopback-only by default.
`--tunnel`, `--public`, or a non-loopback host makes the studio reachable by
others; anyone with the URL can read public GET surfaces, while mutating POST
routes require the per-session `X-OKF-Token` and Origin/Host allow-list checks.
Use `--no-edit` for read-only sharing, and see [SECURITY.md](SECURITY.md) plus
the [HTTP routes reference](docs-bundle/reference/http_routes.md) before
publishing a tunnel URL.

The served studio is the product's heart: a live wiki (dashboard index,
typed concept pages, full rendering incl. Mermaid/KaTeX/highlighting), a
graph view with six evidence-based lenses (Map / Themes / Flow / Bridges /
Recent / Focus — each answers one question and ranks its answers), and
select-to-comment collaboration that agents consume via
`scripts/okf-loom wait`. See the
[Rendering & Feature Showcase](docs-bundle/demo/showcase.md) for everything
on one page.

## Skill resources

| File | Purpose |
|---|---|
| [`resources/overview.md`](resources/overview.md) | OKF purpose and trigger list |
| [`resources/command-reference.md`](resources/command-reference.md) | Invocation and CLI flows |
| [`resources/format-basics.md`](resources/format-basics.md) | Bundles, concepts, frontmatter, links |
| [`resources/authoring.md`](resources/authoring.md) | Curation conventions and mutators |
| [`resources/validation.md`](resources/validation.md) | Validation profiles and fail-closed behavior |
| [`resources/advanced-operations.md`](resources/advanced-operations.md) | Search, discovery, build, capabilities |
| [`resources/studio-agent-loop.md`](resources/studio-agent-loop.md) | Live studio comment loop |
| [`resources/architecture-map.md`](resources/architecture-map.md) | Runtime/source map |
| [`resources/gotchas.md`](resources/gotchas.md) | Hard rules and traps |

The full docs live as an OKF bundle in [`docs-bundle/`](docs-bundle/). The
canonical current spec is [`docs-bundle/reference/spec.md`](docs-bundle/reference/spec.md).

## Repository layout

```text
okf-loom/
├── SKILL.md
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── resources/
├── scripts/
│   ├── okf-loom
│   ├── okf_loom/
│   ├── build_skill_archive.py
│   ├── capture_signal_controls.py
│   ├── capture_viewer_proof.py
│   └── lint-js.sh
├── docs-bundle/
├── docs/
├── samples/
└── tests/
```

`pyproject.toml` is retained only for pytest/coverage configuration. It is not
package metadata.

## Browser proof

Browser proof is optional and installed explicitly into your environment:

```bash
python -m pip install pytest playwright
python -m playwright install chromium
PYTHONPATH=scripts pytest tests/test_viewer_browser.py
PYTHONPATH=scripts python scripts/capture_viewer_proof.py
```

Without Playwright or a browser, browser-marked tests skip cleanly.

## License

okf-loom is licensed under the Apache License, Version 2.0.
Commercial and non-commercial use are both allowed under that license.

okf-loom is compatible with and complementary to the upstream OKF
specification, which is also Apache-2.0 upstream.
This implementation is independent; it is not affiliated with or endorsed by
Google.
