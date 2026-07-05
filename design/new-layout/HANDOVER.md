# Handover — okf-loom layout redesign: IMPLEMENTATION session

Paste-ready prompt for a fresh session. Design is locked, the spec is written
and self-reviewed. Your job: turn the spec into a plan, then build it.

---

Continue the okf-loom studio layout redesign — **implementation phase**. Work in
`/l_kitty_kitty/opt/projects/repos/okf-loom` on branch **`feature/new-layout`**
(stay on it; do not branch off). The user has **delegated implementation
decisions** — proceed spec → plan → build, self-reviewing at each gate; do NOT
pause for per-step sign-off. Still do a real **visual pass on the actual viewer**
(served + tunnelled) and keep tests green before considering it done.

**Read first — these are the contract:**
1. `design/new-layout/SPEC.md` — the locked design, the decoupled-token
   architecture, the theme set, the new `--okf-active-fill/-fg/-border` token
   primitive, the hard contract, and the verification bar.
2. `design/new-layout/mockups/swiss-v1.html` and `.../technical-v1.html` — the
   approved visual reference. Their product CSS is **byte-identical**; only the
   token block differs. That is the decoupling proof — preserve it.

**Process (this is the brainstorming tail, resumed):**
- The spec is done. Run **`superpowers:writing-plans`** to turn `SPEC.md` into a
  staged implementation plan, then execute it (**`superpowers:executing-plans`**
  or **`superpowers:subagent-driven-development`**), TDD where the viewer test
  suite gives you a foothold.
- Do NOT relitigate the locked design (see SPEC §8 for what's rejected).

**Biggest risk — sequence it carefully in the plan (SPEC §4):** the theme
migration. Today's viewer ships 5 themes (`light/dark/pastel/sepia/midnight`);
the redesign ships 4 (`technical`/`swiss` × light/dark) and retires the old
palette themes. `test_render.py` enforces that **every** shipped theme overrides
the **full** token set — and the redesign ADDS tokens (SPEC §6), so every theme
block grows. Touch-points: `wiki.css` token blocks, `studio.js` theme list
(~:3046-3050) + palette switch + top-bar theme switcher, `render.py`
`__THEME_ATTR__`/`__DATA_ATTRS__`, `okf-loom.config.yaml` `theme:` enum +
`StudioConfig.theme`, localStorage migration for returning users, and the
`README.md` "Five colour themes" section.

**The studio chrome is injected server-side** by `server.py:_studio_bootstrap`
(+ `studio.js`): agent chip, watching toggle, view switch, Comments/Changes,
palette, connection status. The redesign folds today's second bar + `.okf-panel`
into the single top bar + bottom status strip + pop-over — so rework the
bootstrap to target the new DOM; don't bypass it. Keep the `okf-viewer` body
class, `#okf-main` skip-target, and all `__TOKEN__` placeholders.

**Visual review (REQUIRED — the user reviews in a browser).** This is a Docker
container (IP 172.17.0.2), NO Tailscale, so `localhost` is not reachable from the
user's browser. Serve on loopback and tunnel with cloudflared:
1. `scripts/okf-loom serve docs-bundle --no-open` (loopback; note the port).
2. `/usr/local/bin/cloudflared tunnel --url http://localhost:<port>` → grep the
   log for `https://<random>.trycloudflare.com` and hand that URL to the user.
   Drive the real flow: `/` focuses search · nav collapses · a comment pin opens
   the pop-over · pop-over closes on scrim/Esc · all four theme×mode combos ·
   all five views.
   *(You can also still spin up the brainstorm visual-companion for static
   mockups — recipe below — but the point now is the REAL viewer.)*

Brainstorm companion (for static HTML mockups only): start
`.../superpowers/5.1.0/skills/brainstorming/scripts/start-server.sh
--project-dir <repo>` → JSON with a port + `screen_dir`; write `*.html` there;
files served at `/files/<name>`; tunnel the port as above.

**Baseline / rollback (SPEC §9):** git tag `pre-redesign-baseline` (commit
`2066013`); restore with
`git checkout pre-redesign-baseline -- scripts/okf_loom/viewer`. A physical copy
is at `.superpowers/backup/viewer-baseline-2026-07-05/` (local; `.superpowers/`
is gitignored).

**Done bar (SPEC §10):** `test_render.py` + full viewer suite green; visual pass
on the real viewer across all four theme×mode combos and all five views; the
user has looked.

**PAUSED side-task — ignore unless the user brings it up:** an `okf-loom-mcp/`
docs-cleanup (untracked folder, user has a backup, nothing deleted). Boundaries
were approved but execution was deferred. Do not touch it unless asked.
