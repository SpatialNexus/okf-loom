# Editorial Workbench Round 2 — Phase 2 (Appearance settings) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two orthogonal, persisted appearance modifiers — a **border toggle** (`data-okf-border` = on/muted/off) and a **contrast modifier** (`data-okf-contrast` = high/soft) — that remap a small token set on top of any of the 4 themes, plus an **Appearance menu (`Aa ▾`)** topbar popover that consolidates family · mode · contrast · border and replaces the bare theme-cycle button. Fold in the carryover **footer Studio button** (off-rail studio access), two **polish nits**, and removal of the dead **`.okf-sidebar-panel`** subsystem — all on branch `feature/new-layout`, suite green.

**Architecture:** Defaults keep **today's contrasty look** (both modifier attributes ABSENT). Soft/muted/off are opt-in root `data-attrs` applied on `<html>` *after* the theme blocks; `:root[data-*]` specificity `(0,2,0)` beats `[data-theme]` `(0,1,0)`, so modifiers win on any theme. New per-theme `*-soft` tokens are added to all 4 theme blocks + `:root` (parity). The Appearance-menu **markup** is emitted once server-side by `render.py:_theme_button_html` (feeds all 5 surfaces); the **wiring** lives inside the existing per-bundle IIFEs — `wiki.js` (concept/index/search) and `graph.js` (graph/single-file) — each reusing its local `applyTheme`, because those setters are **not** exported. contrast/border are read from localStorage and applied **post-paint** by those same IIFEs (there is no pre-paint boot script to extend, and inline scripts are CSP-blocked on 4/5 templates — see "Spec-reality reconciliations").

**Tech Stack:** Python 3.11+ (`render.py`, `pytest`), vanilla ES-module IIFEs (`wiki.js`/`graph.js`/`studio.js`, no build step — `node --check` for syntax), plain CSS custom properties (`wiki.css`/`studio.css`), Playwright + system Chrome for browser tests. Run everything via `scripts/okf-loom`.

**Approved contract:** `docs/superpowers/specs/2026-07-05-editorial-workbench-round2-design.md` (commit `b4a0159`). This plan implements **§5 (Phase 2)** + the carryover items resolved with the user (footer Studio button; polish nits folded here; dead-code removal folded here). §6 (features) is a separate Phase-3 plan.

---

## ⚠️ Spec-reality reconciliations (surfaced at the approval gate — machinery mapping corrected two spec assumptions)

The visible **design is unchanged**; these are mechanism/limitation corrections the mappers uncovered:

- **D1 — contrast/border apply POST-paint, not pre-paint.** The spec (§5.3) said to "extend the inline boot script that sets `data-theme` before first paint." **No such script exists.** Theme is emitted server-side onto `<html>` only when the config theme is a concrete theme; the default `auto` config emits nothing and theme is applied *after* paint by the deferred `wiki.js`/`graph.js` IIFEs. Also, 4 of 5 templates use CSP `script-src 'self'` (no `'unsafe-inline'`), so a new synchronous inline boot `<script>` is **CSP-blocked**. So contrast/border are read from localStorage and applied post-paint by the same IIFEs — **exactly how theme already works today.** Consequence: a user who has opted into `soft`/`muted`/`off` sees a brief flash from default→their-choice on load, *identical in nature to the theme flash that already exists today*; the default (today's look) has **no** flash. Net-new regression ≈ zero. (A true pre-paint would need a CSP hash/nonce + a shared head-builder across 5 hand-duplicated `<head>`s — deferred as not worth it.)
- **D3 — the graph (Cytoscape) canvas will NOT reflect contrast/border.** `graph.js GRAPH_COLORS` hardcodes per-`data-theme` literal hex values (the canvas can't read CSS vars); it is keyed only by family+mode. So `data-okf-contrast`/`data-okf-border` won't reach the canvas. The graph page's *chrome* (topbar, controls, Appearance menu) does reflect them (CSS-var driven); only the node/edge canvas keeps its per-theme high-contrast palette. `--okf-select`/accent (the interactive colours) are unchanged by soft anyway. Mirroring contrast/border into `GRAPH_COLORS` would be a larger refactor that risks `test_iter2_graph_selection_color_is_token_governed` — deferred as a possible Phase-3 item, documented in code.

**Everything else matches the spec.** Defaults keep the contrasty Swiss look; soft/muted/off are opt-in; no theme-enum growth; Swiss stays default.

---

## The decoupling contract (do not violate)

1. **Layout CSS references tokens only.** No hardcoded colour/font/border/radius in any `.okf-*` product rule — every aesthetic value is `var(--okf-*)`. The Appearance-menu CSS (new `.okf-appearance*`) uses only tokens.
2. **Each shipped theme stays one complete self-contained `[data-theme="…"]` block.** `test_render.py::test_theme_blocks_override_full_token_set` `split()`s on the exact selector to the first `}`. Phase 2 **adds** 5 token-checked tokens (the soft set) to all 4 blocks — Task 1 updates the parity list first (RED) then adds them (GREEN). The two modifier blocks (`:root[data-okf-*]`) go **after** all theme blocks and are NOT `[data-theme]` blocks, so they don't affect the split.
3. **Preserve the hard-contract markers** (see "Test contracts" below), incl. `okf-viewer` body class, `#okf-main`, every `__TOKEN__` placeholder, the `.okf-topbar` wrapper, and the search form + Graph/Index links inside `.okf-topbar__controls`.
4. **No Apple/Windows cue** — the Appearance trigger is `Aa ▾` (typographic), no `⌘`/`⊞`, no window dots.
5. **THEMES / THEME_GLYPHS stay swiss-first and identical** across `render.py:_THEMES` (557), `wiki.js` (24), `studio.js` (218), `graph.js` (27). Phase 2 does **not** reorder or rename them. (It removes the *dynamic glyph write* from the JS setters — see Task 5/6 — but leaves the `_THEME_GLYPHS`/`THEME_GLYPHS` maps in place; they are still referenced by tests and by the palette.)
6. **Graph canvas** `GRAPH_COLORS` (graph.js 57-78) stays a four-theme lookup keyed by `data-theme`; do **not** restructure it (keeps `test_iter2_graph_selection_color_is_token_governed` green). Per D3, contrast/border don't mirror into it in Phase 2.

---

## Test contracts — MUST preserve (verified against `tests/` by machinery mappers)

| Contract | Where asserted | What the task must keep |
|---|---|---|
| Every `[data-theme="…"]` block overrides the full token set (now incl. the 5 soft tokens once Task 1 adds them to the list) | `test_render.py::test_theme_blocks_override_full_token_set` (~1250) | Task 1 adds the 5 soft tokens to the required list **and** to all 4 blocks in the same task. |
| `--okf-select` defined in every `[data-theme]` block; `GRAPH_COLORS` has 4 palettes; `node:selected` reads `GRAPH_COLORS["technical-light"].select`; `function syncLabelColour()` body has `var pal = graphPalette()` | `test_render.py::test_iter2_select_token_defined_in_wiki_css` (~1239), `::test_iter2_graph_selection_color_is_token_governed` (~1197) | Tasks 6 must NOT rename `syncLabelColour`/`graphPalette` or restructure `GRAPH_COLORS`. |
| Accent isn't Tailwind blue (splits `[data-theme="technical-light"|-dark]` blocks) | `test_render.py::test_iter1_accent_is_not_tailwind_blue` (~1010) | Don't remove/rename those two block selectors. |
| Static concept nav: search `<form … role="search">` action + `<a class="okf-btn" …>Graph</a>` present | `test_render.py::test_p1_3_static_concept_nav_urls_have_html_extension` (~595) | Task 3 must keep `_nav_controls_html`'s search form + Graph/Index links; only the theme-button call output changes. |
| `.okf-topbar` exists with measurable height on concept page | `test_studio_iter1_browser.py` (~1537) | Task 3/4 keep the `<header class="okf-topbar">` wrapper; the Appearance menu sits inside it. |
| Related is flat: **no** `.okf-sidebar-panel` card in the sidebar (`hasSidebarPanelCard is False`); `.okf-related` is a `SECTION` containing `.okf-local-graph` with inner title hidden | `test_studio_iter1_browser.py::test_related_section_is_flat_not_a_sidebar_panel_card` (~1923) | Task 9 removal keeps this green (it *enforces* the removal). Preserve `buildSidebarPanels`' flat-Related path + `.okf-related` CSS. |
| Rail `.okf-rail__btn[aria-pressed]`, marker ≥24px, split-divider aria, mobile-static `.okf-studio-bar`, `openPanel(kind)` API, `.okf-viewswitch__btn[data-mode]` | Phase-1 browser tests | Tasks 7/8 touch the footer + rail *style* and add a Studio button; keep all these class names + the `openPanel` API + the mobile-static rule. |

**FREE to add/restyle (greenfield or zero test hits):** `data-okf-contrast`/`data-okf-border` (nonexistent today), all `--okf-*-soft` tokens, all `.okf-appearance*` classes, the footer `.okf-studio-open-btn`, the `.okf-rail__btn` resting colour, the footer divider margin. **No test** references `_theme_button_html`, `#okf-theme`, the cycle behaviour, `__NAV_HTML__`, `buildPanel`/`wireSidebarDnD`/`sidebarPanelTitle`/`buildSidebarPanels`/`SIDEBAR_PANELS`.

**Known flakes (rerun once if the ONLY failures):** `test_comment_mark_wraps_selection` (120ms debounce), `test_agent_watching_toggle_posts_presence`, `test_agent_activity_panel_has_unique_sections` (shared-server races).

---

## New names locked for this phase (use these exact strings everywhere)

- **Modifiers:** root attrs `data-okf-contrast="soft"` (emitted only for soft; absent = high) and `data-okf-border="muted"|"off"` (emitted only for those; absent = on). localStorage keys `okf-contrast`, `okf-border`. Existing theme key stays `okf-theme`.
- **Soft tokens (5, added to every theme block + `:root`):** `--okf-fg-soft`, `--okf-active-fill-soft`, `--okf-active-fg-soft`, `--okf-active-border-soft`, `--okf-page-bg-soft`. (Borders reuse existing `--okf-border` — no new border token.)
- **Appearance menu:** wrapper `.okf-appearance`; trigger keeps `id="okf-theme"` + class `.okf-appearance__trigger`; popover `.okf-appearance__menu` (id `okf-appearance-menu`); group `.okf-appearance__group`; group label `.okf-appearance__label`; option button `.okf-appearance__opt` with `data-okf-set` ∈ {family,mode,contrast,border} and `data-okf-val`. Options carry `role="radio"` + `aria-checked`; groups `role="radiogroup"`.
- **Footer Studio button:** `.okf-studiobtn.okf-studio-open-btn` (text "Studio"), opens `openPanel(isConceptPage() ? "comments" : "changes")`.

---

## File-structure map (what each touched file owns this phase)

- `scripts/okf_loom/viewer/static/wiki.css` — soft tokens in `:root` + 4 theme blocks (Task 1); the 2 modifier blocks after the theme blocks (Task 2); the `.okf-appearance*` menu CSS, universal (Task 4); remove the 14 dead `.okf-sidebar-panel*` blocks (Task 9).
- `tests/test_render.py` — parity token list (Task 1); new modifier-block test (Task 2); new Appearance-markup test (Task 3).
- `scripts/okf_loom/render.py` — `_theme_button_html` → Appearance-menu markup, one function feeding all 5 surfaces (Task 3). **Editing render.py requires a serve RESTART** (templates/py read at startup).
- `scripts/okf_loom/viewer/static/wiki.js` — contrast/border post-paint readers + Appearance-menu wiring (popover open/close, option handlers reusing `applyTheme`, state reflection); remove the dynamic glyph write from `applyTheme`; replace the cycle click handler (Task 5).
- `scripts/okf_loom/viewer/static/graph.js` — same readers + wiring reusing graph's `applyTheme` + `syncLabelColour`; replace its cycle click handler; remove its glyph write (Task 6).
- `scripts/okf_loom/viewer/static/studio.js` — remove the glyph write from `applyThemeAttr` (Task 6); add the footer Studio button (Task 7); delete the dead `.okf-sidebar-panel` subsystem (Task 9).
- `scripts/okf_loom/viewer/static/studio.css` — `.okf-rail__btn` resting colour + footer divider (Task 8).
- `tests/test_studio_iter1_browser.py` — new tests (Appearance wiring on a reading page; footer Studio button; graph-page menu).
- `design/../round2-design spec` — a reconciliation note (Task 0).

**Environment recipe:**
- Serve in background: Bash `run_in_background: true`, `exec scripts/okf-loom serve docs-bundle --no-open` (loopback :8787). Wait with `curl -s --retry 20 --retry-delay 1 --retry-connrefused http://localhost:8787/... -o /dev/null` (**no `sleep`**). Stop/restart via the **TaskStop** tool on the bg task id (never `pkill`). **RESTART after the Task-3 render.py edit** (and after any later render.py/template touch); CSS/JS are served fresh — just reload.
- Tests: `python3 -m pip install pytest playwright pytest-playwright` (browser download disabled; system Chrome auto-used). `python3 -m pytest tests/ -q` (~3min incl. e2e). **Never** pipe pytest through `| tail` and trust the exit code — **read the printed summary line**.
- Screenshots: Playwright + system Chrome, `executable_path=$AIC_PLAYWRIGHT_CHROME_PATH`, `args=["--no-sandbox"]`, `wait_until="load"` (SSE breaks networkidle). Default is Swiss-light (don't seed `okf-theme`); seed the other 3. For Phase-2 variants ALSO seed `localStorage['okf-contrast']='soft'` and `localStorage['okf-border']='muted'|'off'`.

---

## PHASE 2 — Appearance settings

### Task 0: Reconcile the round-2 design spec §5 to the post-paint mechanism

**Files:**
- Modify: `docs/superpowers/specs/2026-07-05-editorial-workbench-round2-design.md` — §5.1 and §5.3 (the "inline boot script … before first paint" phrasing).

- [ ] **Step 1: Append a reconciliation note** at the end of §5.3 (after the `graph.js GRAPH_COLORS` bullet). Insert:

```markdown

> **Build reconciliation (2026-07-06, Phase-2 plan):** machinery mapping found there is **no** inline pre-paint boot script to extend, and 4 of 5 templates forbid inline `<script>` (CSP `script-src 'self'`). So `data-okf-contrast`/`data-okf-border` are read from localStorage and applied **post-paint** by the existing `wiki.js` (concept/index/search) and `graph.js` (graph/single-file) IIFEs — the same mechanism theme already uses. Defaults (today's look) stay attribute-absent, so only an opted-in `soft`/`muted`/`off` user sees a brief load flash, identical to the existing theme flash. Separately, the Cytoscape **graph canvas** mirrors tokens via hardcoded `GRAPH_COLORS` literals keyed by `data-theme`, so contrast/border do not reach the canvas in Phase 2 (documented limitation; the graph *chrome* still reflects them).
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-05-editorial-workbench-round2-design.md
git commit -m "docs(spec): reconcile Round-2 §5 to post-paint contrast/border mechanism"
```

---

### Task 1: Soft-contrast tokens + parity (RED → GREEN)

Add the 5 `*-soft` tokens to the parity-required list (RED), then to all 4 theme blocks **and** `:root` (GREEN). Values are starting points — Task 10 tunes them with screenshots. Placement within a block is arbitrary (CSS custom properties resolve lazily at use), so we insert them right after each block's opening selector line for a unique, drift-proof anchor.

**Files:**
- Modify: `tests/test_render.py` — `test_theme_blocks_override_full_token_set` `core_tokens` tuple.
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — `:root` + the 4 `[data-theme]` blocks.

- [ ] **Step 1: RED — extend the required token list.** In `tests/test_render.py`, find the last line of the `core_tokens` tuple:

```python
        "okf-title-weight", "okf-title-spacing", "okf-pop-shadow", "okf-page-bg",
    )
```
Replace it with (adds the soft set):
```python
        "okf-title-weight", "okf-title-spacing", "okf-pop-shadow", "okf-page-bg",
        # Round 2 §5.2 soft-contrast variants — every theme owns its soft look:
        "okf-fg-soft", "okf-active-fill-soft", "okf-active-fg-soft",
        "okf-active-border-soft", "okf-page-bg-soft",
    )
```

- [ ] **Step 2: Run — verify it FAILS** (blocks don't define the tokens yet):

Run: `python3 -m pytest tests/test_render.py::test_theme_blocks_override_full_token_set -q`
Expected: FAIL — "theme missing --okf-fg-soft token" (or similar). Read the summary line.

- [ ] **Step 3: GREEN — add the tokens to `:root`.** In `wiki.css`, replace the opening line `:root {` (line ~24, unique) with:

```css
:root {
  /* Round 2 §5.2 — soft-contrast variants (consumed when the soft-contrast
   * modifier is active). :root carries the Swiss-light fallback so a themeless
   * soft page still resolves. (Do NOT write the literal modifier selector in
   * this comment — the Task 2 test split()s the file on it.) */
  --okf-fg-soft: #2a2f36;
  --okf-active-fill-soft: var(--okf-accent-bg);
  --okf-active-fg-soft: var(--okf-accent);
  --okf-active-border-soft: transparent;
  --okf-page-bg-soft: #eef1f5;
```

- [ ] **Step 4: GREEN — technical-light.** Replace `[data-theme="technical-light"] {` (unique) with:

```css
[data-theme="technical-light"] {
  /* Round 2 §5.2 soft-contrast variants (Technical's active is already tinted). */
  --okf-fg-soft: #2b333f;
  --okf-active-fill-soft: var(--okf-accent-bg);
  --okf-active-fg-soft: var(--okf-accent);
  --okf-active-border-soft: transparent;
  --okf-page-bg-soft: #eef1f5;
```

- [ ] **Step 5: GREEN — technical-dark.** Replace `[data-theme="technical-dark"] {` with:

```css
[data-theme="technical-dark"] {
  /* Round 2 §5.2 soft-contrast variants. */
  --okf-fg-soft: #cdd6df;
  --okf-active-fill-soft: var(--okf-accent-bg);
  --okf-active-fg-soft: var(--okf-accent);
  --okf-active-border-soft: transparent;
  --okf-page-bg-soft: #0b0e13;
```

- [ ] **Step 6: GREEN — swiss-light.** Replace `[data-theme="swiss-light"] {` with (soft turns Swiss's solid boxed active into a Technical-style tint):

```css
[data-theme="swiss-light"] {
  /* Round 2 §5.2 — soft makes Swiss's solid active tinted (like Technical) + softer fg. */
  --okf-fg-soft: #2a2f36;
  --okf-active-fill-soft: var(--okf-accent-bg);
  --okf-active-fg-soft: var(--okf-accent);
  --okf-active-border-soft: transparent;
  --okf-page-bg-soft: #eef0f3;
```

- [ ] **Step 7: GREEN — swiss-dark.** Replace `[data-theme="swiss-dark"] {` with:

```css
[data-theme="swiss-dark"] {
  /* Round 2 §5.2 soft-contrast variants. */
  --okf-fg-soft: #d6dade;
  --okf-active-fill-soft: var(--okf-accent-bg);
  --okf-active-fg-soft: var(--okf-accent);
  --okf-active-border-soft: transparent;
  --okf-page-bg-soft: #0c0e10;
```

- [ ] **Step 8: GREEN — run parity + brace sanity:**

Run: `python3 -m pytest tests/test_render.py::test_theme_blocks_override_full_token_set -q && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/wiki.css').read_text(); assert s.count('{')==s.count('}'), (s.count('{'), s.count('}'))"`
Expected: PASS; braces balanced.

- [ ] **Step 9: Commit**

```bash
git add tests/test_render.py scripts/okf_loom/viewer/static/wiki.css
git commit -m "feat(theme): add per-theme soft-contrast token set (parity across all 4 blocks + root)"
```

---

### Task 2: Border + contrast modifier blocks (RED → GREEN)

Add the two runtime-modifier blocks **after** all theme blocks. Contrast block **first**, border blocks **second**, so `border=off` (transparent) wins over `contrast=soft` (`--okf-border`) on the shared `--okf-border-strong`.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — insert after the `swiss-dark` block (before the `/* ---- Reset / base */` comment).
- Modify: `tests/test_render.py` — new test.

- [ ] **Step 1: RED — write the failing test.** Add to `tests/test_render.py` (near `test_theme_blocks_override_full_token_set`):

```python
def test_appearance_contrast_and_border_modifier_blocks() -> None:
    """Round 2 §5.1: soft-contrast + border modifiers are orthogonal root
    data-attr blocks placed AFTER the theme blocks, border after contrast."""
    css = _runtime_file("viewer", "static", "wiki.css").read_text(encoding="utf-8")
    assert '[data-okf-contrast="soft"]' in css
    assert '[data-okf-border="muted"]' in css
    assert '[data-okf-border="off"]' in css
    # Border block AFTER contrast block (so off's transparent wins on --okf-border-strong).
    assert css.index('[data-okf-contrast="soft"]') < css.index('[data-okf-border="off"]')
    # Contrast=soft remaps the six documented tokens to their soft variants.
    # Split on the FULL selector (with `:root` + brace) so a stray mention of
    # the bare attribute in a comment can't shadow the real block.
    soft = css.split(':root[data-okf-contrast="soft"] {', 1)[1].split("}", 1)[0]
    for token in ("--okf-fg:", "--okf-border-strong:", "--okf-active-fill:",
                  "--okf-active-fg:", "--okf-active-border:", "--okf-page-bg:"):
        assert token in soft, f"contrast=soft must remap {token}"
    # Border modifiers drive --okf-border-strong.
    off = css.split('[data-okf-border="off"]', 1)[1].split("}", 1)[0]
    assert "--okf-border-strong: transparent" in off
```

- [ ] **Step 2: Run — verify it FAILS:**

Run: `python3 -m pytest tests/test_render.py::test_appearance_contrast_and_border_modifier_blocks -q`
Expected: FAIL (`[data-okf-contrast="soft"]` not in css). Read the summary line.

- [ ] **Step 3: GREEN — insert the modifier blocks.** In `wiki.css`, find the reset-section comment that immediately follows the `swiss-dark` block:

```css
/* ---- Reset / base ------------------------------------------------------ */
```
Replace it with (the two modifier blocks, then the original comment):
```css
/* ============ Appearance modifiers (Round 2 §5.1) ====================
 * Orthogonal, persisted runtime modifiers applied on <html> AFTER the theme
 * blocks. :root[data-*] specificity (0,2,0) beats [data-theme] (0,1,0), so
 * these win on any theme. Defaults = attribute ABSENT (today's contrasty
 * look). The border block is placed AFTER the contrast block so
 * border="off" (transparent) wins over contrast="soft" (--okf-border) on the
 * shared --okf-border-strong; border="muted" and contrast="soft" agree. */
:root[data-okf-contrast="soft"] {
  --okf-fg:            var(--okf-fg-soft);
  --okf-border-strong: var(--okf-border);          /* softer frames */
  --okf-active-fill:   var(--okf-active-fill-soft);
  --okf-active-fg:     var(--okf-active-fg-soft);
  --okf-active-border: var(--okf-active-border-soft);
  --okf-page-bg:       var(--okf-page-bg-soft);
}
:root[data-okf-border="muted"] { --okf-border-strong: var(--okf-border); }
:root[data-okf-border="off"]   { --okf-border-strong: transparent; }

/* ---- Reset / base ------------------------------------------------------ */
```

- [ ] **Step 4: GREEN — run the test + brace sanity + full render suite:**

Run: `python3 -m pytest tests/test_render.py -q && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/wiki.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: PASS (new test + all existing render tests); braces balanced.

- [ ] **Step 5: Commit**

```bash
git add tests/test_render.py scripts/okf_loom/viewer/static/wiki.css
git commit -m "feat(theme): border + contrast modifier blocks (orthogonal root data-attrs, defaults unchanged)"
```

---

### Task 3: Appearance-menu markup (server-side, replaces the theme-cycle button)

Rewrite `_theme_button_html` to emit the `Aa ▾` trigger + a hidden popover with 4 radiogroups (family/mode/contrast/border). **One function feeds all 5 surfaces** (via `_nav_controls_html` for concept/index/search + the `__INITIAL_THEME_BUTTON__` placeholder for graph/single_file). The trigger keeps `id="okf-theme"` so the existing JS bindings resolve it. Server reflects family/mode from `initial_theme`; contrast/border default high/on (the server can't read localStorage — the client corrects `aria-checked` at boot, Task 5/6).

**⚠️ After this task, RESTART the serve** (render.py is read at startup). Until Task 5 wires it, the popover is inert on reading pages and the old cycle click no longer fires — that intermediate state is expected; visual correctness lands at Task 5 (reading pages) / Task 6 (graph).

**Files:**
- Modify: `scripts/okf_loom/render.py` — `_theme_button_html` (def ~568-584). Leave `_THEMES`/`_THEME_GLYPHS` defined (still referenced by the sync comment; `_THEME_GLYPHS` simply becomes unused by this function — harmless).
- Modify: `tests/test_render.py` — new markup test.

- [ ] **Step 1: RED — write the failing test.** Add to `tests/test_render.py`, using the same helper + fixture as `test_p1_3_static_concept_nav_urls_have_html_extension` — the review identified these as `_render_concept_html(bundle_root, concept_id)` (test_render.py:309) with the `tiny_good_bundle` fixture (conftest.py:37). Verify by reading test_p1_3 and copy its exact render call:

```python
def test_appearance_menu_replaces_theme_cycle_button(tiny_good_bundle: _Path) -> None:
    """Round 2 §5.3: the topbar theme control is an Appearance popover
    (family/mode/contrast/border), not a bare cycle button. The trigger keeps
    id=okf-theme; the search form + Graph link (P1-3 contract) survive."""
    html = _render_concept_html(tiny_good_bundle, "tables/users")  # same as test_p1_3
    assert 'id="okf-theme"' in html
    assert 'aria-haspopup="true"' in html
    assert 'class="okf-appearance__menu"' in html
    for setk in ("family", "mode", "contrast", "border"):
        assert f'data-okf-set="{setk}"' in html, f"missing {setk} radiogroup"
    for val in ("technical", "swiss", "light", "dark", "auto",
                "high", "soft", "on", "muted", "off"):
        assert f'data-okf-val="{val}"' in html, f"missing option {val}"
    # P1-3 topbar contract survives.
    assert 'role="search"' in html
    assert ">Graph<" in html
```
(If test_p1_3's helper/args differ from `_render_concept_html(tiny_good_bundle, "tables/users")`, copy its exact call — the point is to render one concept page and assert on the returned HTML string.)

- [ ] **Step 2: Run — verify it FAILS:**

Run: `python3 -m pytest tests/test_render.py::test_appearance_menu_replaces_theme_cycle_button -q`
Expected: FAIL (`okf-appearance__menu` not in html). Read the summary line.

- [ ] **Step 3: GREEN — rewrite `_theme_button_html`.** Replace the entire function (`def _theme_button_html(initial_theme: str) -> str:` through its `return (...)`) with:

```python
def _theme_button_html(initial_theme: str) -> str:
    """Appearance-menu trigger + popover (Round 2 §5.3), server-rendered to
    avoid FOUC. Replaces the former theme-cycle button. Consolidates family
    (technical/swiss) · mode (light/dark/auto) · contrast (high/soft) · border
    (on/muted/off). The trigger keeps id="okf-theme" so the wiki.js/graph.js/
    studio.js bindings resolve it; the wiring (open/close + option handlers,
    each reusing its bundle's applyTheme) lives in those IIFEs. contrast/border
    default to high/on server-side (the server can't read the user's
    localStorage); the client corrects aria-checked at boot.
    """
    theme = initial_theme if initial_theme in _THEMES else ""
    if theme:
        family, _, mode = theme.partition("-")  # "swiss-light" -> "swiss","light"
    else:
        family, mode = "swiss", "auto"          # auto resolves within Swiss (see JS)

    def _opt(setk: str, val: str, label: str, checked: bool) -> str:
        return (
            '<button type="button" role="radio" class="okf-appearance__opt" '
            f'data-okf-set="{setk}" data-okf-val="{val}" '
            f'aria-checked="{"true" if checked else "false"}">{label}</button>'
        )

    def _group(setk: str, label: str, opts: tuple, current: str) -> str:
        buttons = "".join(_opt(setk, v, lbl, v == current) for v, lbl in opts)
        return (
            f'<div class="okf-appearance__group" role="radiogroup" aria-label="{label}">'
            f'<span class="okf-appearance__label">{label}</span>{buttons}</div>'
        )

    groups = (
        _group("family", "Family",
               (("technical", "Technical"), ("swiss", "Swiss")), family)
        + _group("mode", "Mode",
                 (("light", "Light"), ("dark", "Dark"), ("auto", "Auto")), mode)
        + _group("contrast", "Contrast",
                 (("high", "High"), ("soft", "Soft")), "high")
        + _group("border", "Border",
                 (("on", "On"), ("muted", "Muted"), ("off", "Off")), "on")
    )
    return (
        '<div class="okf-appearance">'
        '<button id="okf-theme" type="button" class="okf-appearance__trigger" '
        'aria-haspopup="true" aria-expanded="false" '
        'aria-controls="okf-appearance-menu" aria-label="Appearance settings" '
        'title="Appearance">Aa <span aria-hidden="true">▾</span></button>'
        '<div class="okf-appearance__menu" id="okf-appearance-menu" role="dialog" '
        f'aria-label="Appearance" hidden>{groups}</div>'
        '</div>'
    )
```

- [ ] **Step 4: GREEN — run the new test + the P1-3 contract + the full render suite:**

Run: `python3 -m pytest tests/test_render.py -q`
Expected: PASS — the new test, `test_p1_3_static_concept_nav_urls_have_html_extension`, and all others. Read the summary line.

- [ ] **Step 5: Commit**

```bash
git add scripts/okf_loom/render.py tests/test_render.py
git commit -m "feat(viewer): Appearance-menu markup replaces the theme-cycle button (all 5 surfaces)"
```

---

### Task 4: Appearance-menu CSS (universal — `wiki.css`)

Style the trigger + popover with tokens only (works in static builds on every surface; `wiki.css` is the one stylesheet present on all 5). Active option = the active-state token trio, so it reads correctly under every theme AND under soft/border modifiers.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — append near the topbar-controls rules (grep `.okf-btn {` or `.okf-topbar__controls`).

- [ ] **Step 1: Add the CSS.** Append this block adjacent to the existing `.okf-topbar__controls` / `.okf-btn` rules:

```css
/* ---- Appearance menu (Round 2 §5.3) ---------------------------------- */
.okf-appearance { position: relative; display: inline-flex; }
.okf-appearance__trigger {
  display: inline-flex; align-items: center; gap: 2px;
  padding: 4px 10px;
  font: inherit; font-size: var(--okf-text-sm); line-height: 1.2;
  border: var(--okf-border-w) solid var(--okf-border-strong);
  border-radius: var(--okf-radius-sm);
  background: var(--okf-bg-elev); color: var(--okf-fg);
  cursor: pointer;
}
.okf-appearance__trigger:hover { border-color: var(--okf-accent); color: var(--okf-accent); }
.okf-appearance__trigger:focus-visible { outline: 2px solid var(--okf-accent); outline-offset: 1px; }
.okf-appearance__menu {
  position: absolute; top: calc(100% + var(--okf-space-1)); right: 0;
  z-index: 30;                       /* above topbar chrome + content */
  display: flex; flex-direction: column; gap: var(--okf-space-3);
  min-width: 220px;
  padding: var(--okf-space-3) var(--okf-space-4);
  background: var(--okf-bg-elev);
  border: var(--okf-border-w) solid var(--okf-border-strong);
  border-radius: var(--okf-radius);
  box-shadow: var(--okf-pop-shadow);
}
.okf-appearance__menu[hidden] { display: none; }
.okf-appearance__group {
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--okf-space-1);
}
.okf-appearance__label {
  flex: 0 0 100%;
  font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--okf-fg-muted); margin-bottom: 2px;
}
.okf-appearance__opt {
  padding: 4px 10px; font: inherit; font-size: var(--okf-text-sm);
  border: var(--okf-border-w) solid var(--okf-border);
  border-radius: var(--okf-radius-sm);
  background: transparent; color: var(--okf-fg-muted); cursor: pointer;
}
.okf-appearance__opt:hover { color: var(--okf-fg); border-color: var(--okf-border-strong); }
.okf-appearance__opt[aria-checked="true"] {
  color: var(--okf-active-fg);
  background: var(--okf-active-fill);
  border-color: var(--okf-active-border);
}
.okf-appearance__opt:focus-visible { outline: 2px solid var(--okf-accent); outline-offset: 1px; }
```
(The `font-size: 10px` on `.okf-appearance__label` intentionally matches the established micro-label size used by `.okf-nav__group` / `.okf-local-graph__title` — the codebase's accepted exception to the token rule for these tiny uppercase group labels. Keep it consistent with those, or swap all three to a shared token in a later pass.)

- [ ] **Step 2: Sanity — braces balanced:**

Run: `python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/wiki.css').read_text(); assert s.count('{')==s.count('}'), (s.count('{'), s.count('}'))"`
Expected: no assertion error.

- [ ] **Step 3: Commit**

```bash
git add scripts/okf_loom/viewer/static/wiki.css
git commit -m "feat(viewer): Appearance-menu CSS (tokenised trigger + popover, theme/modifier-aware)"
```

---

### Task 5: Appearance-menu wiring — `wiki.js` (concept / index / search) + post-paint modifiers

Wire the popover inside the `wiki.js` IIFE (reusing its local `applyTheme`, which is not exported). Add the post-paint contrast/border readers, the family/mode helpers (D5 semantics), popover open/close, the option-click handler, state reflection, and Esc/click-away. Remove the now-defunct glyph write from `applyTheme` and replace the cycle click handler.

**D5 model (single-key `okf-theme` preserved):** family/mode are *derived* from `okf-theme` for display. Picking a **mode** sets `<family>-<mode>` (concrete, persisted); **Auto** removes the key and applies the OS-resolved theme within the current family (unpinned — a reload of an Auto preference resolves to Swiss, matching today's boot). Picking a **family** swaps the prefix of the current theme (or, when Auto, applies that family at the current OS mode without persisting). contrast/border set/remove their root attr + localStorage key (default value ⇒ attr + key removed).

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.js` — `applyTheme` (glyph block), the cycle click handler.
- Test: `tests/test_studio_iter1_browser.py`.

- [ ] **Step 1: Remove the glyph write from `applyTheme`.** In `wiki.js`, find the `if (themeBtn) { … }` block inside `applyTheme`:

```js
    if (themeBtn) {
      themeBtn.textContent = THEME_GLYPHS[t];
      themeBtn.setAttribute("title", "Theme: " + t + " — click to cycle");
      themeBtn.setAttribute("aria-label", "Change colour theme (current: " + t + ")");
      // The button cycles four themes now; it is no longer a two-state
      // toggle, so aria-pressed would be dishonest.
      themeBtn.removeAttribute("aria-pressed");
    }
```
Replace it with:
```js
    // (Round 2) The trigger is the Appearance popover ("Aa ▾"), not a glyph —
    // nothing to sync here; the popover reflects state via reflectAppearance().
```
(Leave `THEME_GLYPHS` defined — it stays in sync with the other bundles per the decoupling contract; it is simply unused in `wiki.js` now.)

- [ ] **Step 2: Replace the cycle click handler with the Appearance module.** In `wiki.js`, find the cycle handler (the file's last lines of theme wiring):

```js
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = (THEMES.indexOf(currentTheme()) + 1) % THEMES.length;
      applyTheme(THEMES[next]);
    });
  }
```
Replace it with:
```js
  // ---- Appearance menu (Round 2 §5.3) --------------------------------
  // Consolidates family/mode/contrast/border. Wiring lives here because the
  // theme setter applyTheme is IIFE-local. contrast/border are applied
  // POST-paint from localStorage (no pre-paint script exists; inline scripts
  // are CSP-blocked on 4/5 templates) — same timing as the theme read above.
  var CONTRAST_KEY = "okf-contrast", BORDER_KEY = "okf-border";
  var apMenu = document.getElementById("okf-appearance-menu");
  var apWrap = themeBtn && themeBtn.closest ? themeBtn.closest(".okf-appearance") : null;

  function applyModifier(kind, val, persist) {
    var attr = kind === "contrast" ? "data-okf-contrast" : "data-okf-border";
    var key = kind === "contrast" ? CONTRAST_KEY : BORDER_KEY;
    var def = kind === "contrast" ? "high" : "on";   // default = attribute absent
    if (val && val !== def) document.documentElement.setAttribute(attr, val);
    else document.documentElement.removeAttribute(attr);
    if (persist !== false) {
      try {
        if (val && val !== def) localStorage.setItem(key, val);
        else localStorage.removeItem(key);
      } catch (e) {}
    }
  }
  // Apply persisted modifiers now (post-paint; mirrors the theme read above).
  try { applyModifier("contrast", localStorage.getItem(CONTRAST_KEY), false); } catch (e) {}
  try { applyModifier("border", localStorage.getItem(BORDER_KEY), false); } catch (e) {}

  function currentFamily() {
    return currentTheme().indexOf("technical") === 0 ? "technical" : "swiss";
  }
  function currentMode() {
    var s = null; try { s = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    if (s && LEGACY_THEMES[s]) s = LEGACY_THEMES[s];
    if (!s || THEMES.indexOf(s) < 0) return "auto";
    return s.indexOf("dark") >= 0 ? "dark" : "light";
  }
  function resolveAutoFamily(fam) {
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return fam + (dark ? "-dark" : "-light");
  }
  function setFamily(fam) {
    if (currentMode() === "auto") applyTheme(resolveAutoFamily(fam), false); // stay auto, respect family
    else applyTheme(fam + "-" + currentMode());
  }
  function setMode(mode) {
    if (mode === "auto") {
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      applyTheme(resolveAutoFamily(currentFamily()), false);
    } else applyTheme(currentFamily() + "-" + mode);
  }

  function reflectAppearance() {
    if (!apMenu) return;
    var st = {
      family: currentFamily(), mode: currentMode(),
      contrast: document.documentElement.getAttribute("data-okf-contrast") || "high",
      border: document.documentElement.getAttribute("data-okf-border") || "on",
    };
    var opts = apMenu.querySelectorAll(".okf-appearance__opt"), i, o;
    for (i = 0; i < opts.length; i++) {
      o = opts[i];
      o.setAttribute("aria-checked",
        st[o.getAttribute("data-okf-set")] === o.getAttribute("data-okf-val") ? "true" : "false");
    }
  }
  function openAppearance() {
    if (!apMenu) return;
    apMenu.hidden = false;
    if (themeBtn) themeBtn.setAttribute("aria-expanded", "true");
    reflectAppearance();
  }
  function closeAppearance() {
    if (!apMenu) return;
    apMenu.hidden = true;
    if (themeBtn) themeBtn.setAttribute("aria-expanded", "false");
  }

  if (themeBtn) themeBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    if (apMenu && apMenu.hidden) openAppearance(); else closeAppearance();
  });
  if (apMenu) apMenu.addEventListener("click", function (e) {
    var opt = e.target && e.target.closest ? e.target.closest(".okf-appearance__opt") : null;
    if (!opt) return;
    var k = opt.getAttribute("data-okf-set"), v = opt.getAttribute("data-okf-val");
    if (k === "family") setFamily(v);
    else if (k === "mode") setMode(v);
    else applyModifier(k, v);            // contrast | border
    reflectAppearance();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && apMenu && !apMenu.hidden) {
      closeAppearance();
      if (themeBtn) themeBtn.focus();
    }
  });
  document.addEventListener("click", function (e) {
    if (apMenu && !apMenu.hidden && apWrap && !apWrap.contains(e.target)) closeAppearance();
  });
  reflectAppearance();
```

- [ ] **Step 3: Sanity — JS parses:**

Run: `node --check scripts/okf_loom/viewer/static/wiki.js`
Expected: no output (valid).

- [ ] **Step 4: Write the failing browser test.** Add to `tests/test_studio_iter1_browser.py`. The real fixtures are `server_url` (module-scoped serve) + `page`; there is **no** `studio_page` fixture — navigate + `_wait_for_studio(page)` yourself, as the neighbours do (e.g. `page.goto(f"{server_url}/tables/orders", wait_until="load"); _wait_for_studio(page)` at ~line 131):

```python
def test_appearance_menu_sets_contrast_border_and_theme(server_url, page):
    """Round 2 §5.3: the Appearance popover drives contrast/border/theme + persists."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.wait_for_selector("#okf-theme", timeout=10000).click()
    page.wait_for_selector(".okf-appearance__menu:not([hidden])", timeout=5000)
    page.click('.okf-appearance__opt[data-okf-set="contrast"][data-okf-val="soft"]')
    assert page.evaluate("document.documentElement.getAttribute('data-okf-contrast')") == "soft"
    assert page.evaluate("localStorage.getItem('okf-contrast')") == "soft"
    page.click('.okf-appearance__opt[data-okf-set="border"][data-okf-val="off"]')
    assert page.evaluate("document.documentElement.getAttribute('data-okf-border')") == "off"
    assert page.evaluate("localStorage.getItem('okf-border')") == "off"
    page.click('.okf-appearance__opt[data-okf-set="family"][data-okf-val="technical"]')
    assert page.evaluate("document.documentElement.getAttribute('data-theme')").startswith("technical")
    assert page.get_attribute(
        '.okf-appearance__opt[data-okf-set="contrast"][data-okf-val="soft"]', "aria-checked") == "true"
    # Back to defaults removes the attr + key (default = absent).
    page.click('.okf-appearance__opt[data-okf-set="contrast"][data-okf-val="high"]')
    assert page.evaluate("document.documentElement.getAttribute('data-okf-contrast')") is None
    assert page.evaluate("localStorage.getItem('okf-contrast')") is None
```

- [ ] **Step 5: Run — new test passes; render/theme suite stays green:**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "appearance_menu_sets" -q && python3 -m pytest tests/test_render.py -q`
Expected: PASS. Read the summary line. (Serve is not needed for pytest; the browser tests spin their own server.)

- [ ] **Step 6: Commit**

```bash
git add scripts/okf_loom/viewer/static/wiki.js tests/test_studio_iter1_browser.py
git commit -m "feat(viewer): Appearance-menu wiring + post-paint contrast/border (wiki.js: concept/index/search)"
```

---

### Task 6: Appearance-menu wiring — `graph.js` (graph + single-file) + `studio.js` glyph removal

Wire the same popover in `graph.js` (which is also **inlined into `single_file.html`**). Scope note: in `graph.js`, `applyTheme` and the theme button live at **top-level** (IIFE), but `syncLabelColour` (the canvas re-sync) is defined **inside `init(bundle)`** (async, after the graph loads). So we bridge with a top-level `onThemeApplied` hook that `init` registers to `syncLabelColour`; then any `applyTheme` (menu, OS, or boot) recolours the canvas. Also remove the glyph write from `studio.js applyThemeAttr` so a palette-driven theme change doesn't clobber the `Aa ▾` trigger.

Per D3, contrast/border do NOT reach the Cytoscape canvas (`GRAPH_COLORS` is a hardcoded per-`data-theme` mirror) — the graph *chrome* reflects them; the canvas keeps its per-theme palette. This is left as-is (documented) to avoid restructuring `GRAPH_COLORS` (which would risk `test_iter2_graph_selection_color_is_token_governed`). Do NOT touch graph.js's legacy OS-dark boot path (`applyTheme("dark")` etc.) — a separate pre-existing quirk, out of scope.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/graph.js` — `applyTheme` (226-237), the cycle handler (369-372), the `syncLabelColour` click hook (1185-1186, inside `init`).
- Modify: `scripts/okf_loom/viewer/static/studio.js` — `applyThemeAttr` glyph block (244-250).
- Test: `tests/test_viewer_browser.py` (the graph-page browser suite).

- [ ] **Step 1: graph.js — add the `onThemeApplied` hook to `applyTheme` (persist param, drop glyph).** Replace the whole function:

```js
  function applyTheme(t) {
    if (THEMES.indexOf(t) < 0) t = "light";
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem(STORAGE_KEY, t); } catch (e) {}
    if (themeBtn) {
      themeBtn.textContent = THEME_GLYPHS[t];
      themeBtn.setAttribute("title", "Theme: " + t + " — click to cycle");
      themeBtn.setAttribute("aria-label", "Change colour theme (current: " + t + ")");
      // Five-way cycle, not a two-state toggle — aria-pressed would lie.
      themeBtn.removeAttribute("aria-pressed");
    }
  }
```
with:
```js
  var onThemeApplied = null;   // registered by init() → syncLabelColour (canvas re-sync)
  function applyTheme(t, persist) {
    if (THEMES.indexOf(t) < 0) t = "light";
    document.documentElement.setAttribute("data-theme", t);
    if (persist !== false) { try { localStorage.setItem(STORAGE_KEY, t); } catch (e) {} }
    // (Round 2) The trigger is the Appearance popover ("Aa ▾") — no glyph to
    // sync. Any theme change recolours the canvas through onThemeApplied.
    if (onThemeApplied) onThemeApplied();
  }
```

- [ ] **Step 2: graph.js — replace the cycle handler with the Appearance module.** Replace:

```js
  if (themeBtn) themeBtn.addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme") || "light";
    applyTheme(THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length]);
  });
```
with:
```js
  // ---- Appearance menu (Round 2 §5.3) --------------------------------
  // Same popover as wiki.js, wired here for the graph + single-file viewers
  // (graph.js is inlined into single_file). Reuses graph's applyTheme (which
  // drives the canvas re-sync via onThemeApplied). contrast/border apply
  // post-paint and do NOT reach the Cytoscape canvas (documented P2 limit).
  var CONTRAST_KEY = "okf-contrast", BORDER_KEY = "okf-border";
  var apMenu = document.getElementById("okf-appearance-menu");
  var apWrap = themeBtn && themeBtn.closest ? themeBtn.closest(".okf-appearance") : null;

  function applyModifier(kind, val, persist) {
    var attr = kind === "contrast" ? "data-okf-contrast" : "data-okf-border";
    var key = kind === "contrast" ? CONTRAST_KEY : BORDER_KEY;
    var def = kind === "contrast" ? "high" : "on";
    if (val && val !== def) document.documentElement.setAttribute(attr, val);
    else document.documentElement.removeAttribute(attr);
    if (persist !== false) {
      try {
        if (val && val !== def) localStorage.setItem(key, val);
        else localStorage.removeItem(key);
      } catch (e) {}
    }
  }
  try { applyModifier("contrast", localStorage.getItem(CONTRAST_KEY), false); } catch (e) {}
  try { applyModifier("border", localStorage.getItem(BORDER_KEY), false); } catch (e) {}

  function apFamily() {
    return (document.documentElement.getAttribute("data-theme") || "swiss-light")
      .indexOf("technical") === 0 ? "technical" : "swiss";
  }
  function apMode() {
    var s = null; try { s = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    if (!s || THEMES.indexOf(s) < 0) return "auto";
    return s.indexOf("dark") >= 0 ? "dark" : "light";
  }
  function apAutoFamily(fam) {
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return fam + (dark ? "-dark" : "-light");
  }
  function apSetFamily(fam) {
    if (apMode() === "auto") applyTheme(apAutoFamily(fam), false);
    else applyTheme(fam + "-" + apMode());
  }
  function apSetMode(mode) {
    if (mode === "auto") {
      try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
      applyTheme(apAutoFamily(apFamily()), false);
    } else applyTheme(apFamily() + "-" + mode);
  }
  function apReflect() {
    if (!apMenu) return;
    var st = {
      family: apFamily(), mode: apMode(),
      contrast: document.documentElement.getAttribute("data-okf-contrast") || "high",
      border: document.documentElement.getAttribute("data-okf-border") || "on",
    };
    var opts = apMenu.querySelectorAll(".okf-appearance__opt"), i, o;
    for (i = 0; i < opts.length; i++) {
      o = opts[i];
      o.setAttribute("aria-checked",
        st[o.getAttribute("data-okf-set")] === o.getAttribute("data-okf-val") ? "true" : "false");
    }
  }
  function apOpen() { if (apMenu) { apMenu.hidden = false; if (themeBtn) themeBtn.setAttribute("aria-expanded", "true"); apReflect(); } }
  function apClose() { if (apMenu) { apMenu.hidden = true; if (themeBtn) themeBtn.setAttribute("aria-expanded", "false"); } }

  if (themeBtn) themeBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    if (apMenu && apMenu.hidden) apOpen(); else apClose();
  });
  if (apMenu) apMenu.addEventListener("click", function (e) {
    var opt = e.target && e.target.closest ? e.target.closest(".okf-appearance__opt") : null;
    if (!opt) return;
    var k = opt.getAttribute("data-okf-set"), v = opt.getAttribute("data-okf-val");
    if (k === "family") apSetFamily(v);
    else if (k === "mode") apSetMode(v);
    else applyModifier(k, v);
    apReflect();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && apMenu && !apMenu.hidden) { apClose(); if (themeBtn) themeBtn.focus(); }
  });
  document.addEventListener("click", function (e) {
    if (apMenu && !apMenu.hidden && apWrap && !apWrap.contains(e.target)) apClose();
  });
  apReflect();
```

- [ ] **Step 3: graph.js — register the canvas re-sync hook inside `init`.** Find (inside `init`, just after `syncLabelColour()` is first called):

```js
    var themeBtn2 = document.getElementById("okf-theme");
    if (themeBtn2) themeBtn2.addEventListener("click", syncLabelColour);
```
Replace with:
```js
    // (Round 2) Any applyTheme() recolours the canvas via this hook — so a
    // theme change from the Appearance menu (or OS) re-syncs, even though the
    // trigger click now opens the popover instead of cycling.
    onThemeApplied = syncLabelColour;
```
(Leave the OS-change listener below it untouched; its explicit `syncLabelColour()` is now a harmless double-call.)

- [ ] **Step 4: studio.js — remove the glyph write from `applyThemeAttr`.** Replace:

```js
    // Keep the existing topbar cycle button (wiki.js) in sync if present.
    const tb = document.getElementById("okf-theme");
    if (tb) {
      tb.textContent = THEME_GLYPHS[t];
      tb.setAttribute("title", "Theme: " + t + " — click to cycle");
      tb.setAttribute("aria-label", "Change colour theme (current: " + t + ")");
      tb.removeAttribute("aria-pressed");
    }
```
with:
```js
    // (Round 2) The topbar control is the Appearance popover ("Aa ▾"), wired by
    // wiki.js — no glyph to sync here (studio.js does not own the popover).
```
(Leave `THEME_GLYPHS` defined in all three bundles per the decoupling contract; it is now unused by these setters — harmless for `node --check`.)

- [ ] **Step 5: Sanity — both parse:**

Run: `node --check scripts/okf_loom/viewer/static/graph.js && node --check scripts/okf_loom/viewer/static/studio.js`
Expected: no output (valid).

- [ ] **Step 6: Write the failing graph-page test.** Add to `tests/test_viewer_browser.py` (reuse its graph-page fixture — the one that loads `/__graph` / the graph page and waits for `#okf-graph`; match the file's existing pattern):

```python
def test_graph_appearance_menu_sets_contrast_and_theme(server_url, page):
    """Round 2: the graph page's Appearance popover drives contrast + theme."""
    page.goto(f"{server_url}/__graph", wait_until="domcontentloaded")
    page.wait_for_selector("#okf-graph", timeout=15000)
    page.wait_for_selector("#okf-theme", timeout=10000).click()
    page.wait_for_selector(".okf-appearance__menu:not([hidden])", timeout=5000)
    page.click('.okf-appearance__opt[data-okf-set="contrast"][data-okf-val="soft"]')
    assert page.evaluate("document.documentElement.getAttribute('data-okf-contrast')") == "soft"
    page.click('.okf-appearance__opt[data-okf-set="mode"][data-okf-val="dark"]')
    assert page.evaluate("document.documentElement.getAttribute('data-theme')").endswith("-dark")
```
(Match the exact graph-page URL + fixture signature the neighbouring graph tests use — read one and copy its `page.goto(...)` + fixture params.)

- [ ] **Step 7: Run — new test passes; the graph token/selection test stays green:**

Run: `python3 -m pytest tests/test_viewer_browser.py -k "graph_appearance" -q && python3 -m pytest tests/test_render.py -k "graph_selection or select_token" -q`
Expected: PASS. Read the summary line.

- [ ] **Step 8: Commit**

```bash
git add scripts/okf_loom/viewer/static/graph.js scripts/okf_loom/viewer/static/studio.js tests/test_viewer_browser.py
git commit -m "feat(viewer): Appearance-menu wiring for graph/single-file (canvas re-sync bridge) + studio glyph drop"
```

---

### Task 7: Footer Studio button (off-rail studio access — carryover)

Add a footer **Studio** button that opens the overlay, shown only where the rail is **absent** (non-concept pages at any width, OR concept pages on mobile ≤900px). On desktop concept pages the rail owns Comments/Changes, so no footer duplication. The overlay machinery (`openPanel`) already exists on every page.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js` — footer control construction (near `paletteBtn`), `mountBar` (409-417).
- Test: `tests/test_studio_iter1_browser.py`.

- [ ] **Step 1: Build the Studio button.** In `studio.js`, find where `paletteBtn` is constructed (grep `paletteBtn = el(`). Immediately after it, add:

```js
  // Round 2 carryover: a direct studio opener for pages/viewports without the
  // rail. Opens Comments on a concept page (mobile), Changes elsewhere (the
  // global feed; a non-concept page has no per-concept comments).
  const studioBtn = el("button", { type: "button", class: "okf-studiobtn okf-studio-open-btn",
    "aria-haspopup": "dialog", title: "Open the studio panel", "aria-label": "Open studio panel" },
    [document.createTextNode("Studio")]);
  studioBtn.addEventListener("click", function () {
    openPanel(isConceptPage() ? "comments" : "changes");
  });
```

- [ ] **Step 2: Append it only when the rail is absent.** Replace `mountBar`:

```js
  function mountBar() {
    // Bottom status strip: append as the last in-flow child of the flex-column
    // body so it pins to the viewport bottom (sticky, see studio.css).
    document.body.appendChild(bar);
    if (isConceptPage()) {
      leftGroup.appendChild(viewSwitch);
      leftGroup.appendChild(focusBtn);
    }
  }
```
with:
```js
  function mountBar() {
    // Bottom status strip: append as the last in-flow child of the flex-column
    // body so it pins to the viewport bottom (sticky, see studio.css).
    document.body.appendChild(bar);
    // Round 2 carryover: show the direct Studio opener wherever the rail is
    // ABSENT — non-concept pages (any width) OR concept pages on mobile
    // (<=900). Desktop concept pages have the rail, so no footer duplication.
    // (mountBar runs before body.okf-has-rail is set, so test the predicate
    // directly.) Placed before the concept-only view controls so order reads
    // Watch · Commands · Studio · [Rendered/Source/Split · Focus].
    var railPresent = isConceptPage() && window.innerWidth > 900;
    if (!railPresent) leftGroup.appendChild(studioBtn);
    if (isConceptPage()) {
      leftGroup.appendChild(viewSwitch);
      leftGroup.appendChild(focusBtn);
    }
  }
```

- [ ] **Step 3: Sanity — JS parses:**

Run: `node --check scripts/okf_loom/viewer/static/studio.js`
Expected: no output (valid).

- [ ] **Step 4: Write the failing tests.** Add to `tests/test_studio_iter1_browser.py` using the real `server_url` + `page` fixtures (no `studio_page` fixture exists). The first navigates to the **index** (non-concept — no rail); the second to a concept page at desktop width (rail present). studio.js is injected on every page (server.py:1733) so the footer mounts on both:

```python
def test_footer_studio_button_opens_panel_on_non_concept_page(server_url, page):
    """Round 2 carryover: off-rail pages get a direct footer Studio opener."""
    page.set_viewport_size({"width": 1200, "height": 900})
    page.goto(f"{server_url}/", wait_until="load")   # index — non-concept, no rail
    # The button only appears once studio has booted + mountBar ran.
    btn = page.wait_for_selector(".okf-studio-bar--status .okf-studio-open-btn", timeout=15000)
    btn.click()
    page.wait_for_selector(".okf-panel:not([hidden])", timeout=5000)

def test_no_footer_studio_button_on_desktop_concept(server_url, page):
    """Desktop concept pages have the rail, so NO duplicate footer Studio button."""
    page.set_viewport_size({"width": 1200, "height": 900})   # >900 → rail builds at boot
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.wait_for_selector(".okf-rail", timeout=10000)
    assert page.query_selector(".okf-studio-open-btn") is None
```
(The index test gates on the button selector itself rather than `_wait_for_studio`, in case that helper waits on concept-only DOM.)

- [ ] **Step 5: Run — new tests pass:**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "footer_studio_button or no_footer_studio_button" -q`
Expected: PASS. Read the summary line.

- [ ] **Step 6: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.js tests/test_studio_iter1_browser.py
git commit -m "feat(studio): footer Studio button for off-rail pages (mobile concept + non-concept)"
```

---

### Task 8: Polish nits — rail resting contrast + footer divider (carryover)

Two trivial CSS tweaks from the Phase-1 self-review. No tests (visual); confirmed in Task 10.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-rail__btn` resting colour; the footer divider/ambient margin.

- [ ] **Step 1: Make the rail icons prominent at rest.** The bare `color: var(--okf-fg-muted); cursor: pointer;` sequence is NOT unique (it also ends `.okf-toast__close` and a 24px icon-button), so anchor on the unique `.okf-rail__btn {` selector and replace the whole base rule, changing only its resting `color`:

```css
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
```
→
```css
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
  color: var(--okf-fg);      /* Round 2: rail icons read clearly at rest (was --okf-fg-muted) */
  cursor: pointer;
}
```
(Leave `.okf-rail__btn:hover` and `.okf-rail__btn[aria-pressed="true"]` untouched. If `--okf-fg` reads too strong in Task 10's visual pass, dial to a mid tone there.)

- [ ] **Step 2: Move the footer divider beside the ambient group.** The wide gap comes from `margin-left: auto` on the **right group**, which packs the divider against the actions. Move that auto-margin onto the **divider** so the divider hugs the ambient group and all slack sits between actions and divider. Replace:

```css
.okf-studio-bar--status .okf-studio-bar__group--right {
  margin-left: auto;
}
```
with:
```css
/* Round 2: push the divider (and the ambient group after it) to the right so
 * the divider sits BESIDE the ambient readouts, not hugging the actions. */
.okf-studio-bar--status .okf-studio-bar__divider {
  margin-left: auto;
}
```

- [ ] **Step 3: Sanity — braces balanced:**

Run: `python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/studio.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: no assertion error.

- [ ] **Step 4: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.css
git commit -m "fix(studio): rail icons prominent at rest + footer divider beside ambient (Phase-1 polish)"
```

---

### Task 9: Remove the dead `.okf-sidebar-panel` card/drag subsystem

Phase 1 retired all draggable sidebar cards (Related is now flat). The card/drag subsystem is fully dead. Remove it. **Preserve `buildSidebarPanels`** (it still mounts the Diátaxis nav + flat Related + local-graph pills) and `buildIntentsToolbar` (the live Comments-tab intents — unrelated). This is verified safe: the only test touching `.okf-sidebar-panel` (`test_related_section_is_flat_not_a_sidebar_panel_card`) asserts the class is **absent**, so removal *enforces* it; no test references the JS symbols (mapper-confirmed blast radius).

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js` — excise the card path from `buildSidebarPanels`; delete the orphaned symbols.
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — delete the 14 dead `.okf-sidebar-panel*` blocks + the stale doc-comment; keep `.okf-related`.

- [ ] **Step 1: Excise the card path from `buildSidebarPanels`.** In `studio.js`, remove the `getSidebarState()` call line inside `buildSidebarPanels`:

```js
    var sbState = getSidebarState();
```
and remove the dead loop + DnD call (verbatim block):
```js
    // Build any remaining dynamic panels in saved order, below Related.
    // "sections" (→ Outline tab), "intents" (→ Comments tab), and "related"
    // (flat above, handled directly) are retired from the draggable-card
    // path; skip them in any legacy saved order.
    sbState.order.forEach(function (panelId) {
      if (panelId === "sections" || panelId === "intents" || panelId === "related") return;
      var panel = buildPanel(panelId, sbState, existingGraph);
      if (panel) sidebar.appendChild(panel);
    });

    // Wire drag-and-drop reordering.
    wireSidebarDnD(sidebar, sbState);
```
Then **grep `sbState` inside `buildSidebarPanels`** to confirm no remaining use (mapper verified `sbState` fed only the loop+DnD; the nav re-mount + flat Related + local-graph pills do not use it). If any remains, keep only what those live parts need.

- [ ] **Step 2: Delete the orphaned symbols.** Each is now unreachable (mapper-confirmed: no references outside the dead subsystem, no test references). For **each**, grep it first to confirm zero remaining call sites, then delete its full definition from `studio.js`:

```
buildPanel            wireSidebarDnD        sidebarPanelTitle
buildSectionsPanel    buildIntentsPanel     wireTocScrollSpy
getSidebarState       saveSidebarState      SIDEBAR_PANELS  (the `var SIDEBAR_PANELS = [...]` const)
```
Verify with: `grep -nE "buildPanel|wireSidebarDnD|sidebarPanelTitle|buildSectionsPanel|buildIntentsPanel|wireTocScrollSpy|getSidebarState|saveSidebarState|SIDEBAR_PANELS" scripts/okf_loom/viewer/static/studio.js`
Expected after deletion: **no matches** (buildSidebarPanels + buildIntentsToolbar remain — they don't match these names). Do NOT delete `buildSidebarPanels` or `buildIntentsToolbar`.

- [ ] **Step 3: Delete the dead CSS.** In `wiki.css`, delete every rule whose selector begins with `.okf-sidebar-panel` (14 blocks) **and** the now-stale doc-comment that introduces the `.okf-sidebar-panel__body .okf-local-graph*` pair. **Keep** the `.okf-related` rules (incl. `.okf-related .okf-local-graph__title { display: none; }`) and all `.okf-local-graph*` rules — those style the live flat Related.

Verify with: `grep -n "okf-sidebar-panel" scripts/okf_loom/viewer/static/wiki.css`
Expected after deletion: **no matches**. And `grep -c "okf-related" scripts/okf_loom/viewer/static/wiki.css` still > 0.

- [ ] **Step 4: Sanity — JS + CSS well-formed:**

Run: `node --check scripts/okf_loom/viewer/static/studio.js && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/wiki.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: valid; braces balanced.

- [ ] **Step 5: Run — the flat-Related contract stays green + full studio + render suites:**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "related_section_is_flat" -q && python3 -m pytest tests/test_studio_iter1_browser.py tests/test_render.py -q`
Expected: PASS. Read the summary line.

- [ ] **Step 6: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/wiki.css
git commit -m "refactor(studio): remove the dead .okf-sidebar-panel card/drag subsystem"
```

---

### Task 10: Phase-2 verification (suite green + served/tunnelled all-theme × modifier pass)

**Files:** none (verification + tuning only).

- [ ] **Step 1: Full suite green.**
Run: `python3 -m pytest tests/ -q`
Expected: PASS (Phase-1 baseline was 1276 passed / 23 skipped; Phase-2 adds ~4 tests). **Read the printed summary line** — never trust a `| tail`ed exit code. Documented flakes, rerun once if they are the *only* failures: `test_comment_mark_wraps_selection`, `test_agent_watching_toggle_posts_presence`, `test_agent_activity_panel_has_unique_sections`.

- [ ] **Step 2: Serve on loopback (background) — RESTART required (render.py changed in Task 3).**
Run (Bash tool, `run_in_background: true`): `exec scripts/okf-loom serve docs-bundle --no-open`
Wait (no sleep): `curl -s --retry 20 --retry-delay 1 --retry-connrefused http://localhost:8787/demo/showcase -o /dev/null && echo up`
Expected: `up`. (If a prior serve lingers on :8787, bring up your own and control it via TaskStop.)

- [ ] **Step 3: Self-review screenshots across the matrix** (Playwright + system Chrome, `wait_until="load"`). Seed `localStorage`: `okf-theme` (omit for swiss-light default; set for the other 3), `okf-contrast` (`soft`), `okf-border` (`muted`/`off`). Capture, at minimum:
  - **All 4 themes at the default** (no contrast/border seed) → confirms defaults are byte-for-byte today's look (attrs absent).
  - **swiss-light + swiss-dark** each at: `contrast=soft`, `border=muted`, `border=off`, and `soft+off` together → confirms Swiss's solid active becomes tinted under soft, frames soften/vanish under muted/off, and border=off wins over soft on frames.
  - **technical-light at `contrast=soft`** → confirms Technical soft (already tinted) mainly softens fg + page-bg.
  - The **Appearance menu open** on a concept page (all 4 groups, active option highlighted) in ≥2 themes.
  - A **non-concept page (index)** showing the footer **Studio** button; a **desktop concept page** showing NO footer Studio button (rail present).
  - The **graph page** under `contrast=soft` — confirm the chrome/menu reflect it and the **canvas keeps its palette** (expected per D3).
  Confirm: rail icons read clearly at rest; footer divider sits beside the ambient group; Related still flat.

- [ ] **Step 4: Tunnel for the user's browser pass (background).**
Run (Bash tool, `run_in_background: true`): `/usr/local/bin/cloudflared tunnel --url http://localhost:8787`
Read the bg task's output file and grep for `https://<random>.trycloudflare.com`; hand that URL to the user. Ask them to walk **all 4 themes × {high,soft} × {border on,muted,off}** and drive: the Appearance menu (`Aa ▾`) switches family/mode/contrast/border and persists across reload; defaults keep today's contrasty look; soft/muted/off are opt-in; the menu appears on concept/index/search/graph/single-file; the footer Studio button opens the panel on index/mobile; **note (expected) that the graph canvas doesn't change under contrast/border** (D3).

- [ ] **Step 5: Stop the serve + tunnel** via the **TaskStop** tool on the two background task ids (never `pkill`).

- [ ] **Step 6: Tune anything the visual pass flags** — soft token values (per §5.2, tuned here with screenshots), menu z-index/position, rail resting tone, divider balance, Appearance-menu per-theme feel. Edit the relevant asset, reload (restart only if render.py/templates change), re-verify parity + suite stays green, and commit:
```bash
git add scripts/okf_loom/viewer/static docs
git commit -m "fix(viewer): Round-2 Phase-2 visual-pass tuning (soft token values + menu polish)"
```

---

## Self-Review

**1. Spec coverage (Round-2 spec §5, Phase 2) + carryover:**
- §5.1 mechanism (orthogonal root data-attrs, border AFTER contrast, defaults absent, `(0,2,0)` wins) → Task 2. ✔
- §5.2 soft tokens (5, added to all 4 blocks + `:root`, parity) → Task 1 (parity list updated RED→GREEN). ✔
- §5.3 Appearance menu (`Aa ▾` popover; family/mode→`data-theme`; contrast→`data-okf-contrast`+`okf-contrast`; border→`data-okf-border`+`okf-border`; replaces the cycle button) → Task 3 (markup, all 5 surfaces) + Task 4 (CSS) + Task 5 (wiki.js wiring) + Task 6 (graph.js wiring + studio.js glyph drop). ✔
- §5.3 "pre-JS paint" → reconciled to post-paint (D1; no pre-paint script exists, CSP-blocked); Task 0 documents it; Tasks 5/6 apply modifiers post-paint. ✔ (mechanism corrected, design preserved)
- §5.3 `graph.js GRAPH_COLORS` verify → D3: canvas doesn't mirror contrast/border (documented in Task 6 + Task 0 + Task 10 checklist); `GRAPH_COLORS` untouched so `test_iter2_graph_selection_color_is_token_governed` stays green. ✔
- Carryover: footer Studio button → Task 7; polish nits (rail resting + footer divider) → Task 8; dead-code removal → Task 9. ✔
- §7 verification (suite + Playwright + serve/tunnel all-theme × modifier) → Task 10. ✔
- §8 non-goals: stay on `feature/new-layout` (no branch/merge); don't touch `okf-loom-mcp/`/`redesign-files-1.zip`; no theme-enum growth (contrast/border are modifiers); Swiss default untouched; defaults keep today's look (attrs absent). ✔
- Out of scope (correctly deferred to Phase 3): §6 features (ToC/index/search/studio-depth); canvas contrast/border mirroring; a true pre-paint (CSP hash + shared head-builder); graph.js's legacy OS-dark boot quirk.

**2. Placeholder scan:** No "TBD"/"handle appropriately". Every code step shows concrete before/after. Three steps reference an existing test's setup to copy (Task 3 concept-render helper; Task 5/6/7 fixture names) — these are "read this neighbouring test, reuse its 2-4 setup lines" with the exact assertions given, not vague placeholders (the render/browser test files own those helpers; naming them precisely avoids inventing a fixture that doesn't exist). Task 9 deletes by symbol + grep-verify rather than by line number **on purpose** — earlier tasks shift line numbers in the same files, so symbol-anchored deletion is the robust form.

**3. Type/name consistency:** New names used consistently across tasks — attrs `data-okf-contrast`/`data-okf-border`; keys `okf-contrast`/`okf-border`; tokens `--okf-*-soft` (5, same spelling in Task 1 wiki.css, Task 2 modifier block, and the parity list); classes `.okf-appearance`/`__trigger`/`__menu`/`__group`/`__label`/`__opt` (same in Task 3 markup + Task 4 CSS + Task 5/6 JS selectors); `data-okf-set` ∈ {family,mode,contrast,border} and `data-okf-val` values match between the Python markup (Task 3) and the JS handlers (Tasks 5/6) and the tests. `okf-studio-open-btn` (Task 7) matches its test. The `onThemeApplied` bridge (Task 6) is declared top-level (Step 1) and assigned in `init` (Step 3) — reconciled. Contract preserved: `_THEMES`/`THEME_GLYPHS` left defined + swiss-first; `GRAPH_COLORS`/`syncLabelColour`/`graphPalette` not renamed; search form + Graph/Index links + `.okf-topbar` kept; `.okf-related` + flat-Related path kept.

**Risk notes:**
- **Task 3 is a serve-restart boundary** (render.py). Between Task 3 and Task 5/6 the popover is markup-only on reading pages / graph — an expected intermediate; visual correctness lands at Task 5 (reading) / Task 6 (graph). Tests still pass throughout (no test asserts the trigger's rendered glyph).
- **Task 6 scope bridge** (`onThemeApplied`) is the subtlest change — `syncLabelColour` is nested in `init`; the top-level hook lets any `applyTheme` recolour the canvas. The two-stage review + the graph browser test guard it.
- **D5 auto semantics** (single-key model) mean an Auto preference resolves to Swiss family on reload (matches today's boot); documented, acceptable for Phase 2.
- **Soft token exact values** are tuned in Task 10's visual pass (per §5.2), not guessed final here — the plan sets the token names/placement/mechanism; the browser pass dials the hex.
- The **advisor tool is unavailable** this session; each task's two-stage subagent review (spec-compliance then code-quality) + the independent test/screenshot verification compensate.

