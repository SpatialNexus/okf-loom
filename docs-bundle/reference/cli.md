---
type: Reference
title: CLI command reference
description: Every `scripts/okf-loom` subcommand — purpose, key flags, exit codes, and output formats — for the okf-loom v1.0 baseline.
resource: /reference/cli.md
tags: [cli, reference]
timestamp: "2026-06-29T00:00:00Z"
---

# CLI command reference

Run commands from this checkout as `scripts/okf-loom ...`.
From a parent workspace where this checkout is named `okf-loom`, use `okf-loom/scripts/okf-loom ...`.
Do not assume an installed console script.
Bundle and output-format arguments are command-specific; check each synopsis before generating commands.

okf-loom v1.0 implements upstream OKF SPEC `v0.1` as its wire-format baseline.
`scripts/okf-loom --version` prints `okf-loom 1.0.0 (SPEC v0.1)`.
See [index.md](/reference/index.md) for the rest of the reference quadrant.

# Command summary

| Command | Purpose |
|---|---|
| [`info`](#info) | Bundle summary: concept/type/tag/link counts, version, extensions. |
| [`validate`](#validate) | SPEC §9 conformance + soft warnings; profiles, `--strict`, `--fail-on-broken-links`. |
| [`graph`](#graph) | Print the link graph (text / JSON / DOT). |
| [`search`](#search) | Six modes behind one `--mode` flag. |
| [`discover`](#discover) | Find missing links/indexes/descriptions/relations/orphans. |
| [`plan`](#plan) | Build a reviewable, executable action plan. |
| [`capabilities`](#capabilities) | List or resolve the capability registry. |
| [`serve`](#serve) | Run the live collaborative studio (HTTP server). |
| [`watch`](#watch) | Headless change feed; no HTTP server. |
| [`wait`](#wait) | Foreground block-once for the next comment/change. |
| [`token`](#token) | Print the per-session CSRF token. |
| [`comment-claim`](#comment-claim) | Mark a comment `claimed` by the agent, with optional `--summary`. |
| [`comment-resolve`](#comment-resolve) | Mark a comment `resolved` with reply/activity links and optional `--summary`. |
| [`comment-list`](#comment-list) | List comments/directives, optionally filtered. |
| [`presence`](#presence) | Set agent presence (mirror of `POST /__presence`). |
| [`render`](#render) | Render a self-contained `viz.html`. |
| [`build`](#build) | Build a multi-file static site (spa / static / single-file). |
| [`index`](#index) | Regenerate SPEC §6 `index.md` files (marker-safe). |
| [`log`](#log) | Append to SPEC §7 `log.md` (append-only). |
| [`update`](#update) | Apply an update plan or action envelope (idempotent). |
| [`upgrade`](#upgrade) | Check or apply spec-version migrations. |
| [`bootstrap`](#bootstrap) | Scaffold an empty bundle (no config file). |
| [`import`](#import) | Import existing `.md` files into a bundle. |
| [`init`](#init) | Scaffold a bundle with `index.md`, `log.md`, `okf-loom.config.yaml`. |
| [`write-concept`](#write-concept) | Create or update a single concept file. |
| [`set-frontmatter`](#set-frontmatter) | Set one frontmatter key on a concept. |
| [`link-add`](#link-add) | Add a markdown link (and optionally a typed relation). |
| [`entity-add`](#entity-add) | Add an entity to a concept's `entities:` list. |
| [`repair`](#repair) | Apply mechanical fixes (index regen + relation mirroring). |

# Common conventions

| Command shape | Commands |
|---|---|
| Positional `<bundle>` + `--format {text,json,md,dot}` | `info`, `validate`, `graph`, `search`, `discover`, `repair` |
| Positional `<bundle>` + `--format {text,json}` | `plan`, `comment-claim`, `comment-resolve`, `comment-list`, `presence`, `index`, `update` |
| Optional/no positional bundle + `--format {text,json}` | `capabilities` uses optional `--bundle`; `init` requires `--bundle` |
| Positional or bundle option, no `--format` | `serve`, `watch`, `wait`, `token`, `render`, `build`, `log`, `upgrade` (`upgrade` accepts optional positional `<bundle>` or `--bundle`) |
| Non-bundle source/destination, no `--format` | `bootstrap <dest>`, `import <src> <dest>` |
| Authoring verbs | `write-concept`, `set-frontmatter`, `link-add`, `entity-add` use `--bundle` and support `--format {text,json}` |

| Convention | Detail |
|---|---|
| `--group-id` / `--actor` | Mutators accept these for one-click group undo and change-list attribution. Active only when a live studio session exists; otherwise the non-studio atomic write path is used. |
| `--dry-run` | Preview the change without writing (where applicable). |
| Atomic writes | Every file mutation goes through tmp + rename (AGENTS.md hard rule #8). |
| Studio detection | Mutators detect the configured studio session directory (`.okf-loom/session/` by default) and route through `Studio.save_concept` (attribution + undo + events + SSE). Without a session they take the non-studio atomic write path. |
| Exit `0` | Success (or `scripts/okf-loom wait` returned work). |
| Exit `1` | Conformance failure (`validate`), or `scripts/okf-loom wait --timeout` expired with no work. |
| Exit `2` | Strict-mode failure (`validate --strict`); `scripts/okf-loom init` on a non-empty destination; `scripts/okf-loom serve --public` on a non-TTY without `--public-ack`. |

# info

```bash
scripts/okf-loom info <bundle> [--format {text,json,md,dot}]
```

Bundle summary: concept/type/tag/link counts, declared `okf_version`,
declared `okf_extensions`, and any load warnings.
First command to run against an unfamiliar bundle.

See [/tutorials/first_bundle.md](/tutorials/first_bundle.md).

# validate

```bash
scripts/okf-loom validate <bundle> [--strict] [--profile {spec,producer,loose}]
            [--fail-on-broken-links] [--checks CHECKS]
            [--format {text,json,md,dot}]
```

| Flag | Effect |
|---|---|
| `--strict` | Treat warnings as errors (exit `2` instead of `0`). |
| `--profile spec` | Default; only `type` is hard-required (SPEC §9). |
| `--profile producer` | Promote `concept.missing_recommended_keys` to ERROR. |
| `--profile loose` | Downgrade `concept.missing_type` to WARNING (migration aid). |
| `--fail-on-broken-links` | Promote `link.broken` to ERROR; composes with any profile. |
| `--checks a,b` | Run a subset. Category names (`link_integrity`, `concept_required_keys`, …) or dotted codes (`link.broken`, `concept.missing_type`). |

Exit `0` ok, `1` conformance fail, `2` strict fail.
See [/how-to/validate_in_ci.md](/how-to/validate_in_ci.md).

# graph

```bash
scripts/okf-loom graph <bundle> [--format {text,json,md,dot}]
```

Print the link graph. Wikilinks (`[[…]]`) are emitted as edges with
`form="wikilink"`. `dot` output renders with Graphviz; `json` is the
machine-readable shape consumed by the viewer.

# search

```bash
scripts/okf-loom search <bundle> [query] [--mode {lexical,semantic,hybrid,tag,entity,relation}]
            [--type TYPE] [--tag TAG] [--limit N]
            [--relation RELATION] [--source SOURCE] [--target TARGET]
            [--format {text,json,md,dot}]
```

`query` is optional in `relation` mode (edge filters suffice).
Full mode-by-mode detail lives in [search_modes.md](/reference/search_modes.md).

# discover

```bash
scripts/okf-loom discover <bundle> [--rules RULES] [--out OUT]
            [--scope SCOPE] [--neighbors] [--format {text,json,md,dot}]
```

Emit a structured report of gaps the managing agent may fix.
Suggestions carry a rule, severity, message, target concept, and an
`action` verb phrase.

| Flag | Effect |
|---|---|
| `--rules a,b` | Subset of rules: `unlinked_mentions`, `missing_indexes`, `missing_descriptions`, `broken_links`, `missing_relations_hint`, `orphan_concepts`. |
| `--out plan.json` | Write the JSON report to this path. |
| `--scope ID,ID` | Restrict rules to named concept ids (current spec §7). |
| `--neighbors` | Expand `--scope` to 1-hop graph neighbours (in + out edges). |

The agent applies fixes directly via the mutators; the reviewable-plan
workflow (`discover` → `plan` → `update`) is still available.
See [/how-to/discover_and_fix_gaps.md](/how-to/discover_and_fix_gaps.md).

# plan

```bash
scripts/okf-loom plan <bundle> [--rules RULES] [--out OUT]
            [--scope SCOPE] [--neighbors] [--portable] [--format {text,json}]
```

Build a reviewable, executable action plan from discovery + index
staleness + typed-relation mirroring.

| Flag | Effect |
|---|---|
| `--portable` | Emit bundle-relative argv (`--bundle .`) so the plan is portable across machines. Replay from the bundle directory. |
| `--scope ID,ID` / `--neighbors` | Scope the plan (fast per-change enrichment). |

Mechanical actions carry a runnable `argv`; agent-decision actions
carry an `argv_template` with `<PLACEHOLDER>` slots, a `confidence`
score, and an `agent_instruction`.

# capabilities

```bash
scripts/okf-loom capabilities [--bundle BUNDLE] [--format {text,json}]
```

Without `--bundle`, list every capability okf-loom knows.
With `--bundle`, resolve which are active for that bundle (declared
under `okf_extensions:` plus auto-activated by observed keys).
See [capabilities.md](/reference/capabilities.md).

# serve

```bash
scripts/okf-loom serve <bundle> [--host HOST] [--port PORT] [--no-watch] [--no-open]
            [--allow-active-code] [--no-edit] [--tunnel] [--public]
            [--public-ack] [--no-watch-ui]
```

Run the live collaborative studio. Default bind is `127.0.0.1:8787`.

| Flag | Effect |
|---|---|
| `--host HOST` | Bind host. A non-loopback host implies `--public` semantics. |
| `--port PORT` | Bind port (default `8787`). |
| `--no-watch` | Disable the file watcher (no live reload on disk change). |
| `--no-open` | Do not open a browser window on start. |
| `--allow-active-code` | Operator consent enabling viewer overrides + plugins for bundles that declare `viewer.allow_active_code: true`. Default defers to `OKF_LOOM_ALLOW_ACTIVE_CODE`. |
| `--no-edit` | Read-only kiosk: live reads stay on; all POST endpoints are off (current spec §9 and §14). |
| `--tunnel` | Also start a Cloudflare quick tunnel (requires `cloudflared` on `PATH`) and print a public `https://…trycloudflare.com` URL. The tunnel host is added to `allowed_hosts` at runtime so comments/edits work through the link; the server itself stays on loopback. Anyone with the link can read the bundle. |
| `--public` | Bind `0.0.0.0`. Requires `--public-ack` or interactive y/N ack; on a non-TTY without ack, exit `2`. |
| `--public-ack` | Non-interactive acknowledgement of the trust-boundary change implied by `--public`. |
| `--no-watch-ui` | Disable SSE live push server-side (`/__events` returns 503). |

Writes `<bundle>/<studio.session_dir>/.token` (`.okf-loom/session/.token` by default, mode `0600`) on boot.
See [http_routes.md](/reference/http_routes.md),
[comment_lifecycle.md](/reference/comment_lifecycle.md),
[/tutorials/live_studio_basics.md](/tutorials/live_studio_basics.md),
and [/explanation/live_studio_design.md](/explanation/live_studio_design.md).

# watch

```bash
scripts/okf-loom watch <bundle> [--emit {jsonl,text}] [--since SINCE]
            [--auto-repair] [--debounce-ms DEBOUNCE_MS]
```

Headless change feed for the agent loop. Prints one event per line;
no HTTP server. Reuses the same `events.jsonl` append feed `serve` uses.

| Flag | Effect |
|---|---|
| `--emit jsonl` | Default; the §7.2 event schema, one JSON object per line. |
| `--emit text` | Human-readable one-line summaries. |
| `--since <id>` | Replay from `events.jsonl` after this id, then tail live (reconnect-safe). |
| `--auto-repair` | Run mechanical `scripts/okf-loom repair` (index regen + relation mirroring) on change, debounced. |
| `--debounce-ms N` | Coalesce auto-repair runs by this many ms (default `600`). |

# wait

```bash
scripts/okf-loom wait <bundle> [--for {comment,change} ...] [--since SINCE]
            [--timeout TIMEOUT] [--interval INTERVAL]
```

Foreground block-once primitive (current spec §12). Blocks until a new OPEN
comment and/or change event arrives, prints it as JSON, exits.
Run this in the agent's foreground; never background it.

| Flag | Effect |
|---|---|
| `--for comment` | Wait for a new OPEN user comment (default). |
| `--for change` | Wait for a new `changed`/`created`/`removed` event (proactive enrichment). |
| `--for comment change` | Whichever arrives first. |
| `--since <id>` | Skip the backlog; wait only for items whose id sorts after this. |
| `--timeout <s>` | Max seconds to wait; exit `1` on timeout with no work. Default: block indefinitely. |
| `--interval <s>` | Poll interval (default `0.5`). |

Without `--since`, the first call drains the oldest pre-existing open
comment; subsequent calls drain the rest, then settle into wait-for-new.

# token

```bash
scripts/okf-loom token <bundle>
```

Print the per-session CSRF token the studio wrote to the configured session
directory (`<bundle>/.okf-loom/session/.token` by default, mode `0600`). Use only when POSTing
to `/__apply` / `/__undo` / `/__presence` / `/__comment` over HTTP
directly; the CLI mutators attach the token automatically.
Exits non-zero with a clear message if no session exists.

# comment-claim

```bash
scripts/okf-loom comment-claim <bundle> <comment_id> [--actor ACTOR]
            [--summary SUMMARY] [--no-presence] [--format {text,json}]
```

Mark a comment `claimed` by the agent. Sets `claimed_by`; auto-flips
presence to `editing <concept>` unless `--no-presence` is given.

| Flag | Effect |
|---|---|
| `--actor ACTOR` | Who is claiming (default `agent`). |
| `--summary SUMMARY` | Short agent-authored blurb shown in the collapsed thread preview. |
| `--no-presence` | Skip the automatic presence flip to `editing`. |

Canonical loop: `scripts/okf-loom wait` → `scripts/okf-loom comment-claim` → mutators →
`scripts/okf-loom comment-resolve`.

# comment-resolve

```bash
scripts/okf-loom comment-resolve <bundle> <comment_id> [--reply REPLY] [--summary SUMMARY]
            [--activity ACTIVITY] [--actor ACTOR] [--format {text,json}]
```

Mark a comment `resolved` with an optional reply and activity links.

| Flag | Effect |
|---|---|
| `--reply REPLY` | Long-form resolution message shown in the change list. |
| `--summary SUMMARY` | Short agent-authored blurb shown in the collapsed preview (separate from `--reply`). |
| `--activity ID,ID` | Comma-separated change-list entry ids the resolution produced (drives one-click group undo). |
| `--actor ACTOR` | Who is resolving (default `agent`). |

# comment-list

```bash
scripts/okf-loom comment-list <bundle> [--state {open,claimed,resolved,dismissed,archived}]
            [--concept CONCEPT] [--format {text,json}]
```

List directives from the configured session directory (`<bundle>/.okf-loom/session/directives.jsonl` by default),
optionally filtered. Each row carries `archived: bool` (separate
track), `summary: str|null`, `ts` (immutable creation time), and
`updated_at` (bumped on every transition).
See [comment_lifecycle.md](/reference/comment_lifecycle.md) and
[/how-to/archive_threads.md](/how-to/archive_threads.md).

# presence

```bash
scripts/okf-loom presence <bundle> [--state STATE] [--focus FOCUS] [--actor ACTOR]
            [--format {text,json}]
```

CLI mirror of `POST /__presence`.

| Flag | Effect |
|---|---|
| `--state STATE` | One of `idle`, `watching`, `thinking`, `editing` (default `idle`). |
| `--focus FOCUS` | Concept id the agent is focused on. |
| `--actor ACTOR` | Who is setting presence (default `agent`). |

Stale presence is auto-recovered: a watcher sweep reverts to `idle`
after `studio.presence_ttl_seconds` (default `300`).

# render

```bash
scripts/okf-loom render <bundle> [--out OUT] [--name NAME] [--allow-active-code]
```

Render one self-contained `viz.html` (Cytoscape.js + stdlib markdown
renderer; embeds the bundle as JSON). Suitable for `file://`,
email, or attaching to a ticket.

# build

```bash
scripts/okf-loom build <bundle> [--target {spa,static,single-file}] [--out OUT]
            [--name NAME] [--allow-active-code]
```

| Target | Output |
|---|---|
| `spa` | Quartz-style default for published reading. |
| `static` | Server-rendered, JS-optional, printable, SEO/airgapped-friendly. |
| `single-file` | One portable HTML with everything embedded (same shape as `render`). |

`--allow-active-code` is the operator-consent gate for build-time
viewer overrides + plugins.
See [/how-to/build_static_site.md](/how-to/build_static_site.md).

# index

```bash
scripts/okf-loom index <bundle> [--dry-run] [--frozen] [--emit-json] [--format {text,json}]
```

Regenerate SPEC §6 `index.md` files (marker-safe).

| Flag | Effect |
|---|---|
| `--dry-run` | Return a plan: `would_write`, `would_skip_hand_authored`, `would_skip_unchanged`. |
| `--frozen` | CI mode: raise instead of writing to hand-authored files. |
| `--emit-json` | Write portable `content.json` + `graph.json` under `<bundle>/.okf-loom/index/`. |

Safety: hand-authored `index.md` (no `generated: true` marker and no
`<!-- okf:generated:index begin/end -->` markers) is never overwritten.
Generated indexes rewrite only the marked region.

# log

```bash
scripts/okf-loom log <bundle> --append "…" [--kind KIND] [--date DATE]
            [--log-path LOG_PATH] [--dry-run]
```

Append to SPEC §7 `log.md` (always append-only).

| Flag | Effect |
|---|---|
| `--append TEXT` | Entry text to append under today's date. |
| `--kind KIND` | Bold-tag prefix: `Update`, `Creation`, `Deprecation`, `Initialization`. |
| `--date DATE` | Override the date heading (YYYY-MM-DD; default today). |
| `--log-path PATH` | Path to `log.md` relative to the bundle. |

# update

```bash
scripts/okf-loom update <bundle> --plan PLAN [--dry-run] [--group-id GROUP_ID]
            [--actor ACTOR] [--format {text,json}]
```

Apply an update plan or action envelope (idempotent). Accepts both
`{"ops":[...]}` (the original plan shape) and `{"actions":[...]}`
(the envelope emitted by `plan`). Template actions with unfilled
`<...>` slots are skipped with reason `needs_agent_input`.

# upgrade

```bash
scripts/okf-loom upgrade [<bundle>] [--bundle BUNDLE_FLAG] [--check] [--apply] [--to-spec TO_SPEC]
```

Spec-version migration tooling. `--check` previews pending migrations;
`--apply` runs them. Migrations are idempotent transformers reusing
the same parse → modify → serialize pipeline. No migrations are
defined for SPEC `v0.1` (it is the baseline).

See [/how-to/migrate_spec_version.md](/how-to/migrate_spec_version.md).

# bootstrap

```bash
scripts/okf-loom bootstrap <dest> [--name NAME]
```

Scaffold an empty bundle at `<dest>`. Creates the directory and a
minimal root `index.md`. Does NOT write `okf-loom.config.yaml`
(use [`init`](#init) for that).

# import

```bash
scripts/okf-loom import <src> <dest> [--default-type DEFAULT_TYPE] [--overwrite]
```

Import existing `.md` files from `<src>` into a new bundle at `<dest>`,
injecting `type:` frontmatter where missing.

| Flag | Effect |
|---|---|
| `--default-type TYPE` | Default concept type for files without a type guess (default `Reference`). |
| `--overwrite` | Overwrite existing destination files (default: skip). |

# init

```bash
scripts/okf-loom init --bundle BUNDLE [--name NAME] [--format {text,json}]
```

Scaffold a new bundle at `<bundle>` (must not exist or be empty; exit
`2` otherwise). Writes `index.md`, `log.md`, AND a commented-defaults
`okf-loom.config.yaml`.

# write-concept

```bash
scripts/okf-loom write-concept --bundle BUNDLE --id ID --type TYPE
            [--title TITLE] [--description DESCRIPTION] [--resource RESOURCE]
            [--timestamp TIMESTAMP] [--tag TAG] [--body BODY] [--body-file BODY_FILE]
            [--force] [--format {text,json}] [--group-id GROUP_ID] [--actor ACTOR]
```

Create or update a single concept (current spec §7). `--id` is the concept
id (e.g. `tables/orders`); the file path is derived. `--type` is
required. Updating merges frontmatter (only the passed keys are
touched; unknown keys are preserved). The body is replaced only if
`--body`/`--body-file` is given AND the existing body is empty;
otherwise `--force` is required to overwrite prose.

Refuses reserved filenames (`index.md`, `log.md`) case-insensitively.
See [/how-to/author_with_verbs.md](/how-to/author_with_verbs.md) and
[frontmatter.md](/reference/frontmatter.md).

# set-frontmatter

```bash
scripts/okf-loom set-frontmatter --bundle BUNDLE --id ID --key KEY --value VALUE
            [--json-value] [--dry-run] [--format {text,json}]
            [--group-id GROUP_ID] [--actor ACTOR]
```

Set one frontmatter key on a concept. `--json-value` parses the value
as JSON (lists/objects). Thin wrapper over the `set_frontmatter`
update op.

# link-add

```bash
scripts/okf-loom link-add --bundle BUNDLE --source SOURCE --target TARGET
            [--label LABEL] [--section SECTION] [--relation RELATION]
            [--evidence EVIDENCE] [--allow-forward-reference] [--dry-run]
            [--format {text,json}] [--group-id GROUP_ID] [--actor ACTOR]
```

Append a markdown link in `--section` (or end of body). Always emits
the SPEC §5.1 absolute form (`/tables/customers.md`).

| Flag | Effect |
|---|---|
| `--relation TYPE` | Also append a typed relation to the source's `relations:` list (activates `okf.cap.typed_relations`). |
| `--evidence TEXT` | Becomes the relation `detail`. |
| `--allow-forward-reference` | Permit a target that does not yet exist (SPEC §3 forward reference). Default: fail (exit `1`) on a missing target. |

See [links.md](/reference/links.md).

# entity-add

```bash
scripts/okf-loom entity-add --bundle BUNDLE --id ID --label LABEL [--kind KIND]
            [--entity-id ENTITY_ID] [--alias ALIAS] [--dry-run]
            [--format {text,json}] [--group-id GROUP_ID] [--actor ACTOR]
```

Append an entity object to a concept's `entities:` frontmatter list
(activates `okf.cap.entities`). Idempotent on `(label, kind)`:
re-running will not duplicate. `--alias` is repeatable; aliases feed
entity/semantic search.

# repair

```bash
scripts/okf-loom repair <bundle> [--apply] [--indexes] [--mirror-relations] [--all]
            [--group-id GROUP_ID] [--actor ACTOR] [--format {text,json,md,dot}]
```

Mechanical fixes only (current spec §7). Dry-run by default; pass `--apply`
to write. `--all` is the default scope when no filter is given.
Relation mirroring runs **before** index regen so regenerated
indexes reflect the new links.

# Output formats

When supported, `--format` accepts `text` (default) and `json` (the
agent/harness integration path).
Only `info`, `validate`, `graph`, `search`, `discover`, and `repair`
also accept `md` and `dot`.
Commands without `--format` either emit their command-specific text/JSON
shape (`wait` prints one JSON work item; `watch` uses `--emit`) or write
files as their primary output.

# See also

- [index.md](/reference/index.md) — reference quadrant index.
- [frontmatter.md](/reference/frontmatter.md) — the frontmatter contract.
- [links.md](/reference/links.md) — link forms and graph edges.
- [capabilities.md](/reference/capabilities.md) — capability registry.
- [search_modes.md](/reference/search_modes.md) — search backends.
- [http_routes.md](/reference/http_routes.md) — HTTP server routes.
- [comment_lifecycle.md](/reference/comment_lifecycle.md) — comment state model.
- [config_yaml.md](/reference/config_yaml.md) — `okf-loom.config.yaml` keys.
- `scripts/okf-loom <command> --help` — authoritative per-command help.
- [`/reference/spec.md`](/reference/spec.md) — current build-from-docs specification.
