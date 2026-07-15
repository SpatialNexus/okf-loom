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
Frontend changes should also run the JavaScript syntax check and the focused
browser suites covering the changed surface:

```bash
scripts/lint-js.sh

# First paint, responsive chrome, keyboard behavior, and table containment.
uv run --with pytest --with playwright --with pyyaml \
  pytest -q tests/test_first_paint_lifecycle_browser.py \
  tests/test_responsive_keyboard_browser.py

# Graph disclosure/readability/invariants, overlay focus, and LOD behavior.
uv run --with pytest --with playwright --with pyyaml \
  pytest -q tests/test_graph_disclosure_browser.py \
  tests/test_graph_invariant_closure_browser.py \
  tests/test_graph_readability_browser.py tests/test_viewer_browser.py \
  tests/test_studio_iter1_browser.py
```

Install the managed browser once when the environment has no usable system
Chrome/Chromium: `uv run --with playwright playwright install chromium`.

When a viewer change intentionally changes captured output, regenerate the
affected proof rather than leaving stale images or manifests:

```bash
uv run --with playwright --with pillow python scripts/capture_readme_media.py
uv run --with playwright python scripts/capture_viewer_proof.py
uv run --with playwright python scripts/capture_final_workbench_proof.py
python tests/capture_boot_settlement_proof.py  # requires Playwright in this environment
```

Do not regenerate every capture set for an unrelated change. Review the
resulting images and provenance manifests before submitting them.

## Security-sensitive changes

Be careful with live studio routes, CSRF token handling, Origin/Host allow-lists, `--public`, `--tunnel`, and active viewer/plugin code.
Document any exposure-boundary changes in `SECURITY.md`, the README, and the relevant docs-bundle reference page.
