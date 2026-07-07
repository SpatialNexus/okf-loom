# Handover — okf-loom Editorial Workbench · ROUND 2 · PHASE 3 (features) — CONTINUATION

> Paste the block below into a fresh session to continue the redesign. It is self-contained. (Written mid-Phase-3 at a clean, verified stopping point — Task 1 code done + green + committed; its review gate is the first action below.)

---

Continue the okf-loom studio "Editorial Workbench" redesign — **ROUND 2, PHASE 3 (FEATURES: on-page ToC · index dashboard · search quality · studio depth)**. Work in `/l_kitty_kitty/opt/projects/repos/okf-loom` on branch `feature/new-layout` (STAY on it; do NOT branch/merge). **AUTONOMOUS build — no user gate. Proceed through the build → verify, making + documenting design calls; don't stop for approval.**

## THE PLAN IS ALREADY WRITTEN — it is your spec (do NOT re-plan)
**`docs/superpowers/plans/2026-07-06-editorial-workbench-round2-phase3.md`** (committed `2f768bb`) — 10 tasks (0–9), each with **COMPLETE before/after code**, RED→GREEN→commit steps, exact file anchors, and full test code. The task sections are hyper-precise. Its header carries the **design decisions D1–D5**, the **decoupling contract**, the **"Test contracts — MUST preserve"** table, **"New names locked"**, and the **file-structure map**. TRUST IT (but grep-verify line refs — files shift as earlier tasks edit them). Known "read-the-neighbour" spots in the plan were already pre-verified (import paths, test fixtures, seams) before it was committed.

## EXACTLY WHERE WE ARE (all committed on `feature/new-layout`; independently verified green)
Phase 1 + 2 + consistency = through `1b2fe99`. Phase 3 so far:
- `2f768bb` — the Phase-3 plan (docs).
- `3337d44` — **Task 0** (spec §6 reconciliation note). ✅ DONE.
- `7f0f5ff` — **Task 1** (on-page ToC §6.1) feature.
- `a25d8df` — **Task 1** fix (a double-escape bug spec-review caught).

**Task 1 CODE is complete + green:** `tests/test_render.py` = 67 passed; ToC + token-parity + subtitle guards pass; the Task-1 diff (`3337d44..a25d8df`, 4 files / +118) touches **no `[data-theme]`/parity token**; working tree clean (except the 3 untracked don't-touch items). **Task 1's REVIEW GATE is not yet closed** — that's your first action.

## IMMEDIATE NEXT ACTIONS — resume superpowers:subagent-driven-development
Process (unchanged): **fresh `general-purpose` implementer per task** (paste its FULL task text — don't make it read the plan file) **+ two-stage review: spec-compliance THEN code-quality** (fresh reviewers; "don't trust the report, read the diff") **+ fix loops via SendMessage to the SAME implementer** (its `agentId` from spawn) **+ commit per task**. Tasks share files (render.py in 1/2/4; wiki.css in 1/3/4; studio.js in 6/7/8), so run **SEQUENTIALLY — never parallel implementers.** Models used so far: implementers + reviewers on **sonnet** (the plan is precise → execution is mechanical), escalate to **opus** on BLOCKED; **final whole-Phase-3 review on opus.**

1. **Close Task 1's review gate** (deferred at the stop):
   - **Spec re-review** of fix `a25d8df` — confirm the double-escape bug is resolved + nothing new introduced. (The fix: `import html` added at render.py:18; `_build_toc_html` now does `html.unescape(_TOC_TAG_RE.sub("", inner)).strip()` before `_esc()`; new regression test `test_p3_1_toc_escapes_heading_entities_once`.)
   - **Code-quality review** of the full Task-1 diff: `git diff 3337d44..a25d8df -- scripts tests docs`.
   - Fix any findings (SendMessage a Task-1 implementer or a fresh one), re-verify green, mark Task 1 complete.
2. **Tasks 2 → 9 in order** (each: implementer → spec review → quality review → fix loops → commit):
   - **Task 2 (§6.2a)** index card/section `data-okf-*` attrs — `render.py`. **RESTART boundary** (render.py read at startup).
   - **Task 3 (§6.2b)** `wiki.js` `enhanceIndex()` (chips/sort/search-within) + widen-shell CSS.
   - **Task 4 (§6.3a)** live search `_highlight` + match-centred snippet + `<mark>`/type CSS — `render.py`. **RESTART boundary.**
   - **Task 5 (§6.3b)** `static-search.js` meta parity + `<mark>` highlight + match-centred excerpt.
   - **Task 6 (§6.4a)** quick-actions RUN — `studio.js` (post `/__comment` directive via the existing channel).
   - **Task 7 (§6.4b)** Changes-tab on-demand diff — extract `renderDiffInto` in `studio.js`, reuse `/__diff`.
   - **Task 8 (§6.4c)** validation count — read-only `/__validate` in `server.py` + footer chip in `studio.js`. **RESTART boundary** (server.py).
   - **Task 9** verification — full `pytest tests/ -q` green + serve `--port 8788 --tunnel` + Playwright screenshots across the 4 themes (× soft/border where relevant); tune; then the **final whole-Phase-3 opus review**.
3. When done: update memory `editorial-workbench-layout-buildout.md` → "ROUND 2 FEATURE-COMPLETE".

## DESIGN DECISIONS (D1–D5 — in the plan header; honor them, don't relitigate)
- **D1 ToC** extracts from the **rendered/demoted** `<h2>`/`<h3>` (source `#`→`<h2>`; `reference/cli.md` is all `#` → a source-level ToC would be empty), regex over the final `body_html`, ≥3-heading gate, `.okf-toc*` in wiki.css, no-JS, distinct from the JS-only studio Outline.
- **D2 §6.3** relevance sort is **already satisfied** on all 3 search paths; the real work is `<mark>` highlighting (escape-first) + **match-centred snippets** (a prerequisite — the curated description often lacks the term) + **static result-meta parity**. The live-suggest dropdown is left as-is (its a11y contract).
- **D3 RUN** posts the intent as a `/__comment` directive (the existing studio→agent channel — **no new endpoint**); fill the composer with a complete `runPrompt` only when empty, then click Send.
- **D4 Changes diff** reuses `/__diff` via an extracted `renderDiffInto()`; the revs come from the change event's `detail.before` (from) + `rev` (to) — no history scan.
- **D5 `/__validate`** is a read-only, token-gated GET (copies the `/__diff` gate), cached on `studio.current_rev()` — the ONLY new server surface; it completes SPEC §3.5's "validation count".

## PROCESS LEARNINGS (from Task 1 — apply every task)
- **The two-stage review WORKS and is essential** (advisor is unavailable): spec-review caught a real double-escape bug the implementer's own passing tests missed — heading text came from already-escaped `body_html`, so the extra `_esc()` double-escaped it, corrupting the project's own `# Rendering & Feature Showcase`. **Lesson:** when a task extracts text from **already-rendered/escaped HTML, unescape before re-escaping.** Give reviewers the full requirements + "read the diff, don't trust the report" and they find real bugs.
- Implementers execute the precise plan faithfully (Task 1 needed **zero** anchor adaptations). Give them: full task text, scene-setting context, the env recipe, the don't-break contracts, and "grep-confirm each anchor is unique; adapt minimally + report if an `old_string` doesn't match."
- Per-task tests are scoped (`-k "..."`) and fast; the **full** suite runs only in Task 9.

## CRITICAL ENV GOTCHAS (bit prior sessions)
- Foreground `sleep`/`pkill`/`kill` are sandbox-blocked (exit 144). **Serve:** Bash `run_in_background:true`, `exec scripts/okf-loom serve docs-bundle --no-open --port 8788 --tunnel`. **Wait:** `curl -s --retry 30 --retry-delay 1 --retry-connrefused http://localhost:8788/demo/showcase -o /dev/null` (NO `sleep`). **STOP/RESTART:** the **TaskStop** tool on the bg task id (never `pkill`). **RESTART after any `render.py`/`server.py`/template edit** (Tasks 2, 4, 8); css/js served fresh — just reload. A stale prior serve may squat `:8787` — use your own `--port 8788`.
- **Browser tests spin their OWN server** (`server_url` fixture) → pytest needs no manual serve; only Task 9's visual pass serves.
- **Screenshots:** Playwright + system Chrome, `executable_path=$AIC_PLAYWRIGHT_CHROME_PATH` (`/opt/google/chrome/google-chrome`), `args=["--no-sandbox"]`, `wait_until="load"` (SSE breaks networkidle); seed `okf-theme`/`okf-contrast`/`okf-border` via `context.add_init_script`.
- **Tests:** `python3 -m pip install pytest playwright pytest-playwright`. **NEVER `| tail` + trust the exit code — READ the printed summary line.** Flakes (rerun once if the ONLY failure): `test_comment_mark_wraps_selection`; `test_agent_watching_toggle_posts_presence`; `test_agent_activity_panel_has_unique_sections`. 23 skips = optional upstream fixtures (expected).
- **advisor tool is UNAVAILABLE** (errors "unavailable") — compensate with the two-stage subagent reviews + the final whole-Phase-3 review + independent test/screenshot verification.

## DON'T-BREAK (verify at build; full list in the plan's "Test contracts" table)
Token-parity (**no `[data-theme]`/parity-token edits this phase**); THEMES/THEME_GLYPHS/LEGACY_THEMES swiss-first + identical across render.py/wiki.js/studio.js/graph.js; the Phase-2 appearance system + graph `GRAPH_COLORS`/`syncLabelColour`; the **first-anchor contract** on `.okf-concept-list li` (filter by hiding nodes, don't reorder internals); ToC/index toolbar OUTSIDE the tested elements (`.okf-page__body`); conflict-modal DOM + labels (Task 7 extracts the renderer only); **only `/__validate` is new server surface** (read-only + token-gated); RUN/diff reuse existing endpoints; every `__TOKEN__` placeholder replaced; z-index tiers (graph ≤40, topbar 50, studio modals 70+).

## ROLLBACK / DON'T TOUCH
Git tag `pre-redesign-baseline` (`2066013`). Untracked, leave alone: `okf-loom-mcp/`, `redesign-files-1.zip`, `design/new-layout/workbench-preview.html`.

## DELIVERABLE
Close Task 1's review gate → build Tasks 2–9 via subagent-driven-development (suite green, commit per task) → final whole-Phase-3 review → serve + tunnel + screenshots across themes. Autonomous; document decisions. Then the Editorial Workbench redesign is **feature-complete** — update `editorial-workbench-layout-buildout.md`.
