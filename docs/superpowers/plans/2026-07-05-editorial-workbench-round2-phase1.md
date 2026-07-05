# Editorial Workbench Round 2 — Phase 1 (Layout & Chrome) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 380px reflowing docked studio panel with a ~48px always-docked icon **rail + overlay panels** (no reflow); make the inline comment **pin functional** (click → jump + open thread at that comment); add a **Workbench ↔ Focus** reading mode that fixes the trapped **Split** view; turn the thin status strip into a bordered-button **footer toolbar**; flatten the **Related** section into the nav; and fix overlay **spacing** — all on branch `feature/new-layout`, keeping the suite green.

**Architecture:** All Phase-1 changes live in four **static** viewer assets — `studio.js`, `studio.css`, `wiki.css`, `wiki.js` — plus one docs edit (`design/new-layout/SPEC.md`). **No `render.py` or template edits in Phase 1**, so the running serve never needs a restart — static assets are served fresh; just reload the browser. The studio chrome (rail, overlay, footer) is built client-side by `studio.js` at boot (the server injects only a JSON config + asset links via `server.py:_studio_bootstrap`; it is untouched). Every aesthetic value stays a `var(--okf-*)` token (the decoupling contract); the rail/overlay/focus/footer reuse the existing per-theme token set (four themes: swiss/technical × light/dark, Swiss default).

**Tech Stack:** vanilla ES modules (`studio.js`, `wiki.js` — no build step, `node --check` for syntax), plain CSS custom properties (`studio.css`, `wiki.css`), Python `pytest` + Playwright/system-Chrome for the browser suite. Run everything via `scripts/okf-loom`. Python 3.11+.

**Approved contract:** `docs/superpowers/specs/2026-07-05-editorial-workbench-round2-design.md` (commit `b4a0159`). This plan implements **§4 (Phase 1)** only; §5 (appearance) and §6 (features) are separate later plans.

---

## The decoupling contract (do not violate)

1. **Layout CSS references tokens only.** No hardcoded colour/font/border/radius/spacing in any `.okf-*` product rule — every such value is `var(--okf-*)`. Structural sizes (`--okf-topbar-h`, `--okf-status-h`, the new `--okf-rail-w`) live in `:root`; aesthetic values live in the four theme blocks.
2. **Each shipped theme stays one complete `[data-theme="…"]` block.** `test_render.py::test_theme_blocks_override_full_token_set` `split()`s on the exact selector to the first `}`; Phase 1 adds **no** token-checked tokens, so leave the theme blocks alone except where a step says otherwise.
3. **Preserve the hard-contract markers** (see "Test contracts" below). Renamed/retired chrome must keep the class names + JS APIs the studio browser/e2e suite drives.
4. **No Apple/Windows cue** — no `⌘`/`⊞` glyph, no window dots. (Phase 1 adds no new keycaps.)
5. **THEMES / THEME_GLYPHS stay swiss-first and identical** across `render.py:557`, `wiki.js:27`, `studio.js:220`, `graph.js:30`. Phase 1 does not touch them; do not disturb them.

---

## Test contracts — MUST preserve (verified against `tests/` at `b4a0159`)

| Contract | Where asserted | What the task must keep |
|---|---|---|
| Sidebar `aria-label="Navigation"` on the `.okf-page__sidebar` aside; rail `class="okf-nav"` + `okf-nav__group` + `okf-nav__link--current` | `test_render.py:993` `test_iter1_concept_page_sidebar_labeled_related` | Task 5 must **not** touch the aside's `aria-label` or the `.okf-nav*` class strings (server-rendered). |
| `.okf-panel__body` / `.okf-panel__section-title` / `.okf-panel__section-link` selectors; `window.okfLoomStudio.openPanel('comments'\|'changes'\|'agent-activity')` API | `test_studio_iter1_browser.py` (i1b:433,1185,1690,1748,1868,1958,2045; body-selector hits 1202+,2046+) | Tasks 1/4 must keep `openPanel(kind)` exposed on `window.okfLoomStudio` and keep those panel sub-classes. |
| `.okf-split__divider` with `role="separator"`, `aria-orientation="vertical"`, `tabindex="0"`; ArrowRight **grows** `aria-valuenow` under `?view=split` | i1b:1596 `test_split_view_divider_and_synced_scroll` | Task 3 must keep the divider element + `applySplitPct` incrementing `aria-valuenow`. |
| `.okf-studio-bar` is **non-sticky** (`position:static`) on mobile (≤900px) | i1b:1417 `test_mobile_sticky_chrome_under_64px_and_search_note_guard` | Task 4 must keep the `@media (max-width:900px) .okf-studio-bar { position: static }` rule. |
| `.okf-comment-mark` visible + `data-comment-id`; `.okf-comment-marker` width/height **≥24px** + `aria-label` contains "Comment" + `data-state` | i1b:230,267,1284; i2e:295 | Task 2 restyle must keep the mark's `data-comment-id`, keep marker ≥24px, keep the marker aria-label + `data-state`. |
| `.okf-viewswitch__btn[data-mode]` + register-viewmode API | i1b:556 `test_register_viewmode_adds_button` | Tasks 3/4 keep the view-switch button structure + `data-mode`. |
| `.okf-studiobtn--primary` on "Keep mine" (not on "Take agent's") | i1b:1491 | Do not touch conflict-modal buttons. |
| `okf-viewer--search` body class; `okf-focus-root` (graph node halo — **distinct** from layout `okf-focus`) | rn:1404; vb:383,751 | Task 3's `data-okf-focus` is net-new and must not collide with `okf-focus-root` (graph). |

**FREE to restyle/rename (zero test hits, verified):** `body.okf-studio-open` (the reflow class — drop it freely), `okf-statseg`, `okf-studio-toggle`, `okf-sidebar-panel`, `okf-local-graph`, `setView`, `closePanel`, `jumpToCommentMark`, bare `okf-view`/`data-okf-view`, `okf-conn` (only in a comment; the assertion counts `<li>`), and net-new `okf-focus`/`data-okf-focus`.

**Known flake (not a regression):** `test_studio_iter1_browser.py:230 test_comment_mark_wraps_selection` — a 120 ms-debounced `selectionchange` load-flake; passes on rerun. If it is the *only* failure, rerun it before worrying.

---

## New names locked for this phase (use these exact strings everywhere)

- **Rail:** container `.okf-rail`; icon button `.okf-rail__btn`; count badge `.okf-rail__badge`; collapse control `.okf-rail__toggle`. Width token `--okf-rail-w: 48px` (add to `:root`). Body reserve class `body.okf-has-rail` (→ `padding-right: var(--okf-rail-w)` on concept pages ≥900px). Rail is fixed to the right edge, top→footer.
- **Overlay:** reuse `.okf-panel` (re-positioned from docked to overlay) + the **existing** vestigial scrim `.okf-panel-overlay` (studio.css:1133, studio.js:3183) — now *shown* on open as a transparent click-catcher.
- **Focus mode:** attribute `data-okf-focus` on `document.documentElement` (`<html>`). Present = Focus on. JS `setFocus(on)` + `toggleFocus()`. Not persisted in Phase 1.
- **Footer:** keep `.okf-studio-bar--status`; add `.okf-studio-bar__divider` between action group (left) and ambient group (right).
- **Related flat:** reuse `.okf-nav__group` for the "Related" label; restyle `.okf-local-graph`/`__node` flat to match `.okf-nav__link`. New wrapper `.okf-related` (flat section) around the label + list.

---

## File-structure map (what each touched file owns this phase)

- `scripts/okf_loom/viewer/static/studio.js` — builds the studio chrome: **new rail** (`buildRail`/`mountRail`), overlay open/close (`openPanel`/`closePanel` — drop the reflow, show the scrim), functional pin wiring (`wireCommentMarkClicks` + new `jumpToCommentCard`), Focus (`setFocus`/`toggleFocus` + split auto-enter in `setView`), footer reorg (`mountBar`), Related-flat (`buildSidebarPanels`).
- `scripts/okf_loom/viewer/static/studio.css` — rail styling; `.okf-panel` overlay positioning + scrim; comment pin (mark/marker) active-state restyle; `.okf-view`/split-grid reconcile; footer toolbar (drop the `--status .okf-studiobtn` quieting override, bump height, divider); `.okf-panel__intents` spacing fix.
- `scripts/okf_loom/viewer/static/wiki.css` — `--okf-rail-w` token; `.okf-page__main` Focus cap-drop + rendered re-measure; `.okf-page`/frame collapse in Focus; Related-flat (`.okf-sidebar-panel`/`.okf-local-graph` flat restyle).
- `scripts/okf_loom/viewer/static/wiki.js` — `renderLocalGraph` flat markup (title → nav-group; nodes already buttons).
- `design/new-layout/SPEC.md` — reconcile §3.4/§8 (docs, Task 0).
- `tests/test_studio_iter1_browser.py` — new behavioural tests (rail, overlay, pin, focus, footer). `tests/test_render.py` unaffected (no render.py change).

**Environment recipe (from the handover — the prior session got bitten):**
- Foreground `sleep`/`pkill`/`kill` are **sandbox-blocked**. Serve in the background: `exec scripts/okf-loom serve docs-bundle --no-open` (loopback :8787). Wait with `curl -s --retry 20 --retry-delay 1 --retry-connrefused http://localhost:8787/...` (**no sleep**). Stop/restart via the **TaskStop** tool on the bg task id (never `pkill`).
- Static assets (studio.js/css, wiki.css/js) are served **fresh** — just reload. (Phase 1 edits no `render.py`/templates, so no restart is needed at all.)
- Tests: `python3 -m pip install pytest playwright pytest-playwright` (browser download disabled; system Chrome auto-used via `AIC_PLAYWRIGHT_CHROME_PATH`). Run `python3 -m pytest tests/ -q` (~3 min incl. e2e). **Never** pipe pytest through `| tail` and trust the exit code — **read the printed summary line**.
- Self-review screenshots: Playwright + system Chrome, `executable_path=$AIC_PLAYWRIGHT_CHROME_PATH`, `args=["--no-sandbox"]`, `wait_until="load"` (SSE breaks `networkidle`). Default theme is Swiss (don't seed `localStorage['okf-theme']`); seed it to shoot the other three.

---

## PHASE 1 — Layout & chrome

### Task 0: Reconcile SPEC.md §3.4 / §8 to the thin-rail + overlay decision

**Files:**
- Modify: `design/new-layout/SPEC.md` — §3.4 (lines ~69-79) and §8 (lines ~183-191).

- [ ] **Step 1: Rewrite §3.4** (currently titled "Studio loop = docked panel", describing the `body.okf-studio-open` reflow). Replace the body of §3.4 with the rail+overlay decision:

```markdown
**3.4 Studio loop = thin rail + overlays** *(REVISED 2026-07-05, Round 2 —
supersedes the docked-panel decision. The dock reflowed the reading column and
squeezed the split view; the user chose a thin always-docked rail so controls
stay first-class, with panels that pop OVER content on demand.)* — a **thin
(~48px) icon rail** docked at the right edge on concept pages (≥900px):
Comments·N / Changes / Outline / Metadata / quick-actions / rail-toggle. The
page reserves a slim `--okf-rail-w` gutter so content never sits under the rail.
Clicking a rail icon opens the corresponding **overlay panel** (reuse
`.okf-panel`, ~380px) that pops OVER the reading column (no reflow), carries
`--okf-pop-shadow`, and dismisses on **Esc / click-away** (the transparent
`.okf-panel-overlay` scrim). Tabs inside the overlay: **Comments / Changes /
Outline / Metadata**; the **Quick-Action directive buttons** sit at the top of
the Comments overlay where they pre-fill the composer.
```

- [ ] **Step 2: Rewrite the §8 revision note** (the `*(REVISED …)*` paragraph that withdrew the "no docked comments column" non-goal). Replace it with:

```markdown
*(REVISED 2026-07-05, Round 2: the studio loop is a thin rail + on-demand
overlay panels (see §3.4), NOT a docked reflow column. The reading column is
never reflowed by studio chrome — overlays pop over it. Swiss remains the
default family. A Workbench ↔ Focus reading mode (Focus collapses nav + rail +
frame for Source/Split) is added; Rendered prose stays at the ~76ch measure
even in Focus.)*
```

- [ ] **Step 3: Grep for other stale "docked panel" references** in SPEC.md and fix any that still describe the reflow (e.g. the §3.3 pointer to §3.4, or any "reserves `--okf-studio-w`" phrasing). Keep edits minimal and factual:

Run: `grep -n "docked\|studio-w\|reflow\|studio-open" design/new-layout/SPEC.md`
Expected: only the (now-updated) §3.4/§8 mentions remain; fix any other hit that still asserts the reflow.

- [ ] **Step 4: Commit**

```bash
git add design/new-layout/SPEC.md
git commit -m "docs(design): reconcile SPEC §3.4/§8 to thin-rail + overlay decision"
```

---

### Task 1: Thin rail + overlay panels (revises §3.4)

Replace the docked reflow with a thin rail + overlay. Three sub-steps: (1a) CSS for the rail + overlay + scrim, (1b) build/mount the rail and re-wire open/close in JS + move Comments/Changes/Studio-toggle out of the footer, (1c) tests.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — add `--okf-rail-w` to `:root` (after `--okf-status-h` at line 119).
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-panel` (1140-1156), `body.okf-studio-open` (1157-1159), `.okf-panel-overlay` (1133-1139), the 900px block (1198-1206); add `.okf-rail*`.
- Modify: `scripts/okf_loom/viewer/static/studio.js` — panel mount (3182-3216), `openPanel`/`closePanel` (3220-3264), boot auto-open (4337-4375), footer assembly (406-413) + `mountBar` (415-422).
- Test: `tests/test_studio_iter1_browser.py`.

#### 1a — CSS: rail, overlay, scrim

- [ ] **Step 1: Add the rail width token to `:root`.** In `wiki.css` immediately after line 119 (`--okf-status-h: 30px;`) add:

```css
  --okf-rail-w: 48px;          /* thin studio icon rail (Round 2) */
```

- [ ] **Step 2: Re-position `.okf-panel` from docked to overlay.** In `studio.css`, replace the base `.okf-panel` rule (1140-1156) with an overlay that pops to the LEFT of the rail, over content, with pop-shadow:

```css
/* Editorial Workbench Round 2: the studio panel is an OVERLAY that pops OVER
 * the reading column from a rail icon — it no longer reflows content. It sits
 * to the left of the thin rail, elevated by --okf-pop-shadow, dismissed on
 * Esc / click-away (the .okf-panel-overlay scrim). */
.okf-panel {
  position: fixed;
  top: var(--okf-topbar-h);
  right: var(--okf-rail-w);
  bottom: var(--okf-status-h);
  width: var(--okf-studio-w, 380px);
  background: var(--okf-bg-elev);
  border-left: var(--okf-border-w) solid var(--okf-border-strong);
  box-shadow: var(--okf-pop-shadow);   /* elevation over content */
  z-index: 8;                          /* over content + scrim(7); under status(9)/topbar(10) */
  display: flex;
  flex-direction: column;
}
.okf-panel[hidden] { display: none; }
```

- [ ] **Step 3: Drop the reflow rule.** Replace `body.okf-studio-open { padding-right: var(--okf-studio-w, 380px); }` (studio.css:1157-1159) with the slim rail reserve (always-on on concept pages ≥900px, not tied to an open panel):

```css
/* The reading column reserves a slim gutter for the always-docked rail so
 * content never sits under it. The overlay panel does NOT reflow content. */
body.okf-has-rail { padding-right: var(--okf-rail-w); }
```

- [ ] **Step 4: Make the scrim a transparent click-catcher.** Replace `.okf-panel-overlay` (studio.css:1133-1139) so it catches click-away without a modal dim, sitting just under the panel:

```css
.okf-panel-overlay {
  position: fixed;
  inset: 0;
  background: transparent;   /* click-catcher, not a modal dim (pops OVER, not modal) */
  z-index: 7;                /* under panel(8)/rail(8); over content */
}
.okf-panel-overlay[hidden] { display: none; }
```

- [ ] **Step 5: Add the rail CSS.** Append a new block in `studio.css` (near the panel rules, ~after 1156). The rail is a fixed vertical column of icon buttons:

```css
/* ---- Thin studio rail (Round 2) ------------------------------------- */
.okf-rail {
  position: fixed;
  top: var(--okf-topbar-h);
  right: 0;
  bottom: var(--okf-status-h);
  width: var(--okf-rail-w);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--okf-space-1);
  padding: var(--okf-space-2) 0;
  background: var(--okf-bg-elev);
  border-left: var(--okf-border-w) solid var(--okf-border);
  z-index: 8;
}
.okf-rail[hidden] { display: none; }
.okf-rail__btn {
  position: relative;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font: inherit;
  font-size: var(--okf-text-base);
  border: var(--okf-border-w) solid transparent;
  border-radius: var(--okf-radius-sm);
  background: transparent;
  color: var(--okf-fg-muted);
  cursor: pointer;
}
.okf-rail__btn:hover { color: var(--okf-fg); background: var(--okf-bg-inset); }
.okf-rail__btn[aria-pressed="true"] {
  color: var(--okf-active-fg);
  background: var(--okf-active-fill);
  border-color: var(--okf-active-border);
}
.okf-rail__btn:focus-visible { outline: 2px solid var(--okf-accent); outline-offset: 1px; }
.okf-rail__badge {
  position: absolute;
  top: -2px;
  right: -2px;
  min-width: 15px;
  height: 15px;
  padding: 0 3px;
  border-radius: var(--okf-radius-pill);
  background: var(--okf-accent);
  color: var(--okf-accent-on);
  font-size: 10px;
  font-weight: 700;
  line-height: 15px;
  text-align: center;
}
.okf-rail__badge[hidden] { display: none; }
.okf-rail__spacer { flex: 1 1 auto; }   /* pushes the rail toggle to the bottom */
```

- [ ] **Step 6: Update the mobile (≤900px) panel block** (studio.css:1198-1206). On mobile the rail hides and the overlay goes full-width; there is no slim reserve. Replace the block with:

```css
@media (max-width: 900px) {
  /* Narrow screens: no rail reserve; the overlay covers the full width and
   * lifts above the chrome. The user opens/closes it from the footer. */
  .okf-rail { display: none; }
  body.okf-has-rail { padding-right: 0; }
  .okf-panel { top: 0; right: 0; bottom: 0; z-index: 71; }
  .okf-panel-overlay { background: rgba(15, 23, 42, 0.35); z-index: 70; } /* modal dim on mobile */
}
```
(The shared 900px block at studio.css:1434 still sets `.okf-panel { width: 100vw }` — leave it.)

- [ ] **Step 7: Sanity — CSS is well-formed** (no test yet; visual verify in 1c):

Run: `python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/studio.css').read_text(); assert s.count('{')==s.count('}'), (s.count('{'), s.count('}'))"`
Expected: no assertion error (braces balanced).

#### 1b — JS: build the rail, re-wire open/close, move controls out of the footer

- [ ] **Step 8: Show the scrim on open; drop the reflow class.** In `studio.js` `openPanel` (3220-3244), change the docked behaviour to overlay behaviour. Replace these three lines inside `openPanel`:

```js
    document.body.classList.add("okf-studio-open");
    try { localStorage.setItem("okf-studio-collapsed", "0"); } catch (e) {}
    panelShell.hidden = false;
    panelOverlay.hidden = true;   // docked, not modal — never dim the page
```
with:
```js
    panelShell.hidden = false;
    panelOverlay.hidden = false;  // overlay: show the click-away scrim
```
(Delete the `okf-studio-open` add and the `okf-studio-collapsed` write — the panel is now on-demand, not a persisted dock.)

- [ ] **Step 9: Hide the scrim on close; drop the reflow class.** In `closePanel` (3250-3263) replace:

```js
    document.body.classList.remove("okf-studio-open");
    try { localStorage.setItem("okf-studio-collapsed", "1"); } catch (e) {}
    panelShell.hidden = true;
    panelOverlay.hidden = true;
```
with:
```js
    panelShell.hidden = true;
    panelOverlay.hidden = true;
```
(The existing `panelOverlay.addEventListener("click", closePanel)` at studio.js:3208 now does real work — click-away closes. Keep it. The Esc handler at 3210-3215 stays.)

- [ ] **Step 10: Add a rail builder + mount.** In `studio.js`, add a `buildRail()` and mount it in `boot()`. Add this function near the panel construction (after the `togglePanel` def, ~3265). It reuses `openPanel`/`togglePanel` and the existing `commentsBtn`/`changesBtn` badge elements are being retired from the footer (Step 12), so the rail owns the count badge now:

```js
  // Editorial Workbench Round 2: the thin studio rail. Always docked on
  // concept pages (>=900px); each icon opens the matching overlay tab. The
  // Comments icon carries a live count badge (synced by updateCommentCount).
  var railCommentBadge = null;
  function buildRail() {
    var rail = el("aside", { class: "okf-rail", role: "toolbar",
      "aria-label": "Studio", "aria-orientation": "vertical" });
    function railBtn(id, glyph, label) {
      var b = el("button", { type: "button", class: "okf-rail__btn",
        "aria-pressed": "false", "aria-controls": "okf-panel",
        title: label, "aria-label": label, text: glyph });
      b.dataset.railId = id;
      b.addEventListener("click", function () { togglePanel(id); });
      rail.appendChild(b);
      return b;
    }
    var cBtn = railBtn("comments", "💬", "Comments");   // 💬
    railCommentBadge = el("span", { class: "okf-rail__badge", "aria-hidden": "true", hidden: "", text: "0" });
    cBtn.appendChild(railCommentBadge);
    railBtn("changes", "↻", "Changes");                      // ↻
    railBtn("outline", "☰", "Outline");                      // ☰
    railBtn("metadata", "ⓘ", "Metadata");                    // ⓘ
    rail.appendChild(el("span", { class: "okf-rail__spacer", "aria-hidden": "true" }));
    // Quick-actions (+) jumps to the Comments overlay (its intents toolbar).
    var plus = el("button", { type: "button", class: "okf-rail__btn",
      title: "Quick actions", "aria-label": "Quick actions", "aria-controls": "okf-panel", text: "+" });
    plus.addEventListener("click", function () { openPanel("comments", { focusComposer: false }); });
    rail.appendChild(plus);
    document.body.appendChild(rail);
    railButtons = rail.querySelectorAll(".okf-rail__btn[data-rail-id]");
    return rail;
  }
```
Add a module-scope `var railButtons = [];` near the other panel handles (~top of the panel section, e.g. beside `panelLastFocus` at 3218).

- [ ] **Step 11: Sync the rail's active state + comment badge.** In `openPanel` (after the `panelTabBtns` aria-selected loop ~3237-3239) add rail-button pressed sync; and update `closePanel` to clear it. Insert in `openPanel`:

```js
    // Reflect the open tab on the rail icons.
    (railButtons || []).forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.railId === id ? "true" : "false");
    });
```
and in `closePanel` (after the `commentsBtn/changesBtn` aria-expanded reset):
```js
    (railButtons || []).forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
```
Then find where the footer comment badge is updated (grep `commentsBadge` — studio.js sets its text when comments change) and mirror the count onto `railCommentBadge`: wherever `commentsBadge.textContent = String(n)` (or similar) is set, add:
```js
      if (railCommentBadge) {
        railCommentBadge.textContent = String(n);
        railCommentBadge.hidden = !(n > 0);
      }
```
(Grep exact site: `grep -n "commentsBadge" scripts/okf_loom/viewer/static/studio.js`. Apply the mirror at each assignment.)

- [ ] **Step 12: Remove Comments/Changes/Studio-toggle from the footer; mount the rail.** In the footer assembly (studio.js:406-413) the right group appends `studioToggle`, `commentsBtn`, `changesBtn`, `paletteBtn`, `connChip`. The rail now owns Comments/Changes and the dock toggle is gone. Replace lines 406-413:

```js
  // Assemble bar (view switch only on concept pages). Comments/Changes now
  // live in the rail; the dock toggle is retired. Footer keeps only the
  // wired actions + ambient (reorganised in Task 4).
  rightGroup.appendChild(paletteBtn);
  rightGroup.appendChild(connChip);
  bar.appendChild(leftGroup);
  bar.appendChild(rightGroup);
```
(The `commentsBtn`/`changesBtn`/`studioToggle` elements are still constructed at 300-404 and referenced by `openPanel`/`closePanel` aria-sync — leave the constructors so those references don't throw; they simply are no longer appended to the DOM. `commentsBadge` is still updated in memory and mirrored to the rail badge in Step 11.)

- [ ] **Step 13: Mount the rail at boot; drop the auto-open dock.** In `boot()` (studio.js:4337-4375), on concept pages, mount the rail and set the reserve class, and remove the auto-open of the comments dock. Replace the boot block (4346-4354):

```js
    if (isConceptPage()) {
      ensureViewWrap();
      setView(state.view); // also deep-links + lazy-loads source if needed
      bindSelectionAffordance();
      buildSidebarPanels();
      // Round 2: always-docked thin rail (>=900px); overlays open on demand
      // (no auto-open dock). The slim reserve keeps content clear of the rail.
      if (window.innerWidth > 900) {
        buildRail();
        document.body.classList.add("okf-has-rail");
      }
    } else if (document.getElementById("detail-body")) {
```

- [ ] **Step 14: Sanity — JS parses:**

Run: `node --check scripts/okf_loom/viewer/static/studio.js`
Expected: no output (valid).

#### 1c — Tests + commit

- [ ] **Step 15: Write the failing browser tests.** Add to `tests/test_studio_iter1_browser.py` (near the other panel tests). These assert the rail exists, opening does NOT reflow the body, and Esc/scrim close:

```python
def test_rail_present_and_overlay_does_not_reflow(studio_page):
    """Round 2: a thin rail is docked; opening a panel overlays (no reflow)."""
    page = studio_page  # concept page fixture with studio booted (>900px viewport)
    page.wait_for_selector(".okf-rail", timeout=10000)
    # Rail has the four tab icons + quick-actions.
    ids = page.eval_on_selector_all(
        ".okf-rail__btn[data-rail-id]", "els => els.map(e => e.dataset.railId)")
    assert set(ids) >= {"comments", "changes", "outline", "metadata"}
    # Body must NOT reserve 380px (no docked reflow) — only the slim rail gutter.
    pad_before = page.evaluate("getComputedStyle(document.body).paddingRight")
    page.click('.okf-rail__btn[data-rail-id="comments"]')
    page.wait_for_selector(".okf-panel:not([hidden])", timeout=5000)
    pad_after = page.evaluate("getComputedStyle(document.body).paddingRight")
    assert pad_before == pad_after, "opening a panel must not reflow the body"
    # Slim reserve == rail width (48px), never the 380px dock width.
    assert pad_after.startswith("48"), f"expected 48px rail reserve, got {pad_after}"

def test_overlay_closes_on_scrim_and_esc(studio_page):
    page = studio_page
    page.wait_for_selector(".okf-rail", timeout=10000)
    page.click('.okf-rail__btn[data-rail-id="comments"]')
    page.wait_for_selector(".okf-panel:not([hidden])", timeout=5000)
    # click-away on the scrim closes.
    page.eval_on_selector(".okf-panel-overlay", "el => el.click()")
    page.wait_for_selector(".okf-panel[hidden]", timeout=5000)
    # re-open, then Esc closes.
    page.click('.okf-rail__btn[data-rail-id="comments"]')
    page.wait_for_selector(".okf-panel:not([hidden])", timeout=5000)
    page.keyboard.press("Escape")
    page.wait_for_selector(".okf-panel[hidden]", timeout=5000)
```
Note: match the file's existing fixture name/pattern for a booted concept page at a desktop viewport (grep the file for an existing `def test_…(…)` that opens a concept page with `openPanel` — reuse that fixture; if the suite uses a helper like `_studio_page(...)` instead of a fixture, call it the same way the neighbouring tests do).

- [ ] **Step 16: Run the new tests — verify they FAIL (before wiring is confirmed) then PASS after 1a/1b:**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "rail or overlay_closes" -q`
Expected: PASS (rail built, overlay opens without reflow, scrim/Esc close). Read the printed summary line — do not trust a tailed exit code.

- [ ] **Step 17: Run the panel-contract tests — verify still green** (the `openPanel(kind)` API + panel sub-classes must survive):

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "change_list or agent_activity_panel or claimed_comment" -q`
Expected: PASS.

- [ ] **Step 18: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css scripts/okf_loom/viewer/static/wiki.css tests/test_studio_iter1_browser.py
git commit -m "feat(studio): thin rail + overlay panels replace the docked dock"
```

---

### Task 2: Functional comment pin

Make the inline pin a clear, active-state affordance and wire it end-to-end: click a mark → jump to the prose mark → open the Comments overlay → scroll+pulse **that comment's card**. Today `wireCommentMarkClicks` (studio.js:4329) only opens the panel (ignores `data-comment-id`); comment cards carry no `data-comment-id`, so the card-scroll is **new machinery** modelled on `jumpToActivity` (studio.js:3498).

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-comment-mark` (512-542), `.okf-comment-marker` (455-510).
- Modify: `scripts/okf_loom/viewer/static/studio.js` — `wireCommentMarkClicks` (4329-4335), the comment-card builder (grep `buildCommentList` / the `.okf-comment` card element), a new `jumpToCommentCard`.
- Test: `tests/test_studio_iter1_browser.py`.

- [ ] **Step 1: Restyle the inline mark with active-state tokens** (clear affordance, still legible in prose). Replace `.okf-comment-mark` open-state block (studio.css:517-528) — keep `cursor: pointer` and `data-comment-id` untouched:

```css
.okf-comment-mark {
  background: var(--okf-active-fill);
  color: var(--okf-active-fg);
  border-bottom: 2px solid var(--okf-active-border);
  border-radius: var(--okf-radius-sm);
  padding: 0 2px;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
  cursor: pointer;   /* Editorial Workbench §3.3: the span is a pin. */
}
```
(Swiss's `--okf-active-fill` is the solid accent with `--okf-active-fg` = accent-on — a bold highlight; Technical's is the tint with accent text — a subtle highlight. Both read as "clickable". Keep the existing `[data-comment-state="resolved"]`/`"claimed"`/`--stale`/`.okf-pulse` variants at 529-542 unchanged so resolved/claimed still mute.)

- [ ] **Step 2: Strengthen the margin marker** into an obvious active-state dot while keeping the ≥24px target + aria-label + `data-state` (test contract i1b:1284). In `.okf-comment-marker` (studio.css:455-478) change the resting look to the active tokens:

```css
.okf-comment-marker {
  position: absolute;
  pointer-events: auto;
  width: 24px;
  height: 24px;
  border-radius: var(--okf-radius-pill);
  border: var(--okf-border-w) solid var(--okf-active-border);
  background: var(--okf-active-fill);
  color: var(--okf-active-fg);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  line-height: 22px;
  text-align: center;
  cursor: pointer;
  padding: 0;
  box-shadow: var(--okf-shadow);
  left: 0;
}
```
(Leave the `:hover`/`:focus-visible` at 479-482, the `[data-state="resolved"|"claimed"|"dismissed"]` overrides at 484-491, and the `--stub` rules at 492-510 as-is — they still win for resolved/claimed and preserve the 24×24 hit area.)

- [ ] **Step 3: Add `jumpToCommentCard`** (new) in `studio.js`, mirroring `jumpToActivity` (3498-3509). Place it next to `jumpToCommentMark` (~1285):

```js
  // Open the Comments overlay and scroll+pulse the card for a given comment.
  // Mirrors jumpToActivity (changes panel). Requires cards to carry
  // data-comment-id (added in the card builder below).
  function jumpToCommentCard(commentId) {
    openPanel("comments");
    var body = panelBodyEl();
    if (!body) return false;
    // Cards render async on openPanel; poll briefly for the target.
    var tries = 0;
    (function find() {
      var card = body.querySelector('.okf-comment[data-comment-id="' + cssEscape(commentId) + '"]');
      if (!card) { if (tries++ < 20) return void setTimeout(find, 25); return; }
      card.scrollIntoView({ block: "center", behavior: REDUCED_MOTION ? "auto" : "smooth" });
      if (!REDUCED_MOTION) {
        card.classList.remove("okf-pulse");
        void card.offsetWidth;
        card.classList.add("okf-pulse");
      }
    })();
    return true;
  }
```
(`.okf-pulse` already has the highlight keyframe — studio.css:539. If `.okf-comment.okf-pulse` needs a background pulse, the existing `okf-pulse-highlight` animation applies; verify a card is a reasonable pulse target during the browser pass and add `.okf-comment.okf-pulse { animation: okf-pulse-highlight 1.4s ease-out 1; }` if the existing selector list doesn't already cover `.okf-comment`.)

- [ ] **Step 4: Tag comment cards with `data-comment-id`.** Grep the card builder:

Run: `grep -n "okf-comment\"" scripts/okf_loom/viewer/static/studio.js | head` and `grep -n "function buildCommentList\|function renderComment\b\|class: \"okf-comment\"" scripts/okf_loom/viewer/static/studio.js`

At the site that creates each card element (the `el("…", { class: "okf-comment" … })` or equivalent per-comment container inside `buildCommentList`), add the id attribute. For example, where the card is created:
```js
    var card = el("article", { class: "okf-comment", "data-comment-id": c.id, /* …existing… */ });
```
Add `"data-comment-id": c.id` to the existing attrs object (do not change other attrs). If cards are keyed by a different variable than `c.id`, use whatever the comment id is in that scope (the same id `jumpToCommentMark` matches on the mark).

- [ ] **Step 5: Wire the inline-mark click to jump+open+scroll.** Replace `wireCommentMarkClicks` (studio.js:4329-4335):

```js
  function wireCommentMarkClicks() {
    document.addEventListener("click", function (e) {
      var t = e.target;
      var mark = t && t.closest && t.closest(".okf-comment-mark");
      if (!mark) return;
      e.preventDefault();
      var id = mark.getAttribute("data-comment-id");
      jumpToCommentMark(id);       // scroll+pulse the prose mark
      if (id) jumpToCommentCard(id); // open overlay + scroll+pulse the card
      else openPanel("comments");
    });
  }
```

- [ ] **Step 6: Point the margin-marker click at the same path.** In `rebuildMarginMarkers` the marker click (studio.js:1466-1469) currently calls `jumpToCommentMark` then `openPanel` with a no-op ternary. Replace it with:

```js
      marker.addEventListener("click", function () {
        jumpToCommentMark(c.id);
        jumpToCommentCard(c.id);
      });
```

- [ ] **Step 7: Sanity:**

Run: `node --check scripts/okf_loom/viewer/static/studio.js`
Expected: valid.

- [ ] **Step 8: Write the failing test** in `tests/test_studio_iter1_browser.py`:

```python
def test_comment_pin_opens_thread_at_card(studio_page_with_comment):
    """Clicking an inline pin jumps to it AND opens the thread scrolled to the card."""
    page = studio_page_with_comment  # concept page with a known comment id
    cid = page.get_attribute(".okf-page__body mark.okf-comment-mark", "data-comment-id")
    assert cid
    page.click(".okf-page__body mark.okf-comment-mark")
    page.wait_for_selector(".okf-panel:not([hidden])", timeout=5000)
    card = page.wait_for_selector(f'.okf-panel__body .okf-comment[data-comment-id="{cid}"]', timeout=5000)
    assert card is not None
```
(Reuse whatever fixture the existing `test_comment_mark_wraps_selection`/`test_comment_marker_target_size_and_label` use to get a page with a comment; name the test's fixture accordingly. If those tests create the comment inline, replicate that setup.)

- [ ] **Step 9: Run — the new test PASSES and the marker-size + mark tests stay green:**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "comment_pin or comment_marker_target or comment_mark_reapplied" -q`
Expected: PASS. (`test_comment_mark_wraps_selection` is the known flake — if it alone fails, rerun it.)

- [ ] **Step 10: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css tests/test_studio_iter1_browser.py
git commit -m "feat(studio): functional comment pin — click jumps + opens thread at the card"
```

---

### Task 3: Workbench ↔ Focus mode + Split fix

Add a `data-okf-focus` reading mode that collapses nav + rail + frame and drops the `.okf-page__main` cap so Source/Split fill the width, while Rendered stays centered at ~76ch. Reconcile the split grid so the divider drag actually resizes (it currently sets `--okf-split-pct` that the CSS ignores). Split **auto-enters** Focus (the real fix) and exits on leaving split.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — `.okf-page__main` (1588-1594) + new `[data-okf-focus]` rules; `.okf-page` frame collapse in Focus.
- Modify: `scripts/okf_loom/viewer/static/studio.css` — split grid (292-301) to consume `--okf-split-pct`.
- Modify: `scripts/okf_loom/viewer/static/studio.js` — `applySplitPct` (467-475), `setView` (578-593), new `setFocus`/`toggleFocus`.
- Test: `tests/test_studio_iter1_browser.py`.

- [ ] **Step 1: Add the Focus CSS.** In `wiki.css`, after the `.okf-page__main` rule (ends line 1594) add the Focus overrides. Focus collapses the frame + nav, uncaps `__main`, and re-applies the ~76ch measure to the **rendered** view only (spec §8: no edge-to-edge prose):

```css
/* Editorial Workbench Round 2 — Focus mode. Collapses nav + rail + frame and
 * lets Source/Split bleed wide; Rendered prose stays at the ~76ch measure. */
:root[data-okf-focus] .okf-page {
  max-width: none;
  margin: 0;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  grid-template-columns: minmax(0, 1fr);   /* nav column gone */
}
:root[data-okf-focus] .okf-page__sidebar { display: none; }
:root[data-okf-focus] .okf-page__main {
  max-width: none;                          /* drop the split trap */
}
/* Rendered view re-centers at the measure even in Focus. The view wrap always
 * exists on concept pages (ensureViewWrap runs at boot), so target it. */
:root[data-okf-focus] .okf-view[data-okf-view="rendered"] {
  max-width: calc(var(--okf-prose-maxw) + 2 * var(--okf-space-6));
  margin-inline: auto;
}
```

- [ ] **Step 2: Hide the rail in Focus.** In `studio.css` add (near the rail rules):

```css
:root[data-okf-focus] .okf-rail { display: none; }
body.okf-has-rail:has(.okf-view[data-okf-view]) { }  /* no-op guard; keep reserve rule simple */
```
Also drop the slim reserve in Focus — add to `studio.css`:
```css
:root[data-okf-focus] body.okf-has-rail { padding-right: 0; }
```
(If `:root[data-okf-focus] body…` selector nesting is awkward, equivalently write `[data-okf-focus] .okf-rail { display:none }` and gate the reserve with a body class toggled by `setFocus` — see Step 5. Prefer the attribute selector; verify in the browser pass.)

- [ ] **Step 3: Reconcile the split grid to consume the JS pct.** In `studio.css` replace the split grid template (292-301) so the custom property actually drives the columns (percentage model):

```css
.okf-view[data-okf-view="split"] {
  display: grid;
  /* Rendered pane width is driven by --okf-split-pct (set by the divider drag
   * in studio.js); source fills the rest. Divider is a fixed 7px track. */
  grid-template-columns: var(--okf-split-pct, 60%) 7px minmax(0, 1fr);
  gap: 0;
  align-items: stretch;
}
```

- [ ] **Step 4: Make `applySplitPct` write a percentage** (not `fr`). In `studio.js` (467-475) change the property write:

```js
  function applySplitPct(pct) {
    splitPct = Math.max(SPLIT_MIN, Math.min(SPLIT_MAX, pct));
    if (viewWrap) viewWrap.style.setProperty("--okf-split-pct", (splitPct * 100).toFixed(2) + "%");
    if (splitDivider) {
      splitDivider.setAttribute("aria-valuenow", String(Math.round(splitPct * 100)));
      splitDivider.setAttribute("aria-valuetext",
        "Rendered pane " + Math.round(splitPct * 100) + " percent, source " + Math.round((1 - splitPct) * 100) + " percent");
    }
  }
```
(`aria-valuenow` still grows on ArrowRight — the split-divider test i1b:1596 stays green. The drag handler in `wireSplitDivider` already computes `pct` as a 0..1 fraction from `clientX`, so no change there.)

- [ ] **Step 5: Add `setFocus`/`toggleFocus`** in `studio.js` (near `setView`, ~575). They flip the `<html>` attribute and remember whether Focus was auto-entered by Split:

```js
  var focusFromSplit = false;
  function setFocus(on) {
    if (on) document.documentElement.setAttribute("data-okf-focus", "");
    else document.documentElement.removeAttribute("data-okf-focus");
    if (focusBtn) focusBtn.setAttribute("aria-pressed", on ? "true" : "false");
  }
  function isFocus() { return document.documentElement.hasAttribute("data-okf-focus"); }
  function toggleFocus() {
    var on = !isFocus();
    focusFromSplit = false;      // manual toggle detaches from split auto-mode
    setFocus(on);
  }
```
Add a module-scope `var focusBtn = null;` (Task 4 assigns it when building the footer Focus button).

- [ ] **Step 6: Split auto-enters/exits Focus.** In `setView` (578-593) add: entering split turns Focus on (and closes any overlay); leaving split turns Focus off **only if** Split turned it on. Insert after `state.view = mode;`:

```js
    if (mode === "split") {
      if (!isFocus()) { focusFromSplit = true; setFocus(true); }
      closePanel();               // overlays would fight the wide split
    } else if (focusFromSplit) {
      focusFromSplit = false; setFocus(false);
    }
```

- [ ] **Step 7: Sanity:**

Run: `node --check scripts/okf_loom/viewer/static/studio.js`
Expected: valid.

- [ ] **Step 8: Write the failing tests** in `tests/test_studio_iter1_browser.py`:

```python
def test_split_view_auto_enters_focus(studio_page):
    """Round 2: switching to Split auto-enters Focus (drops the measure cap)."""
    page = studio_page
    page.wait_for_selector(".okf-viewswitch__btn[data-mode='split']", timeout=10000)
    assert page.evaluate("document.documentElement.hasAttribute('data-okf-focus')") is False
    page.click(".okf-viewswitch__btn[data-mode='split']")
    page.wait_for_function("document.documentElement.hasAttribute('data-okf-focus')", timeout=5000)
    # In Focus the main column is uncapped, so the source pane is wide (> half
    # of the old ~740px measure).
    w = page.eval_on_selector(".okf-view[data-okf-view='split'] > .okf-source",
                              "el => el.getBoundingClientRect().width")
    assert w > 400, f"source pane should be wide in focus/split, got {w}"
    # Leaving split exits the auto-focus.
    page.click(".okf-viewswitch__btn[data-mode='rendered']")
    page.wait_for_function("!document.documentElement.hasAttribute('data-okf-focus')", timeout=5000)

def test_split_divider_resizes_visually(studio_page):
    """The divider drag now drives --okf-split-pct (was a no-op)."""
    page = studio_page
    page.goto(page.url.split("?")[0] + "?view=split")
    div = page.wait_for_selector(".okf-split__divider", timeout=10000)
    before = page.eval_on_selector(".okf-view[data-okf-view='split']",
                                   "el => getComputedStyle(el).gridTemplateColumns")
    div.focus()
    page.keyboard.press("ArrowRight")
    after = page.eval_on_selector(".okf-view[data-okf-view='split']",
                                  "el => getComputedStyle(el).gridTemplateColumns")
    assert before != after, "divider should change the grid tracks"
```

- [ ] **Step 9: Run — new tests pass; the existing split-divider aria test stays green:**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "split" -q`
Expected: PASS (`test_split_view_divider_and_synced_scroll` + the two new ones). Read the summary line.

- [ ] **Step 10: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css scripts/okf_loom/viewer/static/wiki.css tests/test_studio_iter1_browser.py
git commit -m "feat(studio): Workbench/Focus mode + split fix (auto-focus, divider drives grid)"
```

---

### Task 4: Footer button toolbar

Turn the quiet status strip into a bordered-button toolbar: bump height, drop the `--status .okf-studiobtn` quieting override so actions read as buttons, reorganise to **actions left / ambient right** with a divider, and add the **Focus** button (wired to Task 3's `toggleFocus`).

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-studio-bar--status` (54-68) + the quieting override (69-74); add `.okf-studio-bar__divider`.
- Modify: `scripts/okf_loom/viewer/static/studio.js` — footer construction (279-413), `mountBar` (415-422).
- Test: `tests/test_studio_iter1_browser.py`.

- [ ] **Step 1: Bump the footer + let buttons read as bordered.** Replace the `.okf-studio-bar--status` block and its `.okf-studiobtn` quieting override (studio.css:54-74):

```css
.okf-studio-bar--status {
  position: sticky;
  bottom: 0;
  z-index: 9;
  min-height: 40px;                 /* was --okf-status-h (30px): a real toolbar */
  padding: 0 var(--okf-space-4);
  gap: var(--okf-space-3);
  background: var(--okf-bg-inset);  /* recover the original bar feel */
  border-top: var(--okf-border-w) solid var(--okf-border);
  border-bottom: none;
}
/* Actions read as bordered .okf-studiobtn (the base rule already provides the
 * border + elev bg); ambient bits stay quiet & mono at the right edge. */
.okf-studio-bar__divider {
  width: var(--okf-border-w);
  align-self: stretch;
  margin: var(--okf-space-2) var(--okf-space-1);
  background: var(--okf-border);
}
.okf-studio-bar--status .okf-statseg,
.okf-studio-bar--status .okf-conn,
.okf-studio-bar--status .okf-presence {
  font-family: var(--okf-font-mono);
  font-size: var(--okf-text-xs);
}
```
(Deleting the old `.okf-studio-bar--status .okf-studiobtn { … }` override restores the base bordered look at studio.css:87-125.)

- [ ] **Step 2: Reorganise the footer to actions-left / ambient-right + add Focus.** The current build (studio.js:279-413) puts presence/watching/statseg/viewswitch in `leftGroup` and palette/conn in `rightGroup`. Rework so **left = actions** (Watch · Commands · view-switch · Focus) and **right = ambient** (presence · ◆N · ●Live), separated by a divider.

First, build the Focus button. Add near the view-switch construction (~367):
```js
  const focusBtn = el("button", { type: "button", class: "okf-studiobtn okf-focus-btn",
    "aria-pressed": "false", "aria-label": "Toggle focus mode (wide, no chrome)",
    title: "Focus: collapse nav + rail for a wide reading/split view" },
    [document.createTextNode("Focus")]);
  focusBtn.addEventListener("click", toggleFocus);
```
(Assign the module-scope `focusBtn` declared in Task 3 Step 5 — use `focusBtn = el(...)` not `const` if it was declared with `var focusBtn = null;`; reconcile the declaration so `setFocus` can sync its `aria-pressed`.)

Then replace the assembly (studio.js:406-413, already edited in Task 1 Step 12) with the actions-left / ambient-right layout:
```js
  // Round 2 footer: actions left, ambient right, divider between.
  // LEFT (actions): Watching · Commands · [view-switch] · Focus
  leftGroup.appendChild(watchingToggle);
  leftGroup.appendChild(paletteBtn);
  // view-switch appended in mountBar (concept pages only)
  // (Focus appended after the view-switch in mountBar so order reads L→R.)
  // RIGHT (ambient): presence · ◆N concepts · ● Live
  rightGroup.appendChild(presenceChip);
  if (conceptCount > 0) rightGroup.appendChild(conceptStatseg);
  rightGroup.appendChild(connChip);
  bar.appendChild(leftGroup);
  bar.appendChild(el("span", { class: "okf-studio-bar__divider", "aria-hidden": "true" }));
  bar.appendChild(rightGroup);
```
This requires two small refactors in the construction block above:
- The presence chip (284-291) and the `◆ N concepts` statseg (335-341) are currently appended to `leftGroup` inline. Remove those `leftGroup.appendChild(...)` calls; instead keep references (`presenceChip` already named; name the statseg `const conceptStatseg = el("span", {…}, [...]);` without appending) so the assembly above can place them in `rightGroup`.
- The watching toggle (300-331) currently appends to `leftGroup` — remove that inline append too (the assembly appends it).

- [ ] **Step 3: Append view-switch + Focus in `mountBar`** (concept pages). Replace `mountBar` (415-422):
```js
  function mountBar() {
    document.body.appendChild(bar);
    if (isConceptPage()) {
      leftGroup.appendChild(viewSwitch);
      leftGroup.appendChild(focusBtn);
    }
  }
```

- [ ] **Step 4: Keep the mobile-static rule** (test i1b:1417). Confirm the `@media (max-width:900px) .okf-studio-bar { position: static; … }` block (studio.css:1411-1416) is untouched. Do not add `position: sticky` inside that media query.

- [ ] **Step 5: Sanity:**
Run: `node --check scripts/okf_loom/viewer/static/studio.js`
Expected: valid.

- [ ] **Step 6: Write the failing test** (`tests/test_studio_iter1_browser.py`):
```python
def test_footer_has_focus_button_and_bordered_actions(studio_page):
    page = studio_page
    fbtn = page.wait_for_selector(".okf-studio-bar--status .okf-focus-btn", timeout=10000)
    # Focus button toggles data-okf-focus.
    assert page.evaluate("document.documentElement.hasAttribute('data-okf-focus')") is False
    fbtn.click()
    page.wait_for_function("document.documentElement.hasAttribute('data-okf-focus')", timeout=5000)
    assert page.get_attribute(".okf-focus-btn", "aria-pressed") == "true"
    # Comments/Changes are NOT duplicated in the footer (they live in the rail).
    n = page.eval_on_selector_all(
        ".okf-studio-bar--status .okf-studiobtn",
        "els => els.filter(e => /Comments|Changes/.test(e.textContent)).length")
    assert n == 0, "Comments/Changes must not be duplicated in the footer"
```

- [ ] **Step 7: Run — new test passes; mobile-static stays green:**
Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "footer_has_focus or mobile_sticky_chrome" -q`
Expected: PASS.

- [ ] **Step 8: Commit**
```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css tests/test_studio_iter1_browser.py
git commit -m "feat(studio): footer button toolbar — bordered actions + Focus, ambient right"
```

---

### Task 5: Related → flat nav section

Drop **both** card chromes around Related (the studio `.okf-sidebar-panel` card and the standalone read-only `.okf-local-graph` card) and render it flat: a `.okf-nav__group`-style "Related" label + `.okf-nav__link`-style neighbour rows, one continuous left rail.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js` — `buildSidebarPanels`/`buildPanel` (4101-4175), for `panelId === "related"` skip the card.
- Modify: `scripts/okf_loom/viewer/static/wiki.js` — `renderLocalGraph` (87-163): title → nav-group label.
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — `.okf-local-graph`/`__node`/`__title` (1513-1583) flat; the `.okf-sidebar-panel__body .okf-local-graph { display:contents }` (1541-1546) stays but the card wrapper is bypassed.
- Test: none pinned (`okf-sidebar-panel`/`okf-local-graph` have zero test hits) — verify by screenshot.

- [ ] **Step 1: Bypass the card for "related".** In `studio.js` `buildSidebarPanels` (4101-4136), instead of `buildPanel("related", …)` wrapping it in a `.okf-sidebar-panel` card, append a flat section. Replace the `sbState.order.forEach(...)` loop body for the related case — simplest: special-case related before the loop and drop it from the dynamic-panel order:

```js
    // Related renders FLAT (a nav-group label + the neighbour list), not a
    // draggable card — one continuous left rail. Build it directly.
    if (existingGraph) {
      var related = el("section", { class: "okf-related", "aria-label": "Related" });
      related.appendChild(el("p", { class: "okf-nav__group", text: "Related" }));
      related.appendChild(existingGraph);   // move the node; wiki.js re-renders it flat
      sidebar.appendChild(related);
    }
    sbState.order.forEach(function (panelId) {
      if (panelId === "sections" || panelId === "intents" || panelId === "related") return;
      var panel = buildPanel(panelId, sbState, existingGraph);
      if (panel) sidebar.appendChild(panel);
    });
```
(Since `SIDEBAR_PANELS = ["related"]` and related is now handled directly, the loop runs empty — that is fine. `wireSidebarDnD` then has nothing draggable, harmless.)

- [ ] **Step 2: Make `renderLocalGraph`'s own title a nav-group label + hide it when inside `.okf-related`.** In `wiki.js` (95-113) the title becomes a `.okf-nav__group`; the standalone read-only card keeps a visible label, but inside `.okf-related` the outer `<p class="okf-nav__group">Related</p>` already labels it, so hide the inner one via CSS (Step 3). Change the title element class (wiki.js ~99-108):

```js
    var title = document.createElement("p");
    title.className = "okf-local-graph__title";
    title.textContent = neighbors.length ? "Related (" + neighbors.length + ")" : "Related";
    container.appendChild(title);
```
Leave this as-is (the class stays `okf-local-graph__title`); the flattening is done entirely in CSS (Step 3) so no-JS/read-only pages still show a label. No JS change strictly required here — **skip editing wiki.js** unless the browser pass shows a doubled label; if it does, hide the inner title inside `.okf-related` in CSS (Step 3 already does).

- [ ] **Step 3: Flatten the CSS.** In `wiki.css` restyle `.okf-local-graph` (1513-1523) to be borderless/flush and make its nodes match `.okf-nav__link`. Replace the `.okf-local-graph` base rule:

```css
.okf-local-graph {
  display: flex;
  flex-direction: column;
  gap: 1px;
  max-height: 320px;
  overflow-y: auto;
  /* Round 2: flat — no card border/bg/padding; sits flush in the left rail. */
}
```
Update `.okf-local-graph__title` (1524-1530) to match `.okf-nav__group`:
```css
.okf-local-graph__title {
  margin: var(--okf-space-4) var(--okf-space-1) var(--okf-space-1);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--okf-fg-muted);
}
```
And make `.okf-local-graph__node` (1548-1566) match `.okf-nav__link` padding/typography (it is already a flex row with swatch + label — just align the metrics):
```css
.okf-local-graph__node {
  display: flex;
  align-items: center;
  gap: var(--okf-space-2);
  padding: 6px 9px;
  margin: 1px 0;
  border: var(--okf-border-w) solid transparent;
  border-radius: var(--okf-radius-sm);
  text-decoration: none;
  color: var(--okf-fg-muted);
  font-size: var(--okf-text-sm);
  cursor: pointer;
  background: transparent;
  text-align: left;
  width: 100%;
  font-family: inherit;
}
.okf-local-graph__node:hover {
  background: var(--okf-bg-inset);
  color: var(--okf-fg);
  border-color: transparent;
}
```
Inside `.okf-related`, hide the widget's own title (the section already provides "Related"):
```css
.okf-related .okf-local-graph__title { display: none; }
```
(Keep the existing `.okf-sidebar-panel__body .okf-local-graph { display: contents }` at 1541-1546 — it now never fires since related isn't wrapped in a `__body`, but leaving it is harmless.)

- [ ] **Step 4: Sanity — JS + CSS well-formed:**
Run: `node --check scripts/okf_loom/viewer/static/wiki.js && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/wiki.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: valid; braces balanced.

- [ ] **Step 5: Full suite (no test pins these classes, so confirm nothing regressed):**
Run: `python3 -m pytest tests/test_render.py tests/test_studio_iter1_browser.py -q`
Expected: PASS. Read the summary line.

- [ ] **Step 6: Commit**
```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/wiki.js scripts/okf_loom/viewer/static/wiki.css
git commit -m "feat(viewer): flatten Related into the left nav rail (no card chrome)"
```

---

### Task 6: Spacing pass (overlay rhythm)

Fix the concrete bug (`.okf-panel__intents` zero bottom-padding butts "ASK THE AGENT" against Enrich) and audit the overlay's vertical rhythm. Spacing tokens only — no relayout.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-panel__intents` (1165-1170) + adjacent overlay rhythm.
- Test: none (visual; screenshot-verified).

- [ ] **Step 1: Fix the zero-bottom padding.** Replace `.okf-panel__intents` padding (studio.css:1169):
```css
.okf-panel__intents {
  display: flex;
  flex-wrap: wrap;
  gap: var(--okf-space-1);
  padding: var(--okf-space-3) var(--okf-space-4);   /* was `… 0` — add bottom breathing room */
}
```

- [ ] **Step 2: Audit the overlay rhythm** — the stack is tab bar → intents → composer (`.okf-comment-composer-section`) → toolbar → list. Ensure consistent vertical gaps using spacing tokens. Check these known-tight spots and normalise to `var(--okf-space-3)`:
  - the `.okf-panel__body` top padding (1261) vs the intents top — avoid a doubled gap;
  - the composer `.okf-composer__anchor`/`__hint`/`__actions` internal spacing (grep `okf-composer__` in studio.css) — add `var(--okf-space-2)` where they butt.
Make only spacing edits (padding/margin/gap with tokens); do not change colours, borders, or structure.

- [ ] **Step 3: Sanity:**
Run: `python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/studio.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: braces balanced.

- [ ] **Step 4: Commit**
```bash
git add scripts/okf_loom/viewer/static/studio.css
git commit -m "fix(studio): overlay spacing — intents bottom padding + vertical rhythm"
```

---

### Task 7: Phase-1 verification (suite green + served/tunnelled all-theme pass)

**Files:** none (verification).

- [ ] **Step 1: Full suite green.**
Run: `python3 -m pytest tests/ -q`
Expected: PASS (baseline was 1268 passed / 23 skipped at `cc55daf`; the new tests add to the passed count). **Read the printed summary line** — never trust a `| tail`ed exit code. If `test_comment_mark_wraps_selection` is the *only* failure, rerun it (documented load-flake): `python3 -m pytest tests/test_studio_iter1_browser.py::test_comment_mark_wraps_selection -q`.

- [ ] **Step 2: Serve on loopback (background).**
Run (Bash tool, `run_in_background: true`): `exec scripts/okf-loom serve docs-bundle --no-open`
Wait (no sleep): `curl -s --retry 20 --retry-delay 1 --retry-connrefused http://localhost:8787/demo/showcase -o /dev/null && echo up`
Expected: `up`.

- [ ] **Step 3: Self-review screenshots across all four themes** (Playwright + system Chrome, `wait_until="load"`). Default is Swiss-light (don't seed); seed `localStorage['okf-theme']` to `swiss-dark`, `technical-light`, `technical-dark` for the others. Capture concept (`/demo/showcase`), concept with Comments overlay open, `?view=split` (should be wide + Focus), and index/search. Confirm visually:
  - rail docked (~48px), content not under it; overlay pops OVER content with pop-shadow; Esc/scrim closes.
  - inline pin reads as a clear active-state affordance; clicking opens the thread at the card.
  - Focus collapses nav+rail+frame; Split is wide with unwrapped Source; Rendered stays ~76ch centered.
  - footer reads as a bordered-button toolbar (actions left, ambient right, divider); no Comments/Changes duplicated.
  - Related is a flat nav section (no card).
  - overlay spacing has breathing room under the intents.

- [ ] **Step 4: Tunnel for the user's browser pass (background).**
Run (Bash tool, `run_in_background: true`): `/usr/local/bin/cloudflared tunnel --url http://localhost:8787`
Grep the task output for `https://<random>.trycloudflare.com` and hand that URL to the user. Ask them to walk all four themes and drive: `/` focuses search; rail overlays open/close (Esc + click-away); a pin opens the thread at the comment; Split shows wide unwrapped Source; footer reads as a button toolbar; Related is flat.

- [ ] **Step 5: Stop the serve + tunnel** via the **TaskStop** tool on the two background task ids (never `pkill`).

- [ ] **Step 6: Tune anything the visual pass flags** — spacing, z-index/scrim, pin contrast, footer per-theme feel, Focus frame-collapse. Edit only the relevant static asset, reload (no restart), re-verify parity/suite stays green, and commit the tuning:
```bash
git add scripts/okf_loom/viewer/static
git commit -m "fix(viewer): Round-2 Phase-1 visual-pass tuning"
```

---

## Self-Review

**1. Spec coverage (Round-2 spec §4, Phase 1):**
- §4.1 thin rail + overlays (revises §3.4) → Task 1 (rail CSS/JS, overlay reposition, scrim shown, slim reserve, mobile full-width, Comments/Changes → rail). SPEC.md reconciled → Task 0. ✔
- §4.2 functional pin → Task 2 (active-state mark/marker restyle keeping ≥24px + data-comment-id; `wireCommentMarkClicks` reads id → `jumpToCommentMark` + new `jumpToCommentCard`; marker click aligned; resolve still mutes via existing state variants). ✔
- §4.3 Workbench/Focus + split fix → Task 3 (`data-okf-focus` collapses nav+rail+frame, drops `__main` cap, re-measures Rendered only; split grid consumes `--okf-split-pct`; Split auto-enters/exits Focus; divider aria preserved). ✔
- §4.4 footer toolbar → Task 4 (40px, drop quieting override → bordered buttons, actions-left/ambient-right + divider, Focus button, no Comments/Changes duplication, mobile-static kept). ✔
- §4.5 Related flat → Task 5 (bypass `.okf-sidebar-panel` card + flatten `.okf-local-graph` card; nodes match `.okf-nav__link`; handles both studio + read-only modes). ✔
- §4.6 spacing → Task 6 (`.okf-panel__intents` bottom padding + overlay rhythm). ✔
- §7 verification (suite + Playwright + serve/tunnel all-theme) → Task 7. ✔
- §8 non-goals: no branch/merge (stay on `feature/new-layout`); don't touch `okf-loom-mcp/`/`redesign-files-1.zip`/`workbench-preview.html`; no edge-to-edge prose (Rendered re-measured in Focus, Task 3 Step 1); no new theme-enum; Swiss default untouched. ✔
- Out of scope (correctly deferred): §5 appearance (border/contrast/Appearance menu) and §6 features (ToC/index/search/studio-depth) are **not** in this plan — Phases 2/3.

**2. Placeholder scan:** No "TBD"/"handle appropriately". Every code step shows concrete before/after. Two steps use a `grep` to locate an exact insertion site (Task 1 Step 11 `commentsBadge`; Task 2 Step 4 comment-card builder) — these are precise "find this symbol, add this attribute" instructions with the exact code to add, not vague placeholders (the mappers confirmed the symbols exist; only their line numbers may have shifted).

**3. Type/name consistency:** New names used consistently — `.okf-rail`/`__btn`/`__badge`/`__toggle`/`__spacer`, `--okf-rail-w`, `body.okf-has-rail`, `data-okf-focus` (on `<html>`, distinct from graph `okf-focus-root`), `setFocus`/`toggleFocus`/`isFocus`/`focusFromSplit`/`focusBtn`, `jumpToCommentCard`, `.okf-studio-bar__divider`, `.okf-related`. `--okf-split-pct` written as `%` in `applySplitPct` (Task 3 Step 4) and consumed as `%` in the grid (Step 3) — units match. `focusBtn` is declared module-scope in Task 3 Step 5 and assigned in Task 4 Step 2 — reconcile the declaration (`var focusBtn = null;` then `focusBtn = el(...)`), noted in Task 4 Step 2. `railButtons` declared in Task 1 Step 10 and used in Step 11. Preserved contracts (openPanel API, `.okf-panel__*`, split-divider aria, mobile-static, marker ≥24px, `.okf-nav*` + aria-label) each have an explicit "keep" instruction and a green-check test step.

**Risk notes:**
- Task 1 is the largest, single structural change; its tests assert the *behaviour* (no reflow, scrim/Esc close, `openPanel` API intact) rather than pixels.
- The Focus frame-collapse + split-grid percentage model are the two spots most likely to need screenshot tuning (Task 7 Step 6) — the plan sets the mechanism; exact widths/z-index/scrim are tuned in the browser pass, not guessed here.
- Phase 1 edits **only static assets + SPEC.md** — no `render.py`/template/config edits — so `test_render.py` is unaffected and the running serve needs reloads, not restarts.
