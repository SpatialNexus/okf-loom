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

Important rules:

- Run `wait` in the foreground. It blocks once, prints one work item, exits,
  and then you act. Do not background it.
- Wait for `token` readiness after backgrounding `serve` before mutating.
- Mutators route through `Studio.save_concept` when a live session exists,
  making writes attributed, undoable, and visible over SSE.
- `--group-id` groups several writes into one undoable pass.
- `--public` or non-loopback binds require explicit `--public-ack` or an
  interactive acknowledgement.
- `--no-edit` makes a read-only kiosk: live reads remain on, mutating endpoints
  are disabled.

Full behavior is documented in [`docs-bundle/reference/spec.md`](../docs-bundle/reference/spec.md)
and implemented in [`scripts/okf_loom/studio.py`](../scripts/okf_loom/studio.py)
plus [`scripts/okf_loom/server.py`](../scripts/okf_loom/server.py).
