# Handover — Adopt the okf-loom "Editorial Workbench" theme overhaul

> [!IMPORTANT]
> **Historical and superseded.** This pre-merge adoption handover preserves the
> branch state and instructions that existed before the Editorial Workbench
> hardening closed at `be52770` and stabilized through `ded047c`. Do not use its
> commit counts, duplicated-theme guidance, cache notes, or verification totals
> as current instructions. Use the [current specification](../../docs-bundle/reference/spec.md)
> and the [completed hardening plan](../../docs-bundle/plans/editorial-workbench-hardening.md).

> **Purpose:** get the *complete* new theme system live and stop landing on the **old-looking swiss/technical**. Hand this whole file to the dev (or paste it into a fresh AI coding session working in their okf-loom checkout). Self-contained.

---

## 0. Which situation are you in?
- **(A) You have an okf-loom checkout and want its theme switched to the new look.** ← the common case; read all of this.
- **(B) You deploy/serve okf-loom's output somewhere else** (a site that embeds the served or statically-built pages). Read §1 + §9.
- **(C) You're porting okf-loom's theme layer into a *different* app/framework.** Read §5 + §6 + §9.

---

## 1. TL;DR — the three things that cause "old-looking swiss/technical"

1. **Wrong ref (most likely).** The entire overhaul is **78 commits that live ONLY on branch `feature/new-layout`** (tip `ae05a6a`, pushed to `origin`). It is **NOT merged into `develop`**, and `develop` is the repo's default branch (`origin/HEAD → develop`). So `git clone` / a `develop` checkout / "pull latest" gives you the **pre-redesign** theme system. → **You must be on `feature/new-layout`.**
2. **Partial adoption / broken sync contract.** The 4-theme system is DUPLICATED across **four** files that must stay identical (see §4). Copying only some of them — or an older `wiki.css` — yields a half-old/half-new Frankenstein that renders like an old swiss/technical. → **Take the branch wholesale; never hand-port individual values.**
3. **Stale cached assets.** Asset URLs are **unversioned** (`/__static/wiki.css`, `/__static/wiki.js` — no `?v=hash`). Any browser/CDN/proxy holding the old CSS/JS keeps serving the old look after you deploy. → **Hard-refresh / purge cache** (§8, §9).

---

## 2. What the overhaul IS (so "correct" is unambiguous)

- **4 themes:** `swiss-light`, `swiss-dark`, `technical-light`, `technical-dark` (plus `auto`). **Swiss is the default / primary family** — swiss-first everywhere; `auto` resolves to `swiss-light` / `swiss-dark` by OS scheme.
- **Replaces the OLD 5 themes** `light / dark / pastel / sepia / midnight`. Returning users' saved choices are migrated client-side (see `LEGACY_THEMES`, §4): `light→technical-light`, `dark→technical-dark`, `pastel→swiss-light`, `sepia→swiss-light`, `midnight→technical-dark`.
- **Fully token-driven appearance:** every colour/type/border value is a CSS custom property in `wiki.css` theme blocks — no hardcoded aesthetics in JS/templates. (One documented exception: the graph canvas uses `GRAPH_COLORS` literals per theme in `graph.js` and deliberately does **not** react to the contrast/border modifiers.)
- **`Aa ▾` Appearance menu** in the top bar **replaced the old theme-cycle button.** It consolidates **Family** (Technical/Swiss) × **Mode** (Light/Dark/Auto) × **Contrast** (High/Soft) × **Border** (On/Muted/Off).
- **Two orthogonal modifiers**, independent of theme, applied as root attributes: `data-okf-contrast="soft"` and `data-okf-border="muted"|"off"`. Default = attributes **absent** = today's high-contrast, bordered look.
- Plus the whole layout it's attached to: single top bar, Diátaxis left nav rail, docked studio rail + pop-over overlays, server-rendered on-page ToC, index dashboard (filter/sort/search-within), live+static search highlighting, footer button toolbar + Focus mode, ambient validation chip.

If what you see lacks the `Aa ▾` menu, or the themes are named `pastel`/`sepia`/`midnight`, or borders/contrast toggles do nothing — you're on the old code or a partial copy.

---

## 3. Get the exact code

```bash
git fetch origin
git checkout feature/new-layout        # tip ae05a6a — 78 commits ahead of develop
git log --oneline -1                    # expect: ae05a6a tidy files ready for push
git rev-list --count develop..HEAD      # expect: 78
```

- **It is NOT on `develop`.** If you want the dev to just use the default branch, **merge `feature/new-layout` into `develop` first** (your call — it's 78 commits; ideally via PR/review) and then they pull `develop`. Until then, they must check out `feature/new-layout`.
- Rollback tag if you need the pre-redesign baseline: `pre-redesign-baseline` = `2066013`.
- Repo: `git@github.com:SpatialNexus/okf-loom.git`.

---

## 4. THE sync contract — the #1 silent breakage (there is NO automated test guarding it)

`THEMES` + `THEME_GLYPHS` (swiss-first) are **duplicated in four files** because each JS context loads independently (reading page / studio / graph / single-file) and the server renders the initial theme. The three JS files also carry `LEGACY_THEMES`. **All copies must be byte-identical, same order.**

| File | Anchor | Holds |
|------|--------|-------|
| `scripts/okf_loom/render.py` | `_THEMES` :560, `_THEME_GLYPHS` :563 | server-rendered initial theme + `Aa ▾` markup (`_theme_button_html` :571) |
| `scripts/okf_loom/viewer/static/wiki.js` | :27 / :28 / `LEGACY_THEMES` :30 | reading pages (concept/index/search) theme boot + appearance wiring |
| `scripts/okf_loom/viewer/static/studio.js` | :220 / :221 / :223 | studio chrome |
| `scripts/okf_loom/viewer/static/graph.js` | :29 / :30 / :32 | graph + single-file; also `GRAPH_COLORS` :61 |

Quick desync check:
```bash
grep -nE 'THEMES = \["swiss-light"' scripts/okf_loom/viewer/static/wiki.js \
  scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/graph.js
# all three arrays identical; render.py:_THEMES (:560) must list the SAME order.
```
If you change the theme list/order/glyphs, change **all four**. `renderers.js` detects dark via `/-dark$/` (:96) — a theme name must end in `-dark`. **No test asserts these four match** — it's manual discipline, so verify by eye after any theme edit or partial copy.

---

## 5. Runtime — how a theme actually applies (use this to debug "why old?")

- **localStorage keys:** `okf-theme`, `okf-contrast`, `okf-border`.
- **Boot (wiki.js / graph.js):** read `okf-theme` → migrate through `LEGACY_THEMES` → apply if in `THEMES`, else `resolveAuto()` → `swiss-light`/`swiss-dark`. `okf-contrast`/`okf-border` are applied **post-paint** from localStorage.
- **First paint / no-JS:** `wiki.css :root` (line 24) is the **Swiss-light fallback** (radius 0, Helvetica, solid boxed active state, `--okf-border-strong:#111418`, `--okf-shadow:none`) so pre-JS paint is already the new Swiss, not the old theme.
- **CSP** (`server.py` ~:1813): `script-src 'self' https://cdn.jsdelivr.net` — **no `unsafe-inline`.** There is deliberately no pre-paint inline theme script; contrast/border apply post-paint (opted-in soft/muted/off users get a brief flash ≈ the existing theme flash; defaults never flash). Do **not** add inline `<script>` expecting it to run. `jsdelivr` is allowed only for Cytoscape on the graph page.
- **Appearance menu markup = one source:** `render.py:_theme_button_html` (:571) → trigger `id="okf-theme"`, popover `id="okf-appearance-menu"`, four `role="radiogroup"` groups. Server can't read localStorage, so it renders contrast/border as `high`/`on` and the client corrects `aria-checked` at boot. The open/close + option handlers are **duplicated** in `wiki.js` and `graph.js` (studio.js reuses them); keep those in parity if you touch the menu.

---

## 6. The token blocks — appearance source of truth (`wiki.css`)

- `:root` (:24 — the Swiss-light fallback) **plus four theme blocks:** `[data-theme="technical-light"]` (:171), `technical-dark` (:222), `swiss-light` (:273), `swiss-dark` (:324).
- **Modifier blocks placed AFTER the theme blocks** (order matters — border after contrast so `off` beats `soft` on `--okf-border-strong`): `:root[data-okf-contrast="soft"]` (:383), `:root[data-okf-border="muted"]` (:391), `[data-okf-border="off"]` (:392).
- **Every theme block must define the FULL token set** (light `:root` tokens + redesign additions + soft-contrast variants). This is guarded by `tests/test_render.py::test_theme_blocks_override_full_token_set` — if you add a token, add it to **all four blocks + `:root`**, or the test fails and a theme silently inherits a wrong value. (Dark blocks intentionally use brighter status colours for contrast.)
- Light-vs-dark status colours (e.g. `--okf-ok`/`--okf-warn`/`--okf-error`) are per-theme; the validation chip uses `--okf-error` so it adapts (recent fix).

---

## 7. Templates (5) — all must carry the new chrome

`scripts/okf_loom/viewer/templates/`: `concept_page.html`, `index_page.html`, `search_page.html`, `graph_page.html`, `single_file.html`. All inject the `Aa ▾` appearance menu (`__INITIAL_THEME_BUTTON__` / `_nav_controls_html`) + the brand-mark. CSP `script-src 'self'` on the reading templates (graph additionally allows `jsdelivr` for Cytoscape). A page missing the appearance menu = a stale/partial template.

---

## 8. Verify a correct adoption (do ALL of these)

1. **Tests:** `uv run --with pytest --with playwright --with pyyaml pytest tests/ -q` → expect **~1315 passed / 23 skipped / 0 failed**. (Without `--with playwright` the ~76 browser tests aren't collected → ~1233; that's not a regression. The sandbox `.venv` may be empty — `uv run --with …` supplies deps. Documented flake: `test_comment_mark_wraps_selection` — rerun once if it's the only failure. **Read the printed summary line; don't trust a piped exit code.**)
   - Theme guards specifically: `pytest tests/test_render.py -k "theme or appearance or token" -q` and `pytest tests/test_viewer_browser.py -k "theme or appearance" -q` (incl. `test_graph_theme_resolves_swiss_first`). JS lint: `pytest tests/test_js_lint.py -q` (or `node --check` each of wiki/studio/graph/static-search.js).
2. **Visual:** `scripts/okf-loom serve docs-bundle --no-open` → open a concept page → click `Aa ▾` → flip Family/Mode/Contrast/Border. Confirm: Swiss is default, all four themes render, Border On/Muted/Off changes the hairline frames, Contrast Soft lowers it. Then **hard-refresh** (Cmd/Ctrl-Shift-R) to prove you're not seeing a cached old asset.
3. **Migration:** in devtools, `localStorage.setItem('okf-theme','pastel')` then reload → must resolve to **swiss-light** (proof `LEGACY_THEMES` is present). Try `'midnight'` → `technical-dark`.
4. **Grep sanity:** the §4 desync check prints identical arrays; `grep -rn 'pastel\|sepia\|midnight' scripts/okf_loom/viewer/static/*.js` should only appear inside `LEGACY_THEMES` (as migration keys), nowhere else.

---

## 9. Deploy / cache / other-app notes

- **Unversioned assets:** after deploying the new branch, **purge/hard-refresh** `/__static/*.css` and `/__static/*.js`. This alone can be the whole "it still looks old" bug behind a CDN or aggressive browser cache.
- **Static export:** `scripts/okf-loom build …` (run `scripts/okf-loom build --help` for args) emits a static site; asset links become relative (`__static/…`). Rebuild from the `feature/new-layout` code and redeploy the built output — an old build directory keeps the old look.
- **Live serve:** `scripts/okf-loom serve <bundle> --no-open` (`--port N`, `--tunnel` for a public link via cloudflared). Everything is served from the current files on disk, so a fresh serve on the new branch is authoritative.
- **Porting into a different app (situation C):** you need (1) `wiki.css` — the `:root` + 4 theme blocks + the two modifier blocks; (2) the theme-boot logic from `wiki.js` — `THEMES`, `LEGACY_THEMES`, `applyTheme`, `applyModifier`, `resolveAuto`; (3) the `_theme_button_html` markup for the `Aa ▾` menu. Preserve the contract: localStorage keys `okf-theme`/`okf-contrast`/`okf-border`, the `data-theme` / `data-okf-contrast` / `data-okf-border` root attributes, swiss-first defaults, and CSP-compatible (external, **not** inline) scripts.

---

## 10. Don't-break checklist
- 4-file `THEMES`/`THEME_GLYPHS` sync (+ 3-file `LEGACY_THEMES`), **swiss-first order** (§4).
- Every `wiki.css` theme block defines the **full token set** (test-guarded) (§6).
- No hardcoded aesthetics outside the token system — `graph.js` `GRAPH_COLORS` is the one documented exception (per-theme literals; intentionally ignores contrast/border).
- Appearance menu markup single-sourced in `render.py`; wiring parity across `wiki.js`/`graph.js`.
- Unversioned assets → **cache-bust on every deploy**.
- Untracked, leave alone: `okf-loom-mcp/`, `redesign-files-1.zip`, `design/new-layout/workbench-preview.html`.
- Contract/spec: `design/new-layout/SPEC.md`; the redesign history + rationale lives in the git log of `feature/new-layout` (start at `1454683`).
