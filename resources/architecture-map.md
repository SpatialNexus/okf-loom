# Runtime architecture map

The runtime is not distributed as an installed package. It is source code under
`scripts/okf_loom/` and is invoked through the checked-in `scripts/okf-loom` helper.

| Area | Files |
|---|---|
| CLI dispatcher | `scripts/okf_loom/cli.py`, `__main__.py` |
| Data model | `model.py`, `parse.py`, `paths.py`, `roundtrip.py`, `ignore.py` |
| Validation | `validate.py` |
| Search/index/discovery | `search.py`, `index.py`, `discover.py`, `plan.py`, `update.py` |
| Bundle config/capabilities | `config.py`, `extensions.py` |
| Rendering/server/studio | `render.py`, `server.py`, `studio.py`, `watch.py` |
| Viewer assets | `viewer/templates/`, `viewer/static/`, `viewer/OVERRIDES.md` |
| Appearance state | `viewer/static/theme.js` (shared live/static/single-file preference, resolution, modifiers, Appearance UI, and overlay stack contract) |
| Capture support | `scripts/capture_support.py` (browser resolution, semantic readiness, graph settlement, provenance manifests) |
| Capture entry points | `scripts/capture_readme_media.py` (stable curated media), `scripts/capture_viewer_proof.py` (dated live/static smoke proof), `scripts/capture_final_workbench_proof.py` (final parity matrix), `tests/capture_boot_settlement_proof.py` (first-paint/no-JS/table artifacts) |
| Other archive/proof helpers | `scripts/build_skill_archive.py`, `scripts/capture_signal_controls.py`, `scripts/lint-js.sh` |

Authoritative documentation:

- [`docs-bundle/reference/architecture.md`](../docs-bundle/reference/architecture.md)
- [`docs-bundle/reference/cli.md`](../docs-bundle/reference/cli.md)
- [`docs-bundle/reference/http_routes.md`](../docs-bundle/reference/http_routes.md)
- [`docs-bundle/reference/spec.md`](../docs-bundle/reference/spec.md)

Tests in `tests/` are the executable examples for checkout-local behavior.
