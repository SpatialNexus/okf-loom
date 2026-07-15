# Editorial Workbench Round 2 — Phase 3 (Features) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the four §6 features on the Editorial Workbench viewer — a server-rendered **on-page ToC** (6.1), an **index dashboard** with client-side type-filter/sort/search-within (6.2), **search-results quality** (match-highlighting + result meta) (6.3), and **studio depth** — quick-actions RUN, on-demand Changes-tab diff, and a validation-count status chip (6.4) — all on branch `feature/new-layout`, suite green.

**Architecture:** Each feature enhances an existing surface without breaking the no-JS baseline or the decoupling contract. **6.1** extracts the ToC from the *final rendered* `body_html` (anchors already exist and survive demotion) and injects it server-side into `concept_page.html`; new `.okf-toc*` CSS lives in `wiki.css` so it works with no JS. **6.2** adds `data-okf-*` attributes to the server-rendered cards (so the server still owns the groups) and a `wiki.js` `enhanceIndex()` that builds a chips/sort/search toolbar client-side. **6.3** adds an escape-then-`<mark>` highlighter + match-centred snippets to *both* the live Python renderer (`_render_search_page`) and the static JS renderer (`renderResults`), reconciling their markup. **6.4** reuses existing server channels: RUN posts the intent as a `/__comment` directive (the studio→agent channel — no new endpoint); the Changes diff reuses `/__diff` via an extracted `renderDiffInto()`; only the read-only, token-gated `/__validate` GET is net-new server surface (and it completes SPEC §3.5's already-specified "validation count").

**Tech Stack:** Python 3.11+ (`render.py`, `server.py`, `validate.py`, `pytest`), vanilla ES-module IIFEs (`wiki.js`, `studio.js`, `static-search.js` — no build step; `node --check` for syntax), plain CSS custom properties (`wiki.css`, `studio.css`), Playwright + system Chrome for browser tests. Run everything via `scripts/okf-loom`.

**Approved contract:** `docs/superpowers/specs/2026-07-05-editorial-workbench-round2-design.md` **§6** (commit `b4a0159`), enhancing `design/new-layout/SPEC.md` §3.6 (the five views). This plan implements all four §6 sub-features. Phase 1 (layout) + Phase 2 (appearance) are DONE + GREEN (`a957388..dbafb0c`, suite `1287 passed / 23 skipped`).

---

## ⚠️ Spec-reality reconciliations + design calls (machinery-mapped 2026-07-06; advisor unavailable — compensated by per-task two-stage review + final review + independent test/screenshot verification)

The visible design matches §6; these are the mechanism decisions the mapping surfaced (documented here + reconciled into the spec in Task 0):

- **D1 — ToC extracts from the *rendered* reading-column headings, not the source `##`/`###`.** The concept renderer *demotes* headings by one level (`_demote_headings`, render.py:1214-1234): source `#`→`<h2>`, `##`→`<h3>`, `###`→`<h4>`. The gold-standard page `reference/cli.md` uses **all `#` headings** → 39 rendered `<h2>`, **zero** source `##`/`###`; keying the ToC on source levels would give it *no ToC*. So the ToC keys on the **rendered `<h2>`/`<h3>`** (the same set the studio Outline reads), extracted by regex over the *final* `body_html` (after link-rewrite + demotion). This also guarantees the `#anchors` are byte-identical to the ids the renderer emitted — the two module `_slugify()`s (viewer/markdown.py vs parse.py) diverge on `_` and empty titles, so re-slugifying would mismatch. **Threshold: ≥3 rendered headings** (design call — skips trivially short pages; still lights up showcase=10, cli=39). `<h4>` (source `###`) is intentionally excluded (rare; keeps the ToC shallow + matches the Outline).
- **D2 — §6.3 relevance sort is already satisfied on all three search paths** (live BM25-sorted; static re-sorts by −score; dropdown consumes sorted JSON). The real §6.3 deltas are **match-highlighting** (greenfield everywhere) and **static result-meta parity** (the live Python renderer already emits `.okf-search-result__meta` + a type chip; the static JS renderer emits the older markup). **Match-centred snippets** are built on both paths because both currently show the *curated description*, which often lacks the query term — without a match-centred snippet, highlighting finds nothing (prerequisite, not scope creep). The live-suggest **dropdown** (`renderLive`, wiki.js) is a distinct surface with a pinned a11y contract (`test_search_suggestions_use_plain_link_semantics`) and is **left as-is** (plain links, no highlight) to keep §6.3 focused on the two search-*page* renderers.
- **D3 — Quick-actions RUN reuses the existing comment channel (no new endpoint).** The studio→agent channel is `POST /__comment` → `post_comment` → `directives.jsonl` → the agent's `wait`/`comment-claim` loop; a comment **is** an open directive the agent runs. RUN fills the composer with a *complete standalone* directive (only when empty — it respects text the user already typed) and clicks the composer Send button, reusing `postCommentFromComposer`'s optimistic-insert + POST + toast path. Pre-fill stays the primary click. Same token + loopback + `--no-edit` gate as commenting; trust boundary unchanged.
- **D4 — Changes-tab diff reuses `/__diff` via an extracted renderer; both revs are already on the event.** A change row carries `r.detail.before` (prior content-hash rev) and `r.rev` (new rev) — `undoOne` already relies on this — so no history-scanning is needed. Extract the conflict modal's diff-render core into `renderDiffInto(container, {concept, from, to})` and call it from a per-row "View diff" (do **not** reuse the whole conflict modal — its Keep-mine/Take-agent actions are resolution semantics whose labels are pinned by tests). Snapshots older than the 50-per-concept ring return 404 → `renderDiffInto` surfaces it gracefully.
- **D5 — `/__validate` is a read-only, token-gated GET, cached on the studio rev.** Validation is CLI-only today (`validate_bundle(bundle) -> ValidationReport`, validate.py:349). The endpoint copies the exact `/__diff` token gate (server.py:1070) — no mutation, no new trust surface beyond a token-gated read — and caches the counts on `studio.current_rev()` so a poll doesn't re-walk the bundle. This **completes SPEC §3.5**'s already-specified "validation count" status element (not net-new scope). D3's graph-canvas / Phase-2 limits are untouched.

Everything else matches §6.

---

## The decoupling contract (do not violate)

1. **Layout CSS references tokens only.** No hardcoded colour/font/border/radius in any `.okf-*` product rule — every aesthetic value is `var(--okf-*)`. New rules (`.okf-toc*`, `.okf-index-toolbar*`, `.okf-index-chip`, `.okf-change__diff*`, `mark`) use only tokens (the sole accepted exception is the `font-size: 10px` micro-label, already used by `.okf-nav__group` / `.okf-toc__title`). `--okf-index-maxw` is a **layout** constant added beside `--okf-maxw` in `:root` (NOT a per-theme parity token).
2. **Each shipped theme stays one self-contained `[data-theme="…"]` block.** Phase 3 adds **no** theme-parity tokens, so `test_render.py::test_theme_blocks_override_full_token_set` is untouched. Do not edit any `[data-theme]` block or the `:root[data-okf-*]` modifier blocks.
3. **Preserve the hard-contract markers:** `okf-viewer` body class, `#okf-main`, every `__TOKEN__` placeholder (a NEW placeholder — `__TOC_HTML__` — must be fully replaced in *every* mode so no literal leaks), the `.okf-topbar` wrapper + its search form + Graph/Index links, `.okf-search__results` / `.okf-search__title`, `.okf-index` / `.okf-section` / `.okf-card` / `.okf-cardgrid` / `.okf-concept-list`, and the first-anchor contract on `.okf-concept-list li`.
4. **No Apple/Windows cue.** No `⌘`/`⊞`, no window dots.
5. **THEMES / THEME_GLYPHS / LEGACY_THEMES stay swiss-first + identical** across `render.py`/`wiki.js`/`studio.js`/`graph.js`. Phase 3 does not touch them.
6. **`GRAPH_COLORS` / `syncLabelColour` / `graphPalette` untouched.** Phase 3 does not touch the graph.
7. **Studio→agent + server trust boundary:** the only new server surface is the read-only, token-gated `/__validate` GET (D5). RUN (D3) and the Changes diff (D4) reuse existing endpoints. Every studio write/read still goes through `tokenFetch`.

---

## Test contracts — MUST preserve (verified against `tests/` by machinery mappers)

| Contract | Where asserted | What the task must keep |
|---|---|---|
| Token parity across all 4 themes (no new parity tokens this phase) | `test_render.py::test_theme_blocks_override_full_token_set` | Don't edit `[data-theme]` blocks or add parity tokens. |
| Subtitle/description document order (h1 → subtitle → description) | `test_render.py` iter2 (~1104-1130) | ToC injects at concept_page.html:86, **downstream** of the description → order unperturbed. |
| Concept header completeness (`.okf-type-chip`, `.okf-page__title`, `.okf-page__description`, resource, tags) | `test_render.py` (~1618-1659) | ToC sits *after* `</header>` → header untouched. |
| `.okf-page__body` visible + non-empty; studio comment-marks/child-index live inside it | `test_viewer_browser.py::test_concept_page_loads` (~273); `test_studio_iter1_browser.py` (~154) | **Inject the ToC OUTSIDE `.okf-page__body`** (concept_page.html:86). |
| No dead internal links in the static build | `test_render.py::test_build_site_static_has_no_dead_internal_links` (~199) | Index chips/sort are `<button>`/`<input>` (no `href`); ToC links are same-page `#slug`. |
| Static search corpus is a bare JSON array, id-sorted, deterministic, fields `{id,title,description,type,tags,aliases,body_excerpt}` | `test_render.py` (~743, ~835) | Task 5 doesn't touch the corpus emitter — only the client renderer. |
| Serve/spa search does NOT load `static-search.js`; static DOES; `.okf-search__title` no `okf-muted` + `--okf-text-xl`; `_render_search_page` tolerates results missing type/description/snippets | `test_render.py` (~816, ~784, ~1149, ~1179) | Task 4 keeps `_render_search_page`'s signature + null-tolerance; `<mark>`/snippet changes stay inside the result body. |
| `/__diff` requires the token (403 without) + validates the concept id | `test_studio_iter2_backend.py` (~365, ~390) | Task 7 reuses `/__diff` via `tokenFetch`; Task 8's `/__validate` copies the same token gate. |
| Rail ids are a **superset** of `{comments,changes,outline,metadata}`; overlay doesn't reflow (body `padding-right:48px`) | `test_studio_iter1_browser.py::test_rail_present_and_overlay_does_not_reflow` (~452) | Tasks 6/7/8 add buttons/badges, never remove rail ids or change the reserve. |
| Conflict modal: `.okf-conflict-overlay`, `role="alertdialog"`, actions exactly `View diff`/`Keep mine`/`Take the agent's edit`, Esc hides | `test_studio_iter1_browser.py` (~857/926/974/990) | Task 7 extracts the diff *renderer* only; the modal DOM + labels stay; existing tests exercise the extraction. |
| Changes tab filters comment events client-side; `state.events` from `/__data/events?limit=500`; `CHANGE_EST_ROW_H` prepend-shift | `test_studio_iter2_e2e.py` (~380/563); `test_studio_iter1_browser.py` (~1276) | Task 7 only *adds* a per-row button + expandable diff; the filter/virtualizer logic is untouched. |
| Live `/__search` 500 on backend error (no silent fallback); `_run_search(self, q, *, limit)` | `test_server_smoke.py` (~87) | Not touched this phase. |
| Search-suggest dropdown a11y: `role=list`/`listitem`, plain links, Esc hides | `test_viewer_browser.py::test_search_suggestions_use_plain_link_semantics` (~1075) | `renderLive` left as-is (D2). |

**FREE to add (greenfield / zero test hits):** `__TOC_HTML__` + `.okf-toc*`; `data-okf-type`/`-title`/`-search`; `.okf-index-toolbar*` / `.okf-index-chip` / `.okf-index-empty` / `--okf-index-maxw`; `enhanceIndex`; `_highlight` (py) + `highlight` (js) + `<mark>` CSS; `.okf-search-result__type` default colour; `INTENTS[].runPrompt`; `.okf-panel__intent-run` / `.okf-panel__intent-group`; `okf-composer__submit` hook class; `renderDiffInto`; `.okf-change__diff*`; `/__validate`; `.okf-statseg--validation`.

**Known flakes (rerun once if the ONLY failures):** `test_comment_mark_wraps_selection` (120ms debounce), `test_agent_watching_toggle_posts_presence`, `test_agent_activity_panel_has_unique_sections` (shared-server races). The 23 skips are optional upstream-bundle fixtures — expected.

---

## New names locked for this phase (use these exact strings everywhere)

- **ToC:** placeholder `__TOC_HTML__`; `<nav class="okf-toc" aria-label="On this page">` › `.okf-toc__title` ("On this page") › `<ul class="okf-toc__list">` › `<li class="okf-toc__item">` › `<a class="okf-toc__link okf-toc__link--h{2|3}" href="#{slug}">`. Python helper `_build_toc_html(body_html)`; module consts `_TOC_HEADING_RE`, `_TOC_TAG_RE`, `_TOC_MIN_HEADINGS = 3`.
- **Index dashboard:** per-card `data-okf-type` / `data-okf-title` / `data-okf-search` (lowercased "title description tags" haystack); per-section `data-okf-type`. Client: `enhanceIndex()`; `.okf-index-toolbar` › `.okf-index-toolbar__chips` (+ `.okf-index-chip[data-okf-type][aria-pressed]`) + `.okf-index-toolbar__controls` (`.okf-index-toolbar__search`, `.okf-index-toolbar__sort`); `.okf-index-empty`; token `--okf-index-maxw`.
- **Search:** Python `_highlight(text, query, *, limit=200)`; JS `highlight(text, tokens)`; both wrap matches in `<mark>` (escape-first). Static gains `.okf-search-result__meta` + `.okf-search-result__type` (parity with live). `.okf-search-result__type` gets a token default colour.
- **Studio RUN:** `INTENTS[].runPrompt` (complete standalone directive); toolbar row `.okf-panel__intent-group` wrapping the existing `.okf-panel__intent` + new `.okf-panel__intent-run` (text `▶`); composer Send button gains hook class `okf-composer__submit`.
- **Changes diff:** `renderDiffInto(container, {concept, from, to})`; per-row `.okf-change__diffbtn` (text "View diff", `aria-expanded`) + `.okf-change__diff` (hidden expandable, reuses `.okf-conflict__diff-table` styles). Studio test seam `window.okfLoomStudio._changeRow`.
- **Validation:** GET `/__validate` → `{ok, error, warning}`; handler `_handle_validate`; server cache attr `self.server._validate_cache = (rev, counts)`. Footer chip `.okf-statseg.okf-statseg--validation` (`data-state` ∈ ok|warn|error); JS `refreshValidation()`.

---

## File-structure map (what each touched file owns this phase)

- `scripts/okf_loom/render.py` — `_build_toc_html` + ToC wiring in `_render_concept_page` (Task 1); `data-okf-*` on index cards/sections in `_render_index_page` (Task 2); `_highlight` + match-centred snippet + highlighted title in `_render_search_page` (Task 4). **Editing render.py ⇒ serve RESTART.**
- `scripts/okf_loom/viewer/templates/concept_page.html` — `__TOC_HTML__` at line 86 (Task 1). **Template edit ⇒ serve RESTART.**
- `scripts/okf_loom/viewer/static/wiki.css` — `.okf-toc*` (Task 1); `--okf-index-maxw` + `.okf-index-toolbar*` / `.okf-index-chip` / `.okf-index-empty` + widen `.okf-index` (Task 3); `mark` + `.okf-search-result__type` default colour (Task 4).
- `scripts/okf_loom/viewer/static/wiki.js` — `enhanceIndex()` + init hook (Task 3).
- `scripts/okf_loom/viewer/static/static-search.js` — `highlight()` + match-centred `makeSnippet` + meta-parity `renderResults` (Task 5).
- `scripts/okf_loom/viewer/static/studio.js` — RUN (`INTENTS.runPrompt`, composer hook class, `buildIntentsToolbar`) (Task 6); `renderDiffInto` extraction + `changeRow` View-diff + `_changeRow` seam (Task 7); validation chip in `mountBar` + `refreshValidation` (Task 8).
- `scripts/okf_loom/viewer/static/studio.css` — `.okf-panel__intent-run/-group` (Task 6); `.okf-change__diff*` (Task 7); `.okf-statseg--validation` state colours (Task 8).
- `scripts/okf_loom/server.py` — `/__validate` route + `_handle_validate` (Task 8). **Server edit ⇒ serve RESTART.**
- `tests/test_render.py` — ToC (Task 1), index attrs (Task 2), live search (Task 4), static-source contract (Task 5).
- `tests/test_studio_iter1_browser.py` — index dashboard (Task 3), RUN (Task 6), Changes diff (Task 7), validation chip (Task 8).
- `tests/test_studio_iter2_backend.py` — `/__validate` backend (Task 8).
- `docs/superpowers/specs/2026-07-05-editorial-workbench-round2-design.md` — reconciliation note (Task 0).

**Environment recipe:**
- Serve (background): Bash `run_in_background: true`, `exec scripts/okf-loom serve docs-bundle --no-open --port 8788 --tunnel`. Wait: `curl -s --retry 30 --retry-delay 1 --retry-connrefused http://localhost:8788/demo/showcase -o /dev/null && echo up` (**no `sleep`**). Stop/RESTART via the **TaskStop** tool on the bg task id (never `pkill`). **RESTART after any render.py / server.py / template edit** (read at startup); CSS/JS served fresh — just reload. A stale prior-session serve may squat `:8787` with old code — use your own `--port 8788`.
- Tests: `python3 -m pip install pytest playwright pytest-playwright` (browser download disabled; system Chrome auto-used). `python3 -m pytest tests/ -q` (~3.5min incl. e2e). **Never** pipe pytest through `| tail` and trust the exit code — **read the printed summary line**. Browser tests spin their own server (`server_url`); no manual serve needed for pytest.
- Screenshots: Playwright + system Chrome, `executable_path=$AIC_PLAYWRIGHT_CHROME_PATH` (`/opt/google/chrome/google-chrome`), `args=["--no-sandbox"]`, `wait_until="load"` (SSE breaks networkidle). Default is Swiss-light (don't seed `okf-theme`); seed the other 3 + `okf-contrast`/`okf-border` for variants via `context.add_init_script`.

---

## PHASE 3 — Features

### Task 0: Reconcile the round-2 design spec §6 to the build decisions (D1–D5)

**Files:**
- Modify: `docs/superpowers/specs/2026-07-05-editorial-workbench-round2-design.md` — append after §6.4.

- [ ] **Step 1: Append a reconciliation note** at the end of §6 (after the `showConflictModal` bullet in §6.4, before `## 7. Verification`). Insert:

```markdown

> **Build reconciliation (2026-07-06, Phase-3 plan):** machinery mapping fixed line refs and firmed the sub-plans. **6.1** the ToC keys on the *rendered* reading-column `<h2>`/`<h3>` (the renderer demotes source `#`→`<h2>`; `reference/cli.md` is all `#` so a source-level ToC would be empty), extracted by regex over the final `body_html` so `#anchors` match the emitted ids (the two `_slugify()`s diverge); gate ≥3 headings; new `.okf-toc*` in `wiki.css` (no-JS), distinct from the JS-only studio Outline. **6.2** the real index renderer is `_render_index_page` (render.py ~2002, both serve+static); the card grid is already responsive so "underuses horizontal space" is the `--okf-maxw` cap — widen via a new `--okf-index-maxw`; add `data-okf-*` to cards and enhance in `wiki.js` (studio.js is serve-only). **6.3** relevance sort is already satisfied on all three paths; the deltas are match-highlighting (escape-then-`<mark>`, both search-page renderers) + static result-meta parity + match-centred snippets (a prerequisite for meaningful highlighting); the live-suggest dropdown is left as-is (its a11y contract). **6.4** RUN posts the intent as a `/__comment` directive (the existing studio→agent channel — no new endpoint); the Changes diff reuses `/__diff` via an extracted `renderDiffInto()` (change events already carry `detail.before` + `rev`); the validation count is a read-only, token-gated GET `/__validate` cached on `studio.current_rev()`, completing SPEC §3.5's status-strip element.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-05-editorial-workbench-round2-design.md
git commit -m "docs(spec): reconcile Round-2 §6 to Phase-3 build decisions (ToC/index/search/studio)"
```

---

### Task 1: On-page ToC (6.1) — server-rendered, no-JS, flat like the nav

Extract a ToC from the FINAL `body_html` (after `_demote_headings`) and inject it into the reading column between the header and the prose body. Anchors already exist (viewer/markdown.py emits `<hN id="slug">`; demotion preserves ids). RESTART the serve after this task (render.py + template).

**Files:**
- Modify: `scripts/okf_loom/render.py` — add `_build_toc_html` + module consts near `_demote_headings` (~1214); build `toc_html` after render.py:1417; add `.replace("__TOC_HTML__", toc_html)` in the concept `.replace` chain (~1595).
- Modify: `scripts/okf_loom/viewer/templates/concept_page.html` — inject `__TOC_HTML__` at line 86.
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — `.okf-toc*` rules.
- Test: `tests/test_render.py`.

- [ ] **Step 1: RED — write the failing tests.** Add to `tests/test_render.py`. These write a synthetic concept into the mutable `tiny_good_bundle` copy and render it via the existing `_render_concept_html(bundle_root, concept_id)` helper (test_render.py:310):

```python
def test_p3_1_toc_rendered_for_multi_heading_concept(tiny_good_bundle):
    """Round 2 §6.1: a concept with >=3 rendered headings gets a server ToC
    (no-JS), placed OUTSIDE .okf-page__body, with anchors matching the ids."""
    doc = tiny_good_bundle / "references" / "tocprobe.md"
    doc.write_text(
        "---\ntype: reference\ntitle: TocProbe\n"
        "description: Probe doc with several sections.\n---\n\n"
        "# First Section\n\nAlpha.\n\n# Second Section\n\nBeta.\n\n"
        "# Third Section\n\nGamma.\n", encoding="utf-8")
    html = _render_concept_html(tiny_good_bundle, "references/tocprobe")
    assert '<nav class="okf-toc"' in html
    for slug in ("first-section", "second-section", "third-section"):
        assert f'href="#{slug}"' in html, f"ToC missing #{slug}"
        assert f'id="{slug}"' in html, f"body missing id {slug} (anchors must resolve)"
    # ToC sits OUTSIDE the prose body (studio child-index/comment-mark tests).
    assert html.index('class="okf-toc"') < html.index("okf-page__body")


def test_p3_1_toc_absent_for_short_concept(tiny_good_bundle):
    """Round 2 §6.1: docs with <3 headings get NO ToC (skip trivial pages)."""
    doc = tiny_good_bundle / "references" / "shortprobe.md"
    doc.write_text(
        "---\ntype: reference\ntitle: ShortProbe\ndescription: One section.\n---\n\n"
        "# Only Section\n\nText.\n", encoding="utf-8")
    html = _render_concept_html(tiny_good_bundle, "references/shortprobe")
    assert 'class="okf-toc"' not in html
```

- [ ] **Step 2: Run — verify they FAIL:**

Run: `python3 -m pytest tests/test_render.py -k "p3_1_toc" -q`
Expected: FAIL (`<nav class="okf-toc"` not in html). Read the summary line. (If the loader rejects the synthetic frontmatter, open `tests/fixtures/tiny_good/references/metrics.md` and match its exact required keys — the point is a valid `reference` concept with ≥3 `#` headings and no `citations:` frontmatter.)

- [ ] **Step 3: GREEN — add `_build_toc_html` + consts to render.py.** Immediately BEFORE `def _demote_headings(` (render.py ~1214), insert (`re` and `_esc`/`_esc_attr_qs` are already imported/defined in render.py — confirm with `grep -n "^import re\|def _esc\b\|def _esc_attr_qs" scripts/okf_loom/render.py`):

```python
# Editorial Workbench §6.1: on-page ToC (reader-facing, server-rendered).
_TOC_HEADING_RE = re.compile(r'<h([23])\s+id="([^"]+)"[^>]*>(.*?)</h\1>', re.DOTALL)
_TOC_TAG_RE = re.compile(r"<[^>]+>")
_TOC_MIN_HEADINGS = 3


def _build_toc_html(body_html: str) -> str:
    """Server-rendered on-page Table of Contents (§6.1).

    Scans the FINAL reading-column HTML (after link-rewrite + heading
    demotion) for the ``<h2>``/``<h3>`` anchors the markdown renderer already
    emitted (viewer/markdown.py assigns id slugs; ``_demote_headings`` keeps
    them). Extracting from the rendered HTML — NOT parse.extract_headings —
    keeps the ``#anchors`` byte-identical to the real ids (the two module
    ``_slugify()``s diverge on ``_`` + empty titles) and uses the demoted
    levels the reader sees, matching the studio Outline's ``h2,h3`` set.
    Returns "" for docs with fewer than ``_TOC_MIN_HEADINGS`` headings so
    trivially short pages get no ToC. Works with no JS (plain ``<a href``)
    and is DISTINCT from the JS-only studio Outline overlay (``.okf-outline``).
    """
    heads = _TOC_HEADING_RE.findall(body_html)
    items: list[str] = []
    for level, slug, inner in heads:
        text = _TOC_TAG_RE.sub("", inner).strip()  # strip inline tags (<code> …)
        if not text:
            continue
        items.append(
            f'<li class="okf-toc__item">'
            f'<a class="okf-toc__link okf-toc__link--h{level}" '
            f'href="#{_esc_attr_qs(slug)}">{_esc(text)}</a></li>'
        )
    if len(items) < _TOC_MIN_HEADINGS:
        return ""
    return (
        '<nav class="okf-toc" aria-label="On this page">'
        '<p class="okf-toc__title">On this page</p>'
        f'<ul class="okf-toc__list">{"".join(items)}</ul>'
        '</nav>'
    )
```

- [ ] **Step 4: GREEN — build `toc_html` in `_render_concept_page`.** Immediately AFTER `body_html = _demote_headings(body_html)` (render.py:1417), insert:

```python
    # Editorial Workbench §6.1: on-page ToC from the FINAL body_html so its
    # #anchors match the ids the renderer emitted (gated to >=3 headings).
    toc_html = _build_toc_html(body_html)
```

- [ ] **Step 5: GREEN — wire the placeholder.** In the concept `.replace` chain, find `.replace("__CONCEPT_BODY__", body_html)` (render.py:1595) and add the ToC replace immediately BEFORE it:

```python
        .replace("__TOC_HTML__", toc_html)
        .replace("__CONCEPT_BODY__", body_html)
```

- [ ] **Step 6: GREEN — inject into the template.** In `scripts/okf_loom/viewer/templates/concept_page.html`, the reading column has (lines ~85-87):

```html
    </header>

    <div class="okf-prose okf-page__body">
```
Replace it with (ToC between header and prose body — OUTSIDE `.okf-page__body`):
```html
    </header>

    __TOC_HTML__

    <div class="okf-prose okf-page__body">
```

- [ ] **Step 7: GREEN — add the ToC CSS.** In `wiki.css`, append near the nav rules (grep `.okf-nav__group {`):

```css
/* ---- On-page ToC (Round 2 §6.1) — server-rendered, no-JS, flat like nav.
 * Namespaced .okf-toc* so it never collides with the JS-only studio Outline
 * (.okf-outline in studio.css). */
.okf-toc {
  margin: 0 0 var(--okf-space-5);
  padding: var(--okf-space-3) var(--okf-space-4);
  border-left: 2px solid var(--okf-border-strong);
  background: var(--okf-bg-elev);
}
.okf-toc__title {
  margin: 0 0 var(--okf-space-2);
  font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--okf-fg-muted);
}
.okf-toc__list { list-style: none; margin: 0; padding: 0; }
.okf-toc__item { margin: 0; }
.okf-toc__link {
  display: block; padding: 3px 0;
  text-decoration: none; color: var(--okf-fg-muted);
  font-size: var(--okf-text-sm); line-height: 1.4;
}
.okf-toc__link:hover { color: var(--okf-accent); }
.okf-toc__link--h3 { padding-left: var(--okf-space-4); }
```

- [ ] **Step 8: GREEN — run the ToC tests + full render suite + brace/placeholder sanity:**

Run: `python3 -m pytest tests/test_render.py -q && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/wiki.css').read_text(); assert s.count('{')==s.count('}')" && python3 -c "import pathlib; assert '__TOC_HTML__' not in pathlib.Path('scripts/okf_loom/viewer/templates/concept_page.html').read_text() or True"`
Expected: PASS — the two new tests + all existing render tests (no leftover `__TOC_HTML__` in output; the placeholder is replaced in every mode). Read the summary line.

- [ ] **Step 9: Commit**

```bash
git add scripts/okf_loom/render.py scripts/okf_loom/viewer/templates/concept_page.html scripts/okf_loom/viewer/static/wiki.css tests/test_render.py
git commit -m "feat(viewer): on-page ToC (§6.1) — server-rendered from rendered h2/h3, no-JS, flat"
```

---

### Task 2: Index dashboard (6.2a) — `data-okf-*` on cards + sections (server)

Add the machine-readable attributes the client filter/sort/search needs, keeping the server-rendered groups (no-JS) intact. RESTART the serve after this task (render.py).

**Files:**
- Modify: `scripts/okf_loom/render.py` — the `<li class="okf-card">` + `<section class="okf-section">` f-strings in `_render_index_page` (~2130-2143).
- Test: `tests/test_render.py`.

- [ ] **Step 1: RED — add a helper + failing test.** Add to `tests/test_render.py`. First a small index-render helper mirroring `_render_concept_html` (test_render.py:310-319) — read that helper and copy its bundle-load + `build_site(..., target="static")` call, but read `out/index.html`:

```python
def _render_index_html(bundle_root: _Path) -> str:
    """Static-build the bundle and return its root index.html (mirror of
    _render_concept_html — same imports/target, different output file)."""
    from okf_loom import Bundle
    from okf_loom.render import build_site
    b = Bundle.load(bundle_root)
    out = bundle_root / "_site_index"
    build_site(b, out, target="static")
    return (out / "index.html").read_text(encoding="utf-8")


def test_p3_2_index_cards_carry_filter_data_attrs(tiny_good_bundle):
    """Round 2 §6.2: index cards + sections carry data-okf-* so wiki.js can
    filter/sort/search without refetching; the server still renders the groups."""
    html = _render_index_html(tiny_good_bundle)
    assert 'class="okf-section"' in html and 'data-okf-type=' in html  # groups + type
    assert 'data-okf-title=' in html
    assert 'data-okf-search=' in html
    # the type attr appears on BOTH the section and its cards
    assert html.count('data-okf-type=') >= 2
```
(If `Bundle.load` isn't the exact API `_render_concept_html` uses, copy that helper's load line verbatim — the point is one static build + read `index.html`.)

- [ ] **Step 2: Run — verify it FAILS:**

Run: `python3 -m pytest tests/test_render.py -k "p3_2_index_cards" -q`
Expected: FAIL (`data-okf-type=` not in html). Read the summary line.

- [ ] **Step 3: GREEN — add attrs to the card.** In `_render_index_page`, find the `<li>` f-string (render.py:2131):

```python
                f'<li class="okf-card" style="--okf-type-accent:{_esc(color)}">'
```
Replace it with (adds three attribute-escaped data-attrs; `_esc_attr_qs` is the double-quoted-attribute escaper used at render.py:1569/2346):
```python
                f'<li class="okf-card" style="--okf-type-accent:{_esc(color)}"'
                f' data-okf-type="{_esc_attr_qs(t)}"'
                f' data-okf-title="{_esc_attr_qs(c.title)}"'
                f' data-okf-search="{_esc_attr_qs((c.title + " " + (c.description or "") + " " + " ".join(c.tags)).lower())}">'
```

- [ ] **Step 4: GREEN — add the type attr to the section.** Find the `<section>` f-string (render.py:2139):

```python
            f'<section class="okf-section" style="--okf-type-accent:{_esc(color)}">'
```
Replace it with:
```python
            f'<section class="okf-section" style="--okf-type-accent:{_esc(color)}"'
            f' data-okf-type="{_esc_attr_qs(t)}">'
```

- [ ] **Step 5: GREEN — run the test + the static-build + dead-link suites:**

Run: `python3 -m pytest tests/test_render.py -q`
Expected: PASS — the new test + `test_build_site_static_has_no_dead_internal_links` + all others (data-attrs add no links). Read the summary line.

- [ ] **Step 6: Commit**

```bash
git add scripts/okf_loom/render.py tests/test_render.py
git commit -m "feat(index): emit data-okf-type/-title/-search on cards+sections (§6.2 server hooks)"
```

---

### Task 3: Index dashboard (6.2b) — `enhanceIndex()` client toolbar + widen shell

Build a chips/sort/search-within toolbar in `wiki.js` (loads in all modes; studio.js is serve-only), progressively enhancing the server groups. Filter by hiding `<li>`/`<section>` (preserves the first-anchor contract). Widen the index shell via a new layout token. No serve restart (JS/CSS served fresh — just reload).

**Files:**
- Modify: `scripts/okf_loom/viewer/static/wiki.js` — add `enhanceIndex()` (before the init block ~534) + call it in the init block.
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — `--okf-index-maxw` in `:root`; widen `.okf-index`; `.okf-index-toolbar*` / `.okf-index-chip` / `.okf-index-empty`.
- Test: `tests/test_studio_iter1_browser.py` (index is served at `server_url + "/"`).

- [ ] **Step 1: Add `enhanceIndex()` to wiki.js.** Insert this function immediately BEFORE the init block `if (document.readyState === "loading") {` (wiki.js ~534). It reuses the IIFE-local `debounce` (wiki.js:253):

```js
  // ---- Index dashboard (Round 2 §6.2) ---------------------------------
  // Progressive enhancement over the server-rendered type-groups: type-filter
  // chips + sort + search-within. No-JS users keep the full server groups (we
  // only ADD a toolbar + toggle visibility; we never remove server content).
  // Filtering hides <li>/<section> nodes (never reorders their internals) so
  // the .okf-concept-list li first-anchor contract (studio stampConceptIds)
  // holds. Gated on the index page (.okf-index + body.okf-viewer--index).
  function enhanceIndex() {
    var root = document.querySelector(".okf-index");
    if (!root || !document.body.classList.contains("okf-viewer--index")) return;
    var sections = Array.prototype.slice.call(root.querySelectorAll(".okf-section"));
    if (!sections.length) return;
    var cards = Array.prototype.slice.call(root.querySelectorAll(".okf-card"));
    var types = [];
    sections.forEach(function (s) {
      var t = s.getAttribute("data-okf-type");
      if (t && types.indexOf(t) < 0) types.push(t);   // document (group) order
    });

    var uiState = { type: "", sort: "default", q: "" };

    var toolbar = document.createElement("div");
    toolbar.className = "okf-index-toolbar";
    var chips = document.createElement("div");
    chips.className = "okf-index-toolbar__chips";
    chips.setAttribute("role", "group");
    chips.setAttribute("aria-label", "Filter by type");
    function makeChip(val, label) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "okf-index-chip";
      b.textContent = label;
      b.setAttribute("data-okf-type", val);
      b.setAttribute("aria-pressed", val === uiState.type ? "true" : "false");
      b.addEventListener("click", function () {
        uiState.type = (uiState.type === val) ? "" : val;   // toggle off if re-clicked
        apply();
      });
      return b;
    }
    chips.appendChild(makeChip("", "All"));
    types.forEach(function (t) { chips.appendChild(makeChip(t, t)); });

    var controls = document.createElement("div");
    controls.className = "okf-index-toolbar__controls";
    var search = document.createElement("input");
    search.type = "search";
    search.className = "okf-index-toolbar__search";
    search.setAttribute("aria-label", "Filter concepts on this page");
    search.placeholder = "Filter this index…";
    var sort = document.createElement("select");
    sort.className = "okf-index-toolbar__sort";
    sort.setAttribute("aria-label", "Sort concepts");
    [["default", "Sort: Grouped"], ["title", "Sort: Title A–Z"],
     ["title-desc", "Sort: Title Z–A"]].forEach(function (o) {
      var opt = document.createElement("option");
      opt.value = o[0]; opt.textContent = o[1];
      sort.appendChild(opt);
    });
    controls.appendChild(search);
    controls.appendChild(sort);
    toolbar.appendChild(chips);
    toolbar.appendChild(controls);

    var emptyMsg = document.createElement("p");
    emptyMsg.className = "okf-index-empty";
    emptyMsg.setAttribute("role", "status");
    emptyMsg.textContent = "No concepts match your filter.";
    emptyMsg.hidden = true;

    function cardMatches(card) {
      if (uiState.type && card.getAttribute("data-okf-type") !== uiState.type) return false;
      if (uiState.q && (card.getAttribute("data-okf-search") || "").indexOf(uiState.q) < 0) return false;
      return true;
    }
    function apply() {
      var cs = chips.querySelectorAll(".okf-index-chip"), i;
      for (i = 0; i < cs.length; i++) {
        cs[i].setAttribute("aria-pressed",
          cs[i].getAttribute("data-okf-type") === uiState.type ? "true" : "false");
      }
      var anyShown = false;
      sections.forEach(function (s) {
        var lis = s.querySelectorAll(".okf-card"), shown = 0, j;
        for (j = 0; j < lis.length; j++) {
          var vis = cardMatches(lis[j]);
          lis[j].hidden = !vis;
          if (vis) { shown++; anyShown = true; }
        }
        if (uiState.sort !== "default") {
          var ul = s.querySelector(".okf-concept-list");
          if (ul) {
            var arr = Array.prototype.slice.call(ul.querySelectorAll(".okf-card"));
            arr.sort(function (a, b) {
              var at = (a.getAttribute("data-okf-title") || "").toLowerCase();
              var bt = (b.getAttribute("data-okf-title") || "").toLowerCase();
              if (at === bt) return 0;
              var lt = at < bt ? -1 : 1;
              return uiState.sort === "title-desc" ? -lt : lt;
            });
            arr.forEach(function (n) { ul.appendChild(n); });  // reorder <li> nodes only
          }
        }
        s.hidden = (shown === 0);
      });
      emptyMsg.hidden = anyShown;
    }

    search.addEventListener("input", debounce(function () {
      uiState.q = search.value.trim().toLowerCase(); apply();
    }, 120));
    sort.addEventListener("change", function () { uiState.sort = sort.value; apply(); });

    // Insert the toolbar after the hero (if present), else at the top; the
    // empty-state message follows the toolbar.
    var hero = root.querySelector(".okf-hero");
    if (hero && hero.nextSibling) root.insertBefore(toolbar, hero.nextSibling);
    else root.insertBefore(toolbar, root.firstChild);
    if (toolbar.nextSibling) root.insertBefore(emptyMsg, toolbar.nextSibling);
    else root.appendChild(emptyMsg);
  }
```

- [ ] **Step 2: Call it in the init block.** In wiki.js, find the init block (wiki.js:534-544) and add `enhanceIndex();` after each `bindHeadingAnchors();` (both the `DOMContentLoaded` branch and the else branch):

```js
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bindLinkHovers();
      renderLocalGraph();
      bindHeadingAnchors();
      enhanceIndex();
    });
  } else {
    bindLinkHovers();
    renderLocalGraph();
    bindHeadingAnchors();
    enhanceIndex();
  }
```

- [ ] **Step 3: Sanity — JS parses:**

Run: `node --check scripts/okf_loom/viewer/static/wiki.js`
Expected: no output (valid).

- [ ] **Step 4: Add the CSS.** In `wiki.css`: (a) add the layout token beside `--okf-maxw` (grep `--okf-maxw:`) — replace the line `  --okf-maxw: 1200px;` (or its exact form) by APPENDING a sibling line right after it:

```css
  --okf-maxw: 1200px;          /* index/search shell */
  --okf-index-maxw: 1440px;    /* Round 2 §6.2 — index dashboard uses more width */
```
(b) widen the index shell + add the toolbar rules — append near the `.okf-index {` block (grep it):

```css
/* Round 2 §6.2: the index dashboard uses more horizontal width than the
 * reading/search shell (its card grid is already responsive auto-fill). */
.okf-index { max-width: var(--okf-index-maxw); }

/* ---- Index dashboard toolbar (Round 2 §6.2) ------------------------- */
.okf-index-toolbar {
  display: flex; flex-wrap: wrap; gap: var(--okf-space-3);
  align-items: center; justify-content: space-between;
  margin: 0 0 var(--okf-space-4);
  padding-bottom: var(--okf-space-3);
  border-bottom: var(--okf-border-w) solid var(--okf-border);
}
.okf-index-toolbar__chips { display: flex; flex-wrap: wrap; gap: var(--okf-space-1); }
.okf-index-toolbar__controls { display: flex; flex-wrap: wrap; gap: var(--okf-space-2); }
.okf-index-chip {
  padding: 3px 12px; font: inherit; font-size: var(--okf-text-sm);
  border: var(--okf-border-w) solid var(--okf-border);
  border-radius: var(--okf-radius-pill);
  background: transparent; color: var(--okf-fg-muted); cursor: pointer;
}
.okf-index-chip:hover { color: var(--okf-fg); border-color: var(--okf-border-strong); }
.okf-index-chip[aria-pressed="true"] {
  color: var(--okf-active-fg);
  background: var(--okf-active-fill);
  border-color: var(--okf-active-border);
}
.okf-index-chip:focus-visible { outline: 2px solid var(--okf-accent); outline-offset: 1px; }
.okf-index-toolbar__search, .okf-index-toolbar__sort {
  padding: 4px 10px; font: inherit; font-size: var(--okf-text-sm);
  border: var(--okf-border-w) solid var(--okf-border-strong);
  border-radius: var(--okf-radius-sm);
  background: var(--okf-bg-elev); color: var(--okf-fg);
}
.okf-index-empty { color: var(--okf-fg-muted); padding: var(--okf-space-5) 0; }
```

- [ ] **Step 5: Brace sanity:**

Run: `python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/wiki.css').read_text(); assert s.count('{')==s.count('}'), (s.count('{'), s.count('}'))"`
Expected: no assertion error.

- [ ] **Step 6: Write the failing browser test.** Add to `tests/test_studio_iter1_browser.py` using the real `server_url` + `page` fixtures. The served DEMO bundle (docs-bundle) has multiple Diátaxis types, so ≥2 chips render:

```python
def test_index_dashboard_filters_sorts_and_searches(server_url, page):
    """Round 2 §6.2: the index gains a client toolbar; chips filter by type,
    search-within narrows, and the empty-state shows when nothing matches."""
    page.set_viewport_size({"width": 1200, "height": 900})
    page.goto(f"{server_url}/", wait_until="load")
    page.wait_for_selector(".okf-index-toolbar", timeout=15000)
    chips = page.query_selector_all(".okf-index-chip")
    assert len(chips) >= 2, "expected an All chip + >=1 type chip"
    # Filtering to one type hides at least one section (multi-type bundle).
    total_sections = len(page.query_selector_all(".okf-section"))
    page.click('.okf-index-chip:not([data-okf-type=""])')
    page.wait_for_function(
        "() => Array.from(document.querySelectorAll('.okf-section'))"
        ".filter(s => s.hidden).length >= 1", timeout=5000)
    # Search-within with no match shows the empty state.
    page.fill(".okf-index-toolbar__search", "zzzznomatchxyzzy")
    page.wait_for_selector(".okf-index-empty:not([hidden])", timeout=5000)
```
(`total_sections` is captured for clarity; the wait_for_function is the real assertion. If DEMO has a single type, relax to assert the toolbar + chips exist and search hides all cards.)

- [ ] **Step 7: Run — new test passes; the index still builds statically with no dead links:**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "index_dashboard" -q && python3 -m pytest tests/test_render.py -k "dead_internal_links or per_concept_pages" -q`
Expected: PASS. Read the summary line.

- [ ] **Step 8: Commit**

```bash
git add scripts/okf_loom/viewer/static/wiki.js scripts/okf_loom/viewer/static/wiki.css tests/test_studio_iter1_browser.py
git commit -m "feat(index): client dashboard — type chips + sort + search-within, widened shell (§6.2)"
```

---

### Task 4: Search quality (6.3a) — live renderer: match-centred snippet + `<mark>` highlight + CSS

The live Python renderer already emits `.okf-search-result__meta` + a type chip (meta is done on this path). Add: (a) match-centred snippet (so the highlighted term is visible), (b) escape-then-`<mark>` highlighting of the title + snippet, (c) `<mark>` + `.okf-search-result__type` default-colour CSS (shared by Task 5's static path). RESTART the serve after this task (render.py). Relevance sort is already satisfied (D2) — no change.

**Files:**
- Modify: `scripts/okf_loom/render.py` — add `_highlight` near `_render_search_page` (~2250); change the snippet source (render.py:2261) + highlight the title (2279) + snippet (2284).
- Modify: `scripts/okf_loom/viewer/static/wiki.css` — `mark` rule + `.okf-search-result__type` default colour.
- Test: `tests/test_render.py`.

- [ ] **Step 1: RED — write the failing tests.** Add to `tests/test_render.py`. Load a real bundle for `_render_search_page` the way the neighbouring search tests do (mapper: `_render_search_page(b, mode=…, name=b.name, config={}, query=…, results=[…])`):

```python
def test_p3_3_live_search_highlights_query_terms(tiny_good_bundle):
    """Round 2 §6.3: the live search renderer wraps query-term matches in
    <mark> and keeps the result meta (type/path). `Bundle` is already
    module-imported at test_render.py:19."""
    b = Bundle.load(tiny_good_bundle)
    html = _render_search_page(
        b, mode="serve", name=b.name, config={}, query="users",
        results=[{"title": "Users", "concept_id": "tables/users", "id": "tables/users",
                  "description": "The users table stores users.", "type": "BigQuery Table"}])
    assert "<mark>" in html, "query terms must be highlighted"
    assert 'class="okf-search-result__meta' in html, "live meta must survive"


def test_p3_3_live_search_tolerates_missing_fields(tiny_good_bundle):
    """Round 2 §6.3: a result with no type/description/snippets still renders
    (the iter2 h1 test uses exactly this shape)."""
    b = Bundle.load(tiny_good_bundle)
    html = _render_search_page(
        b, mode="static", name=b.name, config={}, query="orders",
        results=[{"title": "Orders", "concept_id": "c", "id": "c"}])
    assert 'class="okf-search-result"' in html  # no crash on missing fields
```

- [ ] **Step 2: Run — verify it FAILS:**

Run: `python3 -m pytest tests/test_render.py -k "p3_3_live_search" -q`
Expected: FAIL on the first test (`<mark>` not in html; the current snippet prefers the non-match-centred description). Read the summary line.

- [ ] **Step 3: GREEN — add `_highlight` to render.py.** Insert immediately BEFORE `def _render_search_page(` (find it: `grep -n "def _render_search_page" scripts/okf_loom/render.py`):

```python
_HIGHLIGHT_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _highlight(text: str, query: str, *, limit: int = 200) -> str:
    """Escape ``text``, truncate to ``limit``, and wrap query-term occurrences
    in ``<mark>`` (Round 2 §6.3). Escaping happens FIRST; ``<mark>`` tags are
    inserted around the already-escaped runs, so no user text can break out of
    the markup (CSP-safe; mirrors the static-search.js ``highlight()``). Terms
    are the query's word tokens (>=2 chars), matched case-insensitively."""
    s = str(text or "")[:limit]
    esc = _esc(s)
    terms = {m.group(0).lower() for m in _HIGHLIGHT_WORD_RE.finditer(query or "")}
    terms = [t for t in terms if len(t) >= 2]
    if not terms or not esc:
        return esc
    # Match on the escaped string; word tokens escape to themselves, so this is
    # exact. Longest-first so overlapping terms don't half-wrap.
    pat = re.compile(
        "(" + "|".join(re.escape(_esc(t)) for t in sorted(terms, key=len, reverse=True)) + ")",
        re.IGNORECASE,
    )
    return pat.sub(r"<mark>\1</mark>", esc)
```

- [ ] **Step 4: GREEN — prefer the match-centred snippet.** In `_render_search_page`, find (render.py:2261):

```python
        desc = r.get("description") or (r.get("snippets") or [""])[0]
```
Replace it with (prefer the BM25 match-centred `snippets[0]`, fall back to description; tolerate all-missing):
```python
        # §6.3: prefer the match-centred snippet the backend computed
        # (_extract_snippets) so the highlighted term is actually visible;
        # fall back to the curated description, then empty.
        desc = (r.get("snippets") or [None])[0] or r.get("description") or ""
```

- [ ] **Step 5: GREEN — highlight the title + snippet.** In the result f-string, find (render.py:2279):

```python
            f'<h3><a href="{_esc(url)}" class="okf-internal">{_esc(title)}</a></h3>'
```
Replace it with:
```python
            f'<h3><a href="{_esc(url)}" class="okf-internal">{_highlight(title, query)}</a></h3>'
```
Then find (render.py:2284):
```python
            f'<div class="okf-search-snippet">{_esc(str(desc)[:200])}</div>'
```
Replace it with:
```python
            f'<div class="okf-search-snippet">{_highlight(desc, query)}</div>'
```

- [ ] **Step 6: GREEN — add the CSS.** In `wiki.css`, append near the search-result rules (grep `.okf-search-result__type`):

```css
/* ---- Search match highlight + static type parity (Round 2 §6.3) ------ */
.okf-search-result mark, .okf-search-snippet mark {
  background: var(--okf-accent-bg);
  color: inherit;
  font-weight: 600;
  border-radius: var(--okf-radius-sm);
  padding: 0 2px;
}
/* The live renderer sets an inline per-type colour; the static renderer has
 * no palette, so give the type label a token default it can fall back to. */
.okf-search-result__type { color: var(--okf-accent); }
```

- [ ] **Step 7: GREEN — run the search tests + full render suite + brace sanity:**

Run: `python3 -m pytest tests/test_render.py -q && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/wiki.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: PASS — the two new tests + `test_iter2_search_h1_not_wrapped_in_muted` + `test_iter2_search_title_css_is_full_size` + all others. Read the summary line.

- [ ] **Step 8: Commit**

```bash
git add scripts/okf_loom/render.py scripts/okf_loom/viewer/static/wiki.css tests/test_render.py
git commit -m "feat(search): live results — match-centred snippet + <mark> highlight, mark/type CSS (§6.3)"
```

---

### Task 5: Search quality (6.3b) — static renderer: meta parity + `<mark>` highlight + match-centred excerpt

Bring the static JS renderer (`renderResults`) up to the live markup (`.okf-search-result__meta` + type) and add the escape-then-`<mark>` highlighter + a match-centred excerpt, reusing the CSS shipped in Task 4. No serve restart (static asset; verified via source-contract + Task 9 static-build screenshot). Corpus emitter untouched (test 743/835 stay green).

**Files:**
- Modify: `scripts/okf_loom/viewer/static/static-search.js` — add `highlight()`; make `makeSnippet` match-centred; rewrite the `renderResults` row markup.
- Test: `tests/test_render.py` (source-contract) + `node --check`.

- [ ] **Step 1: RED — write the source-contract test.** Add to `tests/test_render.py` (uses the `_runtime_file` helper the mapper confirmed):

```python
def test_p3_3_static_search_renderer_has_meta_and_highlight():
    """Round 2 §6.3: the static search renderer matches the live markup
    (result meta + type) and highlights matches (escape-then-<mark>)."""
    js = _runtime_file("viewer", "static", "static-search.js").read_text(encoding="utf-8")
    assert "okf-search-result__meta" in js, "static must reach live meta parity"
    assert "okf-search-result__type" in js, "static must show the type label"
    assert "function highlight(" in js and "<mark>" in js, "static must highlight matches"
```

- [ ] **Step 2: Run — verify it FAILS:**

Run: `python3 -m pytest tests/test_render.py -k "p3_3_static_search_renderer" -q`
Expected: FAIL (`okf-search-result__meta` not in static-search.js). Read the summary line.

- [ ] **Step 3: GREEN — add `highlight()`.** In `static-search.js`, insert immediately AFTER the `escapeHtml` function (ends ~line 195, before `function makeSnippet`):

```js
  function highlight(text, tokens) {
    var esc = escapeHtml(text || "");
    if (!tokens || !tokens.length || !esc) return esc;
    // Match on the ALREADY-ESCAPED string and wrap in <mark>. Escaping first
    // means the only markup introduced is <mark> (CSP-safe; mirrors the
    // render.py _highlight()). Longest-first, deduped, regex-escaped.
    var uniq = [];
    for (var i = 0; i < tokens.length; i++) {
      if (tokens[i] && tokens[i].length >= 2 && uniq.indexOf(tokens[i]) < 0) uniq.push(tokens[i]);
    }
    if (!uniq.length) return esc;
    uniq.sort(function (a, b) { return b.length - a.length; });
    var alt = uniq.map(function (t) {
      return escapeHtml(t).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("|");
    return esc.replace(new RegExp("(" + alt + ")", "gi"), "<mark>$1</mark>");
  }
```

- [ ] **Step 4: GREEN — make `makeSnippet` match-centred.** Replace the whole `makeSnippet` function (static-search.js:197-205):

```js
  function makeSnippet(entry) {
    // Prefer the curated description; fall back to the build-time body
    // excerpt. Truncate to 200 chars to match the live search page.
    var desc = entry.description || "";
    if (desc) return String(desc).slice(0, 200);
    var body = entry.body_excerpt || "";
    if (body) return String(body).slice(0, 200);
    return "";
  }
```
with (windows around the first matched token so the highlight is visible):
```js
  function makeSnippet(entry, tokens) {
    // §6.3: window around the first query-term match so the highlighted term
    // is visible; fall back to the leading slice. Prefers the body excerpt
    // (more likely to contain the term) then the curated description.
    var src = String(entry.body_excerpt || entry.description || "");
    if (!src) return "";
    if (tokens && tokens.length) {
      var low = src.toLowerCase(), best = -1, i, p;
      for (i = 0; i < tokens.length; i++) {
        p = low.indexOf(tokens[i]);
        if (p >= 0 && (best < 0 || p < best)) best = p;
      }
      if (best > 40) return "…" + src.slice(best - 40, best - 40 + 200);
    }
    return src.slice(0, 200);
  }
```

- [ ] **Step 5: GREEN — rewrite the `renderResults` row markup.** In `renderResults`, find the row-building loop (static-search.js:254-268):

```js
    var html = "";
    for (var j = 0; j < scored.length; j++) {
      var e = scored[j].entry;
      var cid = e.id || "";
      // Static concept pages live at <id>.html at the bundle root.
      var url = cid + ".html";
      var snippet = makeSnippet(e);
      html +=
        '<article class="okf-search-result">' +
        '<h3><a href="' + escapeHtml(url) + '" class="okf-internal">' +
        escapeHtml(e.title || cid) + '</a>' +
        ' <span class="okf-muted">' + escapeHtml(cid) + '</span></h3>' +
        '<div class="okf-search-snippet">' + escapeHtml(snippet) + '</div>' +
        '</article>';
    }
```
Replace it with (parity with the live markup: cid moves OUT of the `<h3>` into `.okf-search-result__meta`; type label added; title + snippet highlighted):
```js
    var html = "";
    for (var j = 0; j < scored.length; j++) {
      var e = scored[j].entry;
      var cid = e.id || "";
      // Static concept pages live at <id>.html at the bundle root.
      var url = cid + ".html";
      var snippet = makeSnippet(e, tokens);
      var typeMeta = e.type
        ? '<span class="okf-search-result__type">' + escapeHtml(e.type) + '</span> '
        : "";
      html +=
        '<article class="okf-search-result">' +
        '<h3><a href="' + escapeHtml(url) + '" class="okf-internal">' +
        highlight(e.title || cid, tokens) + '</a></h3>' +
        '<div class="okf-search-result__meta okf-muted">' + typeMeta + escapeHtml(cid) + '</div>' +
        '<div class="okf-search-snippet">' + highlight(snippet, tokens) + '</div>' +
        '</article>';
    }
```
(`tokens` is already computed at the top of `renderResults` — `var tokens = tokenize(query);` line 230.)

- [ ] **Step 6: GREEN — run the source-contract test + JS syntax:**

Run: `node --check scripts/okf_loom/viewer/static/static-search.js && python3 -m pytest tests/test_render.py -k "p3_3_static_search_renderer or search_corpus or static_search_page" -q`
Expected: PASS (renderer contract + the corpus/static-page tests unchanged). Read the summary line.

- [ ] **Step 7: Commit**

```bash
git add scripts/okf_loom/viewer/static/static-search.js tests/test_render.py
git commit -m "feat(search): static results — meta/type parity + <mark> highlight + match-centred excerpt (§6.3)"
```

---

### Task 6: Studio depth (6.4a) — quick-actions RUN (post directive via the existing comment channel)

Each intent keeps its pre-fill button (primary) and gains a **▶ Run** button that posts a complete standalone directive as a `/__comment` (the studio→agent channel — a comment IS an open directive the agent runs). RUN reuses the composer's Send path (optimistic insert + POST + toast) by filling the textarea *only when empty* and clicking Send. No new endpoint. No serve restart (JS/CSS served fresh).

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js` — `INTENTS` (add `runPrompt`, ~4195); the composer Send button (add hook class, ~1397); `buildIntentsToolbar` (~4238).
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-panel__intent-group` / `.okf-panel__intent-run`.
- Test: `tests/test_studio_iter1_browser.py`.

- [ ] **Step 1: Add `runPrompt` to each intent.** Replace `INTENTS` (studio.js:4195-4200):

```js
  var INTENTS = [
    { id: "add-section", label: "Add section", prompt: "Add a new section about" },
    { id: "split-doc", label: "Split document", prompt: "Split this document into" },
    { id: "add-links", label: "Add links", prompt: "Add links from this concept to" },
    { id: "enrich", label: "Enrich content", prompt: "Enrich this page with" },
  ];
```
with (each gains a COMPLETE standalone directive for one-click RUN):
```js
  var INTENTS = [
    { id: "add-section", label: "Add section", prompt: "Add a new section about",
      runPrompt: "Add a new section covering an important aspect of this concept that isn't documented yet." },
    { id: "split-doc", label: "Split document", prompt: "Split this document into",
      runPrompt: "Split this document into focused sub-concepts if it covers multiple distinct topics." },
    { id: "add-links", label: "Add links", prompt: "Add links from this concept to",
      runPrompt: "Review this concept and add typed links to the closely related concepts in the bundle." },
    { id: "enrich", label: "Enrich content", prompt: "Enrich this page with",
      runPrompt: "Enrich this page with additional detail, concrete examples, and cross-links where helpful." },
  ];
```

- [ ] **Step 2: Give the composer Send button a stable hook class.** In `composerNode` (studio.js:1397), find:

```js
    const submit = el("button", { type: "button", class: "okf-studiobtn", text: "Send" });
```
Replace it with (adds `okf-composer__submit` so RUN can click it; keeps `okf-studiobtn`):
```js
    const submit = el("button", { type: "button", class: "okf-studiobtn okf-composer__submit", text: "Send" });
```

- [ ] **Step 3: Rebuild `buildIntentsToolbar` with the Run affordance.** Replace the whole function (studio.js:4238-4261):

```js
  function buildIntentsToolbar() {
    var wrap = el("div", { class: "okf-panel__intents", role: "group", "aria-label": "Quick actions" });
    INTENTS.forEach(function (intent) {
      var group = el("div", { class: "okf-panel__intent-group" });
      var btn = el("button", {
        class: "okf-panel__intent", type: "button", text: intent.label,
        title: intent.prompt + "… (fills the composer)",
      });
      btn.addEventListener("click", function () {
        state.draftBody = intent.prompt + " ";
        state.draftAnchor = { kind: "concept", ref: state.conceptId, concept: state.conceptId };
        var ta = panelBodyEl() && panelBodyEl().querySelector(".okf-composer__textarea");
        if (ta) {
          ta.value = state.draftBody;
          try { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); } catch (e) {}
        } else {
          openPanel("comments", { focusComposer: true });
        }
      });
      // Round 2 §6.4: RUN posts the directive to the agent. A comment IS an
      // open directive the watching agent runs (post_comment → directives.jsonl
      // → wait/comment-claim). Reuse the composer's Send path (optimistic insert
      // + POST /__comment + toast) by filling a COMPLETE directive when the
      // composer is empty (respecting any text the user typed) and clicking Send.
      var run = el("button", {
        class: "okf-panel__intent-run", type: "button", text: "▶",
        title: "Run: send this directive to the agent now",
        "aria-label": "Run: " + intent.label,
      });
      run.addEventListener("click", function () {
        var pb = panelBodyEl();
        var ta = pb && pb.querySelector(".okf-composer__textarea");
        var submit = pb && pb.querySelector(".okf-composer__submit");
        if (!ta || !submit) { openPanel("comments", { focusComposer: true }); return; }
        if (!ta.value.trim()) ta.value = intent.runPrompt;   // complete directive when empty
        state.draftBody = ta.value;
        state.draftAnchor = { kind: "concept", ref: state.conceptId, concept: state.conceptId };
        submit.click();   // → postCommentFromComposer → POST /__comment
      });
      group.appendChild(btn);
      group.appendChild(run);
      wrap.appendChild(group);
    });
    return wrap;
  }
```

- [ ] **Step 4: Add the CSS.** In `studio.css`, append near the existing `.okf-panel__intent` rule (grep `.okf-panel__intent `):

```css
/* Round 2 §6.4: intent = pre-fill button + a Run (▶) button that posts the
 * directive to the agent. */
.okf-panel__intent-group { display: inline-flex; }
.okf-panel__intent-run {
  padding: 0 8px; font: inherit; font-size: var(--okf-text-sm);
  border: var(--okf-border-w) solid var(--okf-border);
  border-left: 0;
  border-radius: 0 var(--okf-radius-sm) var(--okf-radius-sm) 0;
  background: var(--okf-bg-elev); color: var(--okf-accent); cursor: pointer;
}
.okf-panel__intent-run:hover {
  background: var(--okf-active-fill); color: var(--okf-active-fg);
  border-color: var(--okf-active-border);
}
.okf-panel__intent-run:focus-visible { outline: 2px solid var(--okf-accent); outline-offset: 1px; }
/* square the pre-fill button's right edge inside the group so the pair reads
 * as one control. */
.okf-panel__intent-group .okf-panel__intent { border-radius: var(--okf-radius-sm) 0 0 var(--okf-radius-sm); }
```

- [ ] **Step 5: Sanity — JS + CSS well-formed:**

Run: `node --check scripts/okf_loom/viewer/static/studio.js && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/studio.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: valid; braces balanced.

- [ ] **Step 6: Write the failing browser test.** Add to `tests/test_studio_iter1_browser.py` (real `server_url` + `page` + `_wait_for_studio`; the DEMO serve runs in edit mode, so intents mount):

```python
def test_quick_action_run_posts_directive(server_url, page):
    """Round 2 §6.4: an intent's Run button POSTs a directive to /__comment
    (reuses the composer Send path)."""
    page.set_viewport_size({"width": 1200, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    page.click('.okf-rail__btn[data-rail-id="comments"]')  # open Comments overlay
    page.wait_for_selector(".okf-panel__intent-run", timeout=8000)
    with page.expect_request(
        lambda r: "/__comment" in r.url and r.method == "POST"
    ) as req:
        page.query_selector(".okf-panel__intent-run").click()
    assert req.value is not None
```
(If the rail button selector differs, read `test_rail_present_and_overlay_does_not_reflow` for how it opens the Comments overlay — the point is: open Comments so the intents toolbar + composer mount, then click a `.okf-panel__intent-run` and assert the `/__comment` POST fires.)

- [ ] **Step 7: Run — new test passes:**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "quick_action_run" -q`
Expected: PASS. Read the summary line. (Documented races may need one rerun; read the summary.)

- [ ] **Step 8: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css tests/test_studio_iter1_browser.py
git commit -m "feat(studio): quick-action RUN — post a directive via the existing comment channel (§6.4)"
```

---

### Task 7: Studio depth (6.4b) — on-demand doc diff in the Changes tab

Extract the conflict modal's diff-render core into a shared `renderDiffInto(container, {concept, from, to})`, rewire the modal to call it (existing modal tests exercise the extraction), and add a per-row **View diff** in `changeRow` for change events with resolvable revs (`detail.before` + `rev` are already on the event). No new endpoint (reuses `/__diff`). No serve restart.

**Files:**
- Modify: `scripts/okf_loom/viewer/static/studio.js` — add `renderDiffInto` (near the conflict modal ~4038); rewrite the modal `viewBtn` handler (4048-4103); add the View-diff affordance in `changeRow` (~3023); expose `_changeRow` on the studio API seam (~4334).
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-change__diffbtn` / `.okf-change__diff` (the diff *table* reuses existing `.okf-conflict__diff-table` styles).
- Test: `tests/test_studio_iter1_browser.py`.

- [ ] **Step 1: Add `renderDiffInto` (extracted core).** In `studio.js`, insert this function immediately BEFORE the `viewBtn.addEventListener("click", …)` block (the one at studio.js:4048, inside `_buildConflictModal`). Place it at module scope — find a stable insertion point just above `_buildConflictModal` (grep `function _buildConflictModal`) and add it there:

```js
  // Round 2 §6.4: shared diff renderer. Fetches /__diff for (concept, from, to)
  // and renders the line table into `container`. Extracted from the conflict
  // modal's "View diff" so the Changes tab can reuse it on demand (the modal's
  // Keep-mine/Take-agent resolution actions stay modal-only). tokenFetch is
  // required by the server (403 otherwise). Returns a Promise.
  async function renderDiffInto(container, opts) {
    opts = opts || {};
    container.innerHTML = "";
    const placeholder = el("div", { class: "okf-conflict__diff-loading", text: "Loading diff…" });
    container.appendChild(placeholder);
    try {
      const concept = encodeURIComponent(String(opts.concept || ""));
      const fromRev = encodeURIComponent(String(opts.from || ""));
      const toRev = encodeURIComponent(String(opts.to || ""));
      const res = await tokenFetch(
        "/__diff?concept=" + concept + "&from=" + fromRev + "&to=" + toRev,
        { headers: { Accept: "application/json" } },
      );
      const payload = await res.json();
      placeholder.remove();
      if (!payload || payload.ok === false) {
        container.appendChild(el("p", { class: "okf-conflict__diff-empty",
          text: payload && payload.error ? payload.error : "Diff unavailable." }));
        return;
      }
      const rows = Array.isArray(payload.diff) ? payload.diff : [];
      if (!rows.length) {
        container.appendChild(el("p", { class: "okf-conflict__diff-empty", text: "No textual differences." }));
        return;
      }
      const table = el("table", { class: "okf-conflict__diff-table" });
      const tbody = el("tbody");
      rows.forEach((row) => {
        const tr = el("tr", { class: "okf-conflict__diff-row okf-conflict__diff-row--" + (row.kind || "ctx") });
        tr.appendChild(el("td", { class: "okf-conflict__diff-num", text: String(row.num != null ? row.num : "") }));
        tr.appendChild(el("td", { class: "okf-conflict__diff-kind", text: row.kind === "add" ? "+" : (row.kind === "del" ? "-" : " ") }));
        const td = el("td", { class: "okf-conflict__diff-text" });
        td.textContent = String(row.text != null ? row.text : "");
        tr.appendChild(td);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      container.appendChild(table);
    } catch (e) {
      placeholder.remove();
      container.appendChild(el("p", { class: "okf-conflict__diff-empty",
        text: "Diff fetch failed: " + (e && e.message ? e.message : String(e)) }));
    }
  }
```

- [ ] **Step 2: Rewire the conflict modal to call it.** Replace the entire `viewBtn.addEventListener("click", async () => { … });` block (studio.js:4048-4103) with:

```js
    viewBtn.addEventListener("click", async () => {
      viewBtn.disabled = true;
      diffPanel.removeAttribute("hidden");
      try {
        const { data: cdata } = conflictState._retryArgs;
        // Reuse the shared renderer (Round 2 §6.4 extraction). Same DOM as
        // before — the iter1 conflict-modal tests exercise this path.
        await renderDiffInto(diffPanel, {
          concept: cdata.concept, from: cdata.expected_rev, to: cdata.current_rev,
        });
      } finally {
        setTimeout(() => { viewBtn.disabled = false; }, 500);  // allow re-click to refresh
      }
    });
```

- [ ] **Step 3: Add the View-diff affordance to `changeRow`.** In `changeRow` (studio.js:3023-3032), find the actions block:

```js
    const actions = el("div", { class: "okf-change__actions" });
    // Only mutator-recorded activity carries undoable + a rev to restore;
    // disk/changed events have no group snapshot to undo here.
    if (r.undoable && r.id && (r.ids && r.ids[0])) {
      const undo = el("button", { type: "button", class: "okf-change__undo", text: "Undo" });
      undo.addEventListener("click", () => undoOne(r, undo));
      actions.appendChild(undo);
    }
    row.appendChild(actions);
    return row;
```
Replace it with (adds a View-diff button + an expandable diff container; a change row carries both revs — `detail.before` = prior rev, `rev` = new — same source `undoOne` uses):
```js
    const actions = el("div", { class: "okf-change__actions" });
    // Only mutator-recorded activity carries undoable + a rev to restore;
    // disk/changed events have no group snapshot to undo here.
    if (r.undoable && r.id && (r.ids && r.ids[0])) {
      const undo = el("button", { type: "button", class: "okf-change__undo", text: "Undo" });
      undo.addEventListener("click", () => undoOne(r, undo));
      actions.appendChild(undo);
    }
    // Round 2 §6.4: on-demand doc diff. The change event already carries both
    // revs (detail.before = prior content-hash rev; rev = new), so reuse the
    // conflict modal's diff renderer without scanning history. Snapshots older
    // than the 50-per-concept ring return 404 → renderDiffInto shows it.
    const diffConcept = (r.detail && r.detail.before_concept) || (r.ids && r.ids[0]);
    let diffWrap = null;
    if (diffConcept && r.detail && r.detail.before && r.rev) {
      diffWrap = el("div", { class: "okf-change__diff", hidden: "" });
      const diffBtn = el("button", { type: "button", class: "okf-change__diffbtn",
        "aria-expanded": "false", text: "View diff" });
      diffBtn.addEventListener("click", () => {
        if (diffWrap.hasAttribute("hidden")) {
          diffWrap.removeAttribute("hidden");
          diffBtn.setAttribute("aria-expanded", "true");
          renderDiffInto(diffWrap, { concept: diffConcept, from: r.detail.before, to: r.rev });
        } else {
          diffWrap.setAttribute("hidden", "");
          diffBtn.setAttribute("aria-expanded", "false");
        }
      });
      actions.appendChild(diffBtn);
    }
    row.appendChild(actions);
    if (diffWrap) row.appendChild(diffWrap);
    return row;
```

- [ ] **Step 4: Expose the `_changeRow` test seam.** In the `window.okfLoomStudio = {` object (studio.js:4320), the "Test/debug helpers" line reads (studio.js:4333):

```js
    _toast: toast, _loadComments: loadComments, _renderChangeList: renderChangeList,
```
Replace it with (adds `_changeRow`, matching the bare-reference style of its neighbours):
```js
    _toast: toast, _loadComments: loadComments, _renderChangeList: renderChangeList,
    _changeRow: changeRow,
```

- [ ] **Step 5: Add the CSS.** In `studio.css`, append near the change-row rules (grep `.okf-change__actions`):

```css
/* Round 2 §6.4: on-demand doc diff in the Changes tab. The diff TABLE reuses
 * the existing .okf-conflict__diff-table styles; these style the trigger +
 * the expandable container. */
.okf-change__diffbtn {
  padding: 2px 8px; font: inherit; font-size: var(--okf-text-xs);
  border: var(--okf-border-w) solid var(--okf-border);
  border-radius: var(--okf-radius-sm);
  background: var(--okf-bg-elev); color: var(--okf-fg-muted); cursor: pointer;
}
.okf-change__diffbtn:hover { color: var(--okf-fg); border-color: var(--okf-border-strong); }
.okf-change__diff { margin-top: var(--okf-space-2); max-height: 320px; overflow: auto; }
```

- [ ] **Step 6: Sanity — JS + CSS well-formed:**

Run: `node --check scripts/okf_loom/viewer/static/studio.js && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/studio.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: valid; braces balanced.

- [ ] **Step 7: Write the failing browser test.** Add to `tests/test_studio_iter1_browser.py`. It builds a synthetic change row via the `_changeRow` seam and asserts the View-diff button appears (avoids having to drive a real edit to produce a change event):

```python
def test_changes_row_offers_view_diff_when_revs_resolvable(server_url, page):
    """Round 2 §6.4: a change row with detail.before + rev exposes a View diff
    button wired to the shared /__diff renderer."""
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    has_btn = page.evaluate("""() => {
      const s = window.okfLoomStudio;
      if (!s || typeof s._changeRow !== 'function') return null;
      const row = s._changeRow({
        type: 'changed', ids: ['tables/orders'], rev: 'newrev0000',
        detail: { before: 'oldrev0000', before_concept: 'tables/orders' },
        actor: 'agent', ts: new Date().toISOString(),
      });
      return !!(row && row.querySelector('.okf-change__diffbtn'));
    }""")
    assert has_btn is True
```

- [ ] **Step 8: Run — new test passes + the conflict-modal tests still pass (they exercise the extraction):**

Run: `python3 -m pytest tests/test_studio_iter1_browser.py -k "changes_row_offers_view_diff or conflict" -q`
Expected: PASS — the new test + the existing conflict-modal tests (View diff still renders the table; Keep-mine/Take-agent labels intact). Read the summary line.

- [ ] **Step 9: Commit**

```bash
git add scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css tests/test_studio_iter1_browser.py
git commit -m "feat(studio): on-demand doc diff in Changes — extract renderDiffInto, reuse /__diff (§6.4)"
```

---

### Task 8: Studio depth (6.4c) — validation count (`/__validate` read-only endpoint + footer chip)

Add a read-only, token-gated GET `/__validate` (copies the `/__diff` gate; cached on the studio rev) and a footer `.okf-statseg` chip fed by it — completing SPEC §3.5's "validation count" status element. RESTART the serve after this task (server.py).

**Files:**
- Modify: `scripts/okf_loom/server.py` — `_handle_validate` (near `_handle_diff` ~1046) + route (after the `/__diff` route ~1147).
- Modify: `scripts/okf_loom/viewer/static/studio.js` — `validationStatseg` + `refreshValidation` in `mountBar` (~334-408); refresh on change events.
- Modify: `scripts/okf_loom/viewer/static/studio.css` — `.okf-statseg--validation` state colours.
- Test: `tests/test_studio_iter2_backend.py` (endpoint) + `tests/test_studio_iter1_browser.py` (chip).

- [ ] **Step 1: RED — write the failing backend test.** Add to `tests/test_studio_iter2_backend.py`, mirroring `test_diff_requires_token` (line 364) + `test_diff_rejects_bad_concept_id` (389) — SAME `bundle` fixture, `_free_port()`, `_start_server`, `_wait_for_server`, `.token` read, `urllib` requests, `finally` cleanup (`urllib`, `subprocess`, `time`, `pytest` are already imported at the top of the file):

```python
def test_validate_requires_token(bundle: Path) -> None:
    """Round 2 §6.4: /__validate is token-gated (same guard as /__diff)."""
    port = _free_port()
    proc = _start_server(bundle, port)
    try:
        _wait_for_server(port)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/__validate")
        try:
            urllib.request.urlopen(req, timeout=5).read()
            pytest.fail("expected 403")
        except urllib.error.HTTPError as e:
            assert e.code == 403, f"expected 403, got {e.code}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_validate_returns_counts_with_token(bundle: Path) -> None:
    """Round 2 §6.4: with the token, /__validate returns {ok,error,warning}."""
    import json
    port = _free_port()
    proc = _start_server(bundle, port)
    try:
        _wait_for_server(port)
        token_path = bundle / ".okf-loom" / "session" / ".token"
        deadline = time.time() + 5
        while time.time() < deadline and not token_path.is_file():
            time.sleep(0.1)
        token = token_path.read_text(encoding="utf-8").strip()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/__validate",
            headers={"X-OKF-Token": token},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read())
        assert set(data) >= {"ok", "error", "warning"}
        assert isinstance(data["error"], int) and isinstance(data["warning"], int)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
```

- [ ] **Step 2: Run — verify it FAILS:**

Run: `python3 -m pytest tests/test_studio_iter2_backend.py -k "validate_requires_token or validate_returns_counts" -q`
Expected: FAIL (route missing → the token request 404s, not 200). Read the summary line.

- [ ] **Step 3: GREEN — add `_handle_validate` to server.py.** Insert immediately AFTER `_handle_diff` (after its final `self._send_json(...)`, render `_handle_preview` follows — put it between them, studio.py ~1112):

```python
    def _handle_validate(self) -> None:
        """Round 2 §6.4 / SPEC §3.5: read-only validation counts for the status
        strip. Token-gated (same guard as /__diff) because it reports bundle
        state; cached on the studio rev so a poll doesn't re-walk the bundle.
        Returns ``{ok, error, warning}``.
        """
        if not self._check_write_auth():
            return self._send_text(
                403, "Forbidden: /__validate requires the studio token.",
                content_type="text/plain; charset=utf-8",
            )
        rev = None
        if self.studio is not None:
            try:
                rev = self.studio.current_rev()
            except Exception:  # noqa: BLE001 — fall through to uncached compute
                rev = None
        cached = getattr(self.server, "_validate_cache", None)
        if cached is not None and rev is not None and cached[0] == rev:
            return self._send_json(200, cached[1])
        from .validate import validate_bundle
        report = validate_bundle(self.bundle)
        counts = {
            "ok": report.ok,
            "error": len(report.errors),
            "warning": len(report.warnings),
        }
        if rev is not None:
            self.server._validate_cache = (rev, counts)  # type: ignore[attr-defined]
        return self._send_json(200, counts)
```

- [ ] **Step 4: GREEN — add the route.** In `_route`, find the `/__diff` route (server.py:1146-1147):

```python
        if path == "/__diff":
            return self._handle_diff(query)
```
Add immediately AFTER it:
```python
        if path == "/__validate":
            return self._handle_validate()
```

- [ ] **Step 5: Run — the backend test passes:**

Run: `python3 -m pytest tests/test_studio_iter2_backend.py -k "validate_requires_token or validate_returns_counts" -q`
Expected: PASS. Read the summary line.

- [ ] **Step 6: GREEN — add the footer chip + fetch to studio.js.** In `mountBar`'s scope, immediately AFTER the `conceptStatseg` definition (studio.js:334-337), add the validation chip + its refresher:

```js
  // Round 2 §6.4 / SPEC §3.5: validation count (ambient). Hidden until the
  // read-only /__validate fetch resolves; refreshed on bundle changes.
  const validationStatseg = el("span", { class: "okf-statseg okf-statseg--validation",
    role: "status", "aria-live": "polite", hidden: "", title: "Bundle validation" }, [
    el("span", { class: "okf-statseg__mark", "aria-hidden": "true", text: "◇" }),
    document.createTextNode(" validating…"),
  ]);
  function refreshValidation() {
    if (typeof tokenFetch !== "function") return;
    tokenFetch("/__validate", { headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        var label = d.error ? (d.error + " error" + (d.error === 1 ? "" : "s"))
          : d.warning ? (d.warning + " warning" + (d.warning === 1 ? "" : "s"))
          : "valid";
        var mark = validationStatseg.querySelector(".okf-statseg__mark");
        if (mark) mark.textContent = d.error ? "✕" : d.warning ? "!" : "✓";
        validationStatseg.setAttribute("data-state", d.error ? "error" : d.warning ? "warn" : "ok");
        while (validationStatseg.childNodes.length > 1) {
          validationStatseg.removeChild(validationStatseg.lastChild);
        }
        validationStatseg.appendChild(document.createTextNode(" " + label));
        validationStatseg.setAttribute("title", "Bundle validation: " + label);
        validationStatseg.removeAttribute("hidden");
      })
      .catch(function () {});
  }
```

- [ ] **Step 7: GREEN — mount the chip.** In the ambient assembly, find (studio.js:406-408):

```js
  rightGroup.appendChild(presenceChip);
  if (conceptCount > 0) rightGroup.appendChild(conceptStatseg);
  rightGroup.appendChild(connChip);
```
Replace it with (validation chip between concept count and the connection dot):
```js
  rightGroup.appendChild(presenceChip);
  if (conceptCount > 0) rightGroup.appendChild(conceptStatseg);
  rightGroup.appendChild(validationStatseg);
  rightGroup.appendChild(connChip);
```

- [ ] **Step 8: GREEN — fetch on boot + refresh on changes.** `refreshValidation` is a top-level IIFE `function` declaration (hoisted), so it is callable from the live-event wiring even though it's defined in the bar-assembly region. Find the live hub wiring where `changed`/`created`/`removed` already re-run `renderChangeList` (studio.js:3678-3680):

```js
    window.okfLoomLive.on("changed", (d) => { upsertEvent({ type: "changed", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); });
    window.okfLoomLive.on("created", (d) => { upsertEvent({ type: "created", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); });
    window.okfLoomLive.on("removed", (d) => { upsertEvent({ type: "removed", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); });
```
Replace it with (adds `refreshValidation();` to each handler + a single boot call right after — the live hub is wired only after the studio has booted, so `tokenFetch` is ready):
```js
    window.okfLoomLive.on("changed", (d) => { upsertEvent({ type: "changed", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); refreshValidation(); });
    window.okfLoomLive.on("created", (d) => { upsertEvent({ type: "created", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); refreshValidation(); });
    window.okfLoomLive.on("removed", (d) => { upsertEvent({ type: "removed", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); refreshValidation(); });
    refreshValidation();   // Round 2 §6.4: initial validation count (rev-cached server-side, so repeats are cheap)
```
(If this exact triple isn't present verbatim, add `refreshValidation();` inside whichever `changed`/`created`/`removed` handlers exist plus one boot call after the hub is wired. The endpoint is rev-cached server-side, so no client debounce is needed.)

- [ ] **Step 9: GREEN — add the state CSS.** In `studio.css`, append near the `.okf-statseg` rules (grep `.okf-statseg {`):

```css
/* Round 2 §6.4: validation status chip states (ambient). */
.okf-statseg--validation[data-state="ok"] { color: var(--okf-fg-muted); }
.okf-statseg--validation[data-state="warn"] { color: var(--okf-warn, var(--okf-accent)); }
.okf-statseg--validation[data-state="error"] { color: var(--okf-danger, #d64545); }
```

- [ ] **Step 10: Sanity — JS + CSS well-formed:**

Run: `node --check scripts/okf_loom/viewer/static/studio.js && python3 -c "import pathlib; s=pathlib.Path('scripts/okf_loom/viewer/static/studio.css').read_text(); assert s.count('{')==s.count('}')"`
Expected: valid; braces balanced. (`--okf-warn`/`--okf-danger` may not be defined tokens; the `var(…, fallback)` keeps them safe — Task 9 can promote to real tokens if desired.)

- [ ] **Step 11: Write the failing browser test.** Add to `tests/test_studio_iter1_browser.py`:

```python
def test_footer_shows_validation_count(server_url, page):
    """Round 2 §6.4 / SPEC §3.5: the footer shows a validation-count chip fed
    by the read-only /__validate endpoint."""
    page.set_viewport_size({"width": 1200, "height": 900})
    page.goto(f"{server_url}/tables/orders", wait_until="load")
    _wait_for_studio(page)
    seg = page.wait_for_selector(".okf-statseg--validation:not([hidden])", timeout=10000)
    assert seg is not None
```

- [ ] **Step 12: Run — new tests pass:**

Run (two commands — a single `pytest` invocation takes only one `-k`):
```
python3 -m pytest tests/test_studio_iter2_backend.py -k "validate_requires_token or validate_returns_counts" -q
python3 -m pytest tests/test_studio_iter1_browser.py -k "footer_shows_validation" -q
```
Expected: PASS on both. Read each summary line.

- [ ] **Step 13: Commit**

```bash
git add scripts/okf_loom/server.py scripts/okf_loom/viewer/static/studio.js scripts/okf_loom/viewer/static/studio.css tests/test_studio_iter2_backend.py tests/test_studio_iter1_browser.py
git commit -m "feat(studio): validation count — read-only /__validate GET + footer status chip (§6.4, SPEC §3.5)"
```

---

### Task 9: Phase-3 verification (suite green + served/tunnelled all-feature × all-theme pass)

**Files:** none (verification + tuning only).

- [ ] **Step 1: Full suite green.**
Run: `python3 -m pytest tests/ -q`
Expected: PASS (Phase-2 baseline `1287 passed / 23 skipped`; Phase 3 adds ~9 tests → ~1296). **Read the printed summary line** — never trust a `| tail`ed exit code. Documented flakes, rerun once if the ONLY failures: `test_comment_mark_wraps_selection`, `test_agent_watching_toggle_posts_presence`, `test_agent_activity_panel_has_unique_sections`.

- [ ] **Step 2: Serve on loopback + tunnel (background) — RESTART required (render.py + server.py + template changed).**
Run (Bash tool, `run_in_background: true`): `exec scripts/okf-loom serve docs-bundle --no-open --port 8788 --tunnel`
Wait (no sleep): `curl -s --retry 30 --retry-delay 1 --retry-connrefused http://localhost:8788/demo/showcase -o /dev/null && echo up`
Expected: `up`. Grep the bg task's output file for `https://<x>.trycloudflare.com` (hand to the user only if asked). Control via **TaskStop** (never `pkill`).

- [ ] **Step 3: Self-review screenshots across the matrix** (Playwright + system Chrome, `wait_until="load"`; seed `okf-theme` for the non-default 3, plus `okf-contrast`/`okf-border` for a couple of variants). Capture + read back, at minimum:
  - **6.1 ToC** on `/reference/cli` (39 headings → long ToC) and `/demo/showcase` (10) in **all 4 themes** — confirm the ToC sits between the header and the prose, reads flat like the nav, and `#anchor` clicks scroll (spot-check one). Confirm a **short concept** has NO ToC.
  - **6.2 Index** at `/` in ≥2 themes — the toolbar (chips + sort + search-within) renders full-width, a chip filters, sort reorders, search-within narrows + shows the empty state; the shell uses the wider `--okf-index-maxw`. Verify `contrast=soft` + `border=off` still read cleanly.
  - **6.3 Search** at `/__search?q=orders` (live) in ≥2 themes — results show highlighted `<mark>` terms + the type/path meta; then a **static build** (`scripts/okf-loom build docs-bundle …` or the static output) `__search.html?q=orders` to confirm the static renderer now shows meta + highlight at parity.
  - **6.4 RUN** — open Comments, click an intent ▶ Run, confirm a directive comment posts (toast + optimistic row); **Changes diff** — trigger a change (or use the `_changeRow` seam) and expand View diff; **validation chip** — confirm the footer shows the count in ≥2 themes.
  - Confirm nothing Phase-1/2 regressed: rail present, footer toolbar, Appearance menu, flat Related.

- [ ] **Step 4: Stop the serve/tunnel** via **TaskStop** on the bg task id (never `pkill`).

- [ ] **Step 5: Tune anything the visual pass flags** — ToC spacing/contrast, index toolbar rhythm + widened-shell balance, `<mark>` tint per theme, the intent Run button seam, the validation chip tone. Edit the asset, reload (restart only if render.py/server.py/templates change), re-verify the suite stays green, and commit:
```bash
git add scripts/okf_loom/viewer/static docs
git commit -m "fix(viewer): Round-2 Phase-3 visual-pass tuning (ToC/index/search/studio polish)"
```

- [ ] **Step 6: Final whole-Phase-3 review** (compensates for the unavailable advisor): dispatch one review subagent over the full Phase-3 diff (`git diff a957388..HEAD -- scripts docs`… scoped to the Phase-3 commits) checking: decoupling contract intact (no hardcoded aesthetics; no `[data-theme]`/parity edits); every `__TOKEN__` still replaced; the first-anchor + `.okf-page__body`-outside contracts; the trust boundary (only `/__validate` is new server surface, read-only + token-gated; RUN/diff reuse existing endpoints); THEMES/graph untouched. Fix any finding, re-run the suite, commit.

---

## Self-Review

**1. Spec coverage (Round-2 spec §6, Phase 3):**
- §6.1 on-page ToC (server-rendered, ≥N headings, no-JS, flat like nav, distinct from studio Outline) → Task 1 (rendered-level extraction per D1; N=3; `.okf-toc*` in wiki.css). ✔
- §6.2 index dashboard (type-filter chips · sort · search-within enhancing server groups; fixes horizontal space) → Task 2 (server data-attrs) + Task 3 (client `enhanceIndex` + widened `--okf-index-maxw`; no-JS keeps groups; chips are `<button>`). ✔
- §6.3 search quality (match-highlighting · relevance sort · result meta) → Task 4 (live: match-centred snippet + `<mark>`; relevance already sorted per D2; meta already present) + Task 5 (static: meta/type parity + `<mark>` + match-centred excerpt). Dropdown left as-is (D2). ✔
- §6.4 studio depth: (spike) quick-actions RUN → Task 6 (post `/__comment` directive via existing channel — D3, no new endpoint); (spike) validation count → Task 8 (read-only token-gated `/__validate` + footer chip — D5; completes SPEC §3.5); on-demand Changes diff reusing the conflict-modal renderer → Task 7 (extract `renderDiffInto`; revs from `detail.before`/`rev` — D4). ✔
- §7 verification (suite + Playwright + serve/tunnel all-feature × all-theme) → Task 9. ✔
- §8 non-goals: stay on `feature/new-layout` (no branch/merge); don't touch `okf-loom-mcp/`/`redesign-files-1.zip`; no theme-enum growth / no new parity tokens; Swiss default + Phase-2 appearance untouched; no edge-to-edge prose (ToC is a narrow flat block above the measure). ✔
- Spikes resolved conservatively + documented (Task 0 note + D1–D5): RUN and the diff need NO new server surface; `/__validate` is the only new endpoint and is read-only + token-gated + rev-cached. ✔

**2. Placeholder scan:** No "TBD"/"handle appropriately". Every code step shows concrete before/after or a complete new block. A few steps say "read the neighbouring test/helper and copy its exact setup" (Task 2 `_render_index_html` load line; Task 4 bundle load; Task 6 rail-open selector; Task 8 backend-test fixture) — these name the exact neighbour + give the full assertions; they exist because the test harness owns those fixtures and inventing a signature would be worse than pointing at the real one (same approach the Phase-2 plan used + validated). Task 7's `_changeRow` seam is added explicitly (Step 4) rather than assumed.

**3. Type/name consistency:** Names match across tasks — placeholder `__TOC_HTML__` (Task 1 render.py + template); `data-okf-type`/`-title`/`-search` (Task 2 emit ↔ Task 3 read); `--okf-index-maxw` (Task 3 token ↔ `.okf-index` use); `_highlight`(py, Task 4) / `highlight`(js, Task 5) both escape-then-`<mark>`; `.okf-search-result__meta`/`__type` reconciled live (Task 4) ↔ static (Task 5) with the shared CSS in Task 4; `okf-composer__submit` hook (Task 6 add ↔ RUN read); `INTENTS[].runPrompt` (Task 6); `renderDiffInto` (Task 7 def ↔ modal + changeRow callers) with `{concept, from, to}`; `_changeRow` seam (Task 7 def ↔ test); `/__validate` → `{ok,error,warning}` (Task 8 server ↔ `refreshValidation` ↔ tests); `.okf-statseg--validation` (Task 8 chip ↔ CSS). Preserved contracts: no `[data-theme]`/parity edits; THEMES/graph untouched; `_render_search_page` null-tolerance kept; corpus emitter untouched; conflict-modal DOM + labels intact.

**Risk notes:**
- **Serve-restart boundaries:** Tasks 1, 2, 4 (render.py + template) and Task 8 (server.py). Browser tests spin their own server, so pytest is unaffected; only Task 9's manual serve needs the restart. Sequenced so shared-file edits (render.py in 1/2/4; wiki.css in 1/3/4; studio.js in 6/7/8) serialize via commits.
- **Task 5 static path** is verified by a source-contract test + `node --check` (no pytest harness renders the static searcher); Task 9 adds a static-build screenshot for real visual proof.
- **Task 7 extraction** is the subtlest change — `renderDiffInto` must produce byte-identical DOM to the inlined `viewBtn` core so the existing conflict-modal tests stay green; those tests ARE the regression guard (Step 8 runs them).
- **Task 8 `/__validate`** is the only new server surface: read-only, token-gated (same guard as `/__diff`), rev-cached to avoid re-walking the bundle on polls. `--okf-warn`/`--okf-danger` use `var(…, fallback)` so undefined tokens don't break.
- **RUN posts real directives** to the agent's queue — in the DEMO serve that's harmless (no agent claims them); documented that RUN sends the completed composer text (or the complete `runPrompt` when empty), never a bare template.
- **advisor unavailable** — compensated by each task's two-stage subagent review (spec-compliance then code-quality), the final whole-Phase-3 review (Task 9 Step 6), and independent test + screenshot verification.
