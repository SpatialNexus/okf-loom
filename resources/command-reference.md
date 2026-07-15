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
scripts/okf-loom graph-quality docs-bundle
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

Forgot `--tunnel`? Attach one to the RUNNING session — no restart, no lost
session token or undo history:

```bash
scripts/okf-loom tunnel docs-bundle           # prints the public URL
scripts/okf-loom tunnel docs-bundle --status  # current URL (or none)
scripts/okf-loom tunnel docs-bundle --stop    # detach, restore local-only allowlist
```

## Partial body updates

Change one block of a concept without touching the rest (no whole-body
`write-concept --force`, no staging copies):

```bash
# Replace ONE section (subsections included); fail-closed on missing/ambiguous headings.
scripts/okf-loom update-section --bundle docs-bundle --id reference/cli --heading "## Examples" --body-file /tmp/frag.md
# Append to a section instead of replacing; create it if absent.
scripts/okf-loom update-section --bundle docs-bundle --id reference/cli --heading "Notes" --body "extra line" --append --create-if-missing
# Exact textual patch; must match exactly once (or pass --all).
scripts/okf-loom replace-text --bundle docs-bundle --id reference/cli --old "old exact text" --new "new exact text"
```

## Full surface

- `validate`, `info`, `graph`, `graph-quality`, `search`
- `discover`, `plan`, `repair`, `update`
- `write-concept`, `set-frontmatter`, `link-add`, `entity-add`,
  `update-section`, `replace-text`
- `index`, `log`, `init`, `bootstrap`, `import`
- `serve`, `tunnel`, `wait`, `watch`, `token`, `comment-claim`,
  `comment-reply`, `comment-resolve`, `comment-list`, `presence`
- `render`, `build`, `capabilities`, `upgrade`

Most read/report commands accept `--format json`. `wait` prints one JSON work
item (with a `queue` field showing other still-open comments). `watch --emit
jsonl` tails change events. `write-concept` fills `resource`/`timestamp` on
create so new concepts pass `--strict` (opt out with `--no-defaults`).

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

The browser suites and capture scripts use Playwright, but the repo itself is
still consumed directly from the checkout. An equivalent isolated invocation
is:

```bash
uv run --with pytest --with playwright --with pyyaml pytest -q <test paths>
```

The shared capture helpers resolve a Chromium-family browser in this order: an
explicit `--chrome PATH`, `OKF_CHROME`, `AIC_PLAYWRIGHT_CHROME_PATH`,
Playwright-managed Chromium, then a system Chrome/Chromium channel or
executable. The browser sandbox remains enabled; only constrained root
containers should explicitly set `OKF_CAPTURE_NO_SANDBOX=1`.

`tests/capture_boot_settlement_proof.py` is a standalone exception rather than
a `capture_support.py` consumer. It first tries `AIC_PLAYWRIGHT_CHROME_PATH`,
when present, and automatically launches that environment-provided executable
with `--no-sandbox`; this supports the constrained AIC Chrome environment. Its
system Chrome channel and Playwright-managed fallbacks do not add
`--no-sandbox`. Normal shared capture support remains opt-in only through
`OKF_CAPTURE_NO_SANDBOX=1`.

## Frontend checks and browser proof

```bash
scripts/lint-js.sh
scripts/okf-loom validate docs-bundle --strict

# Stable curated media used by the project overview.
uv run --with playwright --with pillow python scripts/capture_readme_media.py

# Lightweight dated smoke proof for live and static viewer output.
uv run --with playwright python scripts/capture_viewer_proof.py

# Bounded Editorial Workbench matrix: live/static/single-file, themes,
# responsive states, modifiers, reduced motion, forced colors, and no-JS.
uv run --with playwright python scripts/capture_final_workbench_proof.py

# First-paint boot settlement and no-JS/table artifact set.
uv run --with playwright python tests/capture_boot_settlement_proof.py
```

`scripts/capture_support.py` is the shared, import-safe support layer for the
capture entrypoints under `scripts/`: browser launch, server and semantic target
readiness, graph-layout settlement, and normalized provenance manifests. Those
commands fail rather than taking a screenshot of an unavailable, hidden,
unreadable, or not-yet-ready target. The standalone boot-settlement driver owns
its boot-state readiness and provenance independently. Regenerate only the sets
affected by an intentional output change.
