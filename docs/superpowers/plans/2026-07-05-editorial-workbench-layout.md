# Editorial Workbench Layout Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-bar studio chrome with one theme-agnostic "Editorial Workbench" skeleton (top bar · body grid `nav|reading` · bottom status strip · comment pop-over) whose entire visual character lives in `--okf-*` tokens, and ship four themes (technical/swiss × light/dark) on that one skeleton, retiring the old light/dark/pastel/sepia/midnight palette.

**Architecture:** One layout skeleton in server templates + `wiki.css` (base) and `studio.js` + `studio.css` (studio chrome), referencing `var(--okf-*)` only. Four themes are four self-contained `[data-theme="…"]` token blocks in `wiki.css`; a theme that misses a token fails `test_render.py` parity. The aesthetic difference is carried by tokens — most importantly the new active-state primitive `--okf-active-fill/-fg/-border`. The mockups (`design/new-layout/mockups/{technical,swiss}-v1.html`) are the visual reference; their product CSS is byte-identical, only the token block differs — preserve that decoupling.

**Tech Stack:** Python 3.11 (render.py, server.py, config.py — string-template HTML, `pytest`), vanilla ES modules (studio.js, wiki.js, graph.js, renderers.js — no build step), plain CSS with custom properties (wiki.css, studio.css, graph.css), Cytoscape (graph canvas, colours mirrored in a JS constant). Run everything via `scripts/okf-loom`.

---

## The decoupling contract (do not violate)

1. **Layout CSS references tokens only.** No hardcoded colour/font/border/radius/spacing in any `.okf-*` product rule — every such value is `var(--okf-*)`. (Structural spacing/type/layout tokens live in `:root`; everything aesthetic lives in the 4 theme blocks.)
2. **Each shipped theme = one complete `[data-theme="…"]` block** declaring every token the parity test checks. Parity test (`test_theme_blocks_override_full_token_set`) `split()`s on the exact selector and reads to the first `}`, so **no layered family selectors** for token-checked tokens — write all four blocks fully.
3. **Preserve, verbatim across all templates:** the `okf-viewer` body class, the `#okf-main` skip target + `.okf-skip-link`, and every `__TOKEN__` placeholder `render.py` substitutes. Never rename `.okf-*` classes the tests assert on (`okf-viewer--search`, `okf-search__title`, `okf-page__title`, `okf-node-index`, `okf-subtitle`, `okf-topbar`, `okf-studio-bar`→see Phase 3, `okf-panel`→see Phase 3).
4. **No Apple/Windows cue anywhere:** no `⌘`/`⊞` glyph, no window traffic-light dots, no `-apple-system`/SF font as a *display* face, no centered Spotlight search. The palette may stay functionally Ctrl/Cmd+K but must render a plain keycap, never an OS glyph. (Note: `-apple-system` currently appears in the body font stack at wiki.css:302 — that becomes the `--okf-font-body` token value, which for the new themes is Inter/Helvetica, not the Apple stack. Acceptable as a deep fallback inside the stack; it must not be the rendered face.)
5. **Graph canvas colours** mirror `--okf-select`/border/bg per theme in `graph.js` `GRAPH_COLORS` (canvas can't read CSS vars). Keep the four-theme lookup in sync with the token blocks.

---

## Class-name mapping (mockup → real viewer)

The mockups use short demo class names. Do **not** rename real classes to these. Adapt each mockup rule's *visual design + token usage* onto the existing class:

| Mockup class | Real class(es) | Owned by |
|---|---|---|
| `.app` (grid shell) | `body.okf-viewer` / `.okf-page` `main` wrapper | template + wiki.css |
| `.topbar` | `.okf-topbar` | template (server-rendered) |
| `.navtoggle` | `.okf-navtoggle` (NEW) | template + studio.js |
| `.brand` / `.crumb` | `.okf-topbar__brand` + breadcrumb (`__BREADCRUMB_HTML__`) | template |
| `.search` / `.keycap` | `.okf-search-form` input + `.okf-kbd` | template (render.py `_nav_controls_html`) |
| `.tnav` (Index/Graph) | `.okf-topbar__controls` `.okf-btn` links | template |
| `.themeswitch` | `#okf-theme` button (restyled) | template + studio.js |
| `.nav` / `.navgroup` | `.okf-nav` sidebar (`__NAV_HTML__`) | render.py nav builder |
| `.reading` / `.readwrap` / `.prose` | `.okf-page` / `.okf-page__article` | template + wiki.css |
| `.tband` (type band) | `.okf-page__type` / type chip | template + wiki.css |
| `.title` | `.okf-page__title` | template |
| `.cpin` (comment pin) | `.okf-comment-mark` / `.okf-comment-marker` | studio.js |
| `.status` (bottom strip) | `.okf-statusbar` (NEW) | studio.js |
| `.popover` / `.scrim` | `.okf-panel` / `.okf-panel-overlay` (restyled + tabs) | studio.js |
| `.ptabs` | `.okf-panel__tabs` (NEW) | studio.js |

---

## File-structure map (what each touched file is responsible for)

- `scripts/okf_loom/viewer/static/wiki.css` — ALL `--okf-*` tokens: structural `:root` + four theme blocks; base layout skeleton (top bar, body grid, nav sidebar, reading column, type band, status-strip placeholder). **The decoupling lives here.**
- `scripts/okf_loom/viewer/static/studio.css` — studio chrome styling: status strip, pop-over + tabs + scrim, comment pins, palette. Token-only.
- `scripts/okf_loom/viewer/static/studio.js` — builds studio chrome: status strip (§3 rework), pop-over with Comments/Changes/Outline/Metadata tabs, comment pins → pop-over, nav-collapse, `/`-focuses-search, theme list + palette theme commands.
- `scripts/okf_loom/viewer/static/wiki.js` / `graph.js` / `renderers.js` — theme list copies + dark-family detection; graph.js also `GRAPH_COLORS`.
- `scripts/okf_loom/render.py` — `_THEMES`, `_THEME_GLYPHS`, `_theme_button_html`, `_nav_controls_html`, per-template `theme_attr`/`data_attrs` emission; template placeholder substitution.
- `scripts/okf_loom/viewer/templates/*.html` — 5 templates: top-bar chrome, body grid, reading column, `okf-viewer`/`#okf-main`, placeholders. Doc-comments name the theme set.
- `scripts/okf_loom/config.py` — `_ALLOWED_STUDIO_THEMES`, `_DEFAULT_STUDIO_THEME`, `StudioConfig.theme`, sample-config comment.
- `scripts/okf_loom/viewer/assets.py` — `_ALLOWED_THEMES` + docstring.
- `scripts/capture_readme_media.py` — `THEMES` tuple for screenshot capture.
- `tests/test_render.py` — theme list + token-parity `core_tokens`; drives Phase 1 TDD.
- `README.md` — "colour themes" prose + media alt text.

---

## PHASE 0 — Safety net & green baseline

### Task 0: Confirm baseline and record current-green

**Files:** none (verification only)

- [ ] **Step 1: Confirm the rollback tag exists**

Run: `git tag --list pre-redesign-baseline && git rev-parse pre-redesign-baseline`
Expected: prints `pre-redesign-baseline` and `2066013a…`. (Already verified present.)

- [ ] **Step 2: Confirm branch**

Run: `git branch --show-current`
Expected: `feature/new-layout`. Stay on it; do not branch.

- [ ] **Step 3: Establish the current green baseline**

Run: `python -m pytest tests/test_render.py tests/test_viewer_assets.py tests/test_viewer_plugins.py -q`
Expected: PASS. Record the count. (Browser/e2e suites — `test_viewer_browser.py`, `test_studio_iter*` — may need a headless browser; run them too if the harness is available: `python -m pytest tests/ -q`. Note which need a browser so Phase 4 can re-run them.)

- [ ] **Step 4: Commit nothing** — this is a read-only checkpoint. Proceed.

---

## PHASE 1 — Theme migration (5 → 4 + new tokens), OLD layout intact

Goal of this phase: the viewer still renders the *current* layout, but the theme set is the four new themes with the full new token set, and the whole suite is green. This isolates the highest-risk change (SPEC calls it the biggest risk) behind a working checkpoint before any layout churn.

Theme names (final): `technical-light`, `technical-dark`, `swiss-light`, `swiss-dark`. Config also accepts `auto` (resolves client-side). Old names (`light/dark/pastel/sepia/midnight`) are fully retired.

### Task 1.1: Extend the parity test to the new theme set + new tokens (RED)

**Files:**
- Test: `tests/test_render.py` (edit `test_theme_blocks_override_full_token_set` ~1247-1267, `test_iter2_select_token_defined_in_wiki_css` ~1232-1244, `test_iter1_accent_is_not_tailwind_blue` ~1004-1021, `test_iter2_graph_selection_color_is_token_governed` ~1191-1229)

- [ ] **Step 1: Update the theme list + token list in `test_theme_blocks_override_full_token_set`**

Replace the theme loop and extend `core_tokens` with the new required tokens (the redesign adds them, so parity must enforce them):

```python
    core_tokens = (
        "okf-bg", "okf-bg-elev", "okf-bg-inset", "okf-fg", "okf-fg-muted",
        "okf-border", "okf-border-strong", "okf-accent", "okf-accent-hover",
        "okf-accent-on", "okf-accent-bg", "okf-select", "okf-code-bg",
        "okf-code-fg", "okf-pre-bg", "okf-pre-fg", "okf-broken",
        "okf-ok", "okf-ok-bg", "okf-warn", "okf-warn-bg",
        "okf-info", "okf-info-bg", "okf-error", "okf-error-bg", "okf-shadow",
        # redesign additions (SPEC §5/§6) — every theme must define these:
        "okf-active-fill", "okf-active-fg", "okf-active-border",
        "okf-font-display", "okf-font-body", "okf-font-mono",
        "okf-border-w", "okf-tag-transform", "okf-tag-weight", "okf-tag-spacing",
        "okf-title-weight", "okf-title-spacing", "okf-pop-shadow", "okf-page-bg",
    )
    for theme in ("technical-light", "technical-dark", "swiss-light", "swiss-dark"):
        assert f'[data-theme="{theme}"]' in css, f"{theme} theme block missing"
        block = css.split(f'[data-theme="{theme}"]', 1)[1].split("}", 1)[0]
        for token in core_tokens:
            assert re.search(rf'--{token}\s*:', block), (
                f"{theme} theme missing --{token} token"
            )
```

- [ ] **Step 2: Update `test_iter2_select_token_defined_in_wiki_css`** — change the loop to the four new theme names (drop the `:root`-as-light special case; all four are explicit blocks now):

```python
    for theme in ("technical-light", "technical-dark", "swiss-light", "swiss-dark"):
        block = css.split(f'[data-theme="{theme}"]', 1)[1].split("}", 1)[0]
        assert re.search(r'--okf-select\s*:', block), (
            f"{theme} theme missing --okf-select token"
        )
```

- [ ] **Step 3: Update `test_iter1_accent_is_not_tailwind_blue`** — it reads light from `:root` and dark from `[data-theme="dark"]`. Point it at the new blocks:

```python
    # light accent from technical-light, dark accent from technical-dark
    light_block = css.split('[data-theme="technical-light"]', 1)[1].split("}", 1)[0]
    dark_block = css.split('[data-theme="technical-dark"]', 1)[1].split("}", 1)[0]
    m_light = re.search(r"--okf-accent:\s*([^;]+);", light_block)
    m_dark = re.search(r"--okf-accent:\s*([^;]+);", dark_block)
    assert m_light and m_light.group(1).strip().lower() != "#2563eb"
    assert m_dark and m_dark.group(1).strip().lower() != "#60a5fa"
```

- [ ] **Step 4: Update `test_iter2_graph_selection_color_is_token_governed`** — change its theme loop (line ~1207-1210) to require a `GRAPH_COLORS` entry per new theme:

```python
    for theme in ("technical-light", "technical-dark", "swiss-light", "swiss-dark"):
        assert re.search(rf'\b{re.escape(theme)}\s*:\s*\{{', graph_js) or \
               re.search(rf'"{re.escape(theme)}"\s*:\s*\{{', graph_js), (
            f"GRAPH_COLORS missing {theme} block"
        )
    # keep the existing assertions on GRAPH_COLORS.<key>.select literal &
    # syncLabelColour(); update the sample key from `.light.` to `["technical-light"]`
    # if the test references a bare-identifier key (see Step note).
```
Note: JS object keys with a hyphen (`technical-light`) must be quoted (`"technical-light": {…}`) and accessed via bracket notation (`GRAPH_COLORS["technical-light"]`). The existing test literal `GRAPH_COLORS.light.select` becomes `GRAPH_COLORS["technical-light"].select`; update both the test assertion string and graph.js (Task 1.6) together.

- [ ] **Step 5: Run the parity tests — verify they FAIL**

Run: `python -m pytest tests/test_render.py -k "theme or select_token or accent_is_not or graph_selection" -q`
Expected: FAIL — new theme blocks / tokens not yet in wiki.css & graph.js.

- [ ] **Step 6: Commit the RED tests**

```bash
git add tests/test_render.py
git commit -m "test(viewer): require 4 new themes + redesign tokens (parity, RED)"
```

### Task 1.2: Author the four theme token blocks in wiki.css (GREEN for parity)

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — replace the four `[data-theme="dark|pastel|sepia|midnight"]` blocks (lines 119-288) and augment `:root`.

- [ ] **Step 1: Add structural + fallback tokens to `:root`**

Keep the existing structural tokens (spacing scale, type scale, `--okf-maxw`/`--okf-prose-maxw`/`--okf-page-maxw`, `--okf-topbar-h`). Add `--okf-status-h: 30px;`. Keep the existing colour/radius/font tokens in `:root` **as the technical-light fallback** (a themeless page must still render) — leave `:root`'s current colour values but add the new family-default tokens so `:root` is internally consistent with technical-light:

```css
  /* --- redesign: technical-light is the :root fallback; also add the new
     family/active tokens so a themeless page renders coherently --- */
  --okf-radius: 6px;            /* was 8px — technical family default */
  --okf-radius-sm: 5px;
  --okf-radius-pill: 4px;
  --okf-border-w: 1px;
  --okf-font-display: Inter, system-ui, "Segoe UI", Roboto, sans-serif;
  --okf-font-body: Inter, system-ui, "Segoe UI", Roboto, "Noto Sans CJK SC", sans-serif;
  --okf-font-mono: ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  --okf-tag-transform: uppercase; --okf-tag-weight: 600; --okf-tag-spacing: .07em;
  --okf-title-weight: 700; --okf-title-spacing: -.01em;
  --okf-active-fill: var(--okf-accent-bg); --okf-active-fg: var(--okf-accent);
  --okf-active-border: transparent;
  --okf-pop-shadow: -18px 0 46px rgba(15, 23, 42, .18);
  --okf-page-bg: #e6eaef;
  --okf-status-h: 30px;
```
(The `--okf-font-display` serif stack at :root116-117 is REPLACED by the Inter value above; the theme blocks override per family.)

- [ ] **Step 2: Replace lines 119-288 (the four old theme blocks) with the four new blocks.** Each block is complete — every parity token present. Verbatim:

```css
/* ============================ THEMES (4) ============================
 * One skeleton, four token blocks. Values lifted from
 * design/new-layout/mockups/{technical,swiss}-v1.html; the code/status/
 * select tokens the mockups don't define are derived from each theme's
 * accent + surfaces. KEEP GRAPH_COLORS (graph.js) in sync per theme. */

[data-theme="technical-light"] {
  --okf-bg: #f6f8fa; --okf-bg-elev: #ffffff; --okf-bg-inset: #eef1f4;
  --okf-fg: #0f172a; --okf-fg-muted: #57606a;
  --okf-border: #d0d7de; --okf-border-strong: #c0c7d0;
  --okf-accent: #0c7373; --okf-accent-hover: #0a5e5e; --okf-accent-on: #ffffff;
  --okf-accent-bg: #d7ecec;
  --okf-select: #0c7373;
  --okf-code-bg: #eef1f4; --okf-code-fg: #0f172a;
  --okf-pre-bg: #0f172a; --okf-pre-fg: #e2e8f0; --okf-broken: #b91c1c;
  --okf-ok: oklch(0.52 0.10 165); --okf-ok-bg: oklch(0.96 0.03 165);
  --okf-warn: oklch(0.55 0.12 70); --okf-warn-bg: oklch(0.96 0.04 70);
  --okf-info: oklch(0.46 0.09 235); --okf-info-bg: oklch(0.96 0.03 235);
  --okf-error: oklch(0.50 0.17 27); --okf-error-bg: oklch(0.96 0.03 27);
  --okf-shadow: 0 1px 2px rgba(15, 23, 42, .06);
  --okf-radius: 6px; --okf-radius-sm: 5px; --okf-radius-pill: 4px; --okf-border-w: 1px;
  --okf-font-display: Inter, system-ui, "Segoe UI", Roboto, sans-serif;
  --okf-font-body: Inter, system-ui, "Segoe UI", Roboto, "Noto Sans CJK SC", sans-serif;
  --okf-font-mono: ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  --okf-tag-transform: uppercase; --okf-tag-weight: 600; --okf-tag-spacing: .07em;
  --okf-title-weight: 700; --okf-title-spacing: -.01em;
  --okf-active-fill: var(--okf-accent-bg); --okf-active-fg: var(--okf-accent);
  --okf-active-border: transparent;
  --okf-pop-shadow: -18px 0 46px rgba(15, 23, 42, .18);
  --okf-page-bg: #e6eaef;
}
[data-theme="technical-dark"] {
  --okf-bg: #0f1319; --okf-bg-elev: #161b22; --okf-bg-inset: #0b0e13;
  --okf-fg: #e6edf3; --okf-fg-muted: #8b949e;
  --okf-border: #2a313c; --okf-border-strong: #3b444f;
  --okf-accent: #2dd4bf; --okf-accent-hover: #26b3a1; --okf-accent-on: #04211f;
  --okf-accent-bg: #123634;
  --okf-select: #2dd4bf;
  --okf-code-bg: #0b0e13; --okf-code-fg: #e6edf3;
  --okf-pre-bg: #0b0e13; --okf-pre-fg: #e6edf3; --okf-broken: #f87171;
  --okf-ok: oklch(0.74 0.12 165); --okf-ok-bg: oklch(0.30 0.05 165);
  --okf-warn: oklch(0.78 0.13 70); --okf-warn-bg: oklch(0.32 0.06 70);
  --okf-info: oklch(0.72 0.11 235); --okf-info-bg: oklch(0.30 0.05 235);
  --okf-error: oklch(0.68 0.17 27); --okf-error-bg: oklch(0.32 0.08 27);
  --okf-shadow: 0 1px 2px rgba(0, 0, 0, .4);
  --okf-radius: 6px; --okf-radius-sm: 5px; --okf-radius-pill: 4px; --okf-border-w: 1px;
  --okf-font-display: Inter, system-ui, "Segoe UI", Roboto, sans-serif;
  --okf-font-body: Inter, system-ui, "Segoe UI", Roboto, "Noto Sans CJK SC", sans-serif;
  --okf-font-mono: ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  --okf-tag-transform: uppercase; --okf-tag-weight: 600; --okf-tag-spacing: .07em;
  --okf-title-weight: 700; --okf-title-spacing: -.01em;
  --okf-active-fill: var(--okf-accent-bg); --okf-active-fg: var(--okf-accent);
  --okf-active-border: transparent;
  --okf-pop-shadow: -18px 0 46px rgba(0, 0, 0, .5);
  --okf-page-bg: #05070a;
}
[data-theme="swiss-light"] {
  --okf-bg: #ffffff; --okf-bg-elev: #ffffff; --okf-bg-inset: #f2f3f5;
  --okf-fg: #111418; --okf-fg-muted: #5b636e;
  --okf-border: #dfe2e6; --okf-border-strong: #111418;
  --okf-accent: #0c7373; --okf-accent-hover: #0a5e5e; --okf-accent-on: #ffffff;
  --okf-accent-bg: #dbeeee;
  --okf-select: #0c7373;
  --okf-code-bg: #f2f3f5; --okf-code-fg: #111418;
  --okf-pre-bg: #111418; --okf-pre-fg: #f2f3f5; --okf-broken: #b91c1c;
  --okf-ok: oklch(0.52 0.10 165); --okf-ok-bg: oklch(0.96 0.03 165);
  --okf-warn: oklch(0.55 0.12 70); --okf-warn-bg: oklch(0.96 0.04 70);
  --okf-info: oklch(0.46 0.09 235); --okf-info-bg: oklch(0.96 0.03 235);
  --okf-error: oklch(0.50 0.17 27); --okf-error-bg: oklch(0.96 0.03 27);
  --okf-shadow: none;
  --okf-radius: 0; --okf-radius-sm: 0; --okf-radius-pill: 0; --okf-border-w: 1px;
  --okf-font-display: "Helvetica Neue", Arial, "Liberation Sans", system-ui, sans-serif;
  --okf-font-body: "Helvetica Neue", Arial, "Liberation Sans", system-ui, sans-serif;
  --okf-font-mono: ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  --okf-tag-transform: uppercase; --okf-tag-weight: 700; --okf-tag-spacing: .09em;
  --okf-title-weight: 800; --okf-title-spacing: -.02em;
  --okf-active-fill: var(--okf-accent); --okf-active-fg: var(--okf-accent-on);
  --okf-active-border: var(--okf-accent);
  --okf-pop-shadow: -14px 0 40px rgba(17, 20, 24, .22);
  --okf-page-bg: #e6eaef;
}
[data-theme="swiss-dark"] {
  --okf-bg: #121417; --okf-bg-elev: #181b1f; --okf-bg-inset: #0c0e10;
  --okf-fg: #f0f2f4; --okf-fg-muted: #9aa1a9;
  --okf-border: #2b2f34; --okf-border-strong: #f0f2f4;
  --okf-accent: #2dd4bf; --okf-accent-hover: #26b3a1; --okf-accent-on: #04211f;
  --okf-accent-bg: rgba(45, 212, 191, .16);
  --okf-select: #2dd4bf;
  --okf-code-bg: #0c0e10; --okf-code-fg: #f0f2f4;
  --okf-pre-bg: #0c0e10; --okf-pre-fg: #f0f2f4; --okf-broken: #f87171;
  --okf-ok: oklch(0.74 0.12 165); --okf-ok-bg: oklch(0.30 0.05 165);
  --okf-warn: oklch(0.78 0.13 70); --okf-warn-bg: oklch(0.32 0.06 70);
  --okf-info: oklch(0.72 0.11 235); --okf-info-bg: oklch(0.30 0.05 235);
  --okf-error: oklch(0.68 0.17 27); --okf-error-bg: oklch(0.32 0.08 27);
  --okf-shadow: none;
  --okf-radius: 0; --okf-radius-sm: 0; --okf-radius-pill: 0; --okf-border-w: 1px;
  --okf-font-display: "Helvetica Neue", Arial, "Liberation Sans", system-ui, sans-serif;
  --okf-font-body: "Helvetica Neue", Arial, "Liberation Sans", system-ui, sans-serif;
  --okf-font-mono: ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
  --okf-tag-transform: uppercase; --okf-tag-weight: 700; --okf-tag-spacing: .09em;
  --okf-title-weight: 800; --okf-title-spacing: -.02em;
  --okf-active-fill: var(--okf-accent); --okf-active-fg: var(--okf-accent-on);
  --okf-active-border: var(--okf-accent);
  --okf-pop-shadow: -14px 0 40px rgba(0, 0, 0, .5);
  --okf-page-bg: #050607;
}
```

- [ ] **Step 3: Update the wiki.css header comment (line 4)** that names the old theme set to name the four new themes.

- [ ] **Step 4: Run the parity tests — verify GREEN (graph test still red until 1.6)**

Run: `python -m pytest tests/test_render.py -k "theme_blocks_override or select_token or accent_is_not" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/okf_loom/viewer/static/wiki.css
git commit -m "feat(viewer): four Editorial-Workbench theme token blocks (parity GREEN)"
```

### Task 1.3: Migrate render.py theme identifiers

**Files:**
- Modify: `scripts/okf_loom/render.py:554-561` (`_THEMES`, `_THEME_GLYPHS`), sync comment 550-553.

- [ ] **Step 1: Replace `_THEMES` and `_THEME_GLYPHS`:**

```python
_THEMES: tuple[str, ...] = (
    "technical-light", "technical-dark", "swiss-light", "swiss-dark",
)
_THEME_GLYPHS: dict[str, str] = {
    "technical-light": "☀",  # sun
    "technical-dark": "☾",   # moon
    "swiss-light": "◑",      # half-filled circle (solid-fill motif)
    "swiss-dark": "◐",       # half-filled circle
}
```
(The button cycles these four in order. `_theme_button_html`'s fallback `theme if initial_theme in _THEMES else "light"` at line 574 — change the fallback to `"technical-light"` so an unknown theme resolves to a real glyph.)

- [ ] **Step 2: Fix the fallback at line 574:** `theme = initial_theme if initial_theme in _THEMES else "technical-light"`.

- [ ] **Step 3: Update the "KEEP IN SYNC" comment (550-553)** to list the four JS copies + the four new names.

- [ ] **Step 4: Run render tests**

Run: `python -m pytest tests/test_render.py -q`
Expected: theme-name-dependent tests pass; graph test still failing (Task 1.6). Note remaining failures for later tasks.

- [ ] **Step 5: Commit**

```bash
git add scripts/okf_loom/render.py
git commit -m "feat(render): retire 5-theme palette, ship 4 Editorial-Workbench themes"
```

### Task 1.4: Migrate config.py theme enum, default, sample comment

**Files:**
- Modify: `scripts/okf_loom/config.py:83` (`_DEFAULT_STUDIO_THEME`), `:279-281` (`_ALLOWED_STUDIO_THEMES`), `:657` (sample comment).

- [ ] **Step 1: Enum** — keep `auto` (client resolves it) + the four named:

```python
_ALLOWED_STUDIO_THEMES: frozenset[str] = frozenset(
    {"auto", "technical-light", "technical-dark", "swiss-light", "swiss-dark"}
)
```

- [ ] **Step 2: Default** — keep `_DEFAULT_STUDIO_THEME = "auto"` (resolves to `technical-{light,dark}` by OS; preserves current follow-OS behaviour and needs no data migration for config).

- [ ] **Step 3: Sample comment (657):**
`  theme: auto                       # auto | technical-light | technical-dark | swiss-light | swiss-dark`

- [ ] **Step 4: Test**

Run: `python -m pytest tests/ -k config -q`
Expected: PASS (a returning config with an old value like `theme: dark` will now fail validation — this is intended; document in README migration note, Task 1.10). Also grep sample bundles for a pinned old theme:
Run: `grep -rn "theme:" docs-bundle/okf-loom.config.yaml samples/*/okf-loom.config.yaml 2>/dev/null`
If any pins `light/dark/pastel/sepia/midnight`, update it to a new value (or `auto`) in this commit.

- [ ] **Step 5: Commit**

```bash
git add scripts/okf_loom/config.py docs-bundle/okf-loom.config.yaml samples
git commit -m "feat(config): theme enum → 4 Editorial-Workbench themes + auto"
```

### Task 1.5: Migrate assets.py allow-list + capture script

**Files:**
- Modify: `scripts/okf_loom/viewer/assets.py:520` (`_ALLOWED_THEMES`) + docstring `:532`.
- Modify: `scripts/capture_readme_media.py:61` (`THEMES` tuple).

- [ ] **Step 1: `_ALLOWED_THEMES`:**
```python
_ALLOWED_THEMES = frozenset(
    {"technical-light", "technical-dark", "swiss-light", "swiss-dark"}
)
```
Update the adjacent docstring (532) to name the four.

- [ ] **Step 2: capture script (61):**
```python
THEMES = ("technical-light", "technical-dark", "swiss-light", "swiss-dark")
```

- [ ] **Step 3: Test**

Run: `python -m pytest tests/test_viewer_assets.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/okf_loom/viewer/assets.py scripts/capture_readme_media.py
git commit -m "chore(viewer): update theme allow-list + capture script to 4 themes"
```

### Task 1.6: Migrate graph.js — THEMES, GLYPHS, GRAPH_COLORS (4 themes)

**Files:**
- Modify: `scripts/okf_loom/viewer/static/graph.js:30-31` (THEMES/GLYPHS), `:55-87` (GRAPH_COLORS + `graphPalette`).

- [ ] **Step 1: THEMES/GLYPHS (30-31)** — match render.py exactly:
```js
  var THEMES = ["technical-light", "technical-dark", "swiss-light", "swiss-dark"];
  var THEME_GLYPHS = { "technical-light": "☀", "technical-dark": "☾", "swiss-light": "◑", "swiss-dark": "◐" };
```

- [ ] **Step 2: GRAPH_COLORS (55-81)** — quoted hyphenated keys; mirror each theme's `--okf-select`/`--okf-border-strong`/`--okf-bg-elev` from Task 1.2:
```js
  var GRAPH_COLORS = {
    "technical-light": { nodeText: "#0f172a", nodeBorder: "#0f172a", bridgeBorder: "#0f172a", edge: "#c0c7d0", edgeLabel: "#57606a", edgeLabelBg: "#ffffff", select: "#0c7373" },
    "technical-dark":  { nodeText: "#e6edf3", nodeBorder: "#0f1319", bridgeBorder: "#e6edf3", edge: "#3b444f", edgeLabel: "#8b949e", edgeLabelBg: "#161b22", select: "#2dd4bf" },
    "swiss-light":     { nodeText: "#111418", nodeBorder: "#111418", bridgeBorder: "#111418", edge: "#111418", edgeLabel: "#5b636e", edgeLabelBg: "#ffffff", select: "#0c7373" },
    "swiss-dark":      { nodeText: "#f0f2f4", nodeBorder: "#121417", bridgeBorder: "#f0f2f4", edge: "#f0f2f4", edgeLabel: "#9aa1a9", edgeLabelBg: "#181b1f", select: "#2dd4bf" },
  };
```
(Swiss `edge` uses `--okf-border-strong` = fg, matching the hairline-grid identity.)

- [ ] **Step 3: `graphPalette()` fallback (84-87):**
```js
  function graphPalette() {
    var t = document.documentElement.getAttribute("data-theme") || "technical-light";
    return GRAPH_COLORS[t] || GRAPH_COLORS["technical-light"];
  }
```
Also update the static stylesheet literal the test checks: `"border-color": GRAPH_COLORS["technical-light"].select` (was `GRAPH_COLORS.light.select`).

- [ ] **Step 4: Run the graph parity test**

Run: `python -m pytest tests/test_render.py -k graph_selection -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/okf_loom/viewer/static/graph.js
git commit -m "feat(graph): per-theme GRAPH_COLORS for 4 Editorial-Workbench themes"
```

### Task 1.7: Migrate wiki.js theme copies + auto-resolution

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.js:27-28` (THEMES/GLYPHS), the `effectiveTheme`/`bootTheme` helpers (find via `grep -n "effectiveTheme\|matchMedia\|prefers-color-scheme" wiki.js`), doc comment `:4`.

- [ ] **Step 1: THEMES/GLYPHS (27-28)** — identical values to graph.js Step 1.

- [ ] **Step 2: Auto resolution** — wherever `"auto"` maps to light/dark via `matchMedia("(prefers-color-scheme: dark)")`, map to the technical family:
```js
  function effectiveTheme(choice) {
    if (choice && choice !== "auto") return choice;
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    return dark ? "technical-dark" : "technical-light";
  }
```
(If wiki.js validates a saved theme via `THEMES.indexOf(saved) >= 0`, that now accepts only the four new names — old saved values fall through to `effectiveTheme("auto")`, i.e. the localStorage migration is "unknown → auto-resolved technical". Sufficient; explicit mapping happens in studio.js Task 3.x boot.)

- [ ] **Step 3: Doc comment (4)** — name the four themes.

- [ ] **Step 4: Sanity** — no test drives wiki.js auto directly; verify no syntax error:
Run: `node --check scripts/okf_loom/viewer/static/wiki.js`
Expected: no output (valid).

- [ ] **Step 5: Commit**

```bash
git add scripts/okf_loom/viewer/static/wiki.js
git commit -m "feat(wiki.js): 4-theme list + technical-family auto resolution"
```

### Task 1.8: Migrate renderers.js dark-family detection

**Files:**
- Modify: `scripts/okf_loom/viewer/static/renderers.js:93-96`.

- [ ] **Step 1:** Replace the `t === "dark" || t === "midnight"` dark-family check with a suffix test so both dark themes get the dark code-highlight stylesheet:
```js
    var t = document.documentElement.getAttribute("data-theme") || "";
    var isDark = /-dark$/.test(t);
```
Update the neighbouring comment that names pastel/sepia.

- [ ] **Step 2: Sanity**
Run: `node --check scripts/okf_loom/viewer/static/renderers.js`
Expected: valid.

- [ ] **Step 3: Commit**

```bash
git add scripts/okf_loom/viewer/static/renderers.js
git commit -m "feat(renderers): dark-family detection by -dark suffix"
```

### Task 1.9: Migrate studio.js theme list + palette theme commands + boot migration

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js:219-220` (THEMES/GLYPHS), `:3046-3055` (palette theme commands), `bootTheme` (~253-255), doc comment `:20`.

- [ ] **Step 1: THEMES/GLYPHS (219-220)** — identical to the other copies.

- [ ] **Step 2: Palette theme commands (3046-3055)** — replace the five old items with four named + Auto:
```js
    items.push({ label: "Theme: Technical Light", sub: "theme", run: () => applyThemeAttr("technical-light") });
    items.push({ label: "Theme: Technical Dark", sub: "theme", run: () => applyThemeAttr("technical-dark") });
    items.push({ label: "Theme: Swiss Light", sub: "theme", run: () => applyThemeAttr("swiss-light") });
    items.push({ label: "Theme: Swiss Dark", sub: "theme", run: () => applyThemeAttr("swiss-dark") });
    items.push({ label: "Theme: Auto (follow OS)", sub: "theme", run: () => {
      try { localStorage.removeItem("okf-theme"); } catch (e) {}
      applyThemeAttr(effectiveTheme("auto"), { persist: false });
    } });
```

- [ ] **Step 3: localStorage migration in `bootTheme` (~253-255)** — a returning user pinned to a retired theme must land on a real one. After reading `saved = localStorage.getItem("okf-theme")`, map legacy values:
```js
    var LEGACY = { light: "technical-light", dark: "technical-dark",
                   pastel: "swiss-light", sepia: "swiss-light", midnight: "technical-dark" };
    if (saved && LEGACY[saved]) { saved = LEGACY[saved]; try { localStorage.setItem("okf-theme", saved); } catch (e) {} }
    if (saved && THEMES.indexOf(saved) < 0) { saved = null; }  // unknown → fall through to auto
```
(Map matches SPEC §4: dark→technical-dark, light→technical-light, others→nearest. Pastel/sepia were the "warmer/boxed" palettes → swiss-light; midnight→technical-dark.)

- [ ] **Step 4: `effectiveTheme` in studio.js** — same technical-family auto resolution as wiki.js Task 1.7 Step 2 (studio.js has its own copy ~221).

- [ ] **Step 5: Doc comment (20)** — name the four.

- [ ] **Step 6: Sanity + studio backend tests**
Run: `node --check scripts/okf_loom/viewer/static/studio.js && python -m pytest tests/test_studio.py tests/test_studio_iter1_backend.py tests/test_studio_iter2_backend.py -q`
Expected: valid JS; backend studio tests PASS (they don't need a browser).

- [ ] **Step 7: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.js
git commit -m "feat(studio.js): 4-theme palette + legacy localStorage migration"
```

### Task 1.10: Update template doc-comments + README theme prose

**Files:**
- Modify: all 5 `scripts/okf_loom/viewer/templates/*.html` doc-comments that enumerate the 5 themes.
- Modify: `README.md:131` (prose) + `:135` (media alt text).

- [ ] **Step 1: Templates** — in each template's leading HTML comment, replace the 5-theme enumeration with "four themes: technical/swiss × light/dark". (No structural change in this phase — layout rework is Phase 2.)

- [ ] **Step 2: README (131)** — replace "Light, dark, pastel, sepia, and midnight — all token-governed…" with a description of the four themes (Technical dev-tool teal; Swiss utilitarian grid) each in light + dark, all token-governed on one skeleton. Add a one-line migration note: configs pinned to `light/dark/pastel/sepia/midnight` must move to a new value or `auto`; returning browsers auto-migrate their saved theme.

- [ ] **Step 3: README (135)** — update `themes.gif` alt text to the four names. (Regenerating the GIF is a Phase 4 nicety, not required for green.)

- [ ] **Step 4: Full Phase-1 suite**
Run: `python -m pytest tests/test_render.py tests/test_viewer_assets.py tests/test_viewer_plugins.py tests/test_studio*.py -q` (add browser suites if the harness supports them)
Expected: PASS. **This is the Phase-1 checkpoint: 4 themes, full new token set, old layout, green.**

- [ ] **Step 5: Commit**

```bash
git add README.md scripts/okf_loom/viewer/templates
git commit -m "docs(viewer): document 4 Editorial-Workbench themes + migration note"
```

---

## PHASE 2 — Base layout skeleton (top bar · body grid · reading · status placeholder)

Reshape the server-rendered base viewer (templates + wiki.css product rules) into the Editorial Workbench skeleton, referencing tokens only. Lift the visual design from `design/new-layout/mockups/technical-v1.html` product CSS (lines 71-203) onto the `.okf-*` classes per the mapping table. **No studio JS yet** — the status strip + pop-over are Phase 3; here leave a status-strip placeholder region and keep the reading column full-width.

### Task 2.1: Reading-column + type-band + title CSS from tokens

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — the `.okf-page`, `.okf-page__article`, `.okf-page__title`, type-band, aliases, chips, `.okf-prose` rules.
- Test: `tests/test_render.py` (existing `test_iter2_search_title_css_is_full_size`, `okf-page__title` assertions must stay green).

- [ ] **Step 1: Adapt the reading column** to the mockup's `.reading`/`.readwrap`/`.prose` rules (mockup 124-156), mapped onto `.okf-page`/`.okf-page__article`. Keep `--okf-prose-maxw` as the measure (do NOT stretch prose edge-to-edge — SPEC §3.3). Body font becomes `font-family: var(--okf-font-body)` (was the hardcoded Apple stack at wiki.css:302). Titles use `var(--okf-font-display)` + `var(--okf-title-weight)`/`var(--okf-title-spacing)`.

- [ ] **Step 2: Type band** — style the concept type chip (`__CONCEPT_TYPE__`) as the mockup `.tband` (mockup 128-131): `background: var(--okf-active-fill); color: var(--okf-active-fg); border: var(--okf-border-w) solid var(--okf-active-border); text-transform: var(--okf-tag-transform); font-weight: var(--okf-tag-weight); letter-spacing: var(--okf-tag-spacing);`.

- [ ] **Step 3: Tags/chips** — map `.chip`/`.chip.rel` (mockup 136-139) onto the existing tag/relation chip classes, radius `var(--okf-radius-pill)`, border `var(--okf-border-w)`.

- [ ] **Step 4: Run title/search tests**
Run: `python -m pytest tests/test_render.py -k "search_title or page__title or subtitle" -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add scripts/okf_loom/viewer/static/wiki.css tests/test_render.py
git commit -m "feat(viewer): reading column + type band on active-state tokens"
```

### Task 2.2: Top bar (single) + nav sidebar + body grid

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — `.okf-topbar`, `.okf-topbar__controls`, `.okf-search-form`, `.okf-btn`, `.okf-nav`, and the `.okf-page`/`main` grid shell.
- Modify: `scripts/okf_loom/render.py` `_nav_controls_html` (583-618) — search input renders a plain `/` keycap (`.okf-kbd`), no OS glyph; Index/Graph as `.okf-btn`.
- Modify: templates — add a `.okf-navtoggle` button in `.okf-topbar` and wrap the body as a `nav | reading` grid.

- [ ] **Step 1: Top bar** — adapt mockup `.topbar` (82-108) onto `.okf-topbar`: single row, height `var(--okf-topbar-h)`, `background: var(--okf-bg-elev)`, `border-bottom: var(--okf-border-w) solid var(--okf-border)`. Brand `.okf-topbar__brand` uses `var(--okf-font-display)`; add the `.brand .mk` accent square. Search field right-aligned, `min-width` measure, contains a `.okf-kbd` showing `/`. View-nav Index/Graph as `.okf-btn` with the active one using `.on` → active-state tokens (mockup 100-103).

- [ ] **Step 2: Keycap** — in `_nav_controls_html`, append `<span class="okf-kbd">/</span>` inside the search affordance. Style `.okf-kbd` per mockup `.keycap` (96-99): mono font, `border: var(--okf-border-w) solid var(--okf-border-strong)`. Remove any `⌘`/`⊞` from server output (there is none server-side today; confirm).

- [ ] **Step 3: Nav sidebar** — adapt mockup `.nav`/`.navgroup`/`.nav a`/`.nav a.on` (113-122) onto `.okf-nav`. Active item uses active-state tokens. Group labels uppercase (Diátaxis types). The nav content builder in render.py already groups concepts; ensure group headings render as `.okf-nav__group` (uppercase). Active nav link gets `.on`/`aria-current`.

- [ ] **Step 4: Body grid** — the concept `main` becomes a 2-col grid `var(--okf-nav-w, 216px) 1fr` (nav | reading); add a `.navcollapsed` modifier collapsing col 1 to 0 (mockup 111-112). Add the `.okf-navtoggle` button (mockup 84-86, glyph `☰`) to `.okf-topbar`; wiring is Phase 3 (studio.js) but the button + CSS ship here so base pages have the control. For non-concept views (index/search/graph/single-file) keep their current single-column main but under the new top bar.

- [ ] **Step 5: Render + assert placeholders intact** — render the demo bundle and confirm the hard-contract markers survive:
Run: `scripts/okf-loom render docs-bundle -o /tmp/okf-build && grep -l "okf-viewer" /tmp/okf-build/*.html >/dev/null && grep -rn 'id="okf-main"' /tmp/okf-build/index.html`
Expected: `okf-viewer` class present; `#okf-main` present; no `__…__` placeholder leaks (`! grep -rn "__[A-Z_]*__" /tmp/okf-build/*.html`).

- [ ] **Step 6: Full render + browser suite**
Run: `python -m pytest tests/test_render.py tests/test_viewer_browser.py -q`
Expected: PASS (update any browser test that asserts the old two-bar DOM — see Task 3.5 for studio DOM tests; base-viewer browser tests asserting `.okf-topbar`/`okf-page__title` should still pass).

- [ ] **Step 7: Commit**
```bash
git add scripts/okf_loom/viewer/static/wiki.css scripts/okf_loom/render.py scripts/okf_loom/viewer/templates
git commit -m "feat(viewer): single top bar + nav sidebar + body grid skeleton"
```

### Task 2.3: Status-strip placeholder region + status-h token wiring

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — `.okf-statusbar` base rule (mockup `.status` 158-169), height `var(--okf-status-h)`, mono font, top border. Reserve the grid row.

- [ ] **Step 1:** Add the `.okf-statusbar` styles (empty/hidden until studio.js fills it in Phase 3). Ensure the app shell grid is `topbar / body / status` (mockup `.app` 75-79 `grid-template-rows: auto 1fr auto`). On non-studio pages the strip stays empty (or `display:none` via a `:empty` rule) so base pages don't show an empty bar.

- [ ] **Step 2: Visual smoke (local, no tunnel yet)** — render + open one page headless to confirm no layout break:
Run: `scripts/okf-loom render docs-bundle -o /tmp/okf-build && python -m pytest tests/test_viewer_browser.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add scripts/okf_loom/viewer/static/wiki.css
git commit -m "feat(viewer): status-strip region + topbar/body/status shell grid"
```

---

## PHASE 3 — Studio chrome: status strip + comment pop-over

Rework `studio.js` §3 (the client-built second bar) into the bottom status strip, and the `.okf-panel` slide-over into the tabbed comment pop-over. `server.py:_studio_bootstrap` needs **no change** (it only ships config + asset links). Keep `okf-viewer`, `#okf-main`, and studio contracts (presence POST, palette, SSE) intact.

### Task 3.1: Move ambient status into the bottom status strip

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js` §3 (262-390 build, `mountBar` 380-390, mount call ~4136).
- Modify: `scripts/okf_loom/viewer/static/studio.css` — retarget `.okf-studio-bar`→status-strip styling (or add `.okf-statusbar` fill classes).

- [ ] **Step 1:** Repurpose the assembled `bar` from a top second-bar into the bottom `.okf-statusbar`: presence chip (`◉ agent watching`), connection indicator (`● connected/Live`), validation count (`✓ N concepts valid`), and a plain **Commands** button (opens palette; `.okf-kbd` shows a plain key, **no `⌘`**). Mount at the **bottom** of the app shell (into the status row) instead of after `.okf-topbar`. Update `mountBar()` to target the status region.

- [ ] **Step 2:** Move the **view switch** (Rendered/Source/Split) and **Comments/Changes** triggers into the **top bar** (view-nav area) or keep Comments/Changes as pop-over openers on the status strip — per SPEC §3.4 the pop-over is summoned on demand. Simplest faithful mapping: view-switch stays near the reading column top (concept pages only); Comments/Changes/Outline/Metadata become **tabs inside the pop-over** (Task 3.2), opened by a single "Comments" affordance on the status strip + the inline pins.

- [ ] **Step 3:** Remove the `⌘K`/`Ctrl+K` **glyph** from the palette trigger hint (studio.js 362-364 `isApplePlatform`): render a plain `<kbd class="okf-kbd">/</kbd>` or the word "Commands" with no OS glyph. Keep the functional Ctrl/Cmd+K keybinding in `wirePaletteKeys` (2967-2983).

- [ ] **Step 4: Restyle** `.okf-statusbar` fill (mockup `.status`/`.ok`/`.dot`/`.seg`/`.cmdbtn` 158-169): mono font, `var(--okf-status-h)`, accent dot.

- [ ] **Step 5: Sanity**
Run: `node --check scripts/okf_loom/viewer/static/studio.js`
Expected: valid.

- [ ] **Step 6: Commit**
```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css
git commit -m "feat(studio): ambient status → bottom status strip, no OS glyphs"
```

### Task 3.2: Comment pop-over with Comments/Changes/Outline/Metadata tabs + scrim

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js` — `.okf-panel` construction (3104-3239), panel registry, `openPanel`/`closePanel`/`togglePanel`.
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-panel`/`.okf-panel-overlay` → pop-over look (mockup `.popover`/`.scrim`/`.ptabs` 171-202).

- [ ] **Step 1: Tabs** — add a `.okf-panel__tabs` row (mockup `.ptabs` 182-185) with four tabs: Comments, Changes, Outline, Metadata. Register `panels.outline` and `panels.metadata` alongside existing `panels.comments`/`panels.changes`. Outline = the concept's heading list; Metadata = the frontmatter table (reuse `__FRONTMATTER_HTML__` data already in the page, or read from the concept DOM). Active tab uses `--okf-accent` underline (mockup 185 — non-filled indicator uses `--okf-accent`, per SPEC §5 rule, NOT `--okf-active-fg`).

- [ ] **Step 2: Scrim + pop-over styling** — style `.okf-panel-overlay` as the scrim (mockup `.scrim` 172-173) and `.okf-panel` as the right slide-over (mockup `.popover` 174-177): `box-shadow: var(--okf-pop-shadow)`, `transform: translateX(100%)` closed → `none` open, close on scrim-click or `Esc` (Esc already wired at 3120-3126; add scrim-click handler). Default closed.

- [ ] **Step 3: Sanity + studio backend/e2e**
Run: `node --check scripts/okf_loom/viewer/static/studio.js && python -m pytest tests/test_studio_iter2_e2e.py -q`
Expected: valid; e2e passes (update selectors in the e2e test if it asserts the old `.okf-studio-bar` DOM — the Comments/Changes panel behaviour is preserved, only relocated into tabs).

- [ ] **Step 4: Commit**
```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css
git commit -m "feat(studio): tabbed comment pop-over (Comments/Changes/Outline/Metadata)"
```

### Task 3.3: Inline comment pins + open-pop-over + `/`-focuses-search + nav collapse

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js` — comment marker rendering (`.okf-comment-mark`/`.okf-comment-marker`, ~412-501 CSS + the JS that places markers), add `/`-key handler + nav-collapse handler.
- Modify: `scripts/okf_loom/viewer/static/studio.css` — pin styling (mockup `.cpin`/`.commented` 148-155).

- [ ] **Step 1: Inline pin** — render the comment anchor as a small inline pin (`◆ N`) on the commented span (mockup `.cpin` 152-155): active-state tokens, `var(--okf-radius-pill)`. Clicking the pin (or the highlighted span `.commented`, mockup 148-149) opens the pop-over on the Comments tab. Replace/retire the old right-rail marker approach (`.okf-comment-rail`) — SPEC §3.3 supersedes the gutter.

- [ ] **Step 2: `/` focuses search** — add a global keydown (guard against `input`/`textarea` targets): `if (e.key === "/" ) { e.preventDefault(); document.querySelector(".okf-search-form input, #okf-search")?.focus(); }`. No OS glyph — the keycap already shows a plain `/` (Task 2.2).

- [ ] **Step 3: Nav collapse** — wire `.okf-navtoggle` (Task 2.2) to toggle `.navcollapsed` on the app shell; persist in localStorage (`okf-nav-collapsed`).

- [ ] **Step 4: Sanity + e2e**
Run: `node --check scripts/okf_loom/viewer/static/studio.js && python -m pytest tests/test_studio_iter1_browser.py tests/test_studio_iter2_e2e.py -q`
Expected: valid; browser/e2e pass (update comment-marker selectors if the tests assert the old rail).

- [ ] **Step 5: Commit**
```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css
git commit -m "feat(studio): inline comment pins → pop-over, / focuses search, nav collapse"
```

### Task 3.4: Restyle palette to match (no OS glyph) + reconcile studio.css leftovers

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.css` — palette + remove now-dead `.okf-studio-bar` top-bar rules; ensure everything references tokens.

- [ ] **Step 1:** Confirm no product rule hardcodes a colour/font/radius that should be a token (`grep -nE "#[0-9a-fA-F]{3,6}|-apple-system|[0-9]+px" studio.css` → audit each hit; convert stray literals to tokens; spacing literals that match the scale → `var(--okf-space-*)`). Palette overlay/list styled with tokens; `.okf-kbd` inside palette shows plain keys.

- [ ] **Step 2:** Delete or neutralize the obsolete top-`.okf-studio-bar` positioning now that the bar is the bottom status strip (keep the class if tests reference it, but restyle to the strip; otherwise rename consistently and update tests).

- [ ] **Step 3: Full suite**
Run: `python -m pytest tests/ -q`
Expected: PASS (all backend + browser/e2e where the harness supports them). **Phase-3 checkpoint.**

- [ ] **Step 4: Commit**
```bash
git add scripts/okf_loom/viewer/static/studio.css
git commit -m "chore(studio): token-only palette + strip; retire obsolete bar rules"
```

### Task 3.5: Reconcile studio browser/e2e test selectors

**Files:**
- Modify: `tests/test_studio_iter1_browser.py`, `tests/test_studio_iter2_e2e.py`, `tests/test_viewer_browser.py` — any assertion on the old `.okf-studio-bar` (top), old panel-without-tabs, or comment rail.

- [ ] **Step 1:** Update selectors/assertions to the new DOM: status strip (`.okf-statusbar`), pop-over tabs (`.okf-panel__tabs`), inline pins (`.okf-comment-mark`). Assert the *behaviour contracts* preserved: presence POST on watching toggle, palette opens on Ctrl/Cmd+K, Comments opens the pop-over, Esc/scrim closes it, `/` focuses search, nav collapses. Do NOT weaken tests — port them.

- [ ] **Step 2: Run**
Run: `python -m pytest tests/test_studio_iter1_browser.py tests/test_studio_iter2_e2e.py tests/test_viewer_browser.py -q`
Expected: PASS.

- [ ] **Step 3: Commit**
```bash
git add tests
git commit -m "test(studio): reconcile browser/e2e selectors with new chrome DOM"
```

---

## PHASE 4 — Verification (SPEC §10)

### Task 4.1: Full suite green

- [ ] **Step 1:** Run: `python -m pytest tests/ -q` → all PASS. If any browser/e2e test needs a headless browser not available in this container, note it and run the subset that is available; record what was skipped and why.

### Task 4.2: Served + tunnelled visual pass (the required real-viewer review)

- [ ] **Step 1: Serve on loopback**
Run (background): `scripts/okf-loom serve docs-bundle --no-open` — note the port.

- [ ] **Step 2: Tunnel**
Run (background): `/usr/local/bin/cloudflared tunnel --url http://localhost:<port>` — grep the log for `https://<random>.trycloudflare.com`.

- [ ] **Step 3: Hand the trycloudflare URL to the user.** Drive the real flow and confirm each, in **all four theme×mode combos** and **all five views** (Concept, Index, Graph, Search, Single-file):
  - `/` focuses search (plain keycap, no OS glyph anywhere)
  - nav collapses to full-width read and restores
  - a comment pin opens the pop-over on the Comments tab
  - pop-over closes on scrim-click and on `Esc`
  - pop-over tabs Comments/Changes/Outline/Metadata all render
  - Swiss shows solid boxed active fills + radius 0 + hairline grid; Technical shows subtle tinted active states + 6px radius
  - graph canvas selection colour matches the theme accent (GRAPH_COLORS in sync)
  - no window dots, no `⌘`/`⊞`, no serif/SF display face, no centered Spotlight search

- [ ] **Step 4:** Tune token values found lacking in the visual pass (contrast, status-ramp darks) — edit only the theme blocks in wiki.css, re-verify parity stays green, re-serve. Commit any tuning:
```bash
git add scripts/okf_loom/viewer/static/wiki.css
git commit -m "fix(viewer): visual-pass token tuning across 4 themes"
```

### Task 4.3: Optional media refresh

- [ ] **Step 1:** Regenerate `docs/media/themes.gif` via `scripts/capture_readme_media.py` if the capture harness runs in this environment; otherwise leave the alt-text update from Task 1.10 and note the GIF needs a manual refresh.

---

## Self-Review

**1. Spec coverage** (SPEC §-by-§):
- §2 decoupled architecture → Contract §1-2, Task 1.2 (4 complete blocks), Phase 2/3 token-only rules. ✔
- §3.1 top bar (brand·breadcrumb·search·view-nav·theme) → Task 2.2. `/` keycap no OS glyph → 2.2/3.1/3.3. ✔
- §3.2 collapsible Diátaxis nav → Task 2.2 (grid + groups) + 3.3 (toggle wiring). ✔
- §3.3 full-width reading, prose measure, inline pins (supersedes gutter) → Task 2.1 + 3.3. ✔
- §3.4 pop-over Comments/Changes/Outline/Metadata, default closed, Esc/scrim → Task 3.2. ✔
- §3.5 bottom status strip (connection·watching·validation·Commands) → Task 2.3 + 3.1. ✔
- §3.6 five views on one skeleton → Task 2.2 Step 4 + Phase 4 verify. ✔
- §4 theme set + migration sequence → Phase 1 (all touch-points: wiki.css, render.py, config, studio.js, localStorage, tests, README) + assets.py/capture/renderers.js additions. ✔
- §5 active-state primitive + the fill/fg rule (non-filled indicator uses `--okf-accent`) → Task 1.2 tokens + 3.2 Step 1 (tab underline uses `--okf-accent`). ✔
- §6 new tokens in every theme → Task 1.1 parity list + 1.2 blocks. ✔
- §7 hard contract (okf-viewer, #okf-main, placeholders, bootstrap compat, graph sync, preserve frontmatter) → Contract §3-5, Task 2.2 Step 5, 1.6. ✔
- §8 non-goals → Contract §4 + Phase 4 Step 3 checks. ✔
- §9 baseline → Task 0. ✔
- §10 verification → Phase 4. ✔

**2. Placeholder scan:** No "TBD"/"handle appropriately". Token blocks are fully spelled out; migration edits are exact; layout tasks cite exact mockup line ranges + the class-map table (a precise instruction, not a placeholder). Derived status/code tokens have concrete values (tuned in 4.2 if needed).

**3. Type/name consistency:** Theme names identical across render.py/wiki.js/graph.js/studio.js/wiki.css/config/assets/capture/tests (`technical-light|technical-dark|swiss-light|swiss-dark`). GRAPH_COLORS keys quoted + bracket-accessed everywhere. `--okf-status-h` added to `:root` and consumed by `.okf-statusbar`. `.okf-navtoggle`/`.okf-statusbar`/`.okf-panel__tabs` are the agreed new class names, used consistently across Phase 2/3 and Task 3.5 tests.

**Risk note:** Phase 1 is the isolatable, fully-tested checkpoint. Phases 2-3 are design-sensitive; the served+tunnelled pass (4.2) is where token/layout tuning happens — expect iteration there, not in the plan.
