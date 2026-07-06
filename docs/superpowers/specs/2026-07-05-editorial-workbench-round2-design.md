# Editorial Workbench — Round 2 Design (rail · appearance · features)

Status: **design approved by user via brainstorming (2026-07-05); ready for `writing-plans`.**
Branch: `feature/new-layout` (STAY on it — no branch/merge).
Supersedes: `design/new-layout/SPEC.md` **§3.4** (docked panel → thin rail + overlays)
and extends **§3.6** (adds ToC / index dashboard / search quality / studio depth).
SPEC.md is reconciled to these decisions as the first task of Phase 1.

> **For implementers:** consume this with `writing-plans` → `subagent-driven-development`
> / `executing-plans`. Machinery line refs are approximate — **verify at build, files
> shift.** Run everything via `scripts/okf-loom` (Python 3.11+, no package install; vanilla
> ES modules, no build step). Keep the suite green and commit per logical step.

---

## 1. What this round decides (approved forks)

Three architecture forks were put to the user with ASCII previews; all resolved to the
recommended option:

1. **Studio surface → thin rail + overlays.** Replace the current 380px reflowing docked
   panel (`body.okf-studio-open { padding-right }`) with a **thin (~48px) icon rail** that
   stays docked so controls are first-class, and **overlay panels** that pop OVER content
   (no reflow). *Revises SPEC §3.4 — the docked-panel decision from commit `cc55daf`.*
2. **Reading space → Workbench ↔ Focus toggle.** Keep the framed "workbench card" as the
   default (Workbench). Add a **Focus** mode that collapses nav + rail + frame and lets the
   column bleed wide. **Split auto-enters Focus** — this is the fix for the broken split
   view.
3. **Contrast → universal `high`/`soft` modifier.** A lower-contrast alternative shipped as
   an **orthogonal root `data-attr`** (`data-okf-contrast`) that remaps a small token set on
   top of ANY of the 4 themes — the decoupled-token model, sharing the border-toggle
   mechanism. **No theme-enum growth.**

Plus the settled items: **border toggle** (1), **functional pin** (5), and the **3 polish
items** (Related-flat, rail/overlay spacing, footer button-toolbar). And the **4 missing
features** the user selected (item 3): **on-page ToC**, **index dashboard**, **search
quality**, **studio depth**.

**Build order (approved):** phased, with a **serve + tunnel + all-theme browser review after
each phase.** Phase 1 = layout/chrome · Phase 2 = appearance · Phase 3 = features.

---

## 2. The decoupling contract (carry forward — unchanged from Round 1)

1. **Layout CSS references tokens only** — no hardcoded colour/font/border/radius/spacing in
   any `.okf-*` product rule; every aesthetic value is `var(--okf-*)`.
2. **Each shipped theme = one complete self-contained `[data-theme="…"]` block.**
   `test_render.py::test_theme_blocks_override_full_token_set` `split()`s on the exact
   selector to the first `}`, so **no layered family selectors** for token-checked tokens.
   New soft-contrast tokens (§6) are added to **all four blocks + the `:root` fallback.**
3. **Preserve verbatim across templates:** `okf-viewer` body class, `#okf-main` skip target
   + `.okf-skip-link`, every `__TOKEN__` placeholder, and every `.okf-*` class the tests
   assert on. Renamed/retired chrome (docked `.okf-panel` → overlay; `--status` bar →
   toolbar) must keep the class names the studio browser/e2e suite drives.
4. **No Apple/Windows cue** — no `⌘`/`⊞` glyph, no window dots, no SF/`-apple-system` as a
   *rendered* face, no centered Spotlight search.
5. **Graph canvas colours** mirror per-theme `--okf-select`/border/bg in `graph.js`
   `GRAPH_COLORS`; keep the four-theme lookup synced.
6. **THEMES / THEME_GLYPHS stay swiss-first and identical** across `render.py`, `wiki.js`,
   `studio.js`, `graph.js`. Legacy localStorage migration preserved.

---

## 3. The consolidated layout model (concept page)

```
┌─ TOPBAR ───────────────────────────────────────────────────────────┐
│ ◆ brand   Home › How-to › X     [ / search ]   Index Graph    Aa ▾  │
├──────────┬──────────────────────────────────────────────────┬──────┤
│ NAV      │  READING COLUMN  (undivided, full width when idle) │  ▣   │ thin
│ DEMO     │   type · Title · aliases · chips · lead             │ 💬 3 │ rail
│  Showcase│   [ ToC for long docs ]                             │  ⟳   │ (always
│ HOW-TO   │   prose … ◆1 (pin) …                                │  ☰   │  docked)
│  A   B   │            ┌─ overlay panel ───────────┐            │  ⓘ   │
│ REFERENCE│            │ 📌 thread / changes / meta │            │  +   │
│  Spec    │            │   pops OVER content        │            │      │
│ ─ RELATED (flat rows, no card) ─                                │      │
│  ● Neighbour A   ● Neighbour B                                  │      │
├──────────┴──────────────────────────────────────────────┴──────┤
│ FOOTER  Watch · Commands · [Rendered|Source|Split] · Focus │ ◆12 · ●Live │
└─────────────────────────────────────────────────────────────────────┘
```

**Region ownership (no duplication):**

| Region | Owns | Built by |
|---|---|---|
| **Topbar** | brand · breadcrumb · search (`/`) · Index/Graph nav · **Appearance menu `Aa ▾`** | `render.py` templates |
| **Left nav** | Diátaxis nav + **flat Related** section | `render.py _concept_nav_html` + `wiki.js renderLocalGraph` (unwrapped) |
| **Right rail (thin)** | Comments·N · Changes · Outline · Metadata · quick-actions · rail toggle → each opens an **overlay** | `studio.js` (new rail; overlays reuse `.okf-panel`) |
| **Footer toolbar** | Watch · Commands · view-switch (Rendered/Source/Split) · **Focus** · \| ambient: presence · ◆N · ●Live | `studio.js mountBar` |
| **Reading column** | content + inline comment **pins**; overlays pop from the right | template + `studio.js` |

**Focus mode:** a **footer** toggle (and auto in Split) sets a root/body state that (a)
collapses the left nav and thin rail, (b) drops `.okf-page__main`'s max-width cap so the
column is full-width, while (c) **Rendered prose still centers at `--okf-prose-maxw` (~76ch)
— body text never runs edge-to-edge (SPEC §3.3/§8)**; only Source/Split panes fill the full
column.

---

## 4. Phase 1 — Layout & chrome

### 4.1 Thin rail + overlay panels (item 5, revises §3.4)
- **New thin rail** (`~48px`, `position:fixed`, right, top→footer): vertical icon buttons —
  Comments (count badge) · Changes · Outline · Metadata · quick-actions (`+`) · rail toggle.
  Always docked on concept pages ≥900px; the rail itself does **not** reflow content
  meaningfully (a ~48px reserve, or overlay — decide at build; prefer a slim reserve so
  content never sits under the rail).
- **Overlay panels:** clicking a rail icon opens the corresponding panel (reuse `.okf-panel`,
  ~380px) as an **overlay over content** — drop `body.okf-studio-open { padding-right }`
  reflow; add `--okf-pop-shadow`, `z-index` above content (below topbar chrome), dismiss on
  **Esc / click-away**. A rail item can **expand to a full working panel** on demand.
- Quick-actions live at the top of the Comments overlay (as today) — pre-fill the composer
  (running them is Phase 3 studio-depth).
- Mobile (<900px): overlay full-width (existing `.okf-panel { width:100vw }` mobile block).
- Machinery: `.okf-panel` (studio.css ~1144), `body.okf-studio-open` (~1159), `openPanel`/
  `closePanel`, `renderCommentsPanel` / `buildIntentsToolbar` (studio.js ~4255), panel tab
  renderers (~3335+). Keep the class names the studio suite asserts on.

### 4.2 Functional comment pin (item 5)
- Make the inline `.okf-comment-mark` (studio.css ~515) + margin `.okf-comment-marker`
  (~455) a **clear, obvious affordance** styled with active-state tokens (not a faint dot).
- Wire end-to-end: click pin → `jumpToCommentMark` (studio.js ~1123-1276) → open the
  **thread overlay scrolled/highlighted to that comment**; reply/resolve/edit already work
  (audit-verified); resolving updates the pin `data-state`.
- Optional: a header thumbtack on the thread overlay to **keep it open** while reading
  (secondary; only if it reads cleanly).

### 4.3 Workbench ↔ Focus + Split fix (item 4)
- **Root cause of the broken split (verified):** `.okf-view[data-okf-view="split"]` (3fr|7px|2fr
  grid, studio.css ~292) lives inside `.okf-page__main`'s centered ~76ch measure AND the
  380px dock steals width → panes ~402|268px, source wraps ~30 chars.
- **Fix:** (a) the dock → thin rail (§4.1) returns width; (b) **Focus mode** drops the
  `.okf-page__main` max-width cap (new `body.okf-focus` / `data-okf-focus` state);
  (c) Split **auto-enters Focus** and closes overlays; (d) in Focus, `.okf-view` split grid +
  `.okf-source` get `max-width:none` and fill the full column — Source stops wrapping.
- **Rendered** stays centered at `--okf-prose-maxw` even in Focus. **Source** = full-width
  monospace. **Split** = wide two-pane, draggable divider + synced scroll (already built,
  just un-squeezed).
- Machinery: `.okf-page__main` cap (wiki.css), `.okf-view`/`.okf-split` (studio.css ~267-345),
  `setView`/`ensureViewWrap` (studio.js ~477-580). `?view=split` deep-link preserved.

### 4.4 Footer button toolbar (polish 3)
- Recover the original bar feel: ~40px, `background var(--okf-bg-inset)`; **actions as proper
  bordered `.okf-studiobtn`** (`padding 4px 10px; border 1px solid var(--okf-border-strong);
  radius var(--okf-radius-sm); bg var(--okf-bg-elev); font-size sm`) — recover from
  `git show pre-redesign-baseline:scripts/okf_loom/viewer/static/studio.css`.
- Actions (wired only): **Watch · Commands · [Rendered|Source|Split] · Focus.** (Comments/
  Changes live in the rail now — **not duplicated here.**)
- Ambient bits quiet at the right edge with a subtle divider: presence chip · `◆ N concepts`
  (`.okf-statseg`) · `● Live` (`.okf-conn`). Per-theme (Swiss square/crisp, Technical soft).
- Machinery: `.okf-studio-bar--status` (studio.css ~54), `.okf-statseg` (~77), `.okf-conn`
  (wiki.css ~796), `mountBar` (studio.js ~280-420).

### 4.5 Related → flat nav section (polish 1)
- Drop the `.okf-sidebar-panel` card chrome (border + collapse toggle + drag) around Related.
  Render `RELATED` as an uppercase `.okf-nav__group`-style label; each 1-hop neighbour a flat
  `.okf-nav__link`-style row (colour dot + title). One continuous left rail.
- Machinery: `renderLocalGraph` (wiki.js:87, already a vertical list), `buildSidebarPanels`
  (studio.js ~4064, wraps "related" in the card — restyle flat or bypass the card chrome).
  `SIDEBAR_PANELS` is already `["related"]`.

### 4.6 Spacing pass (polish 2)
- Fix the concrete bug: `.okf-panel__intents { padding: … … 0 }` (studio.css ~1169, zero
  bottom) butts "ASK THE AGENT" against Enrich. Add bottom breathing room and audit the
  overlay's vertical rhythm (tab bar → intents → composer `.okf-composer__anchor/__hint/
  __actions` → filter toolbar → thread list). Spacing tokens only. Reconciled with the new
  overlay layout.

---

## 5. Phase 2 — Appearance settings (items 1, 2)

### 5.1 Mechanism — orthogonal root data-attrs (both settings)
Both are **runtime modifiers independent of theme**, applied on `<html>`/`:root` **after** the
theme blocks, persisted to localStorage, defaulting to **today's look** (attr absent):

- **Border (item 1)** — `data-okf-border` emitted only for non-default `muted` | `off`
  (default `on` = attr absent, preserving fg-frames in Swiss):
  ```css
  :root[data-okf-contrast="soft"] { /* …see §5.2… */ }
  :root[data-okf-border="muted"]  { --okf-border-strong: var(--okf-border); }
  :root[data-okf-border="off"]    { --okf-border-strong: transparent; }
  ```
- **Contrast (item 2)** — `data-okf-contrast` emitted only for `soft` (default `high` = attr
  absent):
  ```css
  :root[data-okf-contrast="soft"] {
    --okf-fg:            var(--okf-fg-soft);
    --okf-border-strong: var(--okf-border);        /* softer frames */
    --okf-active-fill:   var(--okf-active-fill-soft);
    --okf-active-fg:     var(--okf-active-fg-soft);
    --okf-active-border: var(--okf-active-border-soft);
    --okf-page-bg:       var(--okf-page-bg-soft);
  }
  ```
- **Specificity & composition:** `:root[data-*]` = (0,2,0) beats `[data-theme]` (0,1,0), so
  modifiers win regardless of theme. Border and contrast both touch `--okf-border-strong`;
  place the **border block AFTER the contrast block** so `border=off` (transparent) wins over
  `contrast=soft` (`--okf-border`); `muted` and `soft` agree (`--okf-border`) — no conflict.

### 5.2 The soft tokens (add to ALL 4 theme blocks + `:root` fallback — parity)
Per-theme soft variants (exact values tuned during build with screenshots):
`--okf-fg-soft` (a softer text tone, e.g. Swiss light `#2a2f36` instead of `#111418`),
`--okf-active-fill-soft` / `--okf-active-fg-soft` / `--okf-active-border-soft` (Swiss soft =
**tinted** like Technical: `accent-bg` / `accent` / `transparent`; Technical soft = its
existing tinted values), `--okf-page-bg-soft` (a less-recessed page bg). Borders reuse
existing `--okf-border` (no new token). **Adding these to the parity set means every block
defines them** — intended (each family owns its soft look).

### 5.3 Appearance menu (`Aa ▾`)
- A small **topbar popover** consolidating: **family** (technical/swiss) · **mode**
  (light/dark/auto) · **contrast** (high/soft) · **border** (on/muted/off) — replacing the bare
  theme-cycle button (`_theme_button_html`). One uncluttered home for all appearance settings
  (item 6: don't clutter).
- Wires: family+mode → `data-theme` (existing THEMES machinery + localStorage migration);
  contrast → `data-okf-contrast` + localStorage `okf-contrast`; border → `data-okf-border` +
  localStorage `okf-border`. Pre-JS paint uses the persisted values (inline boot script, as
  theme already does).
- `graph.js GRAPH_COLORS`: soft/border modifiers change CSS-var-driven surfaces; verify the
  canvas still reads acceptable — the canvas mirrors accent/select which soft leaves largely
  intact; document any needed mirror.

> **Build reconciliation (2026-07-06, Phase-2 plan):** machinery mapping found there is **no** inline pre-paint boot script to extend, and 4 of 5 templates forbid inline `<script>` (CSP `script-src 'self'`). So `data-okf-contrast`/`data-okf-border` are read from localStorage and applied **post-paint** by the existing `wiki.js` (concept/index/search) and `graph.js` (graph/single-file) IIFEs — the same mechanism theme already uses. Defaults (today's look) stay attribute-absent, so only an opted-in `soft`/`muted`/`off` user sees a brief load flash, identical to the existing theme flash. Separately, the Cytoscape **graph canvas** mirrors tokens via hardcoded `GRAPH_COLORS` literals keyed by `data-theme`, so contrast/border do not reach the canvas in Phase 2 (documented limitation; the graph *chrome* still reflects them).

---

## 6. Phase 3 — Missing features (item 3, all four)

Larger and partly server-dependent — firm up each sub-plan when Phase 3 starts. Flagged
**spikes** need a quick capability check before committing.

### 6.1 On-page ToC (reader-facing)
- Server-render a ToC from the concept's `h2`/`h3` into the reading column for docs with ≥N
  headings (works no-JS), flat-styled to match the nav. Distinct from the JS-only studio
  Outline overlay. Machinery: `render.py` concept rendering, `concept_page.html`.

### 6.2 Index dashboard (SPEC §3.6 Index)
- Client-side **type-filter chips · sort · search-within** enhancing the server-rendered
  type-groups; also addresses "index underuses horizontal space." Server still renders groups
  (`render.py` ~650-676); new `wiki.js` index logic progressively enhances.

### 6.3 Search results quality (SPEC §3.6 Search)
- **Match-highlighting · relevance sort · result meta** (type/path). Live serve already ranks
  via BM25 (`/__search`); mostly a results-renderer change + the static path
  (`static-search.js`, `wiki.js` ~193, `search_page.html`).

### 6.4 Studio depth (studio capabilities)
- **(spike) Quick-actions RUN** — POST a directive to the agent instead of only pre-filling
  the composer (`buildIntentsToolbar` ~4255). Check for/introduce a server directive endpoint.
- **(spike) Validation count in rail/footer** — surface validate state (CLI-only today; may
  need a small server endpoint).
- **On-demand doc diff in Changes** — reuse the conflict-modal diff renderer
  (`showConflictModal` ~3816) for a Changes-tab diff (today it's an event feed,
  `renderChangeList` ~2548).

> **Build reconciliation (2026-07-06, Phase-3 plan):** machinery mapping fixed line refs and firmed the sub-plans. **6.1** the ToC keys on the *rendered* reading-column `<h2>`/`<h3>` (the renderer demotes source `#`→`<h2>`; `reference/cli.md` is all `#` so a source-level ToC would be empty), extracted by regex over the final `body_html` so `#anchors` match the emitted ids (the two `_slugify()`s diverge); gate ≥3 headings; new `.okf-toc*` in `wiki.css` (no-JS), distinct from the JS-only studio Outline. **6.2** the real index renderer is `_render_index_page` (render.py ~2002, both serve+static); the card grid is already responsive so "underuses horizontal space" is the `--okf-maxw` cap — widen via a new `--okf-index-maxw`; add `data-okf-*` to cards and enhance in `wiki.js` (studio.js is serve-only). **6.3** relevance sort is already satisfied on all three paths; the deltas are match-highlighting (escape-then-`<mark>`, both search-page renderers) + static result-meta parity + match-centred snippets (a prerequisite for meaningful highlighting); the live-suggest dropdown is left as-is (its a11y contract). **6.4** RUN posts the intent as a `/__comment` directive (the existing studio→agent channel — no new endpoint); the Changes diff reuses `/__diff` via an extracted `renderDiffInto()` (change events already carry `detail.before` + `rev`); the validation count is a read-only, token-gated GET `/__validate` cached on `studio.current_rev()`, completing SPEC §3.5's status-strip element.

---

## 7. Verification (per phase, before "done")
1. `python3 -m pytest tests/ -q` green (~3min, includes e2e). **Never** trust a `| tail`ed
   exit code — read the printed summary line. `test_render` token-parity across all 4 themes;
   `okf-viewer` class + `#okf-main` + placeholders intact.
2. Self-review via Playwright screenshots (`.aic/tmp/shot.py`, system Chrome via
   `AIC_PLAYWRIGHT_CHROME_PATH`, `wait_until="load"` — SSE breaks networkidle).
3. **Serve + tunnel** for the user's browser pass across **all 4 themes × {high,soft} ×
   {border on,muted,off}** and drive the flow: `/` focuses search; nav + rail collapse; a pin
   opens the thread overlay; overlay closes on Esc/click-away; **Split in Focus shows wide,
   unwrapped Source**; Appearance menu switches all four settings; all five views render.
   Recipe: `exec scripts/okf-loom serve docs-bundle --no-open` (bg, loopback :8787),
   `cloudflared tunnel --url http://localhost:8787` (bg); wait with `curl --retry`, **no
   `sleep`**; stop via TaskStop (never `pkill`).

## 8. Non-goals / preserved
- No branch/merge — stay on `feature/new-layout`. Don't touch `okf-loom-mcp/` (untracked) or
  `redesign-files-1.zip`.
- No edge-to-edge body prose (Rendered stays at the measure even in Focus).
- No Apple/Windows cues. No new theme-enum values (contrast is a modifier, not a theme).
- Swiss stays the default family; defaults keep today's contrasty look (soft/muted/off opt-in).
- Preserve unknown frontmatter + hand-authored content (repo ground rule).

## 9. Machinery quick-reference (verify at build)
| Item | Files / symbols |
|---|---|
| Rail + overlays | `studio.css` `.okf-panel` ~1144, `body.okf-studio-open` ~1159; `studio.js` `openPanel`/`closePanel`, `buildIntentsToolbar` ~4255, tab renderers ~3335 |
| Functional pin | `studio.css` `.okf-comment-mark` ~515 / `.okf-comment-marker` ~455; `studio.js` `jumpToCommentMark` ~1123-1276 |
| Workbench/Focus + split | `wiki.css` `.okf-page__main` cap; `studio.css` `.okf-view`/`.okf-split` ~267-345; `studio.js` `setView`/`ensureViewWrap` ~477-580 |
| Footer toolbar | `studio.css` `.okf-studio-bar--status` ~54, `.okf-statseg` ~77; `wiki.css` `.okf-conn` ~796; `studio.js` `mountBar` ~280-420; `pre-redesign-baseline:…/studio.css` for `.okf-studiobtn` |
| Related flat | `wiki.js renderLocalGraph` :87; `studio.js buildSidebarPanels` ~4064 |
| Border/contrast tokens | `wiki.css` `:root` + 4 `[data-theme]` blocks 24-335; boot script + `_theme_button_html` (render.py), THEMES sync render.py/wiki.js/studio.js/graph.js |
| ToC | `render.py` concept render; `concept_page.html` |
| Index dashboard | `index_page.html`; `render.py` groups ~650-676; new `wiki.js` index logic |
| Search quality | `search_page.html`; `static-search.js`; `wiki.js` ~193; live `/__search` |
| Studio depth | `studio.js buildIntentsToolbar` ~4255, `renderChangeList` ~2548, `showConflictModal` ~3816; server endpoints (spike) |

## 10. Rollback
Git tag `pre-redesign-baseline` (commit `2066013`). Physical copy under
`.superpowers/backup/viewer-baseline-2026-07-05/` (gitignored).
