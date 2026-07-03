/**
 * OKF renderers.js — progressive enhancement for rich content blocks.
 *
 * Loads Mermaid (diagrams), highlight.js (syntax highlighting), and KaTeX
 * (math) from CDN ONLY when the page contains elements that need them.
 * Degrades gracefully: if the CDN is unreachable, the raw source text
 * remains visible (readable but unstyled).
 *
 * CSP-safe: loaded as a local <script defer> from /__static/renderers.js.
 * The CDN scripts are dynamically inserted only when needed, so pages
 * without mermaid/code/math incur zero overhead.
 *
 * Supply-chain posture: every CDN URL is pinned to an EXACT
 * version (jsdelivr per-version URLs are immutable), matching the pinned
 * cytoscape tag in render.py. <link>/<script> assets additionally carry
 * SRI integrity hashes. The two dynamic import() modules (mermaid, hljs)
 * cannot carry SRI (the import spec has no integrity slot, and their ESM
 * graphs pull sub-modules anyway) — exact-version pinning is the
 * practical mitigation there. When bumping a version, recompute hashes:
 *   curl -s <url> | openssl dgst -sha384 -binary | openssl base64 -A
 */
(function () {
  "use strict";

  // Single source of truth for CDN versions + SRI hashes.
  var PINS = {
    mermaidEsm: "https://cdn.jsdelivr.net/npm/mermaid@11.16.0/dist/mermaid.esm.min.mjs",
    // jsDelivr's +esm transform: the package's own es/index.js is a
    // bundler-oriented wrapper whose raw browser import provides no
    // default export (verified in-browser: highlighting silently never
    // ran). +esm serves a self-contained ESM bundle with hljs as the
    // default export, still pinned to the exact version.
    hljsEsm: "https://cdn.jsdelivr.net/npm/highlight.js@11.11.1/+esm",
    hljsThemeLight: {
      href: "https://cdn.jsdelivr.net/npm/highlight.js@11.11.1/styles/github.min.css",
      integrity: "sha384-eFTL69TLRZTkNfYZOLM+G04821K1qZao/4QLJbet1pP4tcF+fdXq/9CdqAbWRl/L",
    },
    hljsThemeDark: {
      href: "https://cdn.jsdelivr.net/npm/highlight.js@11.11.1/styles/github-dark.min.css",
      integrity: "sha384-wH75j6z1lH97ZOpMOInqhgKzFkAInZPPSPlZpYKYTOqsaizPvhQZmAtLcPKXpLyH",
    },
    katexCss: {
      href: "https://cdn.jsdelivr.net/npm/katex@0.16.47/dist/katex.min.css",
      integrity: "sha384-nH0MfJ44wi1dd7w6jinlyBgljjS8EJAh2JBoRad8a3VDw2K69vfaaqm4WnR+gXtA",
    },
    katexJs: {
      src: "https://cdn.jsdelivr.net/npm/katex@0.16.47/dist/katex.min.js",
      integrity: "sha384-CwjPRVHTvLiMBFjEoij+QZViMV5rhTOIp7CJzl24JEqpRDA1sJFHVXXLURktbYYp",
    },
  };

  function loadScript(pin, type) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = pin.src || pin;
      if (pin.integrity) {
        s.integrity = pin.integrity;
        s.crossOrigin = "anonymous";
      }
      if (type) s.type = type;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function loadCSS(pin) {
    return new Promise(function (resolve, reject) {
      var l = document.createElement("link");
      l.rel = "stylesheet";
      l.href = pin.href || pin;
      if (pin.integrity) {
        l.integrity = pin.integrity;
        l.crossOrigin = "anonymous";
      }
      l.onload = function () { resolve(l); };
      l.onerror = reject;
      document.head.appendChild(l);
      return l;
    });
  }

  function isDark() {
    return (document.documentElement.getAttribute("data-theme") || "light") === "dark";
  }

  // --- Mermaid ---
  function initMermaid() {
    // Only process mermaid divs that haven't been rendered yet (no SVG child).
    // This prevents re-rendering diagrams that are already shown, which would
    // cause a visible flash on live updates that don't change the diagram.
    var allDivs = document.querySelectorAll("div.mermaid");
    if (allDivs.length === 0) return;
    var mermaidDivs = Array.from(allDivs).filter(function (el) {
      return !el.querySelector("svg"); // skip already-rendered
    });
    if (mermaidDivs.length === 0) return; // nothing to render
    // Stamp the original source text as data-source BEFORE mermaid
    // replaces it with SVG output.
    mermaidDivs.forEach(function (el, i) {
      if (!el.getAttribute("data-source")) {
        el.setAttribute("data-source", el.textContent);
      }
      if (!el.id) el.id = "okf-mermaid-" + i;
    });
    // Mermaid v11 is ESM-only. Use dynamic import() so the module loads
    // asynchronously and we get the mermaid object as a named export.
    // CSP allows this because cdn.jsdelivr.net is in script-src.
    import(PINS.mermaidEsm)
      .then(function (mod) {
        var mermaid = mod.default || window.mermaid;
        if (!mermaid) return;
        mermaid.initialize({
          startOnLoad: false,
          theme: isDark() ? "dark" : "default",
        });
        return mermaid.run({ nodes: mermaidDivs });
      })
      .catch(function () {
        mermaidDivs.forEach(function (el) {
          el.classList.add("mermaid--fallback");
        });
      });
  }

  // --- Syntax highlighting (highlight.js) ---
  // The theme stylesheet follows the page theme. A data-theme mutation observer
  // swaps the sheet on toggle so light pages do not get dark code islands.
  var hljsThemeLink = null;
  function ensureHljsTheme() {
    var pin = isDark() ? PINS.hljsThemeDark : PINS.hljsThemeLight;
    if (hljsThemeLink && hljsThemeLink.href === pin.href) return;
    var old = hljsThemeLink;
    loadCSS(pin)
      .then(function (l) {
        hljsThemeLink = l;
        if (old && old.parentNode) old.parentNode.removeChild(old);
      })
      .catch(function () { /* theme optional; code stays readable */ });
  }

  var themeObserver = null;
  function watchThemeForHljs() {
    if (themeObserver) return;
    themeObserver = new MutationObserver(function () {
      if (hljsThemeLink) ensureHljsTheme();
    });
    themeObserver.observe(document.documentElement, {
      attributes: true, attributeFilter: ["data-theme"],
    });
  }

  function initHighlight() {
    // Only highlight code blocks that haven't been highlighted yet.
    var allBlocks = document.querySelectorAll("pre > code[class*='language-']");
    if (allBlocks.length === 0) return;
    var codeBlocks = Array.from(allBlocks).filter(function (el) {
      return !el.dataset.highlighted; // skip already-highlighted
    });
    if (codeBlocks.length === 0) return;
    ensureHljsTheme();
    watchThemeForHljs();
    // Load highlight.js via dynamic import() of the ESM build.
    // The old common.min.js is UMD/CommonJS (uses module.exports + require)
    // and throws "require is not defined" when loaded as a plain <script>.
    // The ESM build at /es/index.js exports a default `hljs` and runs
    // cleanly under CSP `script-src` that allows the CDN.
    import(PINS.hljsEsm)
      .then(function (mod) {
        // ESM default export is hljs; fall back to named for safety.
        var hljs = (mod && mod.default) || (mod && mod.hljs) || window.hljs;
        if (!hljs) return;
        codeBlocks.forEach(function (block) {
          try { hljs.highlightElement(block); } catch (e) { /* ignore */ }
          block.dataset.highlighted = "true"; // mark so we don't re-highlight
        });
      })
      .catch(function () {
        /* CDN unreachable: code blocks remain unstyled (readable). */
      });
  }

  // --- Math (KaTeX) ---
  function initMath() {
    // Skip blocks already rendered: re-running katex.render over rendered
    // output would typeset the MathML text, garbling it. Matters now that
    // okf-loom:bodyPatched re-scans can fire repeatedly (live patches, graph
    // detail panel).
    var allMath = document.querySelectorAll("div.math");
    if (allMath.length === 0) return;
    var mathDivs = Array.prototype.filter.call(allMath, function (el) {
      return !el.dataset.mathRendered;
    });
    if (mathDivs.length === 0) return;
    Promise.all([
      loadCSS(PINS.katexCss),
      loadScript(PINS.katexJs),
    ])
      .then(function () {
        mathDivs.forEach(function (el, i) {
          if (window.katex && !el.dataset.mathRendered) {
            var tex = el.textContent;
            el.id = el.id || ("okf-math-" + i);
            window.katex.render(tex, el, { throwOnError: false, displayMode: true });
            el.dataset.mathRendered = "true";
          }
        });
      })
      .catch(function () {
        /* CDN unreachable: raw LaTeX remains visible. */
      });
  }

  // Run after DOM is ready.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initMermaid();
      initHighlight();
      initMath();
    });
  } else {
    initMermaid();
    initHighlight();
    initMath();
  }

  // Re-run on live studio patches (when the concept body is re-rendered).
  window.addEventListener("okf-loom:bodyPatched", function () {
    initMermaid();
    initHighlight();
    initMath();
  });
})();
