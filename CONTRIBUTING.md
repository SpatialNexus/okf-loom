# Contributing

Thank you for your interest in okf-loom.
This repository is prepared as a v1.0 Apache-2.0 open-source baseline.

## License expectations

By contributing, you agree that your contribution may be distributed under the Apache License, Version 2.0.
Do not submit code, docs, generated artifacts, or assets that cannot be redistributed under Apache-2.0 unless the maintainers explicitly approve a separate license notice.

## Development model

- Use the checked-in `scripts/okf-loom` helper from a source checkout.
- Do not add PyPI or package-publishing workflow as the primary path.
- Keep upstream OKF SPEC `v0.1` as the wire-format baseline unless runtime code intentionally changes `SPEC_VERSION`.
- Treat okf-loom product version `v1.0` separately from upstream OKF SPEC `v0.1`.
- Validate docs bundles after documentation changes.

## Public-readiness checklist

Before submitting a change, run the focused checks that match your work.
For documentation-only changes, at minimum run:

```bash
scripts/okf-loom validate docs-bundle --strict
```

For runtime changes, add or update tests and run the relevant pytest selection.

## Security-sensitive changes

Be careful with live studio routes, CSRF token handling, Origin/Host allow-lists, `--public`, `--tunnel`, and active viewer/plugin code.
Document any exposure-boundary changes in `SECURITY.md`, the README, and the relevant docs-bundle reference page.
