# Command reference

The runtime lives in `scripts/okf_loom/`. Run it from a checkout with the
checked-in `scripts/okf-loom` helper; do not assume an installed package or console script.

## Helper

From a parent workspace:

```bash
okf-loom/scripts/okf-loom validate okf-loom/docs-bundle --strict
```

From inside `okf-loom/`:

```bash
scripts/okf-loom validate docs-bundle --strict
```

## Common commands

```bash
scripts/okf-loom --help
scripts/okf-loom validate docs-bundle --strict
scripts/okf-loom info docs-bundle
scripts/okf-loom search docs-bundle "current spec" --mode lexical
scripts/okf-loom serve docs-bundle --no-open
scripts/okf-loom serve docs-bundle --no-open --tunnel   # + public https URL (needs cloudflared)
scripts/okf-loom build docs-bundle --target static --out /tmp/okf-docs-site
```

## Sharing a live studio

`serve --tunnel` starts a Cloudflare quick tunnel beside the loopback
server, prints the public `https://…trycloudflare.com` URL, and adds the
tunnel hostname to the studio's cross-origin allowlist at runtime, so
comments/edits work through the link. The server itself stays bound to
127.0.0.1; the tunnel dies with the process. Anyone with the link can READ
the bundle — say so when you hand the URL over. Requires `cloudflared` on
PATH; without it the command warns and serves local-only.

## Full surface

- `validate`, `info`, `graph`, `search`
- `discover`, `plan`, `repair`, `update`
- `write-concept`, `set-frontmatter`, `link-add`, `entity-add`
- `index`, `log`, `init`, `bootstrap`, `import`
- `serve`, `wait`, `watch`, `token`, `comment-claim`, `comment-resolve`,
  `comment-list`, `presence`
- `render`, `build`, `capabilities`, `upgrade`

Most read/report commands accept `--format json`. `wait` prints one JSON work
item. `watch --emit jsonl` tails change events.

## Dependencies

Runtime requires Python 3.11+.
PyYAML is preferred when present, but normal docs validation does not require a primary install step: the skill ships a conservative built-in YAML fallback that fails closed on unsupported advanced YAML.

Test/proof environments can add tools explicitly, without installing this repo
as a package:

```bash
python -m pip install pytest playwright
python -m playwright install chromium
PYTHONPATH=scripts pytest
```
