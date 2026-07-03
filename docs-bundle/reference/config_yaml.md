---
type: Reference
title: okf-loom.config.yaml reference
description: Every `okf-loom.config.yaml` key — `viewer.*`, `search.*`, `validate.*`, `studio.*` — with type, default, and behaviour. Path-bearing fields are bundle-relative; unknown keys are preserved in `OkfConfig.raw`.
resource: /reference/config_yaml.md
tags: [config, reference]
timestamp: "2026-06-29T00:00:00Z"
---

# `okf-loom.config.yaml` reference

A bundle MAY ship an `okf-loom.config.yaml` at its root (current spec §5)
to set viewer / search / validate / studio defaults. **Absence ⇒ all
defaults** — the file is purely additive; nothing breaks without it.
[`scripts/okf-loom init`](cli.md#init) writes a commented-defaults template
automatically; [`scripts/okf-loom bootstrap`](cli.md#bootstrap) does not.
See [index.md](/reference/index.md) for the rest of the reference quadrant.

The canonical filename is `okf-loom.config.yaml` (single constant in
`config.py`; flip it to relocate).

# Top-level shape

```yaml
viewer:   { … }   # display + override settings
search:   { … }   # search-mode default
validate: { … }   # validation profile + broken-link policy
studio:   { … }   # live collaborative studio
```

The four top-level keys are the only recognised top-level keys.
Unknown top-level keys are preserved verbatim in `OkfConfig.raw`
for forward compatibility.

# Path-bearing fields (SPEC §4.5 containment)

The following fields MUST be bundle-relative. Absolute paths and
`..`-escaping paths are rejected fail-closed at load time:

- `viewer.override_dir`
- `viewer.extension_css`
- `viewer.extension_js`
- `studio.session_dir`

The check reuses the SPEC §4.5 guard (`log._resolve_within_bundle`):
it resolves the candidate against the bundle root and confirms
containment via `relative_to`. Empty values are also rejected.

# `viewer.*`

| Key | Type | Default | Description |
|---|---|---|---|
| `title` | string \| null | `null` | Viewer page `<title>`. `null` ⇒ no override; the viewer falls back to the bundle display name. |
| `override_dir` | string (bundle-relative path) | `.okf-loom/viewer` | Directory holding template / static / palette overrides. |
| `extension_css` | string (bundle-relative path) | `.okf-loom/viewer/extension.css` | Optional CSS injected into every page. |
| `extension_js` | string (bundle-relative path) | `.okf-loom/viewer/extension.js` | Optional JS injected into every page (subject to the active-code gate). |
| `allow_active_code` | bool | `false` | Bundle-side gate for viewer overrides + plugins. The operator must ALSO consent via `--allow-active-code` / `OKF_LOOM_ALLOW_ACTIVE_CODE` (two-layer gate). |

## Boolean coercion

`allow_active_code` (and every other bool field) is coerced
fail-closed. Accepted tokens (case-insensitive, whitespace-trimmed):

| True | False |
|---|---|
| `true`, `yes`, `on`, `1` | `false`, `no`, `off`, `0`, `""` |

Any other value (e.g. `"maybe"`, an int, a list) raises
`OkfConfigError`. This is deliberately strict: a quoted `"false"`
must NOT silently enable active code.

# `search.*`

| Key | Type | Default | Description |
|---|---|---|---|
| `default_mode` | enum | `lexical` | Mode used when no `--mode` is passed. One of `lexical`, `semantic`, `hybrid`, `tag`, `entity`, `relation`. |

Unknown values are rejected fail-closed (no silent fallback to a
different backend). See [search_modes.md](search_modes.md).

# `validate.*`

| Key | Type | Default | Description |
|---|---|---|---|
| `default_profile` | enum | `spec` | Profile used when no `--profile` is passed. One of `spec`, `producer`, `loose`. |
| `fail_on_broken_links` | bool | `false` | Promote `link.broken` findings to ERROR. |

| Profile | Behaviour |
|---|---|
| `spec` | Default. Only `type` is required; everything else is WARNING. |
| `producer` | `spec` + `concept.missing_recommended_keys` promoted to ERROR. |
| `loose` | `spec` except `concept.missing_type` downgraded to WARNING. |

Unknown `default_profile` values are rejected fail-closed.
See [cli.md § validate](cli.md#validate).

# `studio.*`

Every default makes the studio fully functional with a plain
`scripts/okf-loom serve`: live updates, commenting/directing, agent enrichment.
No unlock flags required.

| Key | Type | Default | Description |
|---|---|---|---|
| `edit` | bool | `true` | Interactive studio (commenting/directing + live). `--no-edit` flips to a read-only kiosk. |
| `live` | bool | `true` | SSE live updates on. |
| `enrich_offer` | bool | `true` | Agent offers to watch the bundle on bring-up. |
| `auto_enrich` | bool | `true` | While watching, the agent applies edits directly. |
| `constraints` | mapping | `{}` | Empty = fully free agent. A user opts in restraints here (§12.3). |
| `debounce_ms` | int | `600` | Coalesce watcher-triggered work by this many ms. |
| `session_dir` | string (bundle-relative path) | `.okf-loom/session` | Where session state (events, directives, history) lives. |
| `log_edits` | bool | `true` | Append a SPEC §7 `log.md` entry per agent write / resolved comment. |
| `max_sse_clients` | int | `32` | Cap on concurrent SSE streams. Returns 503 when full. |
| `allowed_hosts` | list of strings | `[127.0.0.1, localhost]` | Origin/Host allow-list for the cross-origin guard. Never empty (defaults to loopback on unset). |
| `theme` | enum | `auto` | `auto` / `light` / `dark`. |
| `events_max_bytes` | int | `8388608` (8 MiB) | `events.jsonl` rotation cap (active file size). |
| `events_keep` | int | `7` | Number of rotated `events.jsonl` files to keep. |

## `allowed_hosts`

Both `Origin` (when present) and `Host` headers are checked against
this list (defense in depth against DNS-rebinding). The list is
never empty: a missing/empty value defaults to
`("127.0.0.1", "localhost")`. A non-loopback bind requires
`scripts/okf-loom serve --public --public-ack` (or interactive y/N ack).

## `constraints`

An empty mapping means a fully free agent (the default; the agent
edits the OKF files freely through the mutators). A user opts in
restraints for **their own** agent here — e.g. `propose_only: true`
or `forbidden_paths: [...]`. Constraints are never shipped; they
are per-user, per-bundle policy. The mapping is preserved verbatim.

## `session_dir`

Must be bundle-relative. An absolute path raises `OkfConfigError`;
a `..`-escaping path is rejected by the §4.5 guard. The directory
holds `events.jsonl`, `directives.jsonl`, `history/`, `.token`.

# Unknown keys

Unknown keys (top-level AND section-internal) are preserved verbatim
in `OkfConfig.raw`. The same round-trip rule SPEC §2 applies to
frontmatter applies here: a newer producer's config does not lose
information when consumed by an older toolkit.

```python
from okf_loom.config import OkfConfig

cfg = OkfConfig.load("path/to/bundle")
cfg.raw                  # dict of unknown top-level + section-internal keys
cfg.raw.get("acme_xxx")  # forward-compat read of an unknown key
```

# Loading

| Situation | Behaviour |
|---|---|
| File absent | All defaults (`OkfConfig()`). |
| File empty / comment-only | All defaults (treated as empty mapping). |
| File unparseable | `OkfConfigError` (subclass of `ValueError`). |
| Top level not a mapping | `OkfConfigError`. |
| Path field escapes bundle root | `OkfConfigError`. |
| Unknown enum value (`search.default_mode`, `validate.default_profile`, `studio.theme`) | `OkfConfigError`. |
| Alias/merge-key bomb | `OkfConfigError` (DoS guard via `_NodeLimitedSafeLoader`). |

The loader uses the same node-counting YAML loader as frontmatter
parsing, so the same DoS controls cover both surfaces.

# Library

```python
from okf_loom.config import OkfConfig, OkfConfigError

try:
    cfg = OkfConfig.load("path/to/bundle")
except OkfConfigError as e:
    ...  # unparseable / bad path / unknown enum

cfg.viewer.title                # str | None
cfg.viewer.allow_active_code    # bool
cfg.search.default_mode         # "lexical"
cfg.validate.default_profile    # "spec"
cfg.validate.fail_on_broken_links  # False
cfg.studio.edit                 # True
cfg.studio.allowed_hosts        # ("127.0.0.1", "localhost")
cfg.studio.session_path         # ".okf-loom/session" (normalized)
cfg.raw                         # {"unknown_top": ..., "viewer": {"unknown_sub": ...}}
```

`OkfConfig` and its section dataclasses are **frozen**; construct a
new one to change a value.

# Relationship to other config surfaces

| Surface | Scope | Format |
|---|---|---|
| `okf-loom.config.yaml` | Bundle defaults (this doc) | YAML at bundle root. |
| Bundle-root `index.md` frontmatter | SPEC §6 / §11 declarations (`okf_version`, `okf_extensions`, `generated`) | Frontmatter. |
| Concept frontmatter | Per-concept metadata | SPEC §4.1 (see [frontmatter.md](frontmatter.md)). |
| `<bundle>/.okf-loom/viewer/config.json` | Viewer-only display overrides (name, default_layout, theme) | JSON. |

`okf-loom.config.yaml` is the authoritative bundle-level config; the
viewer's `config.json` is a narrower display-only override.

# Authoring tools

| Goal | Tool |
|---|---|
| Scaffold a new bundle with a commented-defaults config | [`scripts/okf-loom init --bundle <path>`](cli.md#init). |
| Scaffold an empty bundle without a config | [`scripts/okf-loom bootstrap <dest>`](cli.md#bootstrap). |
| Validate the config | [`scripts/okf-loom validate <bundle>`](cli.md#validate) (the loader runs at bundle load; an unparseable config raises before any check). |
| Inspect resolved config | `OkfConfig.load(...)` in Python. |

# See also

- [index.md](/reference/index.md) — reference quadrant index.
- [frontmatter.md](frontmatter.md) — concept-level frontmatter (different contract).
- [cli.md § init](cli.md#init) / [cli.md § bootstrap](cli.md#bootstrap) — scaffolding commands.
- [cli.md § validate](cli.md#validate) — profiles and `--fail-on-broken-links`.
- [search_modes.md](search_modes.md) — `search.default_mode` values.
- [http_routes.md](http_routes.md) — `studio.allowed_hosts`, `studio.max_sse_clients`, `studio.session_dir` in route behaviour.
- [comment_lifecycle.md](comment_lifecycle.md) — `studio.events_max_bytes`, `studio.events_keep`, staleness TTLs.
- [capabilities.md](capabilities.md) — `viewer.allow_active_code` gates viewer plugin discovery.
- [/explanation/architecture.md](/explanation/architecture.md) — module map.
- [`/reference/spec.md`](/reference/spec.md) — current config and studio contract.
- `okf-loom/scripts/okf_loom/config.py` — authoritative source.
