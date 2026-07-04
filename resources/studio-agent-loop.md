# Live studio agent loop

`serve` opens the live collaborative studio. The user reads and directs via
comments; the agent writes OKF files through the mutators.

```bash
scripts/okf-loom serve path/to/bundle --no-open &
until scripts/okf-loom token path/to/bundle >/dev/null 2>&1; do sleep 0.2; done

scripts/okf-loom wait path/to/bundle --for comment
scripts/okf-loom comment-claim path/to/bundle 01JABED9K0 --summary "adding dependency link"
scripts/okf-loom presence path/to/bundle --state editing --focus tables/orders
scripts/okf-loom link-add --bundle path/to/bundle --source tables/orders --target tables/customers --group-id PASS1
scripts/okf-loom comment-resolve path/to/bundle 01JABED9K0 --summary "done: link added"
```

When the ask is ambiguous or arrives cut off, do NOT claim-and-guess or ask
out-of-band — reply in the thread and wait for the answer:

```bash
scripts/okf-loom comment-reply path/to/bundle 01JABED9K0 --body "Did you mean orders or order_items?"
scripts/okf-loom wait path/to/bundle --for comment   # the user's answer is new work
```

Important rules:

- Run `wait` in the foreground. It blocks once, prints one work item, exits,
  and then you act. Do not background it. The returned comment includes a
  `queue` field (`{pending, ids}` of other open comments) so you can see
  backlog depth without diffing `comment-list`.
- Wait for `token` readiness after backgrounding `serve` before mutating.
- Mutators route through `Studio.save_concept` when a live session exists,
  making writes attributed, undoable, and visible over SSE.
- Prefer the partial-update mutators for edits inside an existing body:
  `update-section --heading "## X" --body-file frag.md` swaps one section
  (fail-closed on missing/ambiguous headings), `replace-text --old … --new …`
  applies an exact textual patch. Never reconstruct a whole document (or
  stage a copy) to change one block; reserve `write-concept --force` for
  actual full rewrites.
- `--group-id` groups several writes into one undoable pass.
- During a long pass, keep the user informed:
  `presence --state editing --focus <id> --message "linking 3 of 7 tables"` —
  re-post to update the message; it shows live next to the presence chip.
- To share the running studio publicly without a restart:
  `scripts/okf-loom tunnel path/to/bundle` (needs cloudflared; `--stop`
  detaches). Same warning as `serve --tunnel`: anyone with the link can READ
  the bundle.
- `--public` or non-loopback binds require explicit `--public-ack` or an
  interactive acknowledgement.
- `--no-edit` makes a read-only kiosk: live reads remain on, mutating endpoints
  are disabled.

Full behavior is documented in [`docs-bundle/reference/spec.md`](../docs-bundle/reference/spec.md)
and implemented in [`scripts/okf_loom/studio.py`](../scripts/okf_loom/studio.py)
plus [`scripts/okf_loom/server.py`](../scripts/okf_loom/server.py).
