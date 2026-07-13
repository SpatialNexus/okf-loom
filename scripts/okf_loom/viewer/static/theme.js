/* OKF viewer — canonical theme preference/state contract.
 *
 * SINGLE OWNER of Editorial Workbench appearance state for EVERY output
 * target: served wiki pages, the full-page graph view, the live studio,
 * static builds, and the single-file viewer. Loaded (or inlined) BEFORE
 * wiki.js / graph.js / studio.js in each context; those files consume
 * `window.OKFLoomTheme` and never interpret storage themselves.
 *
 * State model (hardening plan "State ownership contract"):
 *   - User family  → localStorage["okf-theme-family"]: "swiss" | "technical".
 *   - User mode    → localStorage["okf-theme-mode"]:   "auto" | "light" | "dark".
 *     Family and mode are orthogonal preferences; each persists on its own,
 *     so Technical + Auto survives reload and navigation.
 *   - Resolved theme (data-theme on <html>) is DERIVED ONLY:
 *     family + (mode, with "auto" following prefers-color-scheme live).
 *     It is never persisted while mode is Auto — that would freeze Auto.
 *   - Precedence: valid saved user preference > valid configured preference
 *     > Swiss Auto/OS fallback. The configured preference is captured at
 *     boot with ONE authority order: the server-rendered data-theme
 *     attribute (viewer config.json — the value the server already painted)
 *     wins; only when it is absent/invalid does the studio bootstrap JSON
 *     (okf-loom.config.yaml studio.theme) register, and its "auto" default
 *     carries no preference (it IS the fallback). Booting never writes the
 *     configured value into storage.
 *   - Legacy localStorage["okf-theme"] (concrete theme = pinned choice,
 *     absent = auto) is migrated ONCE into the two canonical keys when
 *     neither exists (surviving in-memory even when storage turned
 *     write-only), then maintained as a WRITE-ONLY compatibility mirror:
 *     set to the resolved concrete theme while mode is explicit, removed
 *     while mode is Auto, and reconciled at boot (canonical Auto removes a
 *     stale concrete mirror; a full explicit preference corrects a
 *     conflicting one; partial preferences never bake configured defaults
 *     into storage). It is never read as authority again.
 *   - Contrast/border stay validated persisted modifiers under the existing
 *     "okf-contrast" / "okf-border" keys and data-okf-* attributes.
 *   - Storage denial disables persistence ONLY: resolution and in-page
 *     switching keep working from module state; the theme never changes
 *     because storage threw.
 *
 * On every ACTUAL resolved-theme change this dispatches ONE
 * `okf-loom:themeChanged` CustomEvent on window (no duplicate/no-op events)
 * with detail {theme, previousTheme, family, mode, resolvedMode,
 * previousResolvedMode} — enough for the graph canvas re-sync and for
 * light/dark-sensitive renderers (Mermaid) to decide whether to rerender.
 *
 * Also owns the Appearance popover wiring (#okf-theme trigger +
 * #okf-appearance-menu, server-rendered by render.py:_theme_button_html)
 * because the popover exists on wiki, graph, AND single-file pages —
 * previously each surface carried its own copy. Behaviour is unchanged in
 * this slice (open/close, option clicks, Escape, outside click); composite
 * radiogroup keyboard behaviour is a separate slice.
 */
(function () {
  "use strict";

  // Idempotent: the asset can be both linked and inlined in exotic
  // override setups; the first execution wins.
  if (window.OKFLoomTheme) return;

  var root = document.documentElement;

  var FAMILIES = ["swiss", "technical"];
  var MODES = ["auto", "light", "dark"];
  // KEEP IN SYNC with scripts/okf_loom/theme.py (EXPLICIT_THEMES /
  // LEGACY_THEME_MIGRATIONS) — tests/test_theme_contract.py enforces parity.
  var THEMES = ["swiss-light", "swiss-dark", "technical-light", "technical-dark"];
  var LEGACY_THEMES = {
    light: "technical-light", dark: "technical-dark",
    pastel: "swiss-light", sepia: "swiss-light", midnight: "technical-dark",
  };

  var FAMILY_KEY = "okf-theme-family";
  var MODE_KEY = "okf-theme-mode";
  var LEGACY_KEY = "okf-theme";

  // Validated persisted modifiers (default = attribute/key absent).
  var MODIFIERS = {
    contrast: { attr: "data-okf-contrast", key: "okf-contrast", values: ["high", "soft"], def: "high" },
    border: { attr: "data-okf-border", key: "okf-border", values: ["on", "muted", "off"], def: "on" },
  };

  // ---- Storage (denial-safe) -------------------------------------------
  // Every access is guarded: a throwing localStorage (privacy mode, denied
  // permission, file:// quirks) turns persistence off and nothing else.
  function readKey(k) {
    try { return localStorage.getItem(k); } catch (e) { return null; }
  }
  function writeKey(k, v) {
    try { localStorage.setItem(k, v); } catch (e) {}
  }
  function removeKey(k) {
    try { localStorage.removeItem(k); } catch (e) {}
  }
  function pick(value, allowed) {
    return allowed.indexOf(value) >= 0 ? value : null;
  }

  // ---- Configured preference (captured before any client write) ---------
  var configFamily = null;
  var configMode = null;
  (function captureConfigured() {
    // Server-rendered data-theme (viewer config.json "theme", concrete
    // only) — read before this script mutates the attribute.
    var t = pick(root.getAttribute("data-theme"), THEMES);
    if (!t) {
      // Studio bootstrap (served pages): studio.theme supports "auto" plus
      // the concrete themes. "auto" carries no family/mode preference — it
      // IS the Swiss Auto/OS fallback, so only concrete values register.
      var boot = document.getElementById("okf-studio-bootstrap");
      if (boot) {
        try { t = pick(JSON.parse(boot.textContent || "null").theme, THEMES); } catch (e) {}
      }
    }
    if (t) {
      var sep = t.lastIndexOf("-");
      configFamily = t.slice(0, sep);
      configMode = t.slice(sep + 1);
    }
  })();

  // ---- User preference (canonical keys; legacy migrated once) -----------
  // In-page state: read once at boot, written through on user changes, so
  // storage denial degrades to session-only preferences deterministically.
  //
  // Corruption policy (deliberate asymmetry with the modifiers below): an
  // unrecognized canonical value is IGNORED per dimension (that dimension
  // falls back to configured/default) but the raw key is RETAINED — its
  // presence is the migration gate, and deleting it would let a stale
  // legacy mirror be re-read as authority on the next boot.
  var rawFamily = readKey(FAMILY_KEY);
  var rawMode = readKey(MODE_KEY);
  var userFamily = pick(rawFamily, FAMILIES);
  var userMode = pick(rawMode, MODES);

  if (rawFamily === null && rawMode === null) {
    // One-time legacy migration — only while NEITHER canonical key exists;
    // once either does, they are the sole authority and the legacy key is a
    // write-only mirror.
    var legacy = readKey(LEGACY_KEY);
    if (legacy && LEGACY_THEMES[legacy]) legacy = LEGACY_THEMES[legacy];
    legacy = pick(legacy, THEMES);
    if (legacy) {
      var sep = legacy.lastIndexOf("-");
      // Old model: a stored concrete theme was an explicit pinned choice, so
      // it migrates to explicit family AND explicit mode (not auto). The
      // parsed preference lands in module state FIRST: if storage turned
      // write-only since the legacy value was saved, the writes below fail
      // silently and this page still resolves the user's preference.
      userFamily = legacy.slice(0, sep);
      userMode = legacy.slice(sep + 1);
      writeKey(FAMILY_KEY, userFamily);
      writeKey(MODE_KEY, userMode);
      writeKey(LEGACY_KEY, legacy); // normalize a retired name in the mirror
    }
  } else {
    // Canonical keys exist: reconcile the write-only mirror so pages built
    // by older versions never read a stale/conflicting value. The mirror is
    // REMOVED unless the user state is a FULLY explicit concrete theme
    // (family AND mode both valid) — partial preferences (family-only,
    // mode-only) and corrupt values fall back per dimension, and a stale
    // concrete mirror must never survive that. Only USER state is ever
    // written: configured/fallback dimensions are NOT synthesized into a
    // mirror (a configured dark mode must not become an explicit-looking
    // legacy pin while canonical state is partial).
    var rawMirror = readKey(LEGACY_KEY);
    if (userMode === "auto" || !(userFamily && userMode)) {
      if (rawMirror !== null) removeKey(LEGACY_KEY);
    } else {
      var want = userFamily + "-" + userMode;
      if (rawMirror !== want) writeKey(LEGACY_KEY, want);
    }
  }

  // ---- Resolution (derived only; never persisted) ------------------------
  function effectiveFamily() { return userFamily || configFamily || "swiss"; }
  function effectiveMode() { return userMode || configMode || "auto"; }
  function osDark() {
    return !!(window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  }
  function resolvedTheme() {
    var mode = effectiveMode();
    var dark = mode === "auto" ? osDark() : mode === "dark";
    return effectiveFamily() + (dark ? "-dark" : "-light");
  }
  function resolvedModeOf(theme) {
    return theme && theme.indexOf("-dark") >= 0 ? "dark" : "light";
  }

  var appliedTheme = pick(root.getAttribute("data-theme"), THEMES);
  function apply() {
    var next = resolvedTheme();
    var prev = appliedTheme;
    root.setAttribute("data-theme", next);
    reflectMenu();
    if (next === prev) return; // no-op: no duplicate event
    appliedTheme = next;
    try {
      window.dispatchEvent(new CustomEvent("okf-loom:themeChanged", {
        detail: {
          theme: next,
          previousTheme: prev,
          family: effectiveFamily(),
          mode: effectiveMode(),
          resolvedMode: resolvedModeOf(next),
          previousResolvedMode: prev ? resolvedModeOf(prev) : null,
        },
      }));
    } catch (e) {}
  }

  function persistPreference() {
    if (userFamily) writeKey(FAMILY_KEY, userFamily);
    if (userMode) writeKey(MODE_KEY, userMode);
    // Compatibility mirror: concrete only while the effective mode is
    // explicit; removed while Auto so older same-origin pages (which treat
    // the key's absence as auto) keep following the OS.
    var mode = effectiveMode();
    if (mode !== "auto") writeKey(LEGACY_KEY, effectiveFamily() + "-" + mode);
    else removeKey(LEGACY_KEY);
  }

  // ---- Preference setters (the only writers) -----------------------------
  function setFamily(family) {
    if (FAMILIES.indexOf(family) < 0) return;
    userFamily = family;
    persistPreference();
    apply();
  }
  function setMode(mode) {
    // "auto" is persisted explicitly: a chosen Auto outranks a configured
    // concrete default, unlike the absence of any preference.
    if (MODES.indexOf(mode) < 0) return;
    userMode = mode;
    persistPreference();
    apply();
  }
  function setTheme(theme) {
    // Concrete pick (studio command palette): explicit family AND mode.
    if (THEMES.indexOf(theme) < 0) return;
    var sep = theme.lastIndexOf("-");
    userFamily = theme.slice(0, sep);
    userMode = theme.slice(sep + 1);
    persistPreference();
    apply();
  }

  // ---- Modifiers (contrast / border) -------------------------------------
  function getModifier(kind) {
    var spec = MODIFIERS[kind];
    if (!spec) return null;
    return pick(root.getAttribute(spec.attr), spec.values) || spec.def;
  }
  function setModifier(kind, value, persist) {
    var spec = MODIFIERS[kind];
    if (!spec) return;
    value = pick(value, spec.values) || spec.def; // invalid → default
    if (value !== spec.def) root.setAttribute(spec.attr, value);
    else root.removeAttribute(spec.attr);
    if (persist !== false) {
      if (value !== spec.def) writeKey(spec.key, value);
      else removeKey(spec.key);
    }
    reflectMenu();
  }

  // ---- Appearance popover (Round 2 §5.3) ----------------------------------
  // Server-rendered by render.py:_theme_button_html on wiki, graph, and
  // single-file pages; wired here once instead of per surface. aria-checked
  // is corrected at boot (the server cannot read localStorage).
  var trigger = document.getElementById("okf-theme");
  var menu = document.getElementById("okf-appearance-menu");
  var wrap = trigger && trigger.closest ? trigger.closest(".okf-appearance") : null;

  function reflectMenu() {
    if (!menu) return;
    var state = {
      family: effectiveFamily(), mode: effectiveMode(),
      contrast: getModifier("contrast"), border: getModifier("border"),
    };
    var opts = menu.querySelectorAll(".okf-appearance__opt"), i, o;
    for (i = 0; i < opts.length; i++) {
      o = opts[i];
      o.setAttribute("aria-checked",
        state[o.getAttribute("data-okf-set")] === o.getAttribute("data-okf-val") ? "true" : "false");
    }
  }
  function openMenu() {
    if (!menu) return;
    menu.hidden = false;
    if (trigger) trigger.setAttribute("aria-expanded", "true");
    reflectMenu();
  }
  function closeMenu() {
    if (!menu) return;
    menu.hidden = true;
    if (trigger) trigger.setAttribute("aria-expanded", "false");
  }

  if (trigger) trigger.addEventListener("click", function (e) {
    e.stopPropagation();
    if (menu && menu.hidden) openMenu(); else closeMenu();
  });
  if (menu) menu.addEventListener("click", function (e) {
    var opt = e.target && e.target.closest ? e.target.closest(".okf-appearance__opt") : null;
    if (!opt) return;
    var k = opt.getAttribute("data-okf-set"), v = opt.getAttribute("data-okf-val");
    if (k === "family") setFamily(v);
    else if (k === "mode") setMode(v);
    else setModifier(k, v); // contrast | border
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && menu && !menu.hidden) {
      closeMenu();
      if (trigger) trigger.focus();
    }
  });
  document.addEventListener("click", function (e) {
    if (menu && !menu.hidden && wrap && !wrap.contains(e.target)) closeMenu();
  });

  // ---- Boot ---------------------------------------------------------------
  // Post-paint, same timing as the previous per-surface reads (inline
  // scripts are CSP-blocked on the served templates, so there is no
  // pre-paint hook; the server-rendered data-theme prevents FOUC).
  // Modifiers self-heal: a corrupt stored value is DELETED (unlike the
  // canonical theme keys, no migration gate depends on its presence) and
  // the default applies.
  (function bootModifiers() {
    for (var kind in MODIFIERS) {
      var raw = readKey(MODIFIERS[kind].key);
      if (raw !== null && pick(raw, MODIFIERS[kind].values) === null) {
        removeKey(MODIFIERS[kind].key);
      }
      setModifier(kind, raw, false);
    }
  })();
  apply();

  // Follow the OS while Auto — every change re-resolves and never persists,
  // so consecutive prefers-color-scheme flips keep being honoured.
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onSchemeChange = function () {
      if (effectiveMode() === "auto") apply();
    };
    if (mq.addEventListener) mq.addEventListener("change", onSchemeChange);
    else if (mq.addListener) mq.addListener(onSchemeChange);
  }

  window.OKFLoomTheme = {
    THEMES: THEMES.slice(),
    FAMILIES: FAMILIES.slice(),
    MODES: MODES.slice(),
    FAMILY_KEY: FAMILY_KEY,
    MODE_KEY: MODE_KEY,
    LEGACY_KEY: LEGACY_KEY,
    resolvedTheme: resolvedTheme,
    getState: function () {
      return {
        theme: resolvedTheme(),
        family: effectiveFamily(),
        mode: effectiveMode(),
        userFamily: userFamily,
        userMode: userMode,
        configuredFamily: configFamily,
        configuredMode: configMode,
        contrast: getModifier("contrast"),
        border: getModifier("border"),
      };
    },
    setFamily: setFamily,
    setMode: setMode,
    setTheme: setTheme,
    setModifier: setModifier,
  };
})();
