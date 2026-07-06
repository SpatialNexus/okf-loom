# Handover — okf-loom Editorial Workbench · ROUND 2 · PHASE 3 (features) — CONTINUATION #2

> Paste the block below (everything under the `---`) into a fresh session to continue. It is self-contained. Written at a **clean, verified checkpoint**: Tasks 0–4 complete **and reviewed**; Task 5 feat **committed + green** (full repo suite 1299 passed / 0 failed) but its two-stage **review gate is the first resume action**. Supersedes `handover-round2-phase3-continuation.md`.

---

Continue the okf-loom studio **"Editorial Workbench" redesign — ROUND 2, PHASE 3 (FEATURES: on-page ToC · index dashboard · search quality · studio depth)**. Work in `/l_kitty_kitty/opt/projects/repos/okf-loom` on branch `feature/new-layout` (STAY on it; do NOT branch/merge). **AUTONOMOUS build — no user gate. Proceed through the build → verify, making + documenting design calls; don't stop for approval.**

## THE PLAN IS THE SPEC (don't re-plan)
**`docs/superpowers/plans/2026-07-06-editorial-workbench-round2-phase3.md`** (commit `2f768bb`) — 10 tasks (0–9), each with COMPLETE before/after code, RED→GREEN→commit steps, exact anchors, full test code. Its header carries design decisions **D1–D5**, the decoupling contract, the **"Test contracts — MUST preserve"** table, "New names locked", and the file-structure map. TRUST it, but **grep-verify every line ref** — files shift as earlier tasks edit them (render.py/wiki.css/studio.js are multi-task).

⚠️ **ONE PLAN BUG DISCOVERED THIS SESSION — do not re-introduce it:** the plan's Task-4/5 `_highlight`/`highlight()` code uses an **escape-then-match** order that SPLITS HTML entities (a query term equal to an entity name — "amp"/"lt"/"gt"/"quot", which an identifier query like `amp_events` tokenizes to since tokenization splits on `_` — lands inside an escaped `&amp;`/`&lt;` and shatters it). It was **FIXED** in the live path (commit `083ae4b`) and the static path was built with the CORRECTED algorithm (`7dda160`). The plan TEXT was never updated. **For any reference to `_highlight`/`highlight()`, use the SHIPPED code (match on RAW text → escape each segment → splice a literal `<mark>`), NOT the plan's snippet.** The current `render.py` `_highlight` docstring is the canonical reference.

## PROCESS — superpowers:subagent-driven-development (it's working; keep it)
Fresh **general-purpose** implementer per task (hand it the **pre-staged brief file** `.superpowers/sdd/task-N-brief.md`; do NOT make it read the plan). **Two-stage review per task**: a fresh SPEC-compliance reviewer + a fresh CODE-QUALITY reviewer (run in **parallel**, read-only on the committed diff; tell them "read the diff, don't trust the report"). Fix loops via **SendMessage to the SAME implementer** by agentId (a fresh session can't reach a prior session's agent — dispatch a fresh implementer with the finding + the brief). **Commit per task.** Tasks **6/7/8 share studio.js → SEQUENTIAL, never parallel implementers**. Models: implementers + reviewers on **SONNET** (plan is precise → execution is mechanical); escalate to **OPUS** on BLOCKED; **final whole-Phase-3 review on OPUS**.

- **The two-stage review is ESSENTIAL and WORKING** — it caught + got fixed REAL bugs this session: Task 1 (double-escape), Task 3 (filtered cards stayed visible behind `.okf-card{display:flex}` + "Grouped" sort didn't restore order), Task 4 (entity-split highlight). The **advisor tool is UNAVAILABLE** — the two independent reviewers + the final review + your own diff-verification are the ONLY compensation. Don't skip it. For each fix, verify the tightened test is **RED-proven** (fails pre-fix, passes post-fix).
- **Adjudication:** dispatch a fix for Critical/Important findings; record Minors in the ledger roll-up for the final review to triage. Plan-mandated findings that are genuine defects → FIX (fixing serves the plan's intent); plan-mandated **deliberate choices** (e.g. additive-CSS placement) → leave, roll up. This is an autonomous build — decide + document, don't stop to ask.
- **Helper scripts** (in the SDD skill dir `/home/kitty/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/scripts/`, run from repo root): `task-brief PLAN N` (already run — briefs 1–9 staged), `review-package BASE HEAD` (writes the diff file the reviewers Read — keeps it out of your context), `sdd-workspace`.
- **DURABLE LEDGER: `.superpowers/sdd/progress.md`** (git-ignored scratch) — authoritative task-by-task state + the **MINOR FINDINGS ROLL-UP** (deferred items the FINAL review must triage). **Read it first.** Resume from the first task not marked complete. All 9 briefs + all task/fix reports are in `.superpowers/sdd/`.

## EXACTLY WHERE WE ARE (all committed on `feature/new-layout`; independently verified)
Phases 1+2+consistency through `1b2fe99`. Phase 3:
- `3337d44` **Task 0** (spec §6 reconciliation, docs). ✅
- **Task 1** ToC §6.1: `7f0f5ff` feat + `a25d8df` double-escape fix + `ac5baa5` import-dealias. ✅ reviewed+complete.
- **Task 2** index `data-okf-*` attrs: `02d21eb` feat + `358c9a4` test-harden. ✅ reviewed+complete.
- **Task 3** index dashboard JS/CSS: `673c4dd` feat + `87f9f3c` fix (2 confirmed bugs). ✅ reviewed+complete.
- **Task 4** live-search highlight/snippet: `7a8d776` feat + `083ae4b` entity-safe `_highlight` fix. ✅ reviewed+complete.
- **Task 5** static-search parity/highlight: **`7dda160` feat — COMMITTED + GREEN (full repo suite 1299 passed / 23 skip / 0 fail) but its TWO-STAGE REVIEW HAS NOT RUN.**

## IMMEDIATE NEXT ACTION — close Task 5's review gate (STEP 1)
Task 5 = §6.3b: `static-search.js` meta/type parity + `<mark>` highlight + match-centred excerpt (client JS for the `--target static` build; no server). Feat committed `7dda160`, green, but unreviewed.
1. `review-package 083ae4b 7dda160` → hand the printed diff path + `.superpowers/sdd/task-5-brief.md` + `.superpowers/sdd/task-5-report.md` to two fresh **sonnet** reviewers (spec + quality). Review focus:
   - **(a) ESCAPING / entity-safety** of the JS `highlight()`: it must match on **RAW** text + escape each segment (reuse `escapeHtml`) + literal `<mark>` — mirroring the FIXED `render.py` `_highlight`. Adversarially trace a query term = entity name (e.g. "gt"/"amp") vs text with `>`/`&` → the entity must **NOT** shatter; all text escaped, only `<mark>` literal (XSS-safe).
   - **(b) meta/class PARITY** with the live renderer: `.okf-search-result`, `.okf-search-result__meta`, `.okf-search-result__type`, `.okf-search-snippet`, `<mark>`.
   - **(c) match-centred excerpt** logic (`makeSnippet`) + edge cases.
   - **(d) test hygiene**: the 3 new tests run the ACTUAL shipped `highlight()` (Node subprocess), assert escaping + parity, not mere presence.
   - **Verify the implementer's two claims:** that its JS `highlight()` is byte-identical to `render.py` `_highlight` for entity + match cases, and that it correctly IGNORED the brief's stale escape-then-match snippet. Both should be checkable from the diff + a quick trace.
2. Fix any Critical/Important via a fresh implementer (finding + brief). Record Minors in the ledger roll-up. Mark Task 5 complete.

## THEN Tasks 6 → 7 → 8 → 9 (each: implementer → spec review → quality review → fix loops → commit). Briefs staged at `.superpowers/sdd/task-N-brief.md`.
- **Task 6 (§6.4a) quick-actions RUN** — `studio.js`. **D3:** post the intent as a `/__comment` directive via the EXISTING studio→agent channel (NO new endpoint); fill the composer with a complete `runPrompt` ONLY when it's empty, then click Send.
- **Task 7 (§6.4b) Changes-tab on-demand diff** — extract `renderDiffInto()` in `studio.js`, reuse `/__diff`. **D4:** revs come from the change event's `detail.before` (from) + `rev` (to) — no history scan. Extract the diff RENDERER only; **preserve the conflict-modal DOM + labels.**
- **Task 8 (§6.4c) validation count** — a NEW read-only, token-gated GET `/__validate` in `server.py` (copy the `/__diff` gate; cache on `studio.current_rev()`) + a footer chip in `studio.js`. **D5.** This is the ONLY new server surface in the whole phase. **RESTART boundary** (server.py — restart the serve after editing).
- **Task 9 verification:** full `pytest tests/ -q` green + serve `--port 8788 --tunnel` + Playwright screenshots across the **4 themes** (× soft/border where relevant); tune; then the **FINAL whole-Phase-3 OPUS review** (`review-package <merge-base> HEAD`). Task 9 ALSO must: **(a)** run the Playwright first-anchor / `stampConceptIds` guard `tests/test_studio_iter1_browser.py` (a Task-2 ⚠️ deferred to here); **(b)** TRIAGE the MINOR FINDINGS ROLL-UP in the ledger (fix any that must land before merge); **(c)** include a **static-build** screenshot (Task 5's static type label is single-color/no-icon by design; `makeSnippet`/full-row DOM has unit but no browser-level coverage).
- When done: update memory `editorial-workbench-layout-buildout.md` → "ROUND 2 FEATURE-COMPLETE".

## DESIGN DECISIONS D1–D5 (in the plan header; honor, don't relitigate)
- **D1 ToC**: extract from rendered/demoted `<h2>`/`<h3>`, ≥3-heading gate, `.okf-toc*`, no-JS, distinct from the JS-only studio Outline. [DONE T1]
- **D2 search**: relevance sort ALREADY correct (don't touch); work = `<mark>` highlight (the CORRECT way = match-raw + escape-per-segment) + match-centred snippets + static meta parity; live-suggest dropdown left as-is (a11y). [DONE T4–T5]
- **D3 RUN**: `/__comment` directive on the existing channel (no new endpoint); fill composer only when empty then Send. [T6]
- **D4 Changes diff**: reuse `/__diff` via extracted `renderDiffInto()`; revs from the change event `detail.before` + `rev`. [T7]
- **D5 `/__validate`**: read-only token-gated GET copying the `/__diff` gate, cached on `current_rev()`; only new server surface. [T8]

## CRITICAL ENV GOTCHAS
- Foreground `sleep`/`pkill`/`kill` are sandbox-blocked (exit 144). **Serve:** Bash `run_in_background:true`, `exec scripts/okf-loom serve docs-bundle --no-open --port 8788 --tunnel`. **Wait:** `curl -s --retry 30 --retry-delay 1 --retry-connrefused http://localhost:8788/demo/showcase -o /dev/null` (NO sleep). **STOP/RESTART:** the **TaskStop** tool on the bg task id (never pkill). **RESTART after render.py/server.py/template edits** (Task 8 = server.py). A stale prior serve may squat `:8787` — use your own `--port 8788`.
- **Browser tests spin their OWN server** (`server_url` fixture) → pytest needs no manual serve; only Task 9's visual pass serves.
- **Screenshots:** Playwright + system Chrome, `executable_path=$AIC_PLAYWRIGHT_CHROME_PATH` (`/opt/google/chrome/google-chrome`), `args=["--no-sandbox"]`, `wait_until="load"` (SSE breaks networkidle); seed `okf-theme`/`okf-contrast`/`okf-border` via `context.add_init_script`.
- **Tests:** `python3 -m pip install -q pytest playwright pytest-playwright`. **NEVER `| tail` + trust the exit code — READ the printed summary line.** Known-flaky (rerun ONCE if it is the ONLY failure): `test_comment_mark_wraps_selection`; `test_agent_watching_toggle_posts_presence`; `test_agent_activity_panel_has_unique_sections`. ~23 skips expected. Current baselines: `tests/test_render.py` = 75 passed; full repo suite = 1299 passed / 23 skipped.
- **advisor tool UNAVAILABLE** — compensate with the two-stage reviews + final review + independent verification.
- **render.py**: the stdlib `html` module is imported as `_html` (5 functions bind `html` as a local var). For HTML-escaping use the module helpers `_esc` (text) / `_esc_attr_qs` (attribute values), NOT the stdlib module.

## DON'T-BREAK (verify at build; full list in the plan's "Test contracts")
Token-parity (**NO `[data-theme]`/parity-token edits this phase**); THEMES/THEME_GLYPHS/LEGACY_THEMES swiss-first + identical across render.py/wiki.js/studio.js/graph.js; the Phase-2 appearance system + graph `GRAPH_COLORS`/`syncLabelColour`; the **first-anchor contract** on `.okf-concept-list li` (filter by hiding, don't reorder li internals); ToC/index toolbar OUTSIDE the tested `.okf-page__body`; the **conflict-modal DOM + labels** (Task 7 extracts the renderer only); **only `/__validate` is new server surface**; RUN/diff reuse existing endpoints; every `__TOKEN__` placeholder replaced; z-index tiers (graph ≤40, topbar 50, studio modals 70+).

## ROLLBACK / DON'T TOUCH
Git tag `pre-redesign-baseline` (`2066013`). Untracked, leave alone: `okf-loom-mcp/`, `redesign-files-1.zip`, `design/new-layout/workbench-preview.html`.

## DELIVERABLE
Close Task 5's review gate → Tasks 6–8 via subagent-driven-development (suite green, commit per task) → Task 9 verification (full pytest + serve+tunnel+screenshots across the 4 themes + the first-anchor browser suite + roll-up triage + static-build shot) → final whole-Phase-3 **OPUS** review. Then the Editorial Workbench redesign is **feature-complete** — update `editorial-workbench-layout-buildout.md`. **Read `.superpowers/sdd/progress.md` first** for the precise cursor + the deferred-Minors roll-up.
