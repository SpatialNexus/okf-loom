/* OKF static-build client-side search (current spec §9).
 *
 * Loaded only on the static search page (__search.html) when the bundle was
 * built with `--target static`. Reads `?q=` from the URL, fetches the
 * build-time corpus at __data/search.json (resolved relative to the page so
 * it works regardless of where the static site is hosted), tokenizes the
 * query, scores each corpus entry by term frequency with field weights, and
 * renders the results into the existing results container.
 *
 * Zero dependencies (vanilla JS). CSP compliant: script-src 'self' +
 * connect-src 'self' - both satisfied because the script and the corpus are
 * same-origin. No inline handlers, no eval, no dynamic imports.
 *
 * Determinism: the corpus is sorted by concept_id at build time; results are
 * sorted by (-score, id), so identical (query, corpus) ⇒ identical result
 * order across browsers and runs.
 *
 * The live `serve` search path is UNCHANGED - it still hits /__search
 * server-side. This script is a no-op outside static mode.
 */
(function () {
  "use strict";

  // Only run on the static search page. The <body> carries
  // data-okf-mode="static" in static builds; serve/spa keep using the live
  // /__search backend. Also require the results container so we never run on
  // a concept page that happens to share data-okf-mode.
  var body = document.body;
  if (!body) return;
  if (body.getAttribute("data-okf-mode") !== "static") return;
  var resultsContainer = document.querySelector(".okf-search__results");
  if (!resultsContainer) return;

  // P2-3 (iter-2): the search h1 is no longer wrapped in .okf-muted, so we
  // update the heading element directly. The prior code queried a child
  // `.okf-muted` span (countSpan) + a `.okf-search__query` span that the
  // template never emitted (querySpan was always null). Now we rebuild the
  // heading text with proper pluralisation, mirroring the server-side
  // _render_search_page heading strings.
  var titleEl = document.querySelector(".okf-search__title");
  var inputEl = document.querySelector('input[type="search"][name="q"]');

  // Announce result updates to assistive tech (results replace the empty
  // server-rendered state without a full navigation).
  resultsContainer.setAttribute("aria-live", "polite");
  resultsContainer.setAttribute("aria-busy", "true");

  // ---------------------------------------------------------------------
  // Hide the now-stale "search unavailable" notice that wiki.js appends to
  // the topbar search input on every static page. On the search page itself
  // the client-side searcher is live, so the notice would be misleading.
  // (wiki.js is owned by a different workstream; we hide its artifact here
  // rather than edit wiki.js. This is the only cross-file coupling and is
  // keyed off the stable `.okf-search-note` class + the literal "unavailable"
  // substring, so it degrades safely if wiki.js's note text changes.)
  // ---------------------------------------------------------------------
  function hideStaleNote() {
    var notes = document.querySelectorAll(".okf-search-note");
    for (var i = 0; i < notes.length; i++) {
      var t = notes[i].textContent || "";
      if (t.indexOf("unavailable") >= 0) {
        notes[i].setAttribute("hidden", "");
      }
    }
  }
  hideStaleNote();
  // wiki.js is `defer` and runs before us in document order, but defensively
  // re-check after a microtask in case future ordering changes.
  Promise.resolve().then(hideStaleNote);

  // ---------------------------------------------------------------------
  // URL query parsing (?q=...).
  // ---------------------------------------------------------------------
  function getQuery() {
    var qs = window.location.search || "";
    if (qs.charAt(0) === "?") qs = qs.slice(1);
    if (!qs) return "";
    var pairs = qs.split("&");
    for (var i = 0; i < pairs.length; i++) {
      var eq = pairs[i].indexOf("=");
      if (eq < 0) continue;
      var k = decodeURIComponent(pairs[i].slice(0, eq).replace(/\+/g, " "));
      if (k === "q") {
        return decodeURIComponent(pairs[i].slice(eq + 1).replace(/\+/g, " "));
      }
    }
    return "";
  }

  // ---------------------------------------------------------------------
  // Tokenizer: lowercase, split on Unicode word runs, drop stopwords.
  // APPROXIMATES the Python `search.tokenize` for the static-build use case
  // (no external deps), but is NOT a byte-identical mirror (iter2 P3-1):
  //   - The stopword set is a pragmatic subset; the Python `_STOPWORDS` list
  //     differs (it includes more function words like been/being/having/
  //     into/through/under/until/up/off/once/other/out/over/some/their/
  //     there/what/when/where/which/while/who/whom/why/would; the JS set
  //     includes a few short forms like don/now/d/ll/m/o/re/ve/y).
  //   - The scorer uses field-weighted term-frequency (title×3, aliases×2,
  //     description×2, tags×1, body×1) - simpler than the live BM25+IDF
  //     backend (which uses title×5, headings×3, description×2, body×1,
  //     tags×1 with IDF normalization). The corpus does not carry `headings`
  //     (a live-only field); aliases/type are additive corpus-only fields.
  //   - The scorer uses raw substring indexOf (matches inside other words),
  //     unlike the Python token-set matching.
  // These divergences are acceptable: the static search is a convenience
  // fallback for static-hosted bundles; it is NOT required to produce
  // byte-identical rankings to the live `/__search` backend (which uses a
  // different algorithm). The current browser-proof contract does not mandate parity.
  // `\p{L}`/`\p{N}` require the ES2018 `u` flag (Chrome ≥64, FF ≥78,
  // Safari ≥12 - well within the static-build browser matrix).
  // ---------------------------------------------------------------------
  var STOP = new Set((
    "a an and are as at be but by for from has have in is it its of on or " +
    "that the to was were will with this these those your yours you your we " +
    "our ours us me my mine i he she they them his her hers do does did doing " +
    "can could should shall may might must also via per within without about " +
    "above after again against all because before below between during each " +
    "few further down not no nor if then than so such only own same very don " +
    "now d ll m o re ve y"
  ).split(" "));

  function tokenize(text) {
    if (!text) return [];
    var lowered = String(text).toLowerCase();
    var raw = lowered.match(/[\p{L}\p{N}_]+/gu) || [];
    var out = [];
    for (var i = 0; i < raw.length; i++) {
      var tok = raw[i];
      if (!tok) continue;
      // CJK/ideographic fallback: a token with NO ASCII letter/digit is
      // split per character (so 比特币 indexes as 比, 特, 币).
      if (!/[a-z0-9]/.test(tok)) {
        for (var j = 0; j < tok.length; j++) {
          var ch = tok[j];
          if (ch && !STOP.has(ch)) out.push(ch);
        }
        continue;
      }
      if (STOP.has(tok)) continue;
      out.push(tok);
    }
    return out;
  }

  function countMatches(haystack, needle) {
    if (!haystack || !needle) return 0;
    var count = 0;
    var idx = 0;
    while ((idx = haystack.indexOf(needle, idx)) !== -1) {
      count++;
      idx += needle.length;
    }
    return count;
  }

  // ---------------------------------------------------------------------
  // Scorer: term frequency across field-weighted fields.
  //   title×3 + aliases×2 + description×2 + tags×1 + body_excerpt×1
  // Matches the contract documented at the build-time emitter
  // (render.py:_search_corpus_json) so live and static results stay
  // semantically close.
  // ---------------------------------------------------------------------
  function scoreEntry(entry, queryTokens) {
    if (!queryTokens.length) return 0;
    var title = String(entry.title || "").toLowerCase();
    var aliases = (entry.aliases || []).join(" ").toLowerCase();
    var desc = String(entry.description || "").toLowerCase();
    var tags = (entry.tags || []).join(" ").toLowerCase();
    var bodyExcerpt = String(entry.body_excerpt || "").toLowerCase();
    var score = 0;
    for (var i = 0; i < queryTokens.length; i++) {
      var t = queryTokens[i];
      score += countMatches(title, t) * 3;
      score += countMatches(aliases, t) * 2;
      score += countMatches(desc, t) * 2;
      score += countMatches(tags, t);
      score += countMatches(bodyExcerpt, t);
    }
    return score;
  }

  function escapeHtml(s) {
    // iter2 P3-6: escape single-quote too (defense-in-depth). All current
    // call sites use double-quoted attribute context, but a future edit
    // putting an escaped value into a single-quoted attribute or JS string
    // literal would silently introduce an attribute-breakout hole without
    // this. CSP 'self' caps the blast radius regardless.
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function eligibleTokens(tokens) {
    // Shared by highlight() and makeSnippet() (Round 2 §6.3 fix): the ONE
    // definition of which query tokens are eligible to match, so the two
    // functions can't drift apart again — that drift is exactly what let a
    // makeSnippet defect ship (see the comment there). A token is eligible
    // when it is truthy and >= 2 chars: tokenize()'s `/[\p{L}\p{N}_]+/gu`
    // CAN emit 1-char tokens (e.g. a query like "a protocols" tokenizes to
    // ["a","protocols"]); 1-char tokens are noisy/low-signal, so highlight()
    // has always excluded them here. Also dedupes, preserving first-seen
    // order (callers decide any further ordering, e.g. highlight()'s
    // longest-first sort below).
    var uniq = [];
    if (tokens) {
      for (var i = 0; i < tokens.length; i++) {
        var t = tokens[i];
        if (t && t.length >= 2 && uniq.indexOf(t) < 0) uniq.push(t);
      }
    }
    return uniq;
  }

  function highlight(text, tokens) {
    // Round 2 §6.3: wrap query-term matches in <mark>. Shares the
    // CORRECTED render.py _highlight()'s (scripts/okf_loom/render.py)
    // entity-safe ALGORITHM — terms are matched against the RAW
    // (pre-escape) text, then EVERY segment (the gaps AND each matched
    // run) is escaped independently via escapeHtml, splicing a LITERAL
    // <mark> around the escaped match. Matching the ALREADY-escaped string
    // instead (escape-then-match) would let a token equal to an HTML
    // entity name ("gt"/"amp"/"lt"/"quot") land inside an escaped
    // "&gt;"/"&amp;" and shatter it — data-catalog text routinely carries
    // "<"/">"/"&" (SQL comparisons, "Q&A", "AT&T"). Because
    // eligibleTokens() only lets word-chars-only, >=2-char tokens through,
    // a match can never straddle the "&"/";" of an entity sitting in a
    // gap, so gaps always escape atomically. Terms are deduped (by
    // eligibleTokens) and sorted longest-first here so overlapping terms
    // don't half-wrap one another.
    //
    // Tokenizer parity note: `tokens` here comes from this file's tokenize()
    // (`/[\p{L}\p{N}_]+/gu` — which KEEPS `_`, and also DROPS stopwords and
    // splits CJK runs per character). render.py's _highlight() now tokenizes
    // the query with the same underscore-keeping `\w+` word regex (its
    // `_HIGHLIGHT_WORD_RE`, aligned to the live search backend's `_WORD_RE`),
    // so the shared match-on-raw → escape-per-segment algorithm above marks an
    // underscore/multi-part identifier like "user_role" as ONE run on both
    // sides (and an "a_b"-style token whole on both) — the divergence this
    // reconciliation fixed. The two can still differ where tokenize() does more
    // than the `\w+` split _highlight() shares: a query with a >=2-char
    // STOPWORD (dropped here, marked live) or a pure-CJK query (split per
    // character here, marked as a whole run live). Both are separate,
    // pre-existing differences, independent of the underscore reconciliation.
    var s = String(text == null ? "" : text);
    var uniq = eligibleTokens(tokens);
    if (!s || !uniq.length) return escapeHtml(s);
    uniq.sort(function (a, b) { return b.length - a.length; });
    var special = /[.*+?^${}()|[\]\\]/g;
    var pattern = new RegExp(
      uniq.map(function (tok) { return tok.replace(special, "\\$&"); }).join("|"),
      "gi"
    );
    var out = "";
    var last = 0;
    var m;
    while ((m = pattern.exec(s)) !== null) {
      out += escapeHtml(s.slice(last, m.index));       // escape the gap
      out += "<mark>" + escapeHtml(m[0]) + "</mark>";  // escape+wrap the RAW match
      last = m.index + m[0].length;
    }
    out += escapeHtml(s.slice(last));                  // escape the tail
    return out;
  }

  function makeSnippet(entry, tokens) {
    // §6.3: window around the first query-term match so the highlighted
    // term is visible; fall back to the leading slice. Prefers the
    // build-time body excerpt (more likely to contain the term) then the
    // curated description, mirroring the live renderer's preference for
    // its backend-computed match-centred `snippets` excerpt over
    // `description` (render.py _render_search_page).
    //
    // Round 2 P3-fix: the centre position (`best`) is now scanned over
    // eligibleTokens(tokens) - the SAME >=2-char eligibility filter that
    // highlight() applies - instead of the raw `tokens` array. Before this
    // fix, a sub-2-char token (e.g. "a") could win the earliest-match race
    // (its position is always <= any longer token's) and centre the window
    // somewhere highlight() would never mark, pushing a genuine
    // highlightable match outside the 200-char window entirely; the
    // excerpt then showed no <mark> at all, defeating this function's
    // purpose. Using eligibleTokens() also fixes a related bug for free:
    // the old loop had no truthiness guard, so a falsy tokens[i] entry
    // (e.g. an empty string) reached `low.indexOf(...)` directly, and an
    // empty-string needle always matches at position 0, so a stray empty
    // token would unconditionally "win" the race with best=0.
    var src = String(entry.body_excerpt || entry.description || "");
    if (!src) return "";
    var elig = eligibleTokens(tokens);
    if (elig.length) {
      var low = src.toLowerCase(), best = -1, i, p;
      for (i = 0; i < elig.length; i++) {
        p = low.indexOf(elig[i]);
        if (p >= 0 && (best < 0 || p < best)) best = p;
      }
      if (best > 40) return "\u2026" + src.slice(best - 40, best - 40 + 200);
    }
    return src.slice(0, 200);
  }

  function setStatus(count, query) {
    if (titleEl) {
      var q = query || "";
      // Match the server-side pluralisation (render.py _render_search_page):
      // "No results for ...", "1 result for ...", "N results for ...".
      if (count === 0) {
        titleEl.textContent = "No results for \u201C" + q + "\u201D";
      } else if (count === 1) {
        titleEl.textContent = "1 result for \u201C" + q + "\u201D";
      } else {
        titleEl.textContent = count + " results for \u201C" + q + "\u201D";
      }
    }
    // Reflect the URL query into the topbar input so re-searching works.
    if (inputEl && !inputEl.value) inputEl.value = query || "";
  }

  // ---------------------------------------------------------------------
  // Renderers. Round 2 §6.3: the result shape now reaches parity with the
  // live search page's markup (render.py _render_search_page) —
  // `<article class="okf-search-result">
  //   <h3><a class="okf-internal">title (highlighted)</a></h3>
  //   <div class="okf-search-result__meta okf-muted">type cid</div>
  //   <div class="okf-search-snippet">excerpt (highlighted)</div>
  // </article>` — including the type label and <mark> match highlighting.
  // ---------------------------------------------------------------------
  function renderResults(query, entries) {
    var tokens = tokenize(query);
    var scored = [];
    for (var i = 0; i < entries.length; i++) {
      var s = scoreEntry(entries[i], tokens);
      if (s > 0) scored.push({ entry: entries[i], score: s });
    }
    // Deterministic sort: (-score, id). Corpus is pre-sorted by id, so this
    // is reproducible across runs/browsers.
    scored.sort(function (a, b) {
      if (a.score !== b.score) return b.score - a.score;
      var ai = a.entry.id || "";
      var bi = b.entry.id || "";
      return ai < bi ? -1 : ai > bi ? 1 : 0;
    });

    setStatus(scored.length, query);
    resultsContainer.setAttribute("aria-busy", "false");

    if (!scored.length) {
      resultsContainer.innerHTML =
        '<p class="okf-search-empty">No results for "' +
        escapeHtml(query) + '".</p>';
      return;
    }
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
    resultsContainer.innerHTML = html;
  }

  function renderUnavailable(message) {
    // Older build without __data/search.json, or fetch failure: fail closed
    // with a graceful message pointing to the index. No partial state.
    setStatus(0, getQuery());
    resultsContainer.setAttribute("aria-busy", "false");
    resultsContainer.innerHTML =
      '<p class="okf-search-empty">' + escapeHtml(message) + '</p>';
  }

  // ---------------------------------------------------------------------
  // Corpus URL resolution. The static search page is emitted at the bundle
  // root (__search.html), so __data/search.json is a sibling directory. We
  // resolve the root prefix from the search form's action attribute so the
  // path stays correct if the site is hosted under a sub-path or if the
  // search page is ever nested.
  // ---------------------------------------------------------------------
  function corpusUrl() {
    var form = document.querySelector("form.okf-search-form");
    var root = "./";
    if (form) {
      var act = form.getAttribute("action") || "";
      var idx = act.indexOf("__search");
      if (idx >= 0) root = act.slice(0, idx) || "./";
    }
    return root + "__data/search.json";
  }

  // ---------------------------------------------------------------------
  // Initial render from ?q=. No query yet → friendly prompt (the form is
  // already visible and the user just hasn't typed). Otherwise fetch the
  // corpus and render. Network/HTTP/parse failures all funnel to the same
  // graceful unavailable message - no unhandled rejections.
  // ---------------------------------------------------------------------
  var initialQuery = getQuery();
  if (!initialQuery) {
    setStatus(0, "");
    resultsContainer.setAttribute("aria-busy", "false");
    resultsContainer.innerHTML =
      '<p class="okf-search-empty">Type a query above and press Enter.</p>';
    return;
  }

  fetch(corpusUrl(), { headers: { "Accept": "application/json" } })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (data) {
      // Accept either a bare array (current build) or a wrapper
      // {entries: [...]} (forward-compat). Anything else → empty.
      var entries = Array.isArray(data)
        ? data
        : (data && Array.isArray(data.entries) ? data.entries : []);
      renderResults(initialQuery, entries);
    })
    .catch(function () {
      renderUnavailable(
        "Search corpus not available. This may be an older build; " +
        "use the index to browse concepts."
      );
    });
})();
