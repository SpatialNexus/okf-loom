# Spec — okf-loom studio layout redesign ("Editorial Workbench")

Status: **design locked, self-reviewed, ready for `writing-plans`.**
Branch: `feature/new-layout` (off `develop`). Author decision authority: the
user has delegated implementation decisions ("I trust you with the decisions
going forward"), so the implementing session proceeds spec → plan → build with
a **self-review** at each gate rather than routing back for sign-off. Still
serve the *real* viewer + tunnel for a visual look before merge.

Approved visual reference (open these — they ARE the contract):
- `design/new-layout/mockups/swiss-v1.html`  ← the direction the user liked best
- `design/new-layout/mockups/technical-v1.html`
Both carry a Dark/Light toggle, a nav-collapse, and the comment pop-over. Their
**product CSS is byte-identical** — only the `:root`/`[data-theme]` token block
differs. Preserve that property in the real implementation: it is the proof the
architecture is decoupled.

---

## 1. Goal

Replace today's two-bar studio chrome with one **theme-agnostic layout skeleton**
whose entire visual character lives in `--okf-*` tokens. Ship two aesthetics as
switchable **themes** on that one skeleton — not as parallel hand-built layouts.

## 2. Architecture — DECOUPLED (non-negotiable)

- **One** layout skeleton (HTML structure + CSS that references `var(--okf-*)`
  ONLY). The layout CSS never hardcodes a colour, font, border, radius, or
  spacing value — every such value is a token.
- **Themes override the full token set.** `test_render.py` enforces token
  parity: a theme that misses a token fails the suite. Every shipped theme
  defines every token.
- The aesthetic difference is carried by tokens, most importantly a new
  **active-state token pair** (see §5). Swapping the token block swaps the look.

## 3. Layout skeleton — "Editorial Workbench" hybrid

Grid: `topbar / body / status`, where `body` is a **2-column** grid
`nav | reading`. The comment loop is an **overlay pop-over**, NOT a third column.

**3.1 Top bar** (replaces today's two bars) — one row:
brand · breadcrumb · search · Index/Graph view-nav · theme switch.
- Search focuses on the **`/`** key, shown as a plain keycap. No OS modifier
  glyph anywhere. The real palette keybinding may stay Ctrl/Cmd+K functionally
  but must never render an OS glyph (`⌘`/`⊞`).
- No window traffic-light dots, no SF/`-apple-system` font, no centered
  Spotlight-style search field. The user dislikes Apple/Mac cues.

**3.2 Left nav** — docked, **collapsible** (a toggle in the top bar collapses it
to `0` for a full-width read). Concepts grouped by **Diátaxis type**
(Explanation / How-to / Reference / Tutorial / …) with small uppercase group
labels. Active item uses the active-state tokens (§5).

**3.3 Reading column** — **full width; no reserved comment gutter.**
- Prose sits at a comfortable centered measure (`--okf-prose-maxw`, ~76ch — the
  existing token; do NOT stretch body text edge-to-edge). "Full width" means the
  reading *column* is undivided when the pop-over is closed, not that lines run
  the whole viewport.
- Contents: type band · title · aliases · entity + typed-relation chips · lead ·
  prose (code/math/diagram rendering unchanged).
- **Comments anchor inline as a small pin** on the commented span
  (e.g. `◆ 1`), styled with the active-state tokens. Clicking the pin (or the
  highlighted span) opens the pop-over thread. The thread *content* lives only
  in the pop-over — the reading page stays a reading page.
  *(This SUPERSEDES the earlier "margin notes in a right-hand gutter" idea — the
  gutter reserved space and read like a docked panel; removed per user.)*

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

**3.5 Bottom status strip** — ambient/noisy status moved off the top bar:
connection indicator · agent-watching state · validation count · a plain
**"Commands"** affordance (opens the palette; no key glyph).

**3.6 The five views generalize on this skeleton:**
- **Concept** — the reading column as above.
- **Index** — reading column becomes a card/list dashboard grouped by type.
- **Graph** — reading column becomes the Cytoscape canvas; node detail opens in
  the pop-over.
- **Search** — reading column becomes a results list.
- **Single-file** — reading column with no metadata band.

## 4. Theme set to ship

**Technical** and **Swiss**, each **light + dark** = **4 themes**. Editorial
(serif) and Neo-Brutalist were rejected — do not ship them.

- **Technical** (dev-tool): denser, `Inter` UI + monospace accents, teal accent
  (`#2dd4bf` dark / `#0c7373` light), `--okf-radius` ~6px, subtle borders, and
  **subtle tinted** active states.
- **Swiss** (utilitarian/grid): `Helvetica Neue`-style heavy display type,
  `--okf-radius` 0, hairline grid borders (`--okf-border-strong` = fg in light),
  and **solid "boxed" accent fills** for active states. Keep white bordered
  boxes for surfaces in light mode. (User's favourite.)

**Decision (delegated): retire the old `pastel/sepia/midnight` themes.** The
redesign's scope is a new look; the flat `light/dark` values are replaced by the
four new theme values. Recommended model — keep the existing single `data-theme`
mechanism and flatten to four theme values (`technical-light`,
`technical-dark`, `swiss-light`, `swiss-dark`), each a complete token block
(this satisfies token parity naturally). A two-axis `data-theme-family` ×
`data-theme` model is a viable alternative but doubles attribute plumbing
(`render.py __THEME_ATTR__`, `studio.js`, `config`, tests) — the plan should
weigh it, defaulting to the flat model unless there's a reason not to. Whichever
is chosen, sequence the migration carefully in the plan:
- `render.py` `__THEME_ATTR__` / `__DATA_ATTRS__` emission,
- `studio.js` theme list (`~:3046-3050`) + palette theme-switch commands + the
  top-bar theme switcher UI,
- `okf-loom.config.yaml` `theme:` enum (`auto | light | dark | pastel | sepia |
  midnight` today) + `StudioConfig.theme`,
- **localStorage migration** for a returning user pinned to a retired theme
  (map `dark→technical-dark`, `light→technical-light`, others → nearest),
- `test_render.py` expected-theme list + parity assertions,
- `README.md` "Five colour themes" section + `docs/media/themes.gif`.

## 5. The active-state token primitive (the core new abstraction)

Introduce a token pair (plus a border token) the layout uses for every "active /
selected / boxed accent" surface — nav item, view-nav tab, type band, comment
pin, pop-over primary action, theme-switch selection:

```
--okf-active-fill    /* background of an active surface   */
--okf-active-fg      /* foreground/text on that surface   */
--okf-active-border  /* border of that surface            */
```
- **Technical:** `--okf-active-fill: var(--okf-accent-bg)` (tint),
  `--okf-active-fg: var(--okf-accent)`, `--okf-active-border: transparent`
  → subtle tinted active states.
- **Swiss:** `--okf-active-fill: var(--okf-accent)` (solid),
  `--okf-active-fg: var(--okf-accent-on)`,
  `--okf-active-border: var(--okf-accent)` → solid boxed fills.

**Rule:** filled active surfaces use `--okf-active-fg`; a non-filled active
indicator (e.g. an underline-only tab) uses `--okf-accent` for text, never
`--okf-active-fg` (which is white/dark in Swiss and would vanish without a fill).

## 6. New tokens the skeleton needs (add to EVERY shipped theme)

Beyond today's set, the redesign references these (names as used in the mockups;
finalize in the plan). All must be defined in all four themes or parity fails:
`--okf-active-fill`, `--okf-active-fg`, `--okf-active-border`,
`--okf-font-display`, `--okf-font-body`, `--okf-font-mono` (per-theme faces —
Technical Inter/mono, Swiss Helvetica),
`--okf-border-w`,
`--okf-tag-transform`, `--okf-tag-weight`, `--okf-tag-spacing`,
`--okf-title-weight`, `--okf-title-spacing`,
`--okf-pop-shadow` (pop-over elevation; Swiss keeps it minimal).
Reuse existing tokens where they already exist (`--okf-radius`,
`--okf-radius-sm`, `--okf-radius-pill`, `--okf-accent*`, `--okf-bg*`,
`--okf-fg*`, `--okf-border*`, spacing scale, `--okf-prose-maxw`,
`--okf-topbar-h`). The mockup `:root` blocks are the concrete starting values.

## 7. Hard contract (carry from the baseline — tests enforce parts)

- Keep the `okf-viewer` body class, the `#okf-main` skip-target, and every
  `__TOKEN__` placeholder `render.py` substitutes (see `render.py:1439+`,
  `:2106+`).
- Studio chrome is injected server-side by `server.py:_studio_bootstrap`; the
  new layout must stay compatible with that injection: agent chip, watching
  toggle, view switch, Comments/Changes, palette, connection status. The
  bootstrap currently builds the *second bar* + `.okf-panel` slide-over — the
  redesign folds those into the single top bar + status strip + pop-over, so
  `_studio_bootstrap` (and `studio.js`) get reworked to target the new DOM, not
  bypassed.
- Every theme overrides the SAME full token set (`test_render.py`).
- **Graph canvas colours:** the Cytoscape canvas cannot read CSS vars, so
  `graph.js` mirrors `--okf-select`/accent values in a `GRAPH_COLORS` constant
  block (keep in sync). Any accent change per theme must be reflected there — a
  per-theme lookup, since the four themes differ. Don't let the canvas fall out
  of sync with the token blocks.
- Preserve unknown frontmatter keys and hand-authored content (repo ground rule).

## 8. Non-goals / explicitly rejected

Editorial (serif) theme · Neo-Brutalist theme · any Mac/Windows cue (`⌘K`
glyph, window dots, SF font, centered Spotlight search) · stretching body prose
edge-to-edge.

*(REVISED 2026-07-05, Round 2: the studio loop is a thin rail + on-demand
overlay panels (see §3.4), NOT a docked reflow column. The reading column is
never reflowed by studio chrome — overlays pop over it. Swiss remains the
default family. A Workbench ↔ Focus reading mode (Focus collapses nav + rail +
frame for Source/Split) is added; Rendered prose stays at the ~76ch measure
even in Focus.)*

## 9. Baseline / rollback

- Physical copy: `.superpowers/backup/viewer-baseline-2026-07-05/` (full
  `viewer/` tree). *(Under `.superpowers/`, which is gitignored — local only.)*
- Git tag `pre-redesign-baseline` → commit `2066013`.
  Restore: `git checkout pre-redesign-baseline -- scripts/okf_loom/viewer`.

## 10. Verification (before claiming done)

1. `test_render.py` green — token parity across all four themes, `okf-viewer`
   class + `#okf-main` present, placeholders intact.
2. Full viewer test suite green.
3. Serve the real viewer and **tunnel** for a visual pass in all four
   theme × mode combinations (`scripts/okf-loom serve docs-bundle --no-open`,
   loopback → cloudflared; recipe in the handover). Drive the actual flow:
   `/` focuses search, nav collapses, a comment pin opens the pop-over, the
   pop-over closes on scrim/Esc, all five views render.

## 11. Current-layout architecture map (still accurate)

`scripts/okf_loom/viewer/` — `templates/` (5 standalone HTML templates, no
shared base: `index_page`, `concept_page`, `graph_page`, `search_page`,
`single_file`) + `static/` (`wiki.css` owns ALL `--okf-*` tokens in `:root` +
per-theme overrides; `studio.css`, `graph.css` consume tokens; `studio.js`
injects the second bar / `.okf-panel` slide-over / command palette).
`render.py` substitutes `__TOKEN__` placeholders into the templates. Binding
contract on any ambiguity: `docs-bundle/reference/spec.md`; gotchas:
`resources/gotchas.md`.
