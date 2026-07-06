# Handover — okf-loom Editorial Workbench · ROUND 2 · DEFERRED ITEMS (to 100% finish)

> Paste everything under the `---` into a fresh session. Self-contained. Round 2 is **feature-complete + merge-approved**; these are the **two deferred, non-blocking items** the final Opus review flagged, left as decisions for the user. Finish both → Round 2 is 100% done.

---

Finish the **two deferred items** from the okf-loom "Editorial Workbench" redesign (ROUND 2). Work in `/l_kitty_kitty/opt/projects/repos/okf-loom` on branch `feature/new-layout` (STAY on it; do NOT branch/merge — the user controls integration). HEAD is `99a0443`. Round 2 (P1 layout · P2 appearance · P3 features) is FEATURE-COMPLETE and passed a final whole-Phase-3 OPUS review as READY-TO-MERGE; full suite is green (1312 passed / 23 skip / 0 real fail). These two items are the only open threads.

## FIRST: read the record
- Memory `editorial-workbench-layout-buildout.md` (final entry = "PHASE 3 COMPLETE → ROUND 2 FEATURE-COMPLETE") — the whole redesign history + both deferred items.
- SDD ledger + full Minor-findings roll-up: git-ignored `.superpowers/sdd/progress.md` (per-task deferred Minors, all triaged by the final review).

## PROCESS
Item 2 is mechanical → one implementer + a two-stage review (or do it directly + one review — advisor tool is UNAVAILABLE, so keep at least one independent review). Item 1 is a **design/semantics decision** → **brainstorm + clarify with the user FIRST** (superpowers:brainstorming), THEN implement the chosen direction. Commit each item separately. Verify the suite stays green after each.

---

## ITEM 1 — reconcile the live↔static search `<mark>` tokenizer (DESIGN DECISION — clarify with user first)

**The finding (from the final Opus review, non-corrupting):** the live and static search UIs highlight underscore/identifier queries at DIFFERENT `<mark>` boundaries.
- **Server (`render.py`):** `_HIGHLIGHT_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)` (render.py:2305) **SPLITS on `_`**. Used at render.py:2338 inside `_highlight(text, query)`. So `user_role` → marks `user` and `role` separately; `a_b` (sub-2-char parts) → marks nothing (no ≥2-char term).
- **Static (`static-search.js`):** `tokenize()` (static-search.js:123) uses `/[\p{L}\p{N}_]+/gu` which **KEEPS `_`**; `highlight()` (static-search.js:218) marks those tokens. So `user_role` → marks `user_role` whole; `a_b` → marks `a_b`.
- Both are entity-safe (match-on-RAW → escape-per-segment → literal `<mark>`); the divergence is only mark *granularity*. Docstrings at render.py:~2320 and static-search.js:~230 now HONESTLY scope the "parity" claim to single-alphanumeric-token queries — so doing nothing is a defensible outcome.

**The nuance that decides the fix — each UI should mark consistently with HOW ITS OWN SEARCH matched:**
- **Static is already internally consistent:** its SEARCH scorer (`scoreEntry`, static-search.js:164) matches the SAME `tokenize()` tokens via substring `indexOf` (static-search.js:104 comment, :150) — keeps `_` for BOTH search and highlight. So `user_role` matches "user_role" and marks "user_role". Correct.
- **Live: VERIFY the live search backend's `_` handling FIRST.** The live search is server-side: `server.py:_handle_search` (server.py:1280) → the "lexical/semantic-lite backends tokenize + score the query" (server.py:77). **Find that backend's query tokenizer** (grep from `_handle_search` into the search/index module) and check whether it SPLITS or KEEPS `_`. If live search SPLITS `_` (matches "user"/"role"), then live highlight (which also splits) is already consistent with live search — and the live↔static difference is a *fundamental* consequence of two different search backends (server lexical vs client substring), not a bug. If live search KEEPS `_`, then live highlight is INCONSISTENT with its own search (marks user+role but matched user_role) — a real fix target.

**Decision tree to take to the user:**
- **(A) Accept as intentional (RECOMMENDED if both UIs are each self-consistent):** the two backends legitimately differ; keep the current code + the honest docstrings. Zero code change. Just confirm the user is fine with identifier queries marking differently between the served studio and a static export.
- **(B) Full live↔static parity:** make both UIs mark identically for identifier queries. This means aligning the *search* tokenizers too (so marks always explain matches) — e.g. make static `tokenize()` split on `_` (mirror the server) so static search+highlight both split, matching live. Bigger surface (touches static SEARCH behavior, not just highlight) → re-verify the static-search tests + the `q=bundle`/`q=user_role` result sets.
- **(C) Minimal internal-consistency fix:** if the live-side investigation shows live *highlight* disagrees with live *search*, fix ONLY that side so each UI's marks match its own matches (leave the live↔static difference documented).

**Verify:** `uv run --with pytest --with pyyaml pytest tests/test_render.py -q` (the `_highlight` tests) + `node --check scripts/okf_loom/viewer/static/static-search.js`; if you touch static search behavior, run the static-search tests too and re-check `/__search?q=user_role` live vs the static build. The existing highlight tests are entity-safety RED-provers — keep them green.

---

## ITEM 2 — promote `--okf-danger` to a real per-theme token (mechanical)

**The finding:** the error-state validation chip uses `color: var(--okf-danger, #d64545)` (studio.css:118), but **`--okf-danger` is undefined**, so the error chip renders a FIXED `#d64545` on all four themes — not theme-adaptive. Its sibling `--okf-warn` IS a themed token, so the warn chip adapts light/dark but error does not. (The Phase-3 constraint was "no new parity tokens" — that discipline is OVER now that Phase 3 shipped, so adding this status-color token is fine.)

**The fix — mirror `--okf-warn`'s structure exactly:**
- `--okf-warn` (+ `--okf-warn-bg`) is defined in wiki.css at **`:root`:82, and the four theme blocks :197, :248, :299, :350** — light blocks use `oklch(0.55 0.12 70)`, dark blocks use the brighter `oklch(0.78 0.13 70)` (dark-mode contrast). (Study studio.css:217's note "theme-aware --okf-ok / --okf-warn tokens so dark-mode contrast holds" — danger completes the ok/warn/danger status set.)
- **Add `--okf-danger`** (a red — hue ≈ 25–30 in oklch) to those SAME five blocks: a light value for `:root`/:197/:299 (light themes) and a brighter value for :248/:350 (dark themes), chosen for ≥AA contrast on the chip's background, in the same style as `--okf-warn` (keep the `#d64545` you're replacing as a rough target for the light value). You likely only need `--okf-danger` (the chip uses the color, not a `-bg`); add `--okf-danger-bg` only if you find a background use.
- **Update the parity test:** `test_theme_blocks_override_full_token_set` (tests/test_render.py:1301) enumerates the required per-theme tokens at test_render.py:1312 (`"okf-ok", "okf-ok-bg", "okf-warn", "okf-warn-bg", …`). **Add `"okf-danger"`** to that list so the test asserts every theme block defines it (this is what locks the fix — it will fail if you miss a block).
- Optional: keep the `var(--okf-danger, #d64545)` fallback in studio.css (harmless belt-and-suspenders) or drop the fallback now that the token exists — your call; keeping it is safer.

**Verify:** `uv run --with pytest --with pyyaml pytest tests/test_render.py -k "theme_blocks_override_full_token_set" -q` (must pass with the new token in all blocks) + a quick screenshot: seed a bundle/state that validates with an ERROR so the chip shows `data-state="error"`, confirm the color now differs light vs dark. (If the demo bundle always validates clean, force an error state via devtools by setting the chip's `data-state="error"` + reading `getComputedStyle().color` across two themes.)

---

## ENV GOTCHAS (unchanged from Phase 3)
- **Tests (sandbox `.venv` ships EMPTY):** `uv run --with pytest --with pyyaml pytest tests/ -q` for the full suite; **ADD `--with playwright`** or the ~76 browser tests aren't collected (you'll see ~1233 instead of 1312 — NOT a regression). System Chrome is present for `channel="chrome"`. **READ the printed summary line — never trust a piped exit code.** Documented flake (rerun ONCE if it's the only failure): `test_comment_mark_wraps_selection` (also `test_agent_watching_toggle_posts_presence`, `test_agent_activity_panel_has_unique_sections`). Baselines: `test_render.py` = 82 passed; full suite = 1312 passed / 23 skipped.
- **Serve for visual check:** Bash `run_in_background:true`, `exec scripts/okf-loom serve docs-bundle --no-open --port 8788 --tunnel`; wait via `curl -s --retry 40 --retry-delay 1 --retry-connrefused http://localhost:8788/demo/showcase -o /dev/null` (NO `sleep` — it's sandbox-blocked, exit 144). Tunnel URL is in the bg task output (`grep trycloudflare`). STOP via the **TaskStop** tool (never `pkill`/`kill`).
- **Screenshots:** Playwright + system Chrome `executable_path=$AIC_PLAYWRIGHT_CHROME_PATH` (`/opt/google/chrome/google-chrome`), `args=["--no-sandbox"]`, `wait_until="load"` (SSE breaks networkidle); seed `okf-theme`/`okf-contrast`/`okf-border` via `context.add_init_script`. Theme keys: `swiss-light`, `swiss-dark`, `technical-light`, `technical-dark`.
- **advisor tool UNAVAILABLE** — compensate with an independent review + your own verification.

## DON'T-BREAK
- `THEMES`/`THEME_GLYPHS`/`LEGACY_THEMES` swiss-first + IDENTICAL across render.py / wiki.js / studio.js / graph.js (Item 2 adds a token to the 4 theme blocks + `:root` in wiki.css only — it does NOT touch the THEME enum). The `test_theme_blocks_override_full_token_set` parity test guards Item 2.
- Everything Phase-3 shipped must stay green: on-page ToC (§6.1), index dashboard (§6.2), live+static search highlight/meta (§6.3), studio RUN/`renderDiffInto`/`/__validate` chip (§6.4). The entity-safety of both highlighters (match-on-RAW → escape-per-segment) MUST be preserved if you touch Item 1.
- Untracked, leave alone: `okf-loom-mcp/`, `redesign-files-1.zip`, `design/new-layout/workbench-preview.html`. Rollback tag: `pre-redesign-baseline` (2066013).

## DELIVERABLE
Item 1 (brainstorm+clarify with user → implement chosen direction OR accept-as-is) + Item 2 (add `--okf-danger` to 5 blocks + the parity test) → suite green → commit each → then Round 2 is 100% DONE. Update memory `editorial-workbench-layout-buildout.md` accordingly.
