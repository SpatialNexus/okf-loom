---
type: How-to
title: Embed the viewer in an agent harness
description: Embed okf-loom inside an agent harness (opencode, Claude Code, Codex, LangGraph, or custom) using the CLI shell-out shape, the Python library shape, or a long-running in-process server.
resource: /how-to/embed_in_harness.md
tags: [embedding, harness, integration, library, server]
timestamp: "2026-06-29T00:00:00Z"
---

# Embed the viewer in an agent harness

This guide shows the three integration shapes okf-loom supports and
when to reach for each.

You already have a bundle and a harness that wants to read or enrich it.
If you do not have a bundle yet, [Author your first bundle](/tutorials/first_bundle.md)
gets you started.

# Step 1: Pick an integration shape

| Shape | When to use |
|---|---|
| CLI shell-out | Your harness already runs shell commands and parses JSON. Simplest; no Python import. |
| Python library | Your harness is Python and wants in-process objects. |
| Long-running server | Your harness wants a live URL (browser, scraper, or a long-running studio). |

All three read the same bundle directory and produce the same answers;
pick by what your harness already speaks.

# Step 2: Embed as a CLI shell-out

The simplest shape: shell out to the checkout-local CLI and parse the JSON.

```bash
scripts/okf-loom validate path/to/bundle --format json
scripts/okf-loom discover path/to/bundle --out /tmp/plan.json
scripts/okf-loom update  path/to/bundle --plan /tmp/plan.json
```

Use command-specific JSON/report flags where the command exposes them; a thin
wrapper that captures stdout and `json.loads` it is enough for those report
commands.

This is the shape most agent harnesses start with — it needs no Python
dependency in the harness itself.

For the harness-specific recipes (opencode, Claude Code, Codex,
LangGraph, custom), see
[/reference/embedding_guide.md](/reference/embedding_guide.md).

# Step 3: Embed as a Python library

When the harness is Python, import okf-loom directly and skip the
process boundary.

```python
from okf_loom import Bundle
from okf_loom.validate import validate_bundle
from okf_loom.discover import discover_suggestions
from okf_loom.update import load_plan, apply_plan

bundle = Bundle.load("/path/to/bundle")

# Validate
report = validate_bundle(bundle)
print("Conformant:", report.ok, "Warnings:", len(report.warnings))

# Discover gaps
suggestions = discover_suggestions(bundle, rules=["unlinked_mentions"])

# Apply a plan (idempotent)
plan = load_plan("/tmp/plan.json")
apply_plan(bundle, plan)
```

The library surface is the same pipeline the CLI uses, so behaviour is
identical between the two shapes.

Keep one `Bundle` instance per harness; call `bundle.invalidate()` to
evict the search caches when you reload the underlying files.

# Step 4: Embed as a long-running server

For a live URL — a browser pointed at the viewer, a scraper, or a
long-running studio — embed the HTTP server in a daemon thread inside
the harness.

```python
import threading
from http.server import ThreadingHTTPServer
from okf_loom import Bundle
from okf_loom.server import OKFWikiHandler

bundle = Bundle.load("/path/to/bundle")
httpd = ThreadingHTTPServer(("127.0.0.1", 8787), OKFWikiHandler)
httpd.bundle = bundle
threading.Thread(target=httpd.serve_forever, daemon=True).start()
```

The harness can now point a browser at `http://127.0.0.1:8787/`, or
fetch the JSON data routes directly.

Swap the bundle at runtime by reassigning `httpd.bundle`; the next
request picks it up.

# Step 5: Point a browser at the live studio

When you want the full collaborative studio — comments, presence, live
SSE updates — run `serve` instead of the bare server.

```bash
scripts/okf-loom serve path/to/bundle --no-open
```

The harness hands the user `http://127.0.0.1:8787/` and then drives the
comment loop via the CLI mutators.

See [Direct the agent loop](/tutorials/author_with_agent.md) for the
canonical wait → claim → write → resolve flow, and
[/reference/embedding_guide.md](/reference/embedding_guide.md) for
harness-specific wiring.

# Step 6: Read the CSRF token when you must POST directly

The CLI mutators attach the per-session CSRF token for you.
If you POST to `/__apply`, `/__undo`, `/__presence`, or `/__comment`
over HTTP yourself, read the token the studio wrote on boot.

```bash
scripts/okf-loom serve path/to/bundle --no-open &
TOKEN=$(scripts/okf-loom token path/to/bundle)

curl -s -X POST http://127.0.0.1:8787/__presence \
  -H "Content-Type: application/json" \
  -H "X-OKF-Token: $TOKEN" \
  -d '{"state": "watching", "actor": "agent"}'
```

The token is per-session, mode `0600`, lives only in
`<bundle>/.okf-loom/session/.token`, and is readable only by the user that
launched `serve`.

`token` exits non-zero with a clear message if no session exists.

# End state

You now have okf-loom wired into your harness in the shape that fits
it best, and you know where to deepen the integration when you need the
live studio or the library API.

# See also

* [Embedding guide](/reference/embedding_guide.md) — harness-specific recipes for opencode, Claude Code, Codex, LangGraph.
* [Direct the agent loop](/tutorials/author_with_agent.md) — the comment-driven studio loop.
* [Build a static site](/how-to/build_static_site.md) — ship a bundle as a hostable site when you do not need a live server.
* [CLI command reference](/reference/cli.md) — every command the shell-out shape can call.
* [HTTP server routes](/reference/http_routes.md) — every route the server shape exposes.
* [okf-loom architecture](/explanation/architecture.md) — why okf-loom is harness-agnostic by design.

Return to [How-to guides](/how-to/index.md).
