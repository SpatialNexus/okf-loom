# OKF hard rules and gotchas

## Hard rules

1. OKF v0.1 only requires `type` in concept frontmatter.
2. Preserve unknown frontmatter keys round-trip.
3. Consumers tolerate broken links; authoring mutators fail closed unless a
   forward reference is explicitly allowed.
4. Absolute bundle-relative and relative Markdown links are both valid. Prefer
   absolute bundle-relative links when authoring.
5. `index.md` and `log.md` are reserved filenames, not concept documents.
6. Only the bundle-root `index.md` may carry frontmatter.
7. Auto-update must not destroy hand-curated content; index regeneration is
   marker-safe and log updates are append-only.
8. All okf-loom writes go through tmp + rename atomic writes.
9. Use `scripts/okf-loom`; do not assume package installation.
10. Never commit `<bundle>/.okf-loom/session/` — it holds ephemeral live-feed
    state and the per-session `.token` secret. okf-loom handles this
    automatically: the session and derived-index directories are written
    self-ignoring (a `.gitignore` containing `*` inside each), so they stay
    invisible to git in any repository. Don't delete those files.
11. `serve` binds 127.0.0.1:8787 by default and auto-opens a browser
    unless `--no-open`. Going public is an explicit choice:
    `--tunnel` (cloudflared quick tunnel, read-open to link holders) or
    `--public --public-ack` (raw network bind).

## Common traps

- Bundle scanning prunes hidden dirs, `node_modules`, nested git clones, and
  `.gitignore`-d paths by default (spec §5), so serving a workspace root is
  safe — but it also means a gitignored `.md` will NOT load. Anything can be
  added back with `bundle.include` in `okf-loom.config.yaml` (beats every
  exclusion, even nested-repo pruning — e.g. `include: [vendor-repo/]`);
  tune the rest with `bundle.exclude` / `bundle.respect_gitignore`.
- Images/media must be bundle-local files: the studio serves (and static
  builds copy) allowlisted media (`.png .jpg .jpeg .gif .webp .avif .bmp
  .ico .svg .mp4 .webm .pdf`) under the same §5 visibility rules as
  concepts — a gitignored/pruned asset will 404 in the studio too. Remote
  hot-linked images are CSP-blocked and `data:` URIs are sanitized by
  design. `validate` flags missing image targets (`asset.missing`).
- YAML parses unquoted dates/version-like values. Quote timestamps and versions.
- `tags` should be a YAML list, not a comma-separated scalar.
- Markdown links inside code blocks are not graph edges.
- Do not use `type` as a source-system or per-dataset taxonomy. Use tags and
  custom keys for cross-cutting classifications.
- Do not add a database or sidecar schema for what OKF already represents in
  plain Markdown.
- Do not reintroduce package-publishing as the primary distribution story; this
  git repo skill layout is the artifact.
