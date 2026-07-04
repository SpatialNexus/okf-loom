# Update Log

## 2026-07-04
* **Update**: Friction-report round: added block-level partial updates (`update-section`, `replace-text` — CLI verbs + `/__apply` op kinds), mid-thread `comment-reply` (agent replies post resolved under the thread root; parent stays open), user-side comment body editing over `/__comment-update`, strict-friendly `write-concept` defaults (resource + timestamp on create, `--no-defaults` opts out), runtime tunnel attach (`tunnel` verb + `POST /__tunnel` + session `server.json`), `wait` queue visibility, and live presence `--message` updates. Spec §7/§9/§11–§14/§17 and the CLI/http/comment references updated.

## 2026-07-01

* **Consolidation**: Added [`reference/spec.md`](reference/spec.md) as the
  single canonical current okf-loom v1.0 specification, covering current
  live-studio behavior and loop audit findings.
* **Update**: Reframed active docs around the GitHub-cloneable repository and
  repo-local skill layout use case. Direct checkout execution with
  `scripts/okf-loom` is the primary agent path.
* **Cleanup**: Removed the old iterative audit trail and superseded
  split specs after migrating useful contracts into the current spec.

## 2026-06-29

* **Initialization**: Created the bundle as a Diátaxis-structured
  documentation surface for the okf-loom. Bootstrap with
  `scripts/okf-loom init --bundle okf-loom/docs-bundle --name "okf-loom Documentation"`.
* **Creation**: Added the four quadrant directories (`tutorials/`,
  `how-to/`, `reference/`, `explanation/`) plus index concepts and the
  root index that frames the Diátaxis split.

## 2026-06-29 (later)

* **Import**: Moved the 7 long-form design docs from `docs/` into the
  bundle as first-class OKF concepts so search, graph, and indexes
  reach them. Files moved with `git mv` to preserve history:
  * `docs/architecture.md` → `reference/architecture.md` (type: Reference)
  * `docs/embedding-guide.md` → `reference/embedding_guide.md` (type: Reference)
  * The superseded split specifications were later consolidated into
    `reference/spec.md` and removed from the active bundle.
  * `docs/requirements.md` → `explanation/requirements.md` (type: Explanation)
  * `docs/research.md` → `explanation/research.md` (type: Explanation)
* **Update**: Rewrote cross-links inside the moved files to use
  in-bundle paths (`/reference/foo.md` instead of bare `foo.md`).
  Updated all concise concepts that previously linked out via
  `../../docs/foo.md` to use the new in-bundle paths.
* **Update**: AGENTS.md, README.md, and the okf-* skills now point at
  `docs-bundle/reference/foo.md` instead of `docs/foo.md`.
* **Note**: `docs/screenshots/` (viewer proof PNGs) stays in `docs/` — it is
  retained proof material, not the user-facing documentation surface.
