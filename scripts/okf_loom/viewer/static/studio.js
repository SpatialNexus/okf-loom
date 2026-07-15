/* OKF Studio - the studio UI (spec §8 / §9 / §12 / §13).
 *
 * Owns the presentation layer; live.js owns the SSE transport + the
 * no-refresh body patch. studio.js subscribes to window.okfLoomLive for
 * presence/activity/comment/graph events and renders every studio surface.
 *
 * Surfaces:
 *   - Studio bar: presence chip, view-mode switch (Rendered|Source|Split),
 *     Comments / Changes panel toggles, connection indicator, palette btn.
 *   - Comments (§9): selection → "Comment for agent" affordance, composer
 *     with optimistic posting, margin markers, panel listing open/resolved
 *     per concept + across the bundle, filterable.
 *   - Presence (current spec §12): status chip; focused concept highlighted.
 *   - Change list (§12.2): live timeline from /__data/events with one-click
 *     Undo (single + group) where undoable; filterable.
 *   - Command palette (§13.4): Ctrl/Cmd-K, keyboard-first.
 *   - Extension API (§13.6): okfLoomStudio.register(kind, impl). Wired kinds:
 *     {panel, viewMode}. Reserved (forward-compat, accepted + warned):
 *     {toolbar, graphDecorator, suggestionRenderer}.
 *   - Themes (§13.5): technical-light/technical-dark/swiss-light/swiss-dark
 *     (+ auto), honouring saved choice + bootstrap + OS pref, with legacy
 *     migration for retired theme names.
 *
 * Security: untrusted strings (comment bodies, summaries, ids) go through
 * textContent only. The only innerHTML assignment is the server-rendered
 * concept body (same escaped renderer as the initial page - §7.3). All
 * mutating fetches attach X-OKF-Token from window.__OKF_LOOM_STUDIO__.token.
 *
 * Vanilla ES module, no framework, no bundler. Degrades gracefully: a
 * no-op when window.__OKF_LOOM_STUDIO__ is absent.
 */
(function () {
  "use strict";

  // CSP-safe bootstrap read (see live.js for rationale). studio.js reuses
  // window.__OKF_LOOM_STUDIO__ once live.js publishes it, but reads the data
  // block directly too so the two modules are independently robust.
  function readBoot() {
    if (window.__OKF_LOOM_STUDIO__ && typeof window.__OKF_LOOM_STUDIO__ === "object") {
      return window.__OKF_LOOM_STUDIO__;
    }
    const node = document.getElementById("okf-studio-bootstrap");
    if (node) {
      try {
        const cfg = JSON.parse(node.textContent || "{}");
        window.__OKF_LOOM_STUDIO__ = cfg;
        return cfg;
      } catch (e) { /* fall through */ }
    }
    return null;
  }
  const BOOT = readBoot();
  if (!BOOT) return;
  // iter1 CRI-019 (revised): okf-studio-booted is NOT stamped here. The old
  // code added it synchronously at module evaluation — before boot() ran —
  // which permanently hid the fallback banner even when boot() subsequently
  // threw (the theme.js watchdog saw the class at DOMContentLoaded and
  // skipped the unavailable settlement). Now the class is stamped ONLY after
  // boot() completes successfully; see the _runBoot wrapper at the bottom of
  // this module. If boot() throws, okf-studio-unavailable is stamped instead
  // so the banner is revealed. The theme.js watchdog catches the remaining
  // case (studio.js blocked/missing or no bootstrap) at DOMContentLoaded.
  const EDIT = BOOT.edit !== false; // read-only kiosk when false
  const TOKEN = BOOT.token || "";
  const REDUCED_MOTION =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ====================================================================
  // 0. Helpers
  // ====================================================================
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));

  function el(tag, attrs, kids) {
    const n = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      const v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k === "html") n.innerHTML = v; // ONLY for trusted/server HTML
      else if (k === "dataset") for (const d in v) n.dataset[d] = v[d];
      else if (k === "on" && typeof v === "object") for (const ev in v) n.addEventListener(ev, v[ev]);
      else if (k === "hidden") {
        // Treat "", true, "hidden", "until-found" as present (boolean IDL
        // property - assigning "" directly would coerce to false / visible).
        n.hidden = (v === true || v === "" || v === "hidden" || v === "until-found");
      }
      else if (k in n && k !== "list") {
        try { n[k] = v; } catch (e) { n.setAttribute(k, v); }
      } else n.setAttribute(k, v);
    }
    if (kids) appendKids(n, kids);
    return n;
  }
  function appendKids(n, kids) {
    if (!kids) return;
    if (!Array.isArray(kids)) kids = [kids];
    kids.forEach((k) => {
      if (k == null) return;
      if (typeof k === "string" || typeof k === "number") n.appendChild(document.createTextNode(String(k)));
      else n.appendChild(k);
    });
  }

  async function tokenFetch(url, opts) {
    opts = opts || {};
    // §9.4 conflict UX (INTENT-008): preserve the ORIGINAL body object so a
    // 409 with ``conflict: true`` from /__apply can surface a modal whose
    // "Take the agent's" action re-submits the apply WITHOUT ``expected_rev``
    // (force-overwrite). The body is JSON-stringified just below; we hold
    // the live object reference here.
    const originalBodyObj = (opts.body && typeof opts.body !== "string") ? opts.body : null;
    const headers = Object.assign({ "X-OKF-Token": TOKEN }, opts.headers || {});
    if (opts.body && typeof opts.body !== "string") {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    opts.headers = headers;
    const res = await fetch(url, opts);
    // §9.4: detect a conflict response from /__apply and surface the modal.
    // The caller's await resolves to a Response chosen by the user action:
    //   - "Keep mine" / Esc → the original 409 Response (caller sees !ok).
    //   - "Take the agent's" → a fresh fetch WITHOUT expected_rev.
    if (res.status === 409 && url === "/__apply") {
      try {
        const cloned = res.clone();
        const data = await cloned.json();
        if (data && data.conflict) {
          return showConflictModal({
            data, url, opts, originalBodyObj, originalResponse: res,
          });
        }
      } catch (e) { /* not JSON or no conflict field — fall through */ }
    }
    return res;
  }

  function currentConceptId() {
    let p = window.location.pathname.replace(/^\/+/, "").replace(/\/+$/, "");
    if (p.endsWith(".md")) p = p.slice(0, -3);
    return p;
  }
  const isConceptPage = () => !!document.querySelector("article.okf-page__main");

  function fmtTime(ts) {
    if (!ts) return "";
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return String(ts);
      return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch (e) { return String(ts); }
  }
  // Phase 5: human relative time for the index recency rail ("4m ago").
  function fmtAgo(ts) {
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return "";
      const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
      if (s < 60) return "just now";
      if (s < 3600) return Math.round(s / 60) + "m ago";
      if (s < 86400) return Math.round(s / 3600) + "h ago";
      return Math.round(s / 86400) + "d ago";
    } catch (e) { return ""; }
  }
  function shortId(id) { return id ? id.slice(-6) : ""; }

  // ---- toast region ----------------------------------------------------
  let toastRegion;
  function toast(msg, opts) {
    opts = opts || {};
    if (!toastRegion) {
      toastRegion = el("div", { class: "okf-toast-region", role: "status", "aria-live": "polite", "aria-atomic": "false" });
      document.body.appendChild(toastRegion);
    }
    const node = el("div", { class: "okf-toast", dataset: { tone: opts.tone || "" } });
    node.appendChild(el("span", { class: "okf-toast__msg" }));
    node.querySelector(".okf-toast__msg").innerHTML = ""; // safety
    if (typeof msg === "string") {
      node.querySelector(".okf-toast__msg").textContent = msg;
    } else if (msg && msg.nodeType) {
      node.querySelector(".okf-toast__msg").appendChild(msg);
    }
    const close = el("button", { class: "okf-toast__close", type: "button", "aria-label": "Dismiss notification", text: "×" });
    node.appendChild(close);
    toastRegion.appendChild(node);
    const dismiss = () => { if (node.parentNode) node.parentNode.removeChild(node); };
    close.addEventListener("click", dismiss);
    if (!opts.sticky) setTimeout(dismiss, opts.ttl || 4500);
    return { close: dismiss, node };
  }

  // ====================================================================
  // 1. State
  // ====================================================================
  const state = {
    view: readView(),                // rendered | source | split
    conceptId: currentConceptId(),
    doc: null,                       // cached /__data/doc for the open concept
    graph: null,                     // cached /__data/graph.json
    comments: [],                    // [{id, concept, anchor, state, body, claimed_by, resolved_activity, reply, ts}]
    events: [],                      // change-list rows
    presence: { state: "idle" },
    presenceHistory: [],   // iter2 G13: [{state, focus, ts}] recent transitions (cap 24)
    openPanel: null,                 // current slide-over panel id
    draftBody: "",                   // preserved across view toggles + patches
    draftAnchor: { kind: "concept", ref: currentConceptId() },
    selectionDraft: null,             // last visible text selection for the comment affordance
    filters: { actor: "", concept: "", action: "" },
    nextCommentSeq: 1,               // for local optimistic ids
    commentView: loadCommentView(),  // panel prefs (sort/filter/expand)
  };
  function readView() {
    const q = new URLSearchParams(window.location.search).get("view");
    if (q === "source" || q === "split") return q;
    return "rendered";
  }

  // ====================================================================
  // 2. Themes (§13.5)
  // ====================================================================
  // Theme state is owned by theme.js (window.OKFLoomTheme), loaded before
  // this module. It boots the resolved theme (saved preference > configured
  // — including this page's studio bootstrap theme — > Swiss Auto/OS),
  // follows the OS while Auto, and owns the Appearance popover. Studio only
  // issues preference changes from the command palette through that API.

  // ====================================================================
  // 3. Studio bar
  // ====================================================================
  // Round 2: the studio controls live in a bottom bordered-button TOOLBAR
  // (Editorial Workbench footer) — on-demand actions (Watching / Commands /
  // view-switch / Focus) cluster on the left and read as real bordered
  // buttons; ambient state (presence / ◆N concepts / ●Live) clusters on the
  // right, separated by a thin divider (studio.css).
  const bar = el("div", { class: "okf-studio-bar okf-studio-bar--status", role: "region", "aria-label": "Studio status" });
  const leftGroup = el("div", { class: "okf-studio-bar__group" });
  const rightGroup = el("div", { class: "okf-studio-bar__group okf-studio-bar__group--right" });

  // Presence chip
  const presenceDot = el("span", { class: "okf-presence__dot", "aria-hidden": "true" });
  const presenceLabel = el("span", { class: "okf-presence__label" });
  presenceLabel.appendChild(el("span", { class: "okf-presence__actor", text: "Agent" }));
  presenceLabel.appendChild(document.createTextNode(" idle"));
  const presenceChip = el("span", { class: "okf-presence", "data-state": "idle", role: "status",
    "aria-live": "polite", "aria-label": "Agent presence: idle" },
    [presenceDot, presenceLabel]);
  // Appended to rightGroup (ambient) in the assembly below.

  // iter2 G11 (§3 watch question): an "Agent watching" switch in the studio
  // bar. The user can toggle whether the agent proactively watches + enriches
  // the bundle any time (§3 step 3/4). Toggling on POSTs /__presence
  // {actor:"agent", state:"watching"}; off POSTs {state:"idle"}. It also
  // reflects the agent's live presence (renderPresence syncs aria-pressed),
  // so if the agent starts/stops watching via the CLI the switch follows.
  // Visible label "Watching" + an eye glyph + an accessible name.
  const watchingToggle = el("button", {
    type: "button",
    class: "okf-studiobtn okf-watch-toggle",
    "aria-pressed": "false",
    // iter3 CRI3-010: was a 14-word sentence ("Agent watching. Toggle
    // whether the agent proactively watches and enriches the bundle.").
    // aria-label replaces the visible text for AT users on every focus,
    // so it must be CONCISE (identity + state), not explanatory. The
    // explanation already lives in `title` (tooltip on hover/focus) and
    // the visible "Watching" label supplies context. The label is
    // re-rendered with the live state by renderPresence, so this initial
    // value is overwritten on first presence echo.
    "aria-label": "Agent watching, currently off",
    title: "Toggle proactive agent watching (§3)",
  });
  watchingToggle.appendChild(el("span", { class: "okf-watch-toggle__icon", "aria-hidden": "true", text: "\u25C9" }));
  watchingToggle.appendChild(el("span", { class: "okf-watch-toggle__label", text: "Watching" }));
  watchingToggle.addEventListener("click", () => {
    const nowOn = watchingToggle.getAttribute("aria-pressed") !== "true";
    watchingToggle.setAttribute("aria-pressed", nowOn ? "true" : "false");
    // Fire-and-forget; the presence SSE echoes back and renderPresence
    // re-asserts the canonical state (so a failed POST rolls the toggle back).
    tokenFetch("/__presence", {
      method: "POST",
      body: { actor: "agent", state: nowOn ? "watching" : "idle" },
    }).catch(() => {
      // On network failure, revert the optimistic toggle.
      watchingToggle.setAttribute("aria-pressed", nowOn ? "false" : "true");
      toast("Could not update agent watching state.", { tone: "error" });
    });
  });
  // Appended to leftGroup (actions) in the assembly below.

  // Bundle-size stat (ambient dash): the Diátaxis nav lists every concept, so
  // its link count is the bundle size. Present on concept pages only. Named
  // (not appended here) so the assembly below can place it in rightGroup.
  const conceptCount = document.querySelectorAll(".okf-nav__link").length;
  const conceptStatseg = el("span", { class: "okf-statseg", title: conceptCount + " concepts in this bundle" }, [
    el("span", { class: "okf-statseg__mark", "aria-hidden": "true", text: "◆" }),
    document.createTextNode(" " + conceptCount + " concepts"),
  ]);

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

  // Connection indicator (driven by live.js hub). iter1 CRI-015: aria-live
  // so "Reconnecting…" / "Live" / "Offline" state changes are announced to
  // assistive tech (presence + toasts already were; the conn chip was the
  // odd one out).
  const connDot = el("span", { class: "okf-conn__dot", "aria-hidden": "true" });
  const connLabel = el("span", { text: "Live" });
  const connChip = el("span", { class: "okf-conn", "data-state": "online",
    title: "Live updates connection", role: "status", "aria-live": "polite",
    "aria-label": "Live updates connection: online" }, [connDot, connLabel]);

  // View-mode switch (concept pages only)
  const viewSwitch = el("div", { class: "okf-viewswitch", role: "group", "aria-label": "View mode" });
  function viewBtn(mode, label, desc) {
    const b = el("button", { type: "button", class: "okf-viewswitch__btn",
      "aria-pressed": state.view === mode ? "true" : "false", text: label,
      title: desc || label });
    b.addEventListener("click", () => setView(mode));
    b.dataset.mode = mode;
    return b;
  }
  const viewBtns = {
    rendered: viewBtn("rendered", "Rendered", "Show the rendered page"),
    source: viewBtn("source", "Source", "Show the raw markdown source"),
    split: viewBtn("split", "Split", "Show rendered and source side by side"),
  };
  Object.keys(viewBtns).forEach((k) => viewSwitch.appendChild(viewBtns[k]));

  // Editorial Workbench / SPEC §8: NO OS glyph (no ⌘/⊞). The trigger says
  // what it does ("Commands") with an OS-neutral plain keycap. The functional
  // binding stays Ctrl/Cmd-K (wirePaletteKeys) — only the rendered cue is
  // neutral. macOS users can also open it via the "/"-then-palette path.
  const paletteHint = "Ctrl K";
  const paletteBtn = el("button", { type: "button", class: "okf-studiobtn okf-palettebtn",
    "aria-label": "Open the command palette (Control or Command K)",
    title: "Search pages and run commands  (" + paletteHint + ")" },
    [document.createTextNode("Commands "),
     el("kbd", { class: "okf-kbd", "aria-hidden": "true", text: paletteHint })]);
  paletteBtn.addEventListener("click", openPalette);

  // Round 2 carryover: a direct studio opener for pages/viewports without the
  // rail. Opens Comments on a concept page (mobile), Changes elsewhere (the
  // global feed; a non-concept page has no per-concept comments).
  const studioBtn = el("button", { type: "button", class: "okf-studiobtn okf-studio-open-btn",
    "aria-controls": "okf-panel", title: "Open the studio panel", "aria-label": "Open studio panel" },
    [document.createTextNode("Studio")]);
  studioBtn.addEventListener("click", function () {
    openPanel(isConceptPage() ? "comments" : "changes");
  });

  // Round 2: Focus toggle (Workbench <-> Focus reading mode). Assigns the
  // module-scope `focusBtn` (declared further below, alongside setFocus/
  // toggleFocus) so setFocus can sync its aria-pressed; wired straight to
  // the existing toggleFocus (Task 3 already implements the split coupling
  // — this button does not reimplement any of that state machine).
  focusBtn = el("button", { type: "button", class: "okf-studiobtn okf-focus-btn",
    "aria-pressed": "false", "aria-label": "Toggle focus mode (wide, no chrome)",
    title: "Focus: collapse nav + rail for a wide reading/split view" },
    [document.createTextNode("Focus")]);
  focusBtn.addEventListener("click", toggleFocus);

  // Assemble bar. Comments/Changes now live in the rail; the dock toggle is
  // retired. Round 2: actions left, ambient right, divider between.
  // LEFT (actions): Watching · Commands · [view-switch] · Focus
  leftGroup.appendChild(watchingToggle);
  leftGroup.appendChild(paletteBtn);
  // view-switch + Focus appended in mountBar (concept pages only), so DOM
  // order still reads L->R: Watching, Commands, Rendered/Source/Split, Focus.
  // RIGHT (ambient): presence · ◆ N concepts · ● Live
  rightGroup.appendChild(presenceChip);
  if (conceptCount > 0) rightGroup.appendChild(conceptStatseg);
  rightGroup.appendChild(validationStatseg);
  rightGroup.appendChild(connChip);
  bar.appendChild(leftGroup);
  bar.appendChild(el("span", { class: "okf-studio-bar__divider", "aria-hidden": "true" }));
  bar.appendChild(rightGroup);

  function mountBar() {
    // Bottom status strip: append as the last in-flow child of the flex-column
    // body so it pins to the viewport bottom (sticky, see studio.css).
    document.body.appendChild(bar);
      // Round 2 carryover: show the direct Studio opener wherever the rail is
      // ABSENT — non-concept pages (any width) OR concept pages on mobile
      // (<=900). Desktop concept pages have the rail, so no footer duplication.
      // (Test the width predicate directly: body.okf-has-rail is now
      // server-rendered on ALL concept pages, so the class alone can't tell
      // desktop-rail from mobile-no-rail.) Placed before the concept-only view
      // controls so order reads Watch · Commands · Studio · [Rendered/Source/
      // Split · Focus].
      var railPresent = isConceptPage() && window.innerWidth > 900;
    if (!railPresent) leftGroup.appendChild(studioBtn);
    if (isConceptPage()) {
      leftGroup.appendChild(viewSwitch);
      leftGroup.appendChild(focusBtn);
    }
  }

  // Nav-collapse (Editorial Workbench §3.2): a toggle in the top bar collapses
  // the concept-page sidebar to 0 for a full-width read. Persisted so the
  // choice survives navigation. Only mounted on pages that have the sidebar.
  const NAV_COLLAPSE_KEY = "okf-nav-collapsed";
  function mountNavToggle() {
    if (!isConceptPage()) return;
    const topbar = $(".okf-topbar");
    if (!topbar) return;
    let collapsed = false;
    try { collapsed = localStorage.getItem(NAV_COLLAPSE_KEY) === "1"; } catch (e) {}
    document.body.classList.toggle("okf-nav-collapsed", collapsed);
    const btn = el("button", {
      type: "button", class: "okf-navtoggle",
      "aria-label": "Toggle navigation", "aria-pressed": collapsed ? "true" : "false",
      title: "Collapse navigation for a full-width read",
    });
    btn.innerHTML = svgIcon("navCollapse");
    btn.addEventListener("click", function () {
      collapsed = !collapsed;
      document.body.classList.toggle("okf-nav-collapsed", collapsed);
      btn.setAttribute("aria-pressed", collapsed ? "true" : "false");
      try { localStorage.setItem(NAV_COLLAPSE_KEY, collapsed ? "1" : "0"); } catch (e) {}
    });
    topbar.insertBefore(btn, topbar.firstChild);
  }

  // ====================================================================
  // 4. View modes (§8) + applyDoc(doc)
  // ====================================================================
  let sourcePre = null;
  let viewWrap = null;
  let splitDivider = null;
  // iter2 G8: split-pane niceties — draggable divider (pointer + keyboard)
  // and proportional synced scroll between the rendered + source panes.
  // splitPct is the rendered-pane fraction (0.2–0.8). Persisted to
  // localStorage so a user's preferred split survives reloads.
  const SPLIT_MIN = 0.2, SPLIT_MAX = 0.8;
  let splitPct = 0.5;
  try {
    const saved = parseFloat(localStorage.getItem("okf-split-pct"));
    if (!isNaN(saved) && saved >= SPLIT_MIN && saved <= SPLIT_MAX) splitPct = saved;
  } catch (e) {}
  let splitSyncGuard = false;  // prevents A→B→A scroll-feedback loops

  function applySplitPct(pct) {
    splitPct = Math.max(SPLIT_MIN, Math.min(SPLIT_MAX, pct));
    // Round 2: the split grid now consumes --okf-split-pct as a PERCENTAGE
    // (rendered-pane width); source fills the rest via minmax(0,1fr).
    if (viewWrap) viewWrap.style.setProperty("--okf-split-pct", (splitPct * 100).toFixed(2) + "%");
    if (splitDivider) {
      splitDivider.setAttribute("aria-valuenow", String(Math.round(splitPct * 100)));
      splitDivider.setAttribute("aria-valuetext",
        "Rendered pane " + Math.round(splitPct * 100) + " percent, source " + Math.round((1 - splitPct) * 100) + " percent");
    }
  }

  function ensureViewWrap() {
    if (viewWrap) return;
    const body = $(".okf-page__body");
    if (!body) return;
    viewWrap = el("div", { class: "okf-view", dataset: { okfView: state.view } });
    body.parentNode.insertBefore(viewWrap, body);
    viewWrap.appendChild(body);
    // iter2 G8: draggable divider between the rendered + source panes. Lives
    // in the DOM always but only visible/active in split mode (CSS hides it
    // otherwise + under 900px). role=separator + aria-orientation so AT + kb
    // users can resize with Arrow Left / Right (3% per press, Shift = 10%).
    splitDivider = el("div", {
      class: "okf-split__divider",
      role: "separator",
      "aria-orientation": "vertical",
      "aria-label": "Resize rendered and source panes. Arrow keys to adjust.",
      "aria-valuemin": "20", "aria-valuemax": "80", "aria-valuenow": "50",
      tabindex: "0",
    });
    viewWrap.appendChild(splitDivider);
    sourcePre = el("pre", { class: "okf-source", hidden: state.view === "rendered",
      "aria-label": "Source markdown (read-only)" });
    viewWrap.appendChild(sourcePre);
    wireSplitDivider();
    wireSplitScroll();
    applySplitPct(splitPct);
  }

  // Draggable divider: pointer drag + keyboard arrows. The drag uses
  // pointer events (works for mouse + touch + pen) and updates the split
  // ratio from the pointer's X within the viewWrap bounding rect.
  function wireSplitDivider() {
    if (!splitDivider || !viewWrap) return;
    let dragging = false;
    splitDivider.addEventListener("pointerdown", (e) => {
      if (!isSplitView()) return;
      dragging = true;
      splitDivider.setPointerCapture(e.pointerId);
      e.preventDefault();
    });
    splitDivider.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      const rect = viewWrap.getBoundingClientRect();
      if (!rect.width) return;
      const pct = (e.clientX - rect.left) / rect.width;
      applySplitPct(pct);
    });
    const endDrag = (e) => {
      if (!dragging) return;
      dragging = false;
      try { splitDivider.releasePointerCapture(e.pointerId); } catch (err) {}
      try { localStorage.setItem("okf-split-pct", String(splitPct)); } catch (err) {}
    };
    splitDivider.addEventListener("pointerup", endDrag);
    splitDivider.addEventListener("pointercancel", endDrag);
    // Keyboard: Arrow Left/Right adjust 3%, Shift+Arrow 10%. Home/End reset
    // to the extremes (clamped to SPLIT_MIN/MAX).
    splitDivider.addEventListener("keydown", (e) => {
      if (!isSplitView()) return;
      const step = e.shiftKey ? 0.10 : 0.03;
      let handled = true;
      if (e.key === "ArrowLeft") applySplitPct(splitPct - step);
      else if (e.key === "ArrowRight") applySplitPct(splitPct + step);
      else if (e.key === "Home") applySplitPct(SPLIT_MIN);
      else if (e.key === "End") applySplitPct(SPLIT_MAX);
      else handled = false;
      if (handled) {
        e.preventDefault();
        try { localStorage.setItem("okf-split-pct", String(splitPct)); } catch (err) {}
      }
    });
  }

  // Proportional synced scroll: scrolling one pane scrolls the other by the
  // same fraction of its scroll range. The guard flag breaks the feedback
  // loop (B's scroll firing back into A).
  function wireSplitScroll() {
    const body = $(".okf-page__body");
    if (!body || !sourcePre) return;
    const sync = (src, dst) => {
      if (splitSyncGuard) return;
      if (!isSplitView()) return;
      const max = src.scrollHeight - src.clientHeight;
      if (max <= 0) return;
      const ratio = src.scrollTop / max;
      const dstMax = dst.scrollHeight - dst.clientHeight;
      if (dstMax > 0) {
        splitSyncGuard = true;
        dst.scrollTop = ratio * dstMax;
        splitSyncGuard = false;
      }
    };
    body.addEventListener("scroll", () => sync(body, sourcePre), { passive: true });
    sourcePre.addEventListener("scroll", () => sync(sourcePre, body), { passive: true });
  }

  function isSplitView() {
    return !!viewWrap && viewWrap.dataset.okfView === "split"
      && window.matchMedia("(min-width: 901px)").matches;
  }

  function setView(mode) {
    if (mode !== "rendered" && mode !== "source" && mode !== "split") return;
    state.view = mode;
    // Round 2: Split auto-enters Focus (drops the __main cap so the panes fill
    // the width — the real split fix); leaving Split exits Focus only if Split
    // was what turned it on (a manual toggleFocus detaches from this).
    if (mode === "split") {
      if (!isFocus()) { focusFromSplit = true; setFocus(true); }
      closePanel();               // overlays would fight the wide split
    } else if (focusFromSplit) {
      focusFromSplit = false; setFocus(false);
    }
    ensureViewWrap();
    if (viewWrap) viewWrap.dataset.okfView = mode;
    if (sourcePre) sourcePre.hidden = (mode === "rendered");
    if (splitDivider) splitDivider.hidden = (mode !== "split");
    Object.keys(viewBtns).forEach((k) => viewBtns[k].setAttribute("aria-pressed", k === mode ? "true" : "false"));
    // Deep-link via ?view=. Preserves everything else (no reload).
    const url = new URL(window.location.href);
    if (mode === "rendered") url.searchParams.delete("view");
    else url.searchParams.set("view", mode);
    window.history.replaceState(null, "", url.toString());
    // Source/split need the raw markdown; load lazily.
    if (mode !== "rendered") ensureSourceLoaded();
  }

  // Editorial Workbench Round 2 — Workbench <-> Focus reading mode. Focus is a
  // net-new attribute on <html> (data-okf-focus) that collapses nav + rail +
  // frame and uncaps the reading column for Source/Split (Rendered stays at the
  // ~76ch measure, re-applied in CSS). Distinct from the graph's okf-focus-root.
  // focusBtn: a bare `var` (no initializer) — the hoisted declaration lets
  // setFocus (below) reference it, but it is CONSTRUCTED earlier, in the
  // footer toolbar section (Task 4), which runs before this line executes.
  // A `= null` initializer here would re-run at this point in the top-to-
  // bottom boot sequence and clobber that earlier assignment, so it is
  // deliberately omitted; setFocus still null-guards it defensively.
  var focusBtn;
  var focusFromSplit = false;
  function setFocus(on) {
    if (on) document.documentElement.setAttribute("data-okf-focus", "");
    else document.documentElement.removeAttribute("data-okf-focus");
    if (focusBtn) focusBtn.setAttribute("aria-pressed", on ? "true" : "false");
  }
  function isFocus() { return document.documentElement.hasAttribute("data-okf-focus"); }
  // Invariant: view==="split" ⟺ Focus on. Split needs the wide (uncapped)
  // layout, so turning Focus OFF while in split must also leave split —
  // otherwise the .okf-page__main cap returns and re-traps the panes (the exact
  // bug Task 3 fixes). Clearing focusFromSplit first makes setView("rendered")'s
  // own auto-exit branch a no-op (no double toggle / recursion).
  function toggleFocus() {
    if (isFocus()) {                                     // turning OFF
      focusFromSplit = false;
      if (state.view === "split") setView("rendered");   // drop to Rendered
      setFocus(false);
    } else {                                             // turning ON
      focusFromSplit = false;                            // manual toggle detaches from split auto-mode
      setFocus(true);
    }
  }

  function ensureSourceLoaded() {
    if (!sourcePre || sourcePre.dataset.loaded === "1") return;
    const id = state.conceptId;
    if (!id) return;
    fetch("/__data/doc?id=" + encodeURIComponent(id), { headers: { Accept: "application/json" } })
      .then((r) => r.ok ? r.json() : null)
      .then((doc) => {
        if (!doc) return;
        state.doc = doc;
        if (sourcePre) {
          sourcePre.textContent = doc.raw || "";
          sourcePre.dataset.loaded = "1";
        }
      })
      .catch((e) => console.error("[okf-studio] source load failed", e));
  }

  // Called by live.js after a `changed` on the open concept. Renders the
  // doc in the current view mode and updates title/description in place.
  // iter1 CRI-001: replaces the whole-body innerHTML swap with a block-level
  // diff that patches only the changed/moved/inserted/removed blocks, so a
  // single sentence edit no longer reads as a full-body flash. Returns true
  // so live.js knows the scoped pulse was handled here (not in its fallback).
  function applyDoc(doc, opts) {
    opts = opts || {};
    if (!doc) return false;
    state.doc = doc;
    const titleEl = $(".okf-page__title");
    if (titleEl && typeof doc.title === "string" && doc.title !== titleEl.textContent) {
      titleEl.textContent = doc.title;
    }
    const descEl = $(".okf-page__description");
    if (descEl && typeof doc.description === "string") descEl.textContent = doc.description;
    const body = $(".okf-page__body");
    let changedBlocks = [];
    if (body && typeof doc.html === "string") {
      // Server-rendered HTML from the SAME escaped renderer the page used.
      // Block-diff it against the live body instead of swapping wholesale.
      const sel = saveSelectionAcrossPatch(body);
      changedBlocks = diffAndPatchBody(body, doc.html);
      sel.restore(changedBlocks);
    }
    if (sourcePre) {
      sourcePre.textContent = doc.raw || "";
      sourcePre.dataset.loaded = "1";
    }
    // Re-bind comment affordance + re-apply text-range marks + margin markers
    // over the patched body (iter1 CRI-002). Marks survive because they are
    // re-resolved from persisted anchors after every patch.
    bindSelectionAffordance();
    applyCommentMarks();
    applyPendingDraftMark();
    rebuildMarginMarkers();
    // Scoped pulse: flash ONLY the changed blocks, not the whole body. If
    // nothing changed (e.g. a no-op re-render), no pulse at all.
    if (opts.pulse && changedBlocks.length) pulseBlocks(changedBlocks);
    // Notify renderers.js (mermaid, highlight.js, KaTeX) that the body
    // content changed — but ONLY when blocks actually changed. Firing on
    // every patch (including no-op re-renders) causes a visible flash
    // as mermaid re-renders diagrams that didn't change.
    if (changedBlocks.length > 0) {
      try { window.dispatchEvent(new CustomEvent("okf-loom:bodyPatched")); } catch (e) {}
    }
    return true; // live.js must NOT also pulse the whole body.
  }

  // ---- block-level diff + patch (iter1 CRI-001) ------------------------
  // Splits rendered HTML at block boundaries (heading / paragraph / list /
  // table / pre / blockquote / hr), aligns old vs new via LCS on a
  // normalised signature, and applies the minimal DOM mutation set. List
  // and table blocks that exist on both sides but differ recurse one level
  // to diff their <li>/<tr> children, so "agent added one item to a list"
  // swaps only that item, not the whole list. Depth is capped at 2 so a
  // pathological nested structure can't blow the stack.
  const BLOCK_SELECTOR = "h1,h2,h3,h4,h5,h6,p,ul,ol,table,pre,blockquote,hr,div";
  function blockChildren(parent) {
    const out = [];
    for (let n = parent.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 1) out.push(n);
    }
    return out;
  }
  function blockSig(el) {
    // Whitespace-collapsed text + tag + id (heading ids are stable anchors
    // for comment marks; including them keeps a renamed heading "changed").
    const tag = el.tagName.toLowerCase();
    const id = el.getAttribute("id") || "";
    // Mermaid/math blocks: after CDN rendering (mermaid.js, KaTeX), the
    // element's textContent changes from the raw source to the rendered
    // SVG/MathML output. Use the data attribute (the original source) for
    // the signature so the diff treats "rendered" and "raw" versions of
    // the SAME diagram as equal — preventing a visible flash-to-raw-text
    // on live patches that don't actually change the diagram.
    if (el.classList && (el.classList.contains("mermaid") || el.classList.contains("math"))) {
      var source = el.getAttribute("data-source") || el.textContent || "";
      return tag + "|" + id + "|" + source.replace(/\s+/g, " ").trim().slice(0, 200);
    }
    // Enhancement wrappers (renderers.js table/code UX): sign as the INNER
    // block so an enhanced live table/pre compares equal to the bare
    // server-rendered element on the other side of the diff. The tablewrap
    // uses data-source (the original text captured at enhance time) because
    // user-applied sorting reorders the live textContent without the
    // content having changed. Full-length (no 200-char slice) on both the
    // wrapper AND bare table/pre sides: a sorted table means row-level
    // recursion can't reconcile order, so equality must be exact — a
    // truncated signature would silently drop edits past the prefix.
    if (el.classList && el.classList.contains("okf-tablewrap")) {
      return "table|" + id + "|" + (el.getAttribute("data-source") || "");
    }
    if (el.classList && el.classList.contains("okf-codewrap")) {
      var inner = el.querySelector("pre");
      var innerText = inner ? (inner.textContent || "") : "";
      return "pre|" + id + "|" + innerText.replace(/\s+/g, " ").trim();
    }
    if (tag === "table" || tag === "pre") {
      return tag + "|" + id + "|" + (el.textContent || "").replace(/\s+/g, " ").trim();
    }
    // For headings, exclude the client-only heading-anchor glyph (¶) that
    // bindHeadingAnchors injects into the live DOM, so an unchanged heading
    // compares equal to the server-rendered version (which has no anchor).
    // This keeps heading DOM identity stable across no-op re-renders and
    // prevents unnecessary block replacement on every patch. Intentional
    // heading-level changes (H2→H1) still trigger replacement via the tag
    // component of the signature.
    var text = (el.textContent || "").replace(/\s+/g, " ").trim();
    if (/^h[1-6]$/.test(tag) && el.querySelector && el.querySelector(".okf-heading-anchor")) {
      var clone = el.cloneNode(true);
      var anchors = clone.querySelectorAll(".okf-heading-anchor");
      for (var ai = 0; ai < anchors.length; ai++) anchors[ai].remove();
      text = (clone.textContent || "").replace(/\s+/g, " ").trim();
    }
    return tag + "|" + id + "|" + text.slice(0, 200);
  }
  function parseHtmlToBlocks(html) {
    const tmp = document.createElement("div");
    tmp.innerHTML = html;
    return blockChildren(tmp);
  }
  // Standard LCS DP over signature arrays → edit ops. Returns an array of
  // {op: "keep"|"replace"|"insert"|"remove", oldEl?, newEl?}.
  function lcsOps(oldBlocks, newBlocks) {
    const n = oldBlocks.length, m = newBlocks.length;
    const oldSigs = oldBlocks.map(blockSig);
    const newSigs = newBlocks.map(blockSig);
    // dp[i][j] = LCS length of oldSigs[i:] and newSigs[j:].
    const dp = [];
    for (let i = 0; i <= n; i++) dp.push(new Array(m + 1).fill(0));
    for (let i = n - 1; i >= 0; i--) {
      for (let j = m - 1; j >= 0; j--) {
        dp[i][j] = oldSigs[i] === newSigs[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    const ops = [];
    let i = 0, j = 0;
    while (i < n && j < m) {
      if (oldSigs[i] === newSigs[j]) { ops.push({ op: "keep", oldEl: oldBlocks[i], newEl: newBlocks[j] }); i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ op: "remove", oldEl: oldBlocks[i] }); i++; }
      else { ops.push({ op: "insert", newEl: newBlocks[j] }); j++; }
    }
    while (i < n) { ops.push({ op: "remove", oldEl: oldBlocks[i] }); i++; }
    while (j < m) { ops.push({ op: "insert", newEl: newBlocks[j] }); j++; }
    return ops;
  }
  // diffAndPatchBody mutates `parent` to match `newHtml` at the block level.
  // Returns the list of newly-inserted or replaced element nodes (for the
  // scoped pulse). Recurses into matching list/table blocks that differ.
  function diffAndPatchBody(parent, newHtml) {
    const newBlocks = parseHtmlToBlocks(newHtml);
    return diffChildren(parent, newBlocks, 0);
  }
  function diffChildren(parent, newBlocks, depth) {
    const oldBlocks = blockChildren(parent);
    const ops = lcsOps(oldBlocks, newBlocks);
    const changed = [];
    // Apply ops. We rebuild the child list by walking ops and using
    // parent.insertBefore / removeChild so untouched nodes keep their
    // identity (and any in-body selection/focus on them survives).
    let cursor = parent.firstChild; // node we're currently considering in the live DOM
    for (let k = 0; k < ops.length; k++) {
      const op = ops[k];
      if (op.op === "keep") {
        // Recurse into matching containers whose children may differ.
        if (depth < 2 && (op.oldEl.tagName === "UL" || op.oldEl.tagName === "OL" || op.oldEl.tagName === "TABLE")) {
          const innerChanged = diffChildren(op.oldEl, blockChildren(op.newEl), depth + 1);
          if (innerChanged.length) { changed.push.apply(changed, innerChanged); }
        }
        cursor = op.oldEl.nextSibling;
      } else if (op.op === "replace") {
        // (Not produced by lcsOps directly; handled as remove+insert.)
      } else if (op.op === "remove") {
        const next = op.oldEl.nextSibling;
        parent.removeChild(op.oldEl);
        cursor = next;
      } else if (op.op === "insert") {
        const imported = parent.ownerDocument.importNode(op.newEl, true);
        parent.insertBefore(imported, cursor);
        changed.push(imported);
      }
    }
    return changed;
  }
  function pulseBlocks(blocks) {
    if (REDUCED_MOTION) return;
    blocks.forEach((b) => {
      b.classList.remove("okf-pulse");
      void b.offsetWidth; // restart the animation on consecutive patches
      b.classList.add("okf-pulse");
    });
  }

  // ---- selection preservation across a block patch (iter1 CRI-001) -----
  // Captures the current in-body selection. Because unchanged blocks keep
  // their DOM identity (diffChildren never touches them), a selection that
  // lives entirely inside an unchanged block survives automatically. Only
  // selections whose boundary nodes were disconnected/replaced need a
  // best-effort text-search restore after the patch.
  //
  // CRITICAL: the "did the selection survive?" check must use ACTUAL node
  // connectivity/containment, NOT text equality. A replaced block can carry
  // different text (e.g. an H2→H1 patch that also drops a client-only
  // heading-anchor ¶ glyph), so comparing old-vs-inserted block text would
  // incorrectly treat a detached anchor block as unchanged — collapsing the
  // selection and preventing the comment affordance from appearing.
  //
  // AMBIGUITY FAIL-CLOSED: when re-resolving by text, the search is scoped
  // to the replacement block (by captured block ID / tag / index + local
  // before/after context). If multiple viable ranges remain or identity
  // cannot be established, NO range is restored — never the first global
  // duplicate. Returns {restore(changedBlocks)}.
  function saveSelectionAcrossPatch(body) {
    const sel = window.getSelection && window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return { restore() {} };
    const range = sel.getRangeAt(0);
    if (!body.contains(range.commonAncestorContainer)) return { restore() {} };
    const text = sel.toString().trim();
    if (!text) return { restore() {} };
    // Retain the EXACT boundary node references + their containing blocks.
    const startNode = range.startContainer;
    const startOffset = range.startOffset;
    const endNode = range.endContainer;
    const endOffset = range.endOffset;
    const anchorBlock = containingBlock(startNode, body);
    const focusBlock = containingBlock(endNode, body);
    // Direction: backward when the Selection anchor is NOT at the range start.
    const backward = sel.anchorNode !== range.startContainer ||
      (sel.anchorNode === range.startContainer && sel.anchorOffset !== range.startOffset);
    // Capture structural identity for scoped re-resolution. This lets us
    // search the CORRECT replacement block after a patch instead of blindly
    // matching the first global occurrence of the text (which would be wrong
    // if the same text appears in multiple blocks).
    const ident = captureBlockIdentity(anchorBlock, range, body);
    return {
      _text: text,
      restore(changedBlocks) {
        if (!text) return;
        // Selection survived ONLY if BOTH boundary nodes are still connected
        // AND contained by the current body AND live inside a real block
        // element (not the body root).
        const startLive = startNode && startNode.isConnected &&
          body.contains(startNode) && anchorBlock && anchorBlock !== body &&
          anchorBlock.isConnected && body.contains(anchorBlock);
        const endLive = endNode && endNode.isConnected &&
          body.contains(endNode) && focusBlock && focusBlock !== body &&
          focusBlock.isConnected && body.contains(focusBlock);
        if (startLive && endLive) return; // selection survived untouched
        // At least one boundary node was disconnected/replaced. Re-resolve
        // using scoped search with structural identity. findScopedTextRange
        // fails closed (returns null) when the text is ambiguous or not
        // found, so we never create a wrong range.
        const found = findScopedTextRange(body, text, ident, changedBlocks);
        if (!found) return;
        try {
          if (backward && typeof sel.setBaseAndExtent === "function") {
            sel.removeAllRanges();
            sel.setBaseAndExtent(
              found.endNode, found.endOffset,
              found.startNode, found.startOffset
            );
          } else {
            const r = document.createRange();
            r.setStart(found.startNode, found.startOffset);
            r.setEnd(found.endNode, found.endOffset);
            sel.removeAllRanges();
            sel.addRange(r);
          }
        } catch (e) { /* give up silently; selection is best-effort */ }
      },
    };
  }
  function containingBlock(node, root) {
    let el = node.nodeType === 1 ? node : node.parentElement;
    while (el && el !== root) {
      if (el.tagName === "P" || /^H[1-6]$/.test(el.tagName) || el.tagName === "LI" ||
          el.tagName === "UL" || el.tagName === "OL" || el.tagName === "TABLE" ||
          el.tagName === "PRE" || el.tagName === "BLOCKQUOTE") return el;
      el = el.parentElement;
    }
    return root;
  }
  // Capture structural identity of the anchor block + local text context
  // around the selection. Used after a patch to scope the text search to the
  // correct replacement block and disambiguate duplicate text.
  function captureBlockIdentity(anchorBlock, range, body) {
    if (!anchorBlock || anchorBlock === body) return null;
    var id = anchorBlock.getAttribute("id") || "";
    var tag = anchorBlock.tagName.toLowerCase();
    var index = -1;
    try {
      var el = body.firstElementChild, i = 0;
      while (el) { if (el === anchorBlock) { index = i; break; } el = el.nextElementSibling; i++; }
    } catch (e) {}
    // Local before/after context: text within the anchor block immediately
    // before/after the selection. Used to disambiguate when the same text
    // appears multiple times within the same block.
    var before = "", after = "";
    try {
      var br = document.createRange();
      br.setStart(anchorBlock, 0);
      br.setEnd(range.startContainer, range.startOffset);
      before = br.toString().slice(-60); // last 60 chars before selection
    } catch (e) {}
    try {
      var ar = document.createRange();
      ar.setStart(range.endContainer, range.endOffset);
      ar.setEnd(anchorBlock, anchorBlock.childNodes.length);
      after = ar.toString().slice(0, 60); // first 60 chars after selection
    } catch (e) {}
    return { id: id, tag: tag, index: index, before: before, after: after };
  }
  // Tiered scoped search for re-resolving selection text after a body patch.
  // 1. Block ID match → search within that block.
  // 2. Changed blocks with matching tag → search within each; fail closed
  //    if text is found in more than one.
  // 3. All changed blocks → same fail-closed principle.
  // 4. Entire body → last resort; still fail closed on multiple matches.
  // If identity cannot be established (null ident) and no changed blocks
  // narrow the scope, fail closed — never restore to an unscoped global match.
  function findScopedTextRange(body, text, ident, changedBlocks) {
    // Tier 1: block ID match.
    if (ident && ident.id) {
      var scopeById = body.querySelector('#' + cssEscape(ident.id));
      if (scopeById) {
        var found = findTextRange(scopeById, text, { contextBefore: ident.before, contextAfter: ident.after });
        if (found) return found;
      }
    }
    // Tier 2: changed blocks with matching tag.
    if (changedBlocks && changedBlocks.length && ident && ident.tag) {
      var matches = [];
      for (var ci = 0; ci < changedBlocks.length; ci++) {
        if (changedBlocks[ci].tagName.toLowerCase() === ident.tag) {
          var m = findTextRange(changedBlocks[ci], text, { contextBefore: ident.before, contextAfter: ident.after });
          if (m) { matches.push(m); if (matches.length > 1) return null; }
        }
      }
      if (matches.length === 1) return matches[0];
    }
    // Tier 3: all changed blocks.
    if (changedBlocks && changedBlocks.length) {
      var matches3 = [];
      for (var cj = 0; cj < changedBlocks.length; cj++) {
        var m3 = findTextRange(changedBlocks[cj], text, ident ? { contextBefore: ident.before, contextAfter: ident.after } : {});
        if (m3) { matches3.push(m3); if (matches3.length > 1) return null; }
      }
      if (matches3.length === 1) return matches3[0];
    }
    // Tier 4: entire body — only when we have identity to disambiguate via
    // context. Without identity, a global search is too ambiguous.
    if (ident && (ident.id || ident.tag)) {
      return findTextRange(body, text, { contextBefore: ident.before, contextAfter: ident.after });
    }
    return null; // fail closed
  }
    // Find `text` anywhere under `root` (or within `opts.scopeEl`). Models
    // actual browser Selection.toString() semantics: block elements produce
    // `\n\n` separators, adjacent inline elements concatenate directly
    // (<strong>foo</strong><em>bar</em> → "foobar"), and authored whitespace
    // is preserved. A bounded candidate enumeration finds all occurrences;
    // each is verified by mapping offsets back to DOM nodes. Fails closed
    // (returns null) when 0 or >1 verified matches are found. Context
    // (before/after) disambiguates only when multiple candidates exist.
    function findTextRange(root, text, opts) {
      opts = opts || {};
      if (!text) return null;
      var scopeEl = opts.scopeEl || root;
      var ctxBefore = opts.contextBefore || "";
      var ctxAfter = opts.contextAfter || "";
      var textNodes = collectTextNodes(scopeEl);
      if (!textNodes.length) return null;
      // Build a flat string modeling Selection.toString() semantics:
      // - \n\n between text nodes in DIFFERENT block elements
      // - direct concatenation for text nodes in the SAME block (inline)
      // - authored whitespace preserved as-is
      // - whitespace-only text nodes that are direct children of scopeEl
      //   (inter-block template whitespace) are skipped
      var flat = "";
      var map = []; // map[flatIndex] = {node, offset} | null for separator
      var prevBlock = null;
      for (var i = 0; i < textNodes.length; i++) {
        var tn = textNodes[i];
        var nv = tn.nodeValue;
        if (!nv) continue;
        // Skip inter-block whitespace (direct child of scope, whitespace-only).
        if (nv.trim() === "" && tn.parentElement === scopeEl) continue;
        var block = containingBlock(tn, scopeEl);
        // Insert block separator when transitioning between block elements.
        if (prevBlock !== null && block !== prevBlock && flat.length > 0) {
          flat += "\n\n";
          map.push(null);
          map.push(null);
        }
        for (var j = 0; j < nv.length; j++) {
          map.push({ node: tn, offset: j });
          flat += nv.charAt(j);
        }
        prevBlock = block;
      }
      // Find all occurrences of text in the scope text.
      var candidates = [];
      var MAX_CANDIDATES = 50;
      var found = 0;
      var idx = 0;
      while (idx <= flat.length - text.length && found < MAX_CANDIDATES) {
        idx = flat.indexOf(text, idx);
        if (idx < 0) break;
        found++;
        var startPos = mapPosToDom(map, idx);
        var endPos = mapPosToDom(map, idx + text.length - 1);
        if (startPos && endPos) {
          candidates.push({
            startNode: startPos.node, startOffset: startPos.offset,
            endNode: endPos.node, endOffset: endPos.offset + 1
          });
        }
        idx++;
      }
      // Phase 2: if no exact match, try normalized match (collapse whitespace
      // runs to single spaces). This handles cross-block selections where
      // Selection.toString() produces element-specific separators (\n for
      // <blockquote>, \n\n for <p>) that may differ from our \n\n model.
      if (candidates.length === 0) {
        var normResult = searchNormalizedMatch(map, flat, text, MAX_CANDIDATES);
        if (normResult) return normResult;
        return null;
      }
      // Single candidate: accept without context check.
      if (candidates.length === 1) return candidates[0];
      if (candidates.length === 0) return null;
      // Multiple: use context to disambiguate.
      var ctxMatches = [];
      for (var ci = 0; ci < candidates.length; ci++) {
        if (contextCheck(candidates[ci], ctxBefore, ctxAfter, scopeEl)) {
          ctxMatches.push(candidates[ci]);
          if (ctxMatches.length > 1) return null;
        }
      }
      if (ctxMatches.length === 1) return ctxMatches[0];
      return null;
    }
    // Map a position in the flat string to a DOM (node, offset).
    // Separator chars (null map entries) are resolved to the next real node.
    function mapPosToDom(map, position) {
      var si = position;
      while (si < map.length && !map[si]) si++;
      if (si >= map.length) {
        // Position is in trailing separators; use last real entry.
        si = position;
        while (si >= 0 && !map[si]) si--;
      }
      if (si < 0 || si >= map.length || !map[si]) return null;
      return { node: map[si].node, offset: map[si].offset };
    }
    // Normalized search: collapse whitespace runs in both the flat string
    // and the needle to single spaces, then find matches. Maps normalized
    // positions back to DOM nodes via the original map. Handles cross-block
    // selections where Selection.toString() produces element-specific
    // separators (\n, \n\n) that differ from our \n\n model.
    function searchNormalizedMatch(map, flat, text, maxCandidates) {
      var normNeedle = text.replace(/\s+/g, " ").trim();
      if (!normNeedle) return null;
      // Build normalized flat string, keeping track of which original map
      // entry each normalized character came from.
      var nflat = "";
      var nmap = []; // nmap[nflatIndex] = original map entry | null
      var lastWasSpace = false;
      for (var i = 0; i < flat.length; i++) {
        var ch = flat.charAt(i);
        if (/\s/.test(ch)) {
          if (!lastWasSpace && nflat.length > 0) {
            nflat += " ";
            nmap.push(null);
            lastWasSpace = true;
          }
        } else {
          nflat += ch;
          nmap.push(map[i]);
          lastWasSpace = false;
        }
      }
      // Trim leading space.
      if (nflat.charAt(0) === " ") { nflat = nflat.substring(1); nmap.shift(); }
      var matches = [];
      var idx = 0;
      while (idx <= nflat.length - normNeedle.length && matches.length < 2) {
        idx = nflat.indexOf(normNeedle, idx);
        if (idx < 0) break;
        var startPos = mapPosToDom(nmap, idx);
        var endPos = mapPosToDom(nmap, idx + normNeedle.length - 1);
        if (startPos && endPos) {
          matches.push({
            startNode: startPos.node, startOffset: startPos.offset,
            endNode: endPos.node, endOffset: endPos.offset + 1
          });
        }
        idx++;
      }
      return matches.length === 1 ? matches[0] : null;
    }
    function collectTextNodes(root) {
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
      var out = [];
      var n;
      while ((n = walker.nextNode())) { if (n.nodeValue && n.nodeValue.length > 0) out.push(n); }
      return out;
    }
    // Check if a candidate's surrounding text matches the captured context.
    function contextCheck(cand, ctxBefore, ctxAfter, scopeEl) {
      if (!ctxBefore && !ctxAfter) return true;
      try {
        if (ctxBefore) {
          var br = document.createRange();
          br.setStart(scopeEl, 0);
          br.setEnd(cand.startNode, cand.startOffset);
          if (!br.toString().endsWith(ctxBefore)) return false;
        }
        if (ctxAfter) {
          var ar = document.createRange();
          ar.setStart(cand.endNode, cand.endOffset);
          ar.setEnd(scopeEl, scopeEl.childNodes.length);
          if (!ar.toString().startsWith(ctxAfter)) return false;
        }
        return true;
      } catch (e) { return false; }
    }
    // Backward-compatible wrapper: comment-mark resolution (applyCommentMarks,
  // applyPendingDraftMark, resolveSelectionDraft) expects {node, start, end}
  // and creates a single-node range. Delegates to findTextRange but only
  // returns single-node matches so callers using surroundContents are safe.
  function findTextNode(root, text) {
    var found = findTextRange(root, text);
    if (!found || found.startNode !== found.endNode) return null;
    return { node: found.startNode, start: found.startOffset, end: found.endOffset };
  }
  // Resolve a comment anchor text to a Range, using scoped search (block ID
  // first, then full body) and cross-node findTextRange so a comment whose
  // anchor spans inline elements (<strong>foo</strong>bar) is found and
  // wrapped correctly via wrapRangeInMark → wrapRangeAcrossElements.
  // Returns a Range or null.
  function resolveCommentRange(root, text, blockId) {
    if (!text) return null;
    var scope = null;
    if (blockId) scope = root.querySelector('#' + cssEscape(blockId));
    var found = null;
    if (scope) found = findTextRange(scope, text);
    if (!found) found = findTextRange(root, text);
    if (!found) return null;
    try {
      var r = document.createRange();
      r.setStart(found.startNode, found.startOffset);
      r.setEnd(found.endNode, found.endOffset);
      return r;
    } catch (e) { return null; }
  }

  // ====================================================================
  // 5. Comments (§9)
  // ====================================================================
  // Initial state reconstructed from the events feed (comment events), then
  // kept live by the `comment` SSE signal. Each event carries the full
  // latest record for an id (see studio.post_comment/update_comment).
  async function loadComments() {
    try {
      // ARCH4-003 / QUA4-001 fix: fetch canonical comment state from
      // /__comments (directives.jsonl, last-write-wins) instead of
      // reconstructing from /__data/events (which had a desc-order +
      // last-iteration inversion bug showing claimed/resolved as "open").
      const [commentRes, eventRes] = await Promise.all([
        fetch("/__comments", { headers: { Accept: "application/json" } }),
        fetch("/__data/events?limit=500", { headers: { Accept: "application/json" } }),
      ]);
      const commentData = await commentRes.json();
      const eventData = await eventRes.json();
      // State-ownership fence (async-lifecycle): live SSE events may have been
      // upserted into state.events WHILE this initial fetch was in flight — a
      // slow /__data/events response must NOT wipe a live burst that already
      // rendered. Merge by stable id: the fetched snapshot is the baseline; a
      // live record wins on conflict (it carries the freshest fields + any
      // burst/group tags applied on arrival); and live events absent from the
      // snapshot (they arrived after the server built it, e.g. an id-less
      // changed/created/removed signal) stay on top in arrival order.
      const liveEvents = state.events || [];
      const liveById = new Map();
      liveEvents.forEach((e) => { if (e && e.id) liveById.set(e.id, e); });
      const seenIds = new Set();
      const mergedEvents = [];
      (eventData.events || []).forEach((e) => {
        if (!e) return;
        if (e.id && liveById.has(e.id)) {
          mergedEvents.push(liveById.get(e.id));  // keep the live record (tags intact)
          seenIds.add(e.id);
        } else {
          mergedEvents.push(e);
          if (e.id) seenIds.add(e.id);
        }
      });
      const liveExtras = liveEvents.filter((e) => e && (!e.id || !seenIds.has(e.id)));
      state.events = liveExtras.concat(mergedEvents);
      // Use canonical comment state from the server.
      state.comments = (commentData.comments || []).slice().sort(byTsDesc);
      renderCommentsPanel();
      renderChangeList();
      updateBadges();
      // iter1 CRI-002: apply text-range marks now that comments are loaded.
      applyCommentMarks();
      rebuildMarginMarkers();
    } catch (e) {
      console.error("[okf-studio] load comments/events failed", e);
    }
  }
  function byTsDesc(a, b) {
    const ta = a.ts || "", tb = b.ts || "";
    if (ta < tb) return 1; if (ta > tb) return -1; return 0;
  }
  // id-based upsert (last write wins). Guards against the SSE-vs-POST race
  // where the `comment` event and the POST /__comment response both carry the
  // confirmed record - without dedup the optimistic row + the SSE insert +
  // the POST reconcile could leave 2-3 copies of the same id in state.
  function upsertComment(c) {
    if (!c || !c.id) return;
    const idx = state.comments.findIndex((x) => x.id === c.id);
    if (idx >= 0) state.comments[idx] = Object.assign({}, state.comments[idx], c);
    else state.comments.unshift(Object.assign({ ts: new Date().toISOString() }, c));
    state.comments.sort(byTsDesc);
  }

  // --- selection affordance --------------------------------------------
  // iter1 CRI-017: aria-live announces the affordance when it appears (it
  // shows in response to a user selection), and the leading glyph is an
  // inline SVG with aria-hidden instead of an emoji.
  let affordance;
  const COMMENT_ICON_SVG = '<svg class="okf-comment-afford__icon" viewBox="0 0 16 16" fill="none" aria-hidden="true" focusable="false"><path d="M2 3h12v8H6l-3 3v-3H2z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>';
  function ensureAffordance() {
    if (affordance) return affordance;
    affordance = el("div", { class: "okf-comment-afford", hidden: "", role: "status", "aria-live": "polite" });
    const btn = el("button", { type: "button", class: "okf-studiobtn", "aria-label": "Comment for agent on the selected text" });
    btn.innerHTML = COMMENT_ICON_SVG;
    btn.appendChild(document.createTextNode(" Comment"));
    btn.addEventListener("mousedown", (e) => e.preventDefault()); // keep selection
    btn.addEventListener("click", onAffordanceClick);
    affordance.appendChild(btn);
    document.body.appendChild(affordance);
    return affordance;
  }
  // Stable debounced handlers, created once: bindSelectionAffordance is
  // re-run after every SSE body patch (applyDoc), and a fresh closure per
  // call would stack a new listener each time (addEventListener only
  // dedupes identical function references) — an unbounded leak over a
  // live session.
  const _affordanceOnSelection = debounce(updateAffordance, 120);
  const _affordanceOnResize = debounce(hideAffordance, 120);
  function bindSelectionAffordance() {
    if (!EDIT) return;
    // Bind on concept pages AND graph pages (the graph detail panel
    // has renderable content that should be selectable + commentable).
    if (!isConceptPage() && !document.getElementById("detail-body")) return;
    ensureAffordance();
    // On concept pages, .okf-page__body exists. On graph pages, it doesn't
    // but #detail-body does — don't bail if one is missing, just check the
    // other in getSelectionInBody. Stable references make re-binding after
    // each patch a no-op.
    document.addEventListener("selectionchange", _affordanceOnSelection);
    document.addEventListener("scroll", hideAffordance, { passive: true });
    window.addEventListener("resize", _affordanceOnResize);
  }
  function getSelectionInBody() {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
    const range = sel.getRangeAt(0);
    // Check the rendered body, the source pane, AND the graph detail panel
    // so comments work in all three surfaces.
    const body = $(".okf-page__body");
    const source = $(".okf-source");
    const graphDetail = document.getElementById("detail-body");
    const inRendered = body && body.contains(range.commonAncestorContainer);
    const inSource = source && source.contains(range.commonAncestorContainer);
    const inGraph = graphDetail && graphDetail.contains(range.commonAncestorContainer);
    if (!inRendered && !inSource && !inGraph) return null;
    const text = sel.toString().trim();
    if (!text) return null;
    return { sel, range, text, inSource, inGraph };
  }
  // iter1 CRI-002: find the nearest heading WITH AN ID (the renderer stamps
  // stable slug ids on every heading) so the comment anchor survives block
  // re-rendering. Falls back to the heading text if no id is present.
  function nearestHeadingAnchor(node) {
    const body = $(".okf-page__body");
    if (!body) return { id: "", text: "" };
    const headings = $$("h1, h2, h3, h4, h5, h6", body);
    const startNode = (node && node.nodeType === 1) ? node : (node && node.parentElement);
    if (!startNode) return { id: "", text: "" };
    let last = null;
    for (let i = 0; i < headings.length; i++) {
      if (startNode.compareDocumentPosition(headings[i]) & Node.DOCUMENT_POSITION_PRECEDING) {
        last = headings[i];
      } else break;
    }
    if (!last) return { id: "", text: "" };
    return { id: last.getAttribute("id") || "", text: (last.textContent || "").trim() };
  }
  function updateAffordance() {
    if (!affordance) return;
    const inBody = getSelectionInBody();
    if (!inBody) { affordance.hidden = true; state.selectionDraft = null; return; }
    let rect;
    try { rect = inBody.range.getBoundingClientRect(); } catch (e) { affordance.hidden = true; state.selectionDraft = null; return; }
    if (!rect || (rect.width === 0 && rect.height === 0)) { affordance.hidden = true; state.selectionDraft = null; return; }
    state.selectionDraft = selectionDraftFromRange(inBody);
    affordance.hidden = false;
    const btn = affordance.firstChild;
    const bw = btn.offsetWidth || 180;
    const bh = btn.offsetHeight || 36;
    const margin = 8;
    const maxLeft = Math.max(margin, window.innerWidth - bw - margin);
    const left = Math.min(Math.max(margin, rect.left + rect.width / 2 - bw / 2), maxLeft);
    let top = rect.bottom + 6;
    if (top + bh > window.innerHeight - margin) top = rect.top - bh - 6;
    top = Math.min(Math.max(margin, top), Math.max(margin, window.innerHeight - bh - margin));
    affordance.style.left = left + "px";
    affordance.style.top = top + "px";
  }
  // Central cleanup for abandoned comment draft state. Removes the optimistic
  // pending mark from the DOM, clears transient selection/range/anchor.
  // opts.preserveDraftBody: when true (panel close/navigation), keeps the
  // typed draft text so the user doesn't lose their work. When false/absent
  // (Cancel), clears draftBody too.
  function clearPendingCommentDraft(opts) {
    // Remove ALL matching optimistic marks via the existing helper (handles
    // cross-element marks — a pending ID may have marks in multiple roots).
    if (state._pendingMarkId) {
      removeCommentMark(state._pendingMarkId);
      state._pendingMarkId = null;
    }
    state.selectionDraft = null;
    if (!opts || !opts.preserveDraftBody) {
      state.draftBody = "";
    }
    state.draftAnchor = { kind: "concept", ref: state.conceptId };
    hideAffordance();
    try {
      var sel = window.getSelection();
      if (sel && sel.rangeCount > 0) {
        var r = sel.getRangeAt(0);
        var body = $(".okf-page__body");
        if (body && body.contains(r.commonAncestorContainer)) sel.removeAllRanges();
      }
    } catch (e) {}
  }

  function hideAffordance() {
    if (affordance) affordance.hidden = true;
    state.selectionDraft = null;
  }
  function onAffordanceClick() {
    const inBody = getSelectionInBody() || resolveSelectionDraft();
    if (!inBody) return;
    // Determine which concept the comment is about. On the graph page,
    // the detail panel shows a different concept than state.conceptId.
    var commentConcept = commentConceptForSelection(inBody);
    if (inBody.inSource) {
      state.draftAnchor = {
        kind: "source",
        ref: inBody.text.slice(0, 140),
        concept: commentConcept,
      };
    } else {
      const heading = nearestHeadingAnchor(inBody.range.startContainer);
      const localId = "local-" + (state.nextCommentSeq++);
      const mark = wrapRangeInMark(inBody.range, localId, "open");
      state.draftAnchor = {
        kind: "text",
        ref: inBody.text.slice(0, 140),
        block_id: heading.id,
        block_text: heading.text,
        section: heading.text,
        concept: commentConcept,
      };
      state._pendingMarkId = localId;
    }
    state.draftBody = "";
    openPanel("comments", { focusComposer: true });
    hideAffordance();
    try { window.getSelection().removeAllRanges(); } catch (e) {}
  }

  function selectionDraftFromRange(inBody) {
    const draft = {
      text: inBody.text,
      inSource: !!inBody.inSource,
      inGraph: !!inBody.inGraph,
      concept: commentConceptForSelection(inBody),
      block_id: "",
      block_text: "",
      range: null,
    };
    if (!inBody.inSource && !inBody.inGraph) {
      const heading = nearestHeadingAnchor(inBody.range.startContainer);
      draft.block_id = heading.id;
      draft.block_text = heading.text;
    }
    try { draft.range = inBody.range.cloneRange(); } catch (e) { draft.range = null; }
    return draft;
  }

  function selectionDraftRoot(draft) {
    if (!draft) return null;
    if (draft.inSource) return $(".okf-source");
    if (draft.inGraph) return document.getElementById("detail-body");
    return $(".okf-page__body");
  }

  function resolveSelectionDraft() {
    const draft = state.selectionDraft;
    if (!draft || !draft.text) return null;
    const root = selectionDraftRoot(draft);
    if (!root) return null;
    if (draft.range && root.contains(draft.range.commonAncestorContainer)) {
      try {
        return {
          range: draft.range.cloneRange(),
          text: draft.text,
          inSource: draft.inSource,
          inGraph: draft.inGraph,
        };
      } catch (e) { /* fall through to text re-resolution */ }
    }
    // Cross-node re-resolution: use resolveCommentRange (findTextRange) so a
    // draft whose anchor spans inline elements is found and restored as a
    // proper Range, not just a single-node match.
    const blockId = (!draft.inSource && !draft.inGraph && draft.block_id) ? draft.block_id : "";
    const range = resolveCommentRange(root, draft.text, blockId);
    if (!range) return null;
    return { range, text: draft.text, inSource: draft.inSource, inGraph: draft.inGraph };
  }

  function commentConceptForSelection(inBody) {
    var commentConcept = state.conceptId;
    if (inBody && inBody.inGraph) {
      var graphBody = document.getElementById("detail-body");
      if (graphBody) commentConcept = graphBody.getAttribute("data-concept-id") || commentConcept;
    }
    return commentConcept;
  }

  // ---- comment text-range marks (iter1 CRI-002) -----------------------
  // Wraps a Range in <mark data-comment-id class="okf-comment-mark">. Used
  // optimistically on comment creation and re-applied from persisted anchors
  // after every body patch. surroundContents fails when the range crosses
  // element boundaries, so we extract + rewrap node-by-node.
  function wrapRangeInMark(range, commentId, commentState) {
    try {
      const mark = el("mark", { class: "okf-comment-mark", "data-comment-id": commentId });
      if (commentState) mark.setAttribute("data-comment-state", commentState);
      range.surroundContents(mark);
      return mark;
    } catch (e) {
      // Range crosses element boundaries: fall back to wrapping each text
      // node segment. Collect the wrapped marks so the caller can track them.
      return wrapRangeAcrossElements(range, commentId, commentState);
    }
  }
  function wrapRangeAcrossElements(range, commentId, commentState) {
    const marks = [];
    const nodes = textNodesInRange(range);
    nodes.forEach((tn) => {
      const parent = tn.parentNode;
      if (!parent) return;
      const start = (tn === range.startContainer) ? range.startOffset : 0;
      const end = (tn === range.endContainer) ? range.endOffset : tn.nodeValue.length;
      if (start >= end) return;
      const sub = tn.nodeValue.slice(start, end);
      if (!sub) return;
      const mark = el("mark", { class: "okf-comment-mark", "data-comment-id": commentId });
      if (commentState) mark.setAttribute("data-comment-state", commentState);
      mark.appendChild(document.createTextNode(sub));
      const frag = document.createDocumentFragment();
      const before = tn.nodeValue.slice(0, start);
      const after = tn.nodeValue.slice(end);
      if (before) frag.appendChild(document.createTextNode(before));
      frag.appendChild(mark);
      if (after) frag.appendChild(document.createTextNode(after));
      parent.replaceChild(frag, tn);
      marks.push(mark);
    });
    return marks[0] || null;
  }
  function textNodesInRange(range) {
    const out = [];
    if (range.commonAncestorContainer.nodeType === Node.TEXT_NODE) {
      if (range.intersectsNode(range.commonAncestorContainer)) {
        out.push(range.commonAncestorContainer);
      }
      return out;
    }
    const walker = document.createTreeWalker(range.commonAncestorContainer, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        if (!range.intersectsNode(n)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let n; while ((n = walker.nextNode())) out.push(n);
    return out;
  }
  // Removes a comment's mark(s) by id, unwrapping the text back into the
  // flow. Used on failed post and to clear a stale optimistic mark.
  function removeCommentMark(commentId) {
    if (!commentId) return;
    const marks = $$('.okf-comment-mark[data-comment-id="' + cssEscape(commentId) + '"]');
    marks.forEach((m) => {
      const parent = m.parentNode;
      if (!parent) return;
      while (m.firstChild) parent.insertBefore(m.firstChild, m);
      parent.removeChild(m);
      parent.normalize(); // merge adjacent text nodes back together
    });
  }
  function renameCommentMark(oldId, newId) {
    if (!oldId || !newId || oldId === newId) return;
    const marks = $$('.okf-comment-mark[data-comment-id="' + cssEscape(oldId) + '"]');
    marks.forEach((m) => m.setAttribute("data-comment-id", newId));
  }
  function setCommentMarkState(commentId, commentState) {
    if (!commentId) return;
    const marks = $$('.okf-comment-mark[data-comment-id="' + cssEscape(commentId) + '"]');
    marks.forEach((m) => {
      if (commentState) m.setAttribute("data-comment-state", commentState);
      else m.removeAttribute("data-comment-state");
    });
  }
  // (Re)apply marks for every comment on the open concept whose anchor is a
  // text selection. Idempotent: skips ids that already have a live mark.
  // Marks whose ref text can no longer be found get the --stale style and
  // the comment is flagged so the card can say "anchor moved".
  function applyCommentMarks() {
    if (!isConceptPage()) return;
    const body = $(".okf-page__body");
    if (!body) return;
    const mine = state.comments.filter((c) => c.concept === state.conceptId && c.anchor && c.anchor.kind === "text" && c.anchor.ref);
    // Index existing marks so we skip re-wrapping.
    const existing = Object.create(null);
    $$(".okf-comment-mark", body).forEach((m) => {
      const id = m.getAttribute("data-comment-id");
      if (id) (existing[id] || (existing[id] = [])).push(m);
    });
      mine.forEach((c) => {
        c._stale = false;
        if (existing[c.id] && existing[c.id].length) {
          // Mark exists: just sync its state attribute.
          setCommentMarkState(c.id, c.state || "open");
          return;
        }
        // Resolve the anchor: prefer the block_id heading, else search the
        // whole body. Use cross-node resolveCommentRange so a comment whose
        // anchor spans inline elements is wrapped correctly via
        // wrapRangeInMark → wrapRangeAcrossElements.
        const range = resolveCommentRange(body, c.anchor.ref, c.anchor.block_id);
        if (range) {
          wrapRangeInMark(range, c.id, c.state || "open");
        } else {
          // Try the full body as a last resort (block may have been renamed).
          const range2 = c.anchor.block_id ? resolveCommentRange(body, c.anchor.ref, "") : null;
          if (!range2) {
            c._stale = true;
            appendStaleMark(body, c);
          } else {
            wrapRangeInMark(range2, c.id, c.state || "open");
          }
        }
      });
  }
  // A user can select text and open the comment composer before the lazy
  // /__data/doc load (or a live patch) settles. The body patch correctly
  // re-applies persisted comments via applyCommentMarks(), but a not-yet-sent
  // draft only exists as state._pendingMarkId + state.draftAnchor. Re-resolve
  // that pending local mark as well so the user-visible selection highlight
  // does not disappear underneath the open composer.
  function applyPendingDraftMark() {
    if (!isConceptPage()) return;
    const pendingId = state._pendingMarkId;
    const anchor = state.draftAnchor || {};
    if (!pendingId || anchor.kind !== "text" || !anchor.ref) return;
    if (anchor.concept && anchor.concept !== state.conceptId) return;
    const body = $(".okf-page__body");
    if (!body) return;
    const selector = '.okf-comment-mark[data-comment-id="' + cssEscape(pendingId) + '"]';
    if (body.querySelector(selector)) return; // visible mark exists
    // Cross-node resolution so a pending highlight spanning inline elements
    // survives body patch. Do not keep the pending ID without a visible mark.
    const range = resolveCommentRange(body, anchor.ref, anchor.block_id);
    if (range) wrapRangeInMark(range, pendingId, "open");
  }
  // Retained for compatibility: wraps a single-node {node, start, end} result
  // in a comment mark. New callers should use resolveCommentRange +
  // wrapRangeInMark for full cross-node support.
  function wrapTextNode(found, commentId, commentState) {
    try {
      const range = document.createRange();
      range.setStart(found.node, found.start);
      range.setEnd(found.node, found.end);
      wrapRangeInMark(range, commentId, commentState);
    } catch (e) { /* invalid range; skip */ }
  }
  // Render a visible stale anchor indicator at the end of the body. The
  // comment's original text was edited or removed; this mark gives users a
  // non-color cue (dotted underline via .okf-comment-mark--stale) and a
  // clickable pin to jump to the comment card. Does NOT falsify exact text
  // anchoring — it is clearly appended at the end with its own label.
  function appendStaleMark(body, c) {
    // Don't duplicate if a stale mark for this comment already exists.
    var existing = body.querySelector('.okf-comment-mark--stale[data-comment-id="' + cssEscape(c.id) + '"]');
    if (existing) return;
    var ref = (c.anchor && c.anchor.ref) || "";
    var mark = el("mark", {
      class: "okf-comment-mark okf-comment-mark--stale",
      "data-comment-id": c.id,
      "data-comment-state": c.state || "open",
      role: "button",
      tabindex: "0",
      title: "Comment anchor: \"" + ref + "\" (text was edited or removed)",
      "aria-label": "Stale comment anchor: " + ref.substring(0, 60) + (ref.length > 60 ? "…" : ""),
    });
    mark.textContent = "💬 " + ref.substring(0, 40) + (ref.length > 40 ? "…" : "");
    mark.addEventListener("click", function () { jumpToCommentCard(c.id); });
    mark.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); jumpToCommentCard(c.id); }
    });
    // Wrap in a subtle paragraph so it flows as a separate line at the end.
    var p = el("p", { class: "okf-comment-stale-anchor" });
    p.appendChild(mark);
    body.appendChild(p);
  }
  function jumpToCommentMark(commentId) {
    const mark = document.querySelector('.okf-comment-mark[data-comment-id="' + cssEscape(commentId) + '"]');
    if (!mark) return false;
    mark.scrollIntoView({ block: "center", behavior: REDUCED_MOTION ? "auto" : "smooth" });
    if (!REDUCED_MOTION) {
      mark.classList.remove("okf-pulse");
      void mark.offsetWidth;
      mark.classList.add("okf-pulse");
    }
    return true;
  }
  function cssEscape(s) {
    // Minimal CSS.escape polyfill (attribute selector on comment ids, which
    // are ULID/local-* strings - safe character set, but guard anyway).
    if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, (ch) => "\\" + ch);
  }

  // Editorial Workbench Round 2: open the Comments overlay and scroll+pulse
  // the card for a given comment id. Mirrors jumpToActivity (Changes panel,
  // ~line 3507). Requires cards to carry data-comment-id (tagged in
  // commentCard below) so the pin's click target can be found post-render.
  // Single-owner jump state: only one active comment-id/card/timer at a time.
  // New jump, close, rerender, or resolve cancels the previous and clears
  // transient state without detached-node mutation.
  var _jumpState = { id: null, card: null, timer: null, retryTimer: null, prevTabindex: null };

  function _clearJumpContext() {
    if (_jumpState.timer) { clearTimeout(_jumpState.timer); _jumpState.timer = null; }
    if (_jumpState.retryTimer) { clearTimeout(_jumpState.retryTimer); _jumpState.retryTimer = null; }
    if (_jumpState.card && _jumpState.card.isConnected) {
      _jumpState.card.classList.remove("okf-comment--jumped");
      if (_jumpState.prevTabindex === null) _jumpState.card.removeAttribute("tabindex");
      else _jumpState.card.setAttribute("tabindex", _jumpState.prevTabindex);
    }
    _jumpState.id = null;
    _jumpState.card = null;
    _jumpState.prevTabindex = null;
  }

  function jumpToCommentCard(commentId) {
    _clearJumpContext();
    openPanel("comments");
    const body = panelBodyEl();
    if (!body) return false;
    _jumpState.id = commentId;
    let tries = 0;
    (function find() {
      if (_jumpState.id !== commentId) return; // superseded by new jump/close
      const card = body.querySelector('.okf-comment[data-comment-id="' + cssEscape(commentId) + '"]');
      if (!card) {
        if (tries++ < 20) _jumpState.retryTimer = setTimeout(find, 25);
        return;
      }
      if (_jumpState.id !== commentId) return; // superseded
      card.scrollIntoView({ block: "center", behavior: REDUCED_MOTION ? "auto" : "smooth" });
      if (!REDUCED_MOTION) {
        card.classList.remove("okf-pulse");
        void card.offsetWidth;
        card.classList.add("okf-pulse");
      }
      _jumpState.prevTabindex = card.getAttribute("tabindex");
      card.setAttribute("tabindex", "-1");
      try { card.focus({ preventScroll: true }); } catch (e) {}
      card.classList.add("okf-comment--jumped");
      _jumpState.card = card;
      _jumpState.timer = setTimeout(_clearJumpContext, 4000);
    })();
    return true;
  }

  // --- composer ---------------------------------------------------------
  function composerNode() {
    const wrap = el("div", { class: "okf-composer" });
    const anchorRow = el("div", { class: "okf-composer__anchor", "aria-live": "polite" });
    const anchorLabel = el("span", { text: "On: " });
    const anchorRef = el("code");
    anchorRow.appendChild(anchorLabel);
    anchorRow.appendChild(anchorRef);
    const textarea = el("textarea", { class: "okf-composer__textarea", rows: "3",
      "aria-label": "Comment for agent", placeholder: "Ask the agent to enrich, link, extract, rewrite…" });
    textarea.value = state.draftBody || "";
    textarea.addEventListener("input", () => { state.draftBody = textarea.value; });
    const actions = el("div", { class: "okf-composer__actions" });
    // iter3 CRI3-011: was "⏎ to send · Esc clears selection anchor" — a
    // bare emoji glyph that renders inconsistently across platforms
    // (Apple's return-symbol, some Windows fonts show a missing-glyph
    // box) and was the only non-SVG/Unicode-glyph icon strategy in the
    // composer. Use a <kbd> element per WCAG/UU conventions for keyboard
    // hints: accessible (semantics), consistent across platforms, and
    // conventional for kbd hints. The studio.css already styles kbd
    // (wiki.css:516 .okf-prose code applies; composer adds its own
    // .okf-composer__kbd weight).
    const hint = el("span", { class: "okf-composer__hint" });
    hint.appendChild(el("kbd", { class: "okf-composer__kbd", text: "Enter" }));
    hint.appendChild(document.createTextNode(" to send · "));
    hint.appendChild(el("kbd", { class: "okf-composer__kbd", text: "Esc" }));
    hint.appendChild(document.createTextNode(" clears selection anchor"));
    const cancel = el("button", { type: "button", class: "okf-iconbtn", text: "Cancel" });
    const submit = el("button", { type: "button", class: "okf-studiobtn okf-composer__submit", text: "Send" });
    function refreshAnchor() {
      const a = state.draftAnchor || { kind: "concept", ref: state.conceptId };
      anchorRef.textContent = a.kind === "text" ? ("“" + (a.ref || "") + "”" + (a.section ? "  § " + a.section : "")) : (a.ref || state.conceptId);
    }
    refreshAnchor();
    cancel.addEventListener("click", () => {
      clearPendingCommentDraft(); // Cancel: clear draftBody too
      textarea.value = "";
      refreshAnchor();
    });
    submit.addEventListener("click", () => postCommentFromComposer(textarea, submit, refreshAnchor));
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); postCommentFromComposer(textarea, submit, refreshAnchor); }
      else if (e.key === "Escape") { cancel.click(); }
    });
    actions.appendChild(hint); actions.appendChild(cancel); actions.appendChild(submit);
    wrap.appendChild(anchorRow); wrap.appendChild(textarea); wrap.appendChild(actions);
    wrap._focus = () => { try { textarea.focus(); } catch (e) {} };
    wrap._setAnchorConceptLevel = () => {
      state.draftAnchor = { kind: "concept", ref: state.conceptId };
      refreshAnchor();
    };
    return wrap;
  }
  async function postCommentFromComposer(textarea, submit, refreshAnchor) {
    const body = (textarea.value || "").trim();
    if (!body) { textarea.focus(); return; }
    if (!EDIT) { toast("Commenting is disabled (read-only studio).", { tone: "error" }); return; }
    const anchor = state.draftAnchor || { kind: "concept", ref: state.conceptId };
    // The anchor's concept wins over state.conceptId: on the graph page
    // state.conceptId is the literal "__graph", while onAffordanceClick
    // resolved the detail panel's real concept into draftAnchor.concept.
    // The server takes the top-level `concept` field verbatim, so posting
    // state.conceptId there would file the comment against a nonexistent
    // concept.
    const concept = anchor.concept || state.conceptId;
    var parentForPost = state.replyTo || null;
    state.replyTo = null; // clear after capturing
    // Optimistic: insert a local "posting" comment immediately. The id is
    // the same one used for the mark wrapped in onAffordanceClick, so the
    // mark and the optimistic row stay linked.
    const localId = state._pendingMarkId || ("local-" + (state.nextCommentSeq++));
    state._pendingMarkId = null;
    const optimistic = {
      id: localId, concept, anchor, body, state: "open", claimed_by: null,
      resolved_activity: [], ts: new Date().toISOString(), _posting: true,
      parent_id: parentForPost, // carry the parent so the optimistic row
                                // appears in the right thread immediately
    };
    state.comments.unshift(optimistic);
    renderCommentsPanel(); updateBadges(); rebuildMarginMarkers();
    textarea.value = ""; state.draftBody = "";
    state.draftAnchor = { kind: "concept", ref: state.conceptId };
    refreshAnchor();
    submit.disabled = true; submit.textContent = "Sending…";
    try {
      const res = await tokenFetch("/__comment", {
        method: "POST",
        body: { concept, body, anchor, actor: "user", detail: {}, parent_id: parentForPost || null },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) throw new Error(data.error || ("HTTP " + res.status));
      // Drop the optimistic row, then upsert the server-confirmed record by
      // id (handles the SSE race that may have inserted it already).
      const confirmed = data.comment || {};
      const confirmedId = confirmed.id || localId;
      state.comments = state.comments.filter((c) => c.id !== localId);
      upsertComment(confirmed);
      // iter1 CRI-002: rename the optimistic mark to the confirmed id so the
      // highlight survives the optimistic→confirmed transition.
      if (confirmedId !== localId) renameCommentMark(localId, confirmedId);
      renderCommentsPanel(); updateBadges(); applyCommentMarks(); rebuildMarginMarkers();
      toast("Comment posted.", { tone: "success" });
    } catch (e) {
      // Roll back the optimistic row AND the optimistic mark.
      state.comments = state.comments.filter((c) => c.id !== localId);
      removeCommentMark(localId);
      renderCommentsPanel(); updateBadges(); applyCommentMarks(); rebuildMarginMarkers();
      // iter1 CRI-009: em dash replaced with a period.
      toast("Comment failed: " + (e.message || e) + ". Your text is still in the composer.", { tone: "error", ttl: 7000 });
      textarea.value = body; state.draftBody = body;
      state.draftAnchor = anchor; refreshAnchor();
    } finally {
      submit.disabled = false; submit.textContent = "Send";
    }
  }

  // --- margin markers ---------------------------------------------------
  // iter1 CRI-002/CRI-014: markers now anchor to the commented <mark>
  // element (not the section heading), so the indicator sits beside the
  // exact text the user pointed at. Stale comments (mark not found after a
  // patch) get no marker. Resolved comments collapse to a small stub.
  function rebuildMarginMarkers() {
    const article = $("article.okf-page__main");
    if (!article) return;
    let rail = $(".okf-comment-rail", article);
    if (!EDIT || !isConceptPage()) { if (rail) rail.remove(); return; }
    if (!rail) {
      // The article needs relative positioning for the absolute rail.
      const cs = getComputedStyle(article);
      if (cs.position === "static") article.style.position = "relative";
      rail = el("div", { class: "okf-comment-rail", "aria-hidden": "true" });
      article.appendChild(rail);
    }
    rail.innerHTML = "";
    const mine = state.comments.filter((c) => c.concept === state.conceptId);
    if (!mine.length) return;
    const body = $(".okf-page__body") || article;
    const placed = []; // {top, comment} to stack overlapping markers
    mine.forEach((c) => {
      const marks = $$('.okf-comment-mark[data-comment-id="' + cssEscape(c.id) + '"]', body);
      if (!marks.length) return; // stale or not-yet-applied: no marker
      // Use the first mark's vertical position; stack if it overlaps a prior.
      const first = marks[0];
      const top = (first.offsetTop != null)
        ? first.offsetTop
        : (first.getBoundingClientRect().top - article.getBoundingClientRect().top + article.scrollTop);
      // Stack: nudge down if within 22px of a prior marker.
      let adjusted = top;
      for (let attempt = 0; attempt < 8; attempt++) {
        const clash = placed.some((p) => Math.abs(p.top - adjusted) < 22);
        if (!clash) break;
        adjusted += 20;
      }
      placed.push({ top: adjusted, comment: c });
      const isResolved = c.state === "resolved";
      // iter2 CRI2-010: the marker is a real <button> (keyboard-focusable,
      // click opens the comment) but had only a visual title=, so screen
      // readers announced an empty button. Give it an accessible name that
      // conveys what it's on + its lifecycle state. Comments in this model
      // are user-authored (the agent claims/resolves), so the actor is the
      // user; claimed_by (the agent) surfaces in the state chip + panel.
      const sel = (c.anchor && c.anchor.ref) ? ("\u201c" + c.anchor.ref + "\u201d") : ("\u201c" + c.body.slice(0, 60) + "\u201d");
      const ariaLabel = "Comment by user on " + sel + ", " + (c.state || "open");
      const marker = el("button", {
        type: "button",
        class: "okf-comment-marker" + (isResolved ? " okf-comment-marker--stub" : ""),
        "data-state": c.state || "open",
        "data-comment-id": c.id,
        "aria-label": ariaLabel,
        title: (isResolved ? "Resolved: " : "Comment on ") + sel,
        style: { top: adjusted + "px" },
      });
      if (!isResolved) marker.textContent = "•";
      marker.addEventListener("click", () => {
        jumpToCommentMark(c.id);   // scroll+pulse the prose mark
        jumpToCommentCard(c.id);   // open the overlay + scroll+pulse the card
      });
      rail.appendChild(marker);
    });
  }

  // --- comments panel render -------------------------------------------
  //
  // Comments panel structure. The panel is split into three persistent zones that
  // live inside panelBody for the lifetime of one "open" session:
  //
  //   .okf-comment-composer-section  — composer (or read-only notice)
  //   .okf-comment-toolbar-wrap      — sort / time / archive / expand-all
  //   .okf-comment-list-wrap         — the threaded list (2-level cap)
  //
  // Each render mutates ONE zone's innerHTML at a time. The composer zone
  // is left untouched when the user is typing in it (preserveComposer
  // guard below) so a live SSE rebuild NEVER blurs the textarea or wipes
  // the in-progress draft. The toolbar + list always rebuild — their
  // state lives in state.commentView / state.comments, never in DOM. Scroll
  // position is saved + restored around the list rebuild so the user
  // isn't yanked back to the top when a new comment arrives.
  //
  // Threading: 2 levels max (root → reply → reply-to-reply). Anything
  // deeper is rendered flat at level 2 (buildCommentTree /
  // effectiveLevel). Orphans (parent_id pointing at a comment not in the
  // current set) are hoisted to roots. Cycles are guarded.
  //
  // State: view prefs (sort / timeFilter / showArchived / expanded /
  // allExpanded) live in state.commentView, persisted to localStorage under
  // "okf:commentView" so they survive a refresh.

  // localStorage key for commentView. Inlined into load/save (rather than
  // a shared var) so the state literal at the top of the IIFE can call
  // loadCommentView() at init time without depending on a var-declaration
  // hoisting order: a top-level `var KEY = "..."` would still be undefined
  // when the state object literal runs.
  var COMMENT_VIEW_KEY = "okf:commentView";
  function loadCommentView() {
    var defaults = {
      sort: "newest",        // newest | status | updated
      timeFilter: "all",     // today | 7days | all
      showArchived: false,
      expanded: {},          // { commentId: true/false }
      allExpanded: true,     // global default for threads w/o an override
    };
    try {
      var raw = localStorage.getItem("okf:commentView");
      if (!raw) return Object.assign({}, defaults);
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return Object.assign({}, defaults);
      return Object.assign({}, defaults, parsed, {
        expanded: Object.assign({}, parsed.expanded || {}),
      });
    } catch (e) {
      return Object.assign({}, defaults);
    }
  }
  function saveCommentView() {
    try {
      localStorage.setItem("okf:commentView", JSON.stringify(state.commentView));
    } catch (e) { /* localStorage may be unavailable (private mode, quota); non-fatal */ }
  }

  // Status rank for "sort by status" — open first, then claimed, then
  // resolved, then dismissed, then archived. Anything unknown sorts last.
  // NOTE: use nullish check, not `|| 5` — open's rank IS 0 (falsy), so
  // `0 || 5` would incorrectly fall through to 5 and bury open comments
  // at the bottom of a status sort.
  function commentStatusRank(s) {
    // Archived is no longer a state value (separate track).
    var v = ({ open: 0, claimed: 1, resolved: 2, dismissed: 3 })[s];
    return v === undefined ? 4 : v;
  }
  function sortRoots(list, mode) {
    var arr = list.slice();
    if (mode === "status") {
      arr.sort(function (a, b) {
        var ra = commentStatusRank(a.state), rb = commentStatusRank(b.state);
        if (ra !== rb) return ra - rb;
        return byTsDesc(a, b);
      });
    } else {
      // "newest" and "updated" both fall back to ts-desc. The directives
      // feed is append-only with last-write-wins, so the visible ts on a
      // root already reflects its latest activity (state transition OR new
      // reply post, both of which append a record). The two sorts are
      // distinct menu options because future schema work may split
      // created_ts from updated_ts; the client code is identical today.
      arr.sort(byTsDesc);
    }
    return arr;
  }
  // Epoch-ms within the time-filter window. today = last 24h, 7days = last
  // 7d. Sliding window in UTC epoch ms — no DST / timezone sensitivity
  // (the cutoff is "now - window", independent of the user's zone).
  function commentInTimeWindow(c, mode) {
    if (!mode || mode === "all") return true;
    if (!c.ts) return false;
    var t = Date.parse(c.ts);
    if (isNaN(t)) return false;
    var cutoff = Date.now() - (mode === "today" ? 24 * 3600 * 1000 : 7 * 24 * 3600 * 1000);
    return t >= cutoff;
  }

  // Build the 2-level-capped thread tree. Returns:
  //   roots              — array of effective-level-0 comments (sorted ts-desc)
  //   directChildren(id) — level-1 replies (children of a root)
  //   level2Of(id)       — flat list of all transitive descendants of a
  //                        level-1 reply, rendered at level 2
  //   byId               — id → comment lookup
  function buildCommentTree(comments) {
    var byId = {};
    comments.forEach(function (c) { if (c && c.id) byId[c.id] = c; });
    var byParent = {};
    comments.forEach(function (c) {
      if (!c || !c.parent_id) return;
      if (!byParent[c.parent_id]) byParent[c.parent_id] = [];
      byParent[c.parent_id].push(c);
    });
    function effectiveLevel(comment) {
      var lvl = 0;
      var guard = {};
      var cur = comment;
      // Walk parent chain until we hit a root, a missing parent, or a
      // cycle. Cap at 2 (rendered depth); guard set defends against
      // cycles in malformed data.
      while (cur && cur.parent_id && byId[cur.parent_id]) {
        if (guard[cur.id]) break;
        guard[cur.id] = true;
        lvl++;
        cur = byId[cur.parent_id];
        if (lvl >= 2) break; // 2-level cap; deeper renders as level 2
      }
      return lvl;
    }
    var roots = comments.filter(function (c) { return effectiveLevel(c) === 0; });
    roots = roots.slice().sort(byTsDesc);
    function directChildren(id) {
      return (byParent[id] || []).slice().sort(byTsDesc);
    }
    // Flat BFS over all descendants of a level-1 reply. The `seen` set
    // guards against cycles; everything collected renders at level 2.
    function level2Of(id) {
      var out = [];
      var stack = (byParent[id] || []).slice();
      var seen = {};
      while (stack.length) {
        var c = stack.shift();
        if (!c || seen[c.id]) continue;
        seen[c.id] = true;
        out.push(c);
        var kids = byParent[c.id] || [];
        for (var i = 0; i < kids.length; i++) stack.push(kids[i]);
      }
      return out.sort(byTsDesc);
    }
    // All transitive descendants of a root (for the time-filter "any
    // activity in this thread" rule).
    function threadHasRecentActivity(root, mode) {
      if (commentInTimeWindow(root, mode)) return true;
      var stack = (byParent[root.id] || []).slice();
      var seen = {};
      while (stack.length) {
        var c = stack.shift();
        if (!c || seen[c.id]) continue;
        seen[c.id] = true;
        if (commentInTimeWindow(c, mode)) return true;
        var kids = byParent[c.id] || [];
        for (var i = 0; i < kids.length; i++) stack.push(kids[i]);
      }
      return false;
    }
    return {
      roots: roots, byId: byId, byParent: byParent,
      directChildren: directChildren, level2Of: level2Of,
      threadHasRecentActivity: threadHasRecentActivity,
    };
  }

  // Expand/collapse. Per-comment overrides live in commentView.expanded
  // and take precedence over the global allExpanded default. Toggling a
  // single thread writes only that one id; "expand/collapse all" resets
  // the per-comment overrides and flips the global default.
  function isCommentExpanded(commentId) {
    if (Object.prototype.hasOwnProperty.call(state.commentView.expanded, commentId)) {
      return !!state.commentView.expanded[commentId];
    }
    return !!state.commentView.allExpanded;
  }
  function setCommentExpanded(commentId, expanded) {
    state.commentView.expanded[commentId] = !!expanded;
    saveCommentView();
  }
  function toggleCommentExpand(commentId) {
    setCommentExpanded(commentId, !isCommentExpanded(commentId));
    renderCommentsPanel();
  }
  function toggleAllExpand() {
    state.commentView.allExpanded = !state.commentView.allExpanded;
    state.commentView.expanded = {};
    saveCommentView();
    renderCommentsPanel();
  }

  function renderCommentsPanel() {
    if (state.openPanel !== "comments") return;
    var body = panelBodyEl();
    if (!body) return;

    // Resolve or create the three persistent zones. On the first render
    // of an open session they don't exist yet; create + append them. On
    // subsequent renders (SSE, user toggles, etc.) they persist, so the
    // composer textarea node survives across rebuilds.
    var intentsZone = body.querySelector(".okf-comment-intents-wrap");
    var composerZone = body.querySelector(".okf-comment-composer-section");
    var toolbarZone = body.querySelector(".okf-comment-toolbar-wrap");
    var listZone = body.querySelector(".okf-comment-list-wrap");
    var initial = !(intentsZone && composerZone && toolbarZone && listZone);
    if (initial) {
      body.innerHTML = "";
      // Quick-action directives sit at the very top of the Comments tab.
      intentsZone = el("div", { class: "okf-comment-intents-wrap" });
      composerZone = el("div", { class: "okf-panel__section okf-comment-composer-section" });
      toolbarZone = el("div", { class: "okf-comment-toolbar-wrap" });
      listZone = el("div", { class: "okf-comment-list-wrap" });
      body.appendChild(intentsZone);
      body.appendChild(composerZone);
      body.appendChild(toolbarZone);
      body.appendChild(listZone);
    }

    // Preserve the composer zone if the user is interacting with it. The
    // textarea is never removed from the DOM during a typing session, so
    // focus + selection + draft are all retained byte-for-byte.
    var ta = composerZone.querySelector(".okf-composer__textarea");
    var active = document.activeElement;
    var preserveComposer = !initial && ta &&
      (ta === active || (ta.value && ta.value.trim().length > 0));
    if (!preserveComposer) {
      var composerScroll = body.scrollTop;
      composerZone.innerHTML = "";
      if (EDIT) {
        appendComposerContents(composerZone, body);
      } else {
        composerZone.appendChild(el("p", {
          class: "okf-empty",
          text: "Commenting is disabled (read-only studio).",
        }));
      }
      body.scrollTop = composerScroll;
    }

    // Quick-action directive toolbar (stateless — rebuilt each render). Only
    // when commenting is enabled; the buttons pre-fill the composer above.
    intentsZone.innerHTML = "";
    if (EDIT) intentsZone.appendChild(buildIntentsToolbar());

    // Rebuild the toolbar + list, EXCEPT when the user is mid-
    // reply in an inline composer. The inline composer lives inside
    // listZone; rebuilding would destroy its textarea, losing the draft
    // and focus. Skip the whole list rebuild in that case — the next
    // SSE update (after the user submits or cancels) will catch up.
    // The toolbar zone has no user-input elements, so it's safe to
    // always rebuild.
    var listScroll = body.scrollTop;
    toolbarZone.innerHTML = "";
    toolbarZone.appendChild(buildCommentToolbar());
    var inlineBusy = _inlineReplyBusy();
    if (!inlineBusy) {
      listZone.innerHTML = "";
      listZone.appendChild(buildCommentList());
    }
    body.scrollTop = listScroll;
  }

  // Returns true if there's an inline reply composer (the per-card
  // textarea created by buildCommentActions' Reply button) that is
  // currently focused OR contains non-empty draft text. Used to skip the
  // comment-list rebuild during renderCommentsPanel so a live update can
  // never destroy a draft the user is actively typing.
  //
  // Mirrors the top-level composer guard at line ~1440. Both guards exist
  // because the two composers live in different DOM zones (composerZone
  // vs listZone) with different rebuild semantics.
  function _inlineReplyBusy() {
    var inline = document.querySelector(".okf-inline-reply textarea");
    if (!inline) return false;
    var active = document.activeElement;
    if (inline === active) return true;
    var v = (inline.value || "").trim();
    return v.length > 0;
  }

  // Build the composer block (h3 + reply context + composerNode). Honors
  // the openPanel({focusComposer:true}) flag exactly once — the flag is
  // consumed on first build so an SSE rebuild mid-typing can't steal focus.
  function appendComposerContents(zone, body) {
    var replyContext = "";
    if (state.replyTo) {
      var parent = state.comments.find(function (c) { return c.id === state.replyTo; });
      if (parent) replyContext = "Replying to: " + (parent.body || "").slice(0, 60);
    }
    var composer = composerNode();
    if (replyContext) {
      var ctx = el("div", { class: "okf-composer__reply-context", text: replyContext });
      composer.insertBefore(ctx, composer.firstChild);
    }
    zone.appendChild(el("h3", {
      class: "okf-panel__section-title",
      text: replyContext ? "Reply" : "Ask the agent",
    }));
    zone.appendChild(composer);
    if (composer._focus && body && body._focusComposer) {
      body._focusComposer = false; // consume: only the openPanel opener focuses
      setTimeout(function () { try { composer._focus(); } catch (e) {} }, 30);
    }
  }

  // Toolbar: sort + time-filter selects on the left, "show archived" +
  // "expand/collapse all" toggles on the right. Each control writes back
  // to state.commentView, persists, and re-renders.
  function buildCommentToolbar() {
    var tb = el("div", {
      class: "okf-comment-toolbar",
      role: "region",
      "aria-label": "Comment view controls",
    });
    var g1 = el("div", { class: "okf-comment-toolbar__group" });
    var sortSel = el("select", {
      class: "okf-comment-toolbar__select",
      "aria-label": "Sort comments",
      title: "Sort order",
    });
    [["newest", "Newest"], ["status", "Status"], ["updated", "Updated"]].forEach(function (opt) {
      var o = el("option", { value: opt[0], text: opt[1] });
      if (state.commentView.sort === opt[0]) o.selected = true;
      sortSel.appendChild(o);
    });
    sortSel.addEventListener("change", function () {
      state.commentView.sort = sortSel.value;
      saveCommentView();
      renderCommentsPanel();
    });
    g1.appendChild(sortSel);

    var timeSel = el("select", {
      class: "okf-comment-toolbar__select",
      "aria-label": "Filter comments by time",
      title: "Time window",
    });
    [["all", "All time"], ["today", "Today"], ["7days", "Last 7 days"]].forEach(function (opt) {
      var o = el("option", { value: opt[0], text: opt[1] });
      if (state.commentView.timeFilter === opt[0]) o.selected = true;
      timeSel.appendChild(o);
    });
    timeSel.addEventListener("change", function () {
      state.commentView.timeFilter = timeSel.value;
      saveCommentView();
      renderCommentsPanel();
    });
    g1.appendChild(timeSel);
    tb.appendChild(g1);

    var g2 = el("div", { class: "okf-comment-toolbar__group" });
    var archBtn = el("button", {
      type: "button",
      class: "okf-studiobtn okf-comment-toolbar__toggle",
      "aria-pressed": state.commentView.showArchived ? "true" : "false",
      text: state.commentView.showArchived ? "Hide archived" : "Show archived",
    });
    archBtn.addEventListener("click", function () {
      state.commentView.showArchived = !state.commentView.showArchived;
      saveCommentView();
      renderCommentsPanel();
    });
    g2.appendChild(archBtn);

    var allOpen = state.commentView.allExpanded;
    var expBtn = el("button", {
      type: "button",
      class: "okf-studiobtn okf-comment-toolbar__toggle",
      text: allOpen ? "Collapse all" : "Expand all",
      title: allOpen ? "Collapse every thread" : "Expand every thread",
    });
    expBtn.addEventListener("click", toggleAllExpand);
    g2.appendChild(expBtn);
    tb.appendChild(g2);

    return tb;
  }

  function buildCommentList() {
    var wrap = el("div", { class: "okf-comment-list" });
    var tree = buildCommentTree(state.comments);

    // Apply archive + time filters at the ROOT level. Replies inherit
    // visibility from their root (collapsing a thread hides everything;
    // expanding shows all descendants regardless of their own ts).
    var visibleRoots = tree.roots.filter(function (root) {
      if (root.archived && !state.commentView.showArchived) return false;
      if (!tree.threadHasRecentActivity(root, state.commentView.timeFilter)) return false;
      return true;
    });
    var sorted = sortRoots(visibleRoots, state.commentView.sort);

    if (sorted.length === 0) {
      wrap.appendChild(el("p", { class: "okf-empty", text: commentListEmptyMessage() }));
      return wrap;
    }
    sorted.forEach(function (root) {
      wrap.appendChild(renderRootCard(root, tree));
    });
    return wrap;
  }

  function commentListEmptyMessage() {
    if (!state.comments || state.comments.length === 0) {
      return "No comments yet. Select text and click Comment, or use the composer above.";
    }
    var hasArchived = state.comments.some(function (c) { return !!c.archived; });
    if (!state.commentView.showArchived && hasArchived &&
        state.comments.every(function (c) { return !!c.archived; })) {
      return "All comments are archived. Toggle “Show archived” to see them.";
    }
    if (state.commentView.timeFilter !== "all") {
      return "No comments in this time window. Try a wider filter.";
    }
    return "No comments match the current filter.";
  }

  function renderRootCard(root, tree) {
    var expanded = isCommentExpanded(root.id);
    // Gather all replies for the collapsed preview + thread-resolved check.
    var allReplies = [];
    tree.directChildren(root.id).forEach(function (l1) {
      allReplies.push(l1);
      tree.level2Of(l1.id).forEach(function (l2) { allReplies.push(l2); });
    });
    var threadResolved = root.state === "resolved" &&
      allReplies.every(function (r) { return r.state === "resolved"; });
    var card = commentCard(root, 0, {
      expanded: expanded,
      replies: allReplies,
      isRoot: true,
      threadResolved: threadResolved,
    });
    if (!expanded) return card;
    var l1 = tree.directChildren(root.id);
    if (!l1.length) return card;
    var children = el("div", { class: "okf-comment__children" });
    l1.forEach(function (reply) {
      children.appendChild(commentCard(reply, 1, { isRoot: false }));
      var l2 = tree.level2Of(reply.id);
      if (l2.length) {
        var inner = el("div", { class: "okf-comment__children" });
        l2.forEach(function (r2) { inner.appendChild(commentCard(r2, 2, { isRoot: false })); });
        children.appendChild(inner);
      }
    });
    card.appendChild(children);
    return card;
  }

  // level: 0 (root), 1 (reply), 2 (reply-to-reply, or anything deeper that
  // has been capped to level 2 by buildCommentTree). opts.expanded only
  // applies to roots; replies never collapse independently.
  function commentCard(c, level, opts) {
    level = level || 0;
    opts = opts || {};
    var expanded = Object.prototype.hasOwnProperty.call(opts, "expanded")
      ? !!opts.expanded
      : true;
    var isRoot = level === 0;
    var collapsed = isRoot && !expanded;

    var cls = "okf-comment okf-comment--level-" + level;
    if (level > 0) cls += " okf-comment--reply"; // compatibility hook for extensions
    if (collapsed) cls += " okf-comment--collapsed";

    var card = el("div", {
      class: cls,
      id: "comment-" + (c.id || ""),
      // commentId: data-comment-id — the functional pin (jumpToCommentCard)
      // matches on this to scroll+pulse the card a mark/marker points at.
      dataset: { state: c.state || "open", level: String(level), commentId: c.id || "" },
    });

    // Header row: chevron (root only) + state chip + anchor + meta.
    var header = el("div", { class: "okf-comment__header" });
    if (isRoot) {
      var chev = el("button", {
        type: "button",
        class: "okf-comment__chevron",
        "aria-expanded": expanded ? "true" : "false",
        "aria-controls": "comment-" + (c.id || ""),
        "aria-label": (expanded ? "Collapse" : "Expand") + " thread" +
          (c.body ? ": " + c.body.slice(0, 60) : ""),
        title: expanded ? "Collapse thread" : "Expand thread",
      });
      chev.addEventListener("click", function () { toggleCommentExpand(c.id); });
      header.appendChild(chev);
    }
    header.appendChild(el("span", { class: "okf-comment__state", text: c.state || "open" }));
    if (c.archived) {
      header.appendChild(el("span", { class: "okf-comment__archived-chip", text: "archived" }));
    }
    appendAnchorChip(header, c);
    // Show created-at + updated-at timestamps. Server stamps updated_at on
    // every transition (claim/resolve/dismiss/reopen/archive/unarchive/
    // reply). If they differ, show both; otherwise show just created.
    var createdTs = c.ts || "";
    var updatedTs = c.updated_at || c.ts || "";
    if (createdTs && updatedTs && createdTs !== updatedTs) {
      header.appendChild(el("span", { class: "okf-comment__ts", text: "created " + fmtTime(createdTs) }));
      header.appendChild(el("span", { class: "okf-comment__ts okf-comment__ts--updated", text: "updated " + fmtTime(updatedTs) }));
    } else {
      header.appendChild(el("span", { class: "okf-comment__ts", text: fmtTime(createdTs) }));
    }
    if (c._posting) header.appendChild(el("span", { class: "okf-comment__posting", text: "posting…" }));
    card.appendChild(header);

    if (collapsed) {
      // Collapsed preview: show short body for EVERY comment in the thread
      // (root + all replies), not just the root. Each preview is a one-line
      // ellipsis with the actor prefix.
      //
      // Two summary fields, shown in priority order:
      //   - ``summary`` (resolve-time "what the agent did") — explicit,
      //     takes precedence when set (typically on agent replies).
      //   - ``request_summary`` (claim-time "what was asked" OR auto-
      //     derived from body) — always present, used for user comments
      //     and as a fallback.
      // The preview reads as a status board: each agent reply shows its
      // "done" tag; each user comment shows its "ask" tag.
      var allInThread = [c];
      if (opts.replies) {
        opts.replies.forEach(function (r) { allInThread.push(r); });
      }
      allInThread.forEach(function (tc) {
        var bodyText = (tc.body || "").trim();
        var doneSummary = (tc.summary || "").trim();
        var askSummary = (tc.request_summary || "").trim();
        var who = tc.actor === "agent" ? "Agent" : "You";
        var line = el("div", { class: "okf-comment__preview" });
        line.appendChild(el("span", { class: "okf-comment__preview-who", text: who + ": " }));
        if (doneSummary) {
          // Agent's "done" tag — accent + italic.
          var dSlice = doneSummary.length > 100 ? doneSummary.slice(0, 100) + "\u2026" : doneSummary;
          line.appendChild(el("span", { class: "okf-comment__preview-summary", text: dSlice }));
        } else if (askSummary) {
          // Auto-derived or claim-set "ask" tag — muted + italic.
          var aSlice = askSummary.length > 100 ? askSummary.slice(0, 100) + "\u2026" : askSummary;
          line.appendChild(el("span", { class: "okf-comment__preview-ask", text: aSlice }));
        } else {
          var previewText = bodyText.length > 100 ? bodyText.slice(0, 100) + "\u2026" : bodyText;
          line.appendChild(document.createTextNode(previewText));
        }
        card.appendChild(line);
      });
      return card;
    }

    // Expanded body + ask/done summaries + reply + resolved details + actions.
    card.appendChild(el("div", { class: "okf-comment__body", text: c.body || "" }));
    // Two summary chips side by side.
    //   - request_summary: short of what was ASKED (auto-derived from body
    //     or set explicitly via claim --summary). Labelled "asked".
    //   - summary: short of what the agent DID (set via resolve --summary).
    //     Labelled "done".
    // Both are shown above the longform reply so the card reads as
    // ask → done → detail at a glance.
    if (c.request_summary) {
      var askEl = el("div", { class: "okf-comment__summary okf-comment__summary--ask" });
      askEl.appendChild(el("span", { class: "okf-comment__summary-label", text: "asked: " }));
      askEl.appendChild(document.createTextNode(c.request_summary));
      card.appendChild(askEl);
    }
    if (c.summary) {
      var doneEl = el("div", { class: "okf-comment__summary okf-comment__summary--done" });
      doneEl.appendChild(el("span", { class: "okf-comment__summary-label", text: "done: " }));
      doneEl.appendChild(document.createTextNode(c.summary));
      card.appendChild(doneEl);
    }
    if (c.reply) {
      var rep = el("div", { class: "okf-comment__reply" });
      rep.appendChild(el("strong", { text: "Agent: " }));
      rep.appendChild(document.createTextNode(c.reply));
      card.appendChild(rep);
    }
    if (c.resolved_activity && c.resolved_activity.length) {
      var det = el("details");
      det.appendChild(el("summary", {
        text: "Resolved by " + c.resolved_activity.length + " change(s). Jump",
      }));
      c.resolved_activity.forEach(function (aid) {
        var a = el("a", { href: "#", text: "change #" + shortId(String(aid)) });
        a.addEventListener("click", function (e) {
          e.preventDefault();
          jumpToActivity(String(aid));
        });
        det.appendChild(el("div", {}, [a]));
      });
      card.appendChild(det);
    }

    // Action row. Hidden in read-only studios — the writes would 403 and
    // presenting dead verbs is worse than hiding them.
    if (EDIT) {
      card.appendChild(buildCommentActions(c, {
        isRoot: opts.isRoot,
        threadResolved: opts.threadResolved,
      }));
    }
    return card;
  }

  function appendAnchorChip(header, c) {
    if (c.anchor && c.anchor.kind === "text" && c.anchor.ref) {
      var jump = el("button", {
        type: "button",
        class: "okf-comment__anchor",
        title: "Jump to the commented text",
        text: "“" + c.anchor.ref + "”",
      });
      jump.addEventListener("click", function () {
        var ok = jumpToCommentMark(c.id);
        if (!ok) toast("The commented text was edited or removed.", { tone: "info", ttl: 4000 });
      });
      header.appendChild(jump);
      if (c._stale) header.appendChild(el("span", { class: "okf-comment__posting", text: "anchor moved" }));
    } else if (c.concept) {
      var a = el("a", { href: "/" + c.concept });
      a.textContent = c.concept;
      header.appendChild(document.createTextNode("on "));
      header.appendChild(a);
    }
  }

  function buildCommentActions(c, opts) {
    opts = opts || {};
    var isRoot = !!opts.isRoot;
    var threadResolved = !!opts.threadResolved;
    var actions = el("div", { class: "okf-comment__actions" });
    var replyBtn = el("button", { type: "button", class: "okf-comment__action", text: "Reply" });
    replyBtn.addEventListener("click", function () {
      // Insert an inline reply composer directly below this comment card.
      // Remove any existing inline composer first (one at a time).
      var existing = document.querySelector(".okf-inline-reply");
      if (existing) existing.remove();
      var card = document.getElementById("comment-" + c.id);
      if (!card) return;
      var replyWrap = el("div", { class: "okf-inline-reply" });
      // Context indicator.
      replyWrap.appendChild(el("div", {
        class: "okf-composer__reply-context",
        text: "Replying to: " + (c.body || "").slice(0, 80),
      }));
      // Inline textarea.
      var ta = el("textarea", {
        class: "okf-composer__textarea okf-inline-reply__textarea",
        rows: "2",
        placeholder: "Reply…",
        "aria-label": "Reply to comment",
      });
      replyWrap.appendChild(ta);
      // Action row.
      var row = el("div", { class: "okf-composer__actions" });
      var submit = el("button", { type: "button", class: "okf-studiobtn okf-studiobtn--primary", text: "Reply" });
      var cancel = el("button", { type: "button", class: "okf-studiobtn", text: "Cancel" });
      cancel.addEventListener("click", function () { replyWrap.remove(); });
      submit.addEventListener("click", function () {
        var body = (ta.value || "").trim();
        if (!body) { ta.focus(); return; }
        submit.disabled = true; submit.textContent = "Sending…";
        tokenFetch("/__comment", {
          method: "POST",
          body: {
            concept: c.concept || state.conceptId,
            body: body,
            anchor: { kind: "concept", ref: c.concept || state.conceptId },
            actor: "user",
            detail: {},
            parent_id: c.id,
          },
        }).then(function (res) { return res.json(); }).then(function (data) {
          if (!data.ok) throw new Error(data.error || "failed");
          upsertComment(data.comment);
          // Server auto-unarchives parent on reply; refresh the parent too.
          if (c.parent_id) {
            var p = state.comments.find(function (x) { return x.id === c.parent_id; });
            if (p && p.archived) p.archived = false;
          }
          replyWrap.remove();
          renderCommentsPanel();
          toast("Reply posted.", { tone: "success" });
        }).catch(function (e) {
          submit.disabled = false; submit.textContent = "Reply";
          toast("Reply failed: " + e.message, { tone: "error" });
        });
      });
      ta.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit.click(); }
        if (e.key === "Escape") { replyWrap.remove(); }
      });
      row.appendChild(submit);
      row.appendChild(cancel);
      replyWrap.appendChild(row);
      // Insert AFTER the card's children container (if any) so the reply
      // box appears at the bottom of the thread, right where the Reply
      // button is. Fall back to after the card itself.
      var childrenEl = card.querySelector(":scope > .okf-comment__children");
      if (childrenEl) {
        childrenEl.appendChild(replyWrap);
      } else {
        card.appendChild(replyWrap);
      }
      setTimeout(function () { ta.focus(); }, 30);
    });
    actions.appendChild(replyBtn);

    // Edit: amend the body of a not-yet-resolved comment in place (the
    // enter-too-soon fix). Shown on user-authored comments only — agent
    // comments/replies are the agent's record, not the user's to rewrite.
    // The server rejects edits on resolved/dismissed comments (409).
    if (c.actor !== "agent" && c.state !== "resolved" && c.state !== "dismissed") {
      var editBtn = el("button", { type: "button", class: "okf-comment__action", text: "Edit" });
      editBtn.addEventListener("click", function () {
        var existing = document.querySelector(".okf-inline-reply");
        if (existing) existing.remove();
        var card = document.getElementById("comment-" + c.id);
        if (!card) return;
        var editWrap = el("div", { class: "okf-inline-reply okf-inline-edit" });
        editWrap.appendChild(el("div", {
          class: "okf-composer__reply-context",
          text: "Editing comment",
        }));
        var ta = el("textarea", {
          class: "okf-composer__textarea okf-inline-reply__textarea",
          rows: "3",
          "aria-label": "Edit comment",
        });
        ta.value = c.body || "";
        editWrap.appendChild(ta);
        var row = el("div", { class: "okf-composer__actions" });
        var save = el("button", { type: "button", class: "okf-studiobtn okf-studiobtn--primary", text: "Save" });
        var cancelEdit = el("button", { type: "button", class: "okf-studiobtn", text: "Cancel" });
        cancelEdit.addEventListener("click", function () { editWrap.remove(); });
        save.addEventListener("click", function () {
          var body = (ta.value || "").trim();
          if (!body) { ta.focus(); return; }
          if (body === (c.body || "").trim()) { editWrap.remove(); return; }
          save.disabled = true; save.textContent = "Saving…";
          tokenFetch("/__comment-update", {
            method: "POST",
            body: { id: c.id, body: body },
          }).then(function (res) { return res.json(); }).then(function (data) {
            if (!data.ok) throw new Error(data.error || "failed");
            upsertComment(data.comment);
            editWrap.remove();
            renderCommentsPanel();
            toast("Comment updated.", { tone: "success" });
          }).catch(function (e) {
            save.disabled = false; save.textContent = "Save";
            toast("Edit failed: " + e.message, { tone: "error" });
          });
        });
        ta.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); save.click(); }
          if (e.key === "Escape") { editWrap.remove(); }
        });
        row.appendChild(save);
        row.appendChild(cancelEdit);
        editWrap.appendChild(row);
        card.appendChild(editWrap);
        setTimeout(function () { ta.focus(); }, 30);
      });
      actions.appendChild(editBtn);
    }

    // Lifecycle verbs (Cancel / Reopen). These DO NOT touch the archive
    // flag — archive is a separate track.
    if (c.state === "open" && !c.claimed_by) {
      var cancelBtn = el("button", { type: "button", class: "okf-comment__action", text: "Cancel" });
      cancelBtn.addEventListener("click", function () { updateCommentState(c.id, "dismissed"); });
      actions.appendChild(cancelBtn);
    }
    if (c.state === "dismissed") {
      var reopenBtn = el("button", { type: "button", class: "okf-comment__action", text: "Reopen" });
      reopenBtn.addEventListener("click", function () { updateCommentState(c.id, "open"); });
      actions.appendChild(reopenBtn);
    }

    // Archive / Unarchive: ONLY on the root comment. Archive requires
    // every comment in the thread to be resolved (server-enforced, but
    // we also disable the button client-side to give a clear affordance).
    // Unarchive is always available on an archived root.
    if (isRoot) {
      if (c.archived) {
        var unarchBtn = el("button", {
          type: "button",
          class: "okf-comment__action",
          text: "Unarchive",
        });
        unarchBtn.addEventListener("click", function () { setCommentArchived(c.id, false); });
        actions.appendChild(unarchBtn);
      } else if (threadResolved) {
        var archBtn2 = el("button", {
          type: "button",
          class: "okf-comment__action",
          text: "Archive thread",
          title: "Archive this thread. Requires all comments resolved.",
        });
        archBtn2.addEventListener("click", function () { setCommentArchived(c.id, true); });
        actions.appendChild(archBtn2);
      } else {
        // Disabled affordance so the user can see what's missing.
        var archDisabled = el("button", {
          type: "button",
          class: "okf-comment__action okf-comment__action--disabled",
          text: "Archive thread",
          disabled: true,
          title: "Archive is available once every comment in the thread is resolved.",
        });
        actions.appendChild(archDisabled);
      }
    }
    return actions;
  }

  async function updateCommentState(commentId, newState) {
    try {
      await tokenFetch("/__comment-update", {
        method: "POST",
        body: { id: commentId, state: newState },
      });
      var c = state.comments.find(function (x) { return x.id === commentId; });
      if (c) {
        c.state = newState;
        c.updated_at = new Date().toISOString();
        // Clear jump context if the resolved/canceled comment was the active
        // jump target — its card will be destroyed by renderCommentsPanel.
        if (_jumpState.id === commentId) _clearJumpContext();
        renderCommentsPanel();
      }
    } catch (e) {
      toast("Failed to update comment.", { tone: "error" });
    }
  }

  // Archive is a SEPARATE track from lifecycle state. Setting
  // archived=true/false does NOT touch open/resolved/dismissed. The server
  // enforces "archive only on root + only when whole thread is resolved";
  // we surface the rejection reason in the toast.
  async function setCommentArchived(commentId, archived) {
    try {
      var res = await tokenFetch("/__comment-update", {
        method: "POST",
        body: { id: commentId, archived: archived },
      });
      var data = await res.json();
      if (!data.ok) {
        var msg = data.error || "failed";
        if (data.unresolved_ids && data.unresolved_ids.length) {
          msg = "Resolve every comment in the thread first (" +
            data.unresolved_ids.length + " unresolved).";
        }
        toast(msg, { tone: "error", ttl: 6000 });
        return;
      }
      var c = state.comments.find(function (x) { return x.id === commentId; });
      if (c) {
        c.archived = archived;
        c.updated_at = new Date().toISOString();
        renderCommentsPanel();
        toast(archived ? "Thread archived." : "Thread unarchived.",
          { tone: "info" });
      }
    } catch (e) {
      toast("Failed to update archive.", { tone: "error" });
    }
  }

  // ====================================================================
  // 6. Presence (current spec §12)
  // ====================================================================
  function renderPresence(p) {
    state.presence = p || { state: "idle" };
    const st = p && p.state || "idle";
    // iter2 G13: record presence transitions for the Agent-activity panel's
    // presence-history section (unique content the Changes panel doesn't
    // show). Dedup consecutive identical (state, focus) so a noisy feed
    // doesn't flood the log; cap at 24 entries.
    const focus = (p && p.focus) || "";
    // The free-text progress line ("linking 3 of 7 tables…") is part of the
    // dedup key so mid-pass message updates land in the presence history —
    // that history IS the progress log for a long multi-concept pass.
    const message = (p && p.message) || "";
    const last = state.presenceHistory[0];
    if (!last || last.state !== st || last.focus !== focus || (last.message || "") !== message) {
      state.presenceHistory.unshift({ state: st, focus: focus, message: message, ts: new Date().toISOString() });
      if (state.presenceHistory.length > 24) state.presenceHistory.length = 24;
    }
    presenceChip.dataset.state = st;
    presenceChip.setAttribute("aria-label", "Agent presence: " + st
      + (p && p.focus ? " " + p.focus : "")
      + (message ? " — " + message : ""));
    presenceLabel.innerHTML = "";
    presenceLabel.appendChild(el("span", { class: "okf-presence__actor", text: "Agent" }));
    const verb = ({ idle: "idle", watching: "watching", thinking: "thinking about", editing: "editing" })[st] || st;
    presenceLabel.appendChild(document.createTextNode(" " + verb));
    if (p && p.focus) {
      presenceLabel.appendChild(document.createTextNode(" "));
      const a = el("a", { href: "/" + p.focus });
      a.textContent = p.focus;
      presenceLabel.appendChild(a);
    }
    if (message) {
      presenceLabel.appendChild(el("span", {
        class: "okf-presence__message",
        text: " — " + message,
        title: message,
      }));
    }
    // iter2 G11: keep the "Agent watching" toggle in sync with the agent's
    // live presence. Only "watching" reads as on; every other state (idle,
    // thinking, editing) reads as off. This is the canonical source — the
    // click handler's optimistic toggle is reverted here if the POST failed.
    // iter3 CRI3-010: also keep the concise aria-label in sync with state
    // so the screen-reader name reflects the live value (not just the
    // initial "currently off").
    if (watchingToggle) {
      const watchingOn = st === "watching";
      watchingToggle.setAttribute("aria-pressed", watchingOn ? "true" : "false");
      watchingToggle.setAttribute("aria-label",
        "Agent watching, currently " + (watchingOn ? "on" : "off"));
    }
    highlightFocusedConcept(p && p.focus);
  }
  function highlightFocusedConcept(focus) {
    stampConceptIds();
    // iter1 CRI-004: clear every presence highlight (list rows + article),
    // then re-apply to the matching row if any. Idle (no focus) leaves the
    // workspace clean so a stale "agent here" cue never lingers.
    $$(".okf-presence-focus").forEach((n) => n.classList.remove("okf-presence-focus"));
    $$(".okf-focus-highlight").forEach((n) => n.classList.remove("okf-focus-highlight"));
    state._lastFocus = focus || null;
    if (!focus) return;
    // On the open concept page, outline the article.
    if (focus === state.conceptId) {
      const article = $("article.okf-page__main");
      if (article) article.classList.add("okf-focus-highlight");
    }
    // On index/search pages, highlight the matching row by data-concept-id.
    const row = document.querySelector('[data-concept-id="' + cssEscape(focus) + '"]');
    if (row) row.classList.add("okf-presence-focus");
  }
  // iter1 CRI-004: stamp data-concept-id on list/search/sidebar rows so the
  // presence focus highlight can resolve against them. Done lazily once per
  // page (rows are server-rendered; a patch would re-trigger via boot).
  let conceptIdsStamped = false;
  function stampConceptIds() {
    if (conceptIdsStamped) return;
    conceptIdsStamped = true;
    $$(".okf-concept-list li").forEach((li) => {
      if (li.getAttribute("data-concept-id")) return;
      const a = li.querySelector("a[href]");
      const id = hrefToConceptId(a && a.getAttribute("href"));
      if (id) li.setAttribute("data-concept-id", id);
    });
    $$(".okf-search-result").forEach((art) => {
      if (art.getAttribute("data-concept-id")) return;
      const a = art.querySelector("a[href]");
      const id = hrefToConceptId(a && a.getAttribute("href"));
      if (id) art.setAttribute("data-concept-id", id);
    });
    $$(".okf-local-graph__node").forEach((btn) => {
      if (btn.getAttribute("data-concept-id")) return;
      const t = btn.getAttribute("data-target");
      if (t) btn.setAttribute("data-concept-id", t);
    });
  }
  // ---- Phase 5: index engagement (recency rail + comment chips) --------
  // Runs on index pages only, after loadGraph()/loadComments() resolve
  // (called from both — idempotent; the rail rebuilds so labels upgrade
  // once graph data lands). Everything reads state the studio already
  // fetched, so this costs no extra requests.
  function buildIndexEngagement() {
    if (!document.body.classList.contains("okf-viewer--index")) return;
    const titleOf = {};
    if (state.graph && Array.isArray(state.graph.nodes)) {
      state.graph.nodes.forEach((n) => { if (n && n.data) titleOf[n.data.id] = n.data.label; });
    }
    // 1) Comment-count chips on concept cards.
    const counts = {};
    (state.comments || []).forEach((c) => {
      if (!c || !c.concept) return;
      if (c.state === "archived") return;
      counts[c.concept] = (counts[c.concept] || 0) + 1;
    });
    $$(".okf-concept-list li[data-concept-id]").forEach((li) => {
      const id = li.getAttribute("data-concept-id");
      if (!counts[id]) return;
      let chip = li.querySelector(".okf-card__comments");
      if (!chip) {
        chip = el("span", { class: "okf-card__comments" });
        const meta = li.querySelector(".okf-card__meta");
        if (meta) meta.appendChild(chip);
        else li.appendChild(el("span", { class: "okf-card__meta" }, [chip]));
      }
      chip.textContent = "💬 " + counts[id];
      chip.title = counts[id] + " comment" + (counts[id] === 1 ? "" : "s");
    });
    // 2) Recently-changed rail in the hero (top 5 concepts by latest
    // structural event, newest first).
    const hero = $(".okf-hero");
    if (!hero || !Array.isArray(state.events) || !state.events.length) return;
    const latest = {};
    state.events.forEach((ev) => {
      if (!ev || !ev.ts) return;
      if (ev.type !== "changed" && ev.type !== "created" && ev.type !== "removed" && ev.type !== "activity") return;
      (ev.ids || []).forEach((id) => {
        if (!latest[id] || latest[id].ts < ev.ts) latest[id] = { ts: ev.ts, type: ev.type };
      });
    });
    const ranked = Object.keys(latest)
      .sort((a, b) => (latest[a].ts < latest[b].ts ? 1 : -1))
      .slice(0, 5);
    if (!ranked.length) return;
    let rail = $("#okf-recent-rail");
    if (rail) rail.remove();
    rail = el("div", { class: "okf-recent", id: "okf-recent-rail" });
    rail.appendChild(el("span", { class: "okf-recent__label", text: "Recently changed" }));
    ranked.forEach((id) => {
      const a = el("a", { class: "okf-recent__item", href: "/" + id });
      a.appendChild(el("strong", { text: titleOf[id] || id }));
      a.appendChild(document.createTextNode(" · " + fmtAgo(latest[id].ts)));
      rail.appendChild(a);
    });
    hero.appendChild(rail);
  }

  function hrefToConceptId(href) {
    if (!href || typeof href !== "string") return null;
    // Strip .html (static mode) AND .md (some index render paths emit the
    // source extension), plus any leading slash, so the id matches the form
    // presence.focus / currentConceptId use (e.g. "tables/orders").
    let h = href.trim().replace(/\.(html|md)$/, "").replace(/^\/+/, "");
    if (!h || h.indexOf("__") === 0 || h.indexOf("://") >= 0 || h.indexOf("#") === 0) return null;
    return h;
  }

  // ====================================================================
  // 7. Change list (§12.2) + Undo (§12.5)
  // ====================================================================
  // iter1 CRI-005 → iter2 G9: virtualization constants. iter3 CRI3-005
  // hoists these ABOVE renderChangeList so the prepend-shift compensation
  // can read CHANGE_EST_ROW_H without hitting a `const` temporal-dead-zone
  // (the function is defined before the constants were under the old
  // structure).
  const CHANGE_VIRTUAL_WINDOW = 80;   // rows kept in the DOM at any time
  const CHANGE_VIRTUAL_OVERSCAN = 20; // extra rows rendered above/below the viewport
  const CHANGE_VIRTUAL_STEP = 30;     // how far the window slides per sentinel hit
  const CHANGE_EST_ROW_H = 56;        // initial estimate; re-measured after first paint
  const CHANGE_HARD_CAP = 1000;       // display cap (gates the upfront note)
  const CHANGE_TOTAL_CAP = (window.OKF_LOOM_CHANGE_TOTAL_CAP > 0) ? window.OKF_LOOM_CHANGE_TOTAL_CAP : 10000;

  // iter3 CRI3-005: when a live event is prepended to state.events (via
  // upsertEvent → unshift), the next renderChangeList rebuild produces an
  // ordered array that is 1 row longer at the TOP. The virtualizer
  // honours savedScroll by indexing into the NEW ordered array — so the
  // same INDEX window now points at different rows (everything shifted
  // down by `prepended`). The user's reading row drifts UP by one row
  // per live event. Compensate by tracking the previous render's ordered
  // count + the active filter tuple: when the filters are unchanged AND
  // the new ordered is longer at the head (a genuine prepend, not a
  // filter relaxation), shift savedScroll by `prepended * CHANGE_EST_ROW_H`
  // so the same ROWS stay at the same on-screen offset. Only shift when
  // the user was actually scrolled into the list (savedScroll > 0); a
  // user at the top wants to see the new event arrive at the top.
  let _lastChangeListOrderedCount = 0;
  let _lastChangeListFilters = { actor: "", action: "", concept: "" };

  function renderChangeList() {
    if (state.openPanel !== "changes") return;
    const body = panelBodyEl();
    if (!body) return;
    // iter2 CRI2-003 / §7.3: renderChangeList rebuilds the panel from scratch
    // on every live event (activity/changed/created/removed). A from-scratch
    // rebuild resets scroll to the top AND drops focus/selection inside the
    // filter inputs, so a user scrolled down to row 200 reading history loses
    // their place the moment a new event lands. Capture the scroll offset +
    // the focused filter (with its caret selection) before the rebuild and
    // restore both after, so a live update is non-disruptive while the panel
    // is open. (The windowing IntersectionObserver still owns lazy row load.)
    const savedScroll = body.scrollTop;
    const active = document.activeElement;
    const savedFocus = (active && body.contains(active) && (active.tagName === "INPUT" || active.tagName === "SELECT"))
      ? { tag: active.tagName, ariaLabel: active.getAttribute("aria-label") || "",
          selStart: active.selectionStart, selEnd: active.selectionEnd,
          selDir: active.selectionDirection }
      : null;
    // iter3 CRI3-005: snapshot the previous render's bookkeeping BEFORE
    // the rebuild so we can detect a genuine prepend (vs a filter change).
    const prevOrderedCount = _lastChangeListOrderedCount;
    const prevFilters = _lastChangeListFilters;
    const filtersUnchanged =
      prevFilters.actor === state.filters.actor &&
      prevFilters.action === state.filters.action &&
      prevFilters.concept === state.filters.concept;
    body.innerHTML = "";

    const filters = el("div", { class: "okf-filters" });
    const actorSel = el("select", { "aria-label": "Filter by actor" });
    actorSel.appendChild(el("option", { value: "", text: "All actors" }));
    ["agent", "user", "cli", "disk"].forEach((a) => actorSel.appendChild(el("option", { value: a, text: a })));
    actorSel.value = state.filters.actor;
    actorSel.addEventListener("change", () => { state.filters.actor = actorSel.value; renderChangeList(); });
    const actionInput = el("input", { type: "search", placeholder: "filter action…",
      "aria-label": "Filter by action", value: state.filters.action });
    actionInput.addEventListener("input", () => { state.filters.action = actionInput.value.trim(); renderChangeList(); });
    const conceptInput = el("input", { type: "search", placeholder: "filter concept…",
      "aria-label": "Filter by concept", value: state.filters.concept });
    conceptInput.addEventListener("input", () => { state.filters.concept = conceptInput.value.trim(); renderChangeList(); });
    filters.appendChild(actorSel); filters.appendChild(actionInput); filters.appendChild(conceptInput);
    body.appendChild(filters);

    const list = el("div", { class: "okf-changes" });
    // iter3 CRI3-005: hoist `effectiveSavedScroll` and `newOrderedCount`
    // out of the else-branch so the post-rebuild scroll restore + the
    // next-render bookkeeping can both read them. effectiveSavedScroll
    // starts at savedScroll and is bumped inside the else-branch when a
    // genuine prepend is detected; newOrderedCount is 0 for the empty
    // state and `ordered.length` when rows render.
    let effectiveSavedScroll = savedScroll;
    let newOrderedCount = 0;
    // Timeline rows: agent activity (has `action`) AND bundle changes
    // (changed/created/removed - e.g. a disk save the watcher picked up).
    // comment/presence/graph/ready have their own surfaces and are excluded.
    let rows = state.events.filter((e) => {
      const t = e.type;
      if (t === "comment" || t === "presence" || t === "graph" || t === "ready") return false;
      return !!e.action || (Array.isArray(e.ids) && e.ids.length) ||
        t === "changed" || t === "created" || t === "removed";
    });
    if (state.filters.actor) rows = rows.filter((e) => (e.actor || e.origin || "") === state.filters.actor);
    if (state.filters.action) rows = rows.filter((e) => String(e.action || e.type || "").indexOf(state.filters.action) >= 0);
    if (state.filters.concept) rows = rows.filter((e) => (e.ids || []).some((id) => id.indexOf(state.filters.concept) >= 0));
    if (!rows.length) {
      list.appendChild(el("p", { class: "okf-empty", text: "No changes yet. Edit a file on disk, or the agent will act on your comments." }));
    } else {
      // Group consecutive same-group_id rows into single composite items so
      // the window count reflects what the user actually sees. iter2 G12:
      // events tagged with a burst_id (10+ standalone events in 1s) collapse
      // the same way into one expandable "Agent made N changes" row.
      const groups = Object.create(null);
      const bursts = Object.create(null);
      const ordered = [];
      rows.forEach((r) => {
        if (r.group_id) {
          if (!groups[r.group_id]) { groups[r.group_id] = []; ordered.push({ group: r.group_id }); }
          groups[r.group_id].push(r);
        } else if (r.burst_id) {
          if (!bursts[r.burst_id]) { bursts[r.burst_id] = []; ordered.push({ burst: r.burst_id }); }
          bursts[r.burst_id].push(r);
        } else ordered.push({ row: r });
      });
      newOrderedCount = ordered.length;
      // iter1 CRI-005 / iter2 G9: virtualize the rendered rows so a long
      // session keeps only the visible window in the DOM. iter2 G12 burst
      // coalescing + G10 upfront cap messaging ride the same renderer.
      //
      // iter3 CRI3-005: if this rebuild prepended rows at the head (a live
      // event arrived, filters unchanged, ordered grew), shift savedScroll
      // by `prepended * CHANGE_EST_ROW_H` so the virtualizer renders the
      // window that contains the SAME rows the user was reading (instead
      // of the same INDICES, which now point at different rows). Skip the
      // shift when the user was at the top (savedScroll === 0) — they
      // expect to see new events land at the top.
      if (
        savedScroll > 0 && filtersUnchanged && ordered.length > prevOrderedCount
      ) {
        const prepended = ordered.length - prevOrderedCount;
        effectiveSavedScroll = savedScroll + prepended * CHANGE_EST_ROW_H;
      }
      renderWindowedChanges(list, ordered, groups, {
        savedScroll: effectiveSavedScroll, savedFocus, body, bursts,
      });
    }
    body.appendChild(list);
    // Remember this render's bookkeeping for the NEXT render's prepend
    // detection (CRI3-005). Snapshot the filters too so a filter change
    // (which can also change ordered.length) is not misread as a prepend.
    _lastChangeListOrderedCount = newOrderedCount;
    _lastChangeListFilters = {
      actor: state.filters.actor,
      action: state.filters.action,
      concept: state.filters.concept,
    };
    // iter2 CRI2-003: restore the panel scroll offset + filter focus captured
    // before the rebuild. The virtualizer (renderWindowedChanges) positions
    // its initial window at the rows visible at savedScroll, so setting
    // scrollTop here lands at the same reading position without a flash.
    // iter3 CRI3-005: when a prepend shifted the window, restore the
    // SHIFTED offset so the user keeps looking at the same row.
    if (rows.length && typeof effectiveSavedScroll === "number") {
      body.scrollTop = effectiveSavedScroll;
    } else if (typeof savedScroll === "number") {
      body.scrollTop = savedScroll;
    }
    if (savedFocus) {
      const sel = savedFocus.ariaLabel
        ? body.querySelector(savedFocus.tag + '[aria-label="' + savedFocus.ariaLabel + '"]')
        : null;
      if (sel) {
        try { sel.focus({ preventScroll: true }); } catch (e) {}
        try {
          if (typeof sel.setSelectionRange === "function" && savedFocus.selStart != null) {
            sel.setSelectionRange(savedFocus.selStart, savedFocus.selEnd, savedFocus.selDir || "none");
          }
        } catch (e) {}
      }
    }
  }

  // ---- change-list virtualization (iter1 CRI-005 → iter2 G9) -----------
  // iter1 shipped incremental-prepend windowing: the first N rows rendered,
  // then a bottom sentinel IntersectionObserver appended more as the user
  // scrolled, but rows were never REMOVED, so a long session left hundreds
  // of DOM nodes attached. iter2 G9 replaces it with TRUE virtualization:
  // only a sliding window of ~CHANGE_VIRTUAL_WINDOW rows is ever in the DOM,
  // driven by top + bottom IntersectionObserver sentinels; top/bottom
  // spacers (sized by a measured row height) maintain the scrollbar
  // geometry so the user can scroll through the full history. A display
  // cap (CHANGE_HARD_CAP) gates the visible count with an UPFRONT "Showing
  // first N of M. Show all" note (G10 — shown before the user scrolls, not
  // after). The absolute virtualization ceiling is CHANGE_TOTAL_CAP (10000,
  // configurable via window.OKF_LOOM_CHANGE_TOTAL_CAP); upsertEvent caps the
  // in-memory log to match so older entries rotate out of state cleanly.
  // (Constants declared above renderChangeList — iter3 CRI3-005.)

  function renderWindowedChanges(list, ordered, groups, restore) {
    restore = restore || {};
    const bursts = restore.bursts || Object.create(null);  // iter2 G12 burst members
    const scrollContainer = restore.body || list;  // .okf-panel__body (overflow-y: auto)
    const savedScroll = (typeof restore.savedScroll === "number") ? restore.savedScroll : 0;

    // G10: the display cap. If the filtered set exceeds CHANGE_HARD_CAP,
    // surface the "Showing first N of M. Show all" note UP FRONT (before the
    // user scrolls), and virtualize only the first N until the user asks for
    // all. "Show all" raises the virtualization ceiling to CHANGE_TOTAL_CAP
    // (the absolute max; rows beyond it are rotated out of state by
    // upsertEvent).
    let virtualTotal = Math.min(ordered.length, CHANGE_HARD_CAP);
    let capped = ordered.length > CHANGE_HARD_CAP;
    if (capped) {
      const note = el("div", { class: "okf-changes__cap-note" });
      note.appendChild(document.createTextNode(
        "Showing first " + CHANGE_HARD_CAP + " of " + ordered.length + " events. "));
      const show = el("button", { type: "button", text: "Show more" });
      show.addEventListener("click", () => {
        // Raise the ceiling to the absolute cap and re-virtualize the full
        // tail. The note stays (it now reads as the absolute ceiling).
        note.parentNode && note.parentNode.removeChild(note);
        virtualTotal = Math.min(ordered.length, CHANGE_TOTAL_CAP);
        capped = ordered.length > CHANGE_TOTAL_CAP;
        if (capped) appendAbsoluteCapNote();
        rebuild();
      });
      note.appendChild(show);
      list.appendChild(note);
    }
    function appendAbsoluteCapNote() {
      const note = el("div", { class: "okf-changes__cap-note", role: "status" });
      note.appendChild(document.createTextNode(
        "Showing the most recent " + CHANGE_TOTAL_CAP + " of " + ordered.length +
        " events. Older entries are in events.jsonl."));
      list.appendChild(note);
    }

    // Virtualization scaffold: topSpacer + window rows + bottomSpacer. The
    // spacers carry the scrollbar geometry (height = offscreen-rows *
    // rowH); the window rows are the only .okf-change nodes in the DOM.
    const topSpacer = el("div", { class: "okf-changes__spacer okf-changes__spacer--top", "aria-hidden": "true" });
    const bottomSpacer = el("div", { class: "okf-changes__spacer okf-changes__spacer--bottom", "aria-hidden": "true" });
    const topSentinel = el("div", { class: "okf-changes__sentinel okf-changes__sentinel--top", "aria-hidden": "true" });
    const bottomSentinel = el("div", { class: "okf-changes__sentinel okf-changes__sentinel--bottom", "aria-hidden": "true" });
    const rowsHost = el("div", { class: "okf-changes__rows" });
    list.appendChild(topSpacer);
    list.appendChild(topSentinel);
    list.appendChild(rowsHost);
    list.appendChild(bottomSentinel);
    list.appendChild(bottomSpacer);

    let windowStart = 0;           // index of the first rendered row
    let rowH = CHANGE_EST_ROW_H;   // measured row height (updated after paint)
    const renderedIdx = new Map(); // index -> DOM node currently attached

    function clampStart(s) {
      const maxStart = Math.max(0, virtualTotal - windowSize());
      return Math.max(0, Math.min(s, maxStart));
    }
    function windowSize() {
      return Math.min(CHANGE_VIRTUAL_WINDOW, virtualTotal);
    }
    // syncWindow(start): make the rendered set exactly the window
    // [start, start + windowSize) (clamped). Removes rows that scrolled out,
    // adds rows that scrolled in, and resizes the spacers so the scrollbar
    // reflects the full virtualTotal * rowH content height.
    function syncWindow(start) {
      const want = clampStart(start);
      if (want === windowStart && renderedIdx.size > 0) return;
      windowStart = want;
      const last = Math.min(virtualTotal, want + windowSize());
      // Drop rows outside [want, last).
      Array.from(renderedIdx.keys()).forEach((i) => {
        if (i < want || i >= last) {
          const node = renderedIdx.get(i);
          if (node && node.parentNode) node.parentNode.removeChild(node);
          renderedIdx.delete(i);
        }
      });
      // Add missing rows in [want, last), in order.
      for (let i = want; i < last; i++) {
        if (renderedIdx.has(i)) continue;
        const node = changeItemOrGroup(ordered[i], groups, bursts);
        node.setAttribute("data-virtual-idx", String(i));
        // Insert before any later-rendered node; since we iterate ascending,
        // append unless a higher-index node already exists.
        let inserted = false;
        for (let j = i + 1; j < last; j++) {
          const after = renderedIdx.get(j);
          if (after) { rowsHost.insertBefore(node, after); inserted = true; break; }
        }
        if (!inserted) rowsHost.appendChild(node);
        renderedIdx.set(i, node);
      }
      topSpacer.style.height = (want * rowH) + "px";
      bottomSpacer.style.height = (Math.max(0, virtualTotal - last) * rowH) + "px";
    }
    // Measure the real row height once rows are painted, then re-sync so the
    // spacers match actual geometry (avoids scrollbar drift on wrap).
    function measureRowH() {
      const sample = rowsHost.firstElementChild;
      if (!sample) return;
      const h = sample.getBoundingClientRect().height;
      if (h > 12 && Math.abs(h - rowH) > 1) {
        rowH = h;
        // Re-sync spacer heights with the corrected height (windowStart unchanged).
        const last = Math.min(virtualTotal, windowStart + windowSize());
        topSpacer.style.height = (windowStart * rowH) + "px";
        bottomSpacer.style.height = (Math.max(0, virtualTotal - last) * rowH) + "px";
      }
    }

    // Initial window. Honour a saved scroll offset (G1): start the window at
    // the rows that would be visible at savedScroll so the restore doesn't
    // flash the top.
    const initialStart = clampStart(Math.floor((savedScroll || 0) / rowH) - CHANGE_VIRTUAL_OVERSCAN);
    syncWindow(initialStart);
    requestAnimationFrame(measureRowH);

    // IntersectionObserver sentinels: when the user scrolls to either edge
    // of the window, slide it by CHANGE_VIRTUAL_STEP (re-sync removes the
    // rows that left + adds the new ones). root is the scroll container
    // (.okf-panel__body), NOT panelShell (the .okf-panel aside does not
    // scroll; using it was a latent bug in the iter1 observer).
    function shift(delta) { syncWindow(windowStart + delta); }
    const ioOpts = { root: scrollContainer, rootMargin: "120px" };
    const topIo = new IntersectionObserver((entries) => {
      for (const ent of entries) {
        if (ent.isIntersecting && windowStart > 0) shift(-CHANGE_VIRTUAL_STEP);
      }
    }, ioOpts);
    const bottomIo = new IntersectionObserver((entries) => {
      for (const ent of entries) {
        if (ent.isIntersecting && windowStart + windowSize() < virtualTotal) shift(CHANGE_VIRTUAL_STEP);
      }
    }, ioOpts);
    topIo.observe(topSentinel);
    bottomIo.observe(bottomSentinel);

    // rebuild(): used by "Show more" to re-virtualize against a raised
    // ceiling without rebuilding the whole panel (preserves scroll + focus).
    function rebuild() {
      // Reset the window against the new virtualTotal, keeping the current
      // scroll position.
      const curScroll = scrollContainer.scrollTop;
      renderedIdx.forEach((n) => { if (n.parentNode) n.parentNode.removeChild(n); });
      renderedIdx.clear();
      const start = clampStart(Math.floor(curScroll / rowH) - CHANGE_VIRTUAL_OVERSCAN);
      syncWindow(start);
      requestAnimationFrame(measureRowH);
    }
  }
  // Builds a change row/group node without appending (used by the loader).
  function changeItemOrGroup(item, groups, bursts) {
    if (item.row) return changeRow(item.row);
    if (item.burst) {
      // iter2 G12: a burst composite (10+ standalone events in 1s). Renders
      // as a <details> so the expand is native + keyboard-accessible (Enter/
      // Space toggles). The summary is one "Agent made N changes" line; the
      // body lists the individual change rows so the user can drill in.
      const members = bursts[item.burst];
      const det = el("details", { class: "okf-change okf-change--burst", dataset: { actor: members[0].actor } });
      const sum = el("summary", { class: "okf-change__summary" });
      sum.appendChild(el("span", { class: "okf-change__icon", "aria-hidden": "true" }));
      const actorRaw = (members[0] && members[0].actor) || "agent";
      const actor = actorRaw.charAt(0).toUpperCase() + actorRaw.slice(1);
      sum.appendChild(el("span", { text: actor + " made " + members.length + " changes in one burst. " }));
      sum.appendChild(el("span", { class: "okf-change__burst-hint", text: "Expand for detail" }));
      det.appendChild(sum);
      const body = el("div", { class: "okf-change__burst-body" });
      members.forEach((m) => body.appendChild(changeRow(m)));
      det.appendChild(body);
      return det;
    }
    const members = groups[item.group];
    const wrap = el("div", { class: "okf-change okf-change--group", dataset: { actor: members[0].actor } });
    wrap.appendChild(el("span", { class: "okf-change__icon", "aria-hidden": "true" }));
    const b = el("div", { class: "okf-change__body" });
    b.appendChild(el("div", { class: "okf-change__summary", text: members.length + " changes · group pass" }));
    b.appendChild(el("div", { class: "okf-change__meta" }, [el("span", { text: members[0].actor + " · " + fmtTime(members[0].ts) })]));
    wrap.appendChild(b);
    const actions = el("div", { class: "okf-change__actions" });
    const undo = el("button", { type: "button", class: "okf-change__undo", text: "Undo group" });
    undo.addEventListener("click", () => undoGroup(item.group, undo));
    actions.appendChild(undo);
    wrap.appendChild(actions);
    return wrap;
  }

  function changeRow(r) {
    const actor = r.actor || r.origin || "system";
    const kind = r.type === "changed" ? "Saved" : r.type === "created" ? "Created" : r.type === "removed" ? "Removed" : null;
    const summary = r.summary || (kind ? (kind + " " + ((r.ids || [])[0] || "")) : (actor + " " + (r.action || "acted")));
    const row = el("div", { class: "okf-change", dataset: { actor: actor, activityId: String(r.id || "") } });
    row.appendChild(el("span", { class: "okf-change__icon", "aria-hidden": "true" }));
    const b = el("div", { class: "okf-change__body" });
    b.appendChild(el("div", { class: "okf-change__summary", text: summary }));
    const meta = el("div", { class: "okf-change__meta" });
    meta.appendChild(el("span", { text: actor + " · " + (r.action || r.type || "") + " · " + fmtTime(r.ts) }));
    (r.ids || []).forEach((id) => {
      meta.appendChild(document.createTextNode(" · "));
      const a = el("a", { href: "/" + id, text: id });
      meta.appendChild(a);
    });
    b.appendChild(meta);
    // R1 (INTENT2-007): if a comment_link event exists for this activity,
    // render a back-link to the originating comment. The comment_link event
    // is emitted by resolve_comment and carries (activity_id, comment_id).
    const link = state.events.find(
      (e) => e.type === "comment_link" && e.activity_id === r.id,
    );
    if (link) {
      const commentDiv = el("div", { class: "okf-change__comment-link" });
      commentDiv.appendChild(document.createTextNode("Resolved "));
      const cLink = el("a", {
        href: "#comment-" + link.comment_id,
        text: "comment " + (link.comment_id || "").slice(0, 10),
        title: "Jump to the comment this change resolved",
      });
      cLink.addEventListener("click", (ev) => {
        ev.preventDefault();
        openPanel("comments");
        // Defer to the next frame so the comments panel exists in the DOM.
        requestAnimationFrame(() => {
          const target = document.getElementById("comment-" + link.comment_id);
          if (target) {
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.classList.add("okf-comment--pulse");
            setTimeout(() => target.classList.remove("okf-comment--pulse"), 2000);
          }
        });
      });
      commentDiv.appendChild(cLink);
      b.appendChild(commentDiv);
    }
    row.appendChild(b);
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
          // Round 2 §6.4 review-gate fix: guard against overlapping renders.
          // Without this, rapid expand->collapse->expand within one /__diff
          // round-trip starts a second renderDiffInto against the same
          // diffWrap before the first settles (a slower/erroring call can
          // clobber a faster/successful render). Mirrors the conflict
          // modal's viewBtn precedent (disable for the fetch duration).
          diffBtn.disabled = true;
          renderDiffInto(diffWrap, { concept: diffConcept, from: r.detail.before, to: r.rev })
            .finally(() => { diffBtn.disabled = false; });
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
  }

  async function undoOne(r, btn) {
    if (!r || !r.id) return;
    // F2: the change-list row carries the content-hash rev to restore in
    // ``detail.before`` (stamped by _handle_apply from snapshot_for_undo, the
    // sha1[:12] of the prior concept bytes - NOT the integer bundle rev). Use
    // it as the rev and ``detail.before_concept`` as the concept; fall back to
    // the old ids+rev behaviour ONLY when ``detail.before`` is absent (older
    // events recorded before the pointer was wired through). The fallback rev
    // is the integer bundle rev, which undo_snapshot cannot resolve → silent
    // no-op; this is why the content-hash pointer is required.
    const before = (r.detail && r.detail.before) || null;
    const concept = before
      ? (r.detail.before_concept || (r.ids && r.ids[0]) || state.conceptId)
      : ((r.ids && r.ids[0]) || state.conceptId);
    const rev = before || r.rev || "";
    Btn.busy(btn);
    try {
      const res = await tokenFetch("/__undo", { method: "POST", body: { concept, rev } });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) throw new Error(data.error || ("HTTP " + res.status));
      toast("Undid change on " + concept + ".", { tone: "success" });
    } catch (e) {
      toast("Undo failed: " + (e.message || e), { tone: "error" });
    } finally {
      Btn.done(btn, "Undo");
    }
  }
  async function undoGroup(groupId, btn) {
    Btn.busy(btn);
    try {
      const res = await tokenFetch("/__undo", { method: "POST", body: { group_id: groupId } });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) throw new Error(data.error || ("HTTP " + res.status));
      toast("Reverted group pass (" + (data.restored || 0) + " file(s)).", { tone: "success" });
    } catch (e) {
      toast("Group undo failed: " + (e.message || e), { tone: "error" });
    } finally {
      Btn.done(btn, "Undo group");
    }
  }
  const Btn = {
    busy(b) { b.disabled = true; b.dataset._txt = b.textContent; b.textContent = "…"; },
    done(b, txt) { b.disabled = false; b.textContent = txt || b.dataset._txt || "Undo"; },
  };

  // ====================================================================
  // 8. Command palette (§13.4)
  // ====================================================================
  let paletteState = { open: false, items: [], active: 0, lastReturn: null };
  function buildPalette() {
    const overlay = el("div", { class: "okf-palette-overlay", hidden: "", role: "dialog",
      "aria-modal": "true", "aria-label": "Command palette" });
    const pal = el("div", { class: "okf-palette" });
    const input = el("input", { type: "search", class: "okf-palette__input",
      placeholder: "Jump to a concept, run a command…", "aria-label": "Command palette input", "aria-autocomplete": "list" });
    const list = el("ul", { class: "okf-palette__list", role: "listbox", "aria-label": "Commands" });
    const hint = el("div", { class: "okf-palette__hint" }, [
      el("span", { text: "↑↓ navigate" }), el("span", { text: "⏎ select" }), el("span", { text: "Esc close" }),
    ]);
    pal.appendChild(input); pal.appendChild(list); pal.appendChild(hint);
    overlay.appendChild(pal);
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) closePalette(); });
    input.addEventListener("input", () => refreshPaletteList(input.value));
    list.addEventListener("click", (e) => {
      const li = e.target.closest(".okf-palette__item");
      if (!li) return;
      paletteState.active = +li.dataset.idx;
      activatePalette();
    });
    document.body.appendChild(overlay);
    paletteState.overlay = overlay;
    paletteState.input = input;
    paletteState.list = list;
  }
  // Global keyboard wiring (registered at boot, independent of the lazy DOM
  // build, so Ctrl/Cmd-K toggles the palette on first press and arrow/enter
  // navigation works once it is open).
  function wirePaletteKeys() {
    document.addEventListener("keydown", (e) => {
      const meta = e.ctrlKey || e.metaKey;
      if (meta && (e.key === "k" || e.key === "K")) { e.preventDefault(); togglePalette(); return; }
      // "/" focuses the top-bar search (Editorial Workbench; SPEC §3.1). Skip
      // when typing in a field or when a modifier is held.
      if (e.key === "/" && !meta && !e.altKey) {
        const t = e.target;
        const typing = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
        if (!typing) {
          const search = $('.okf-topbar__controls input[type="search"], #okf-search');
          if (search) { e.preventDefault(); search.focus(); search.select && search.select(); return; }
        }
      }
      if (!paletteState.open) return;
      // Escape is handled by the shared overlay stack — no separate handler.
      if (e.key === "ArrowDown") { e.preventDefault(); movePalette(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); movePalette(-1); }
      else if (e.key === "Enter") { e.preventDefault(); activatePalette(); }
      // iter1 CRI-016: trap focus inside the modal so Tab/Shift+Tab can't
      // escape to the page behind (aria-modal="true" claims a trap).
      else if (e.key === "Tab") {
        e.preventDefault();
        trapFocusIn(paletteState.overlay, !e.shiftKey);
      }
    });
  }
  // iter1 CRI-016: focus trap shared by the palette, panel, and conflict
  // modal. Returns the focusable elements of a container in DOM order,
  // skipping hidden/disabled/negative-tabindex/inert-ancestor nodes.
  function focusableIn(root) {
    if (!root) return [];
    const sel = 'a[href], button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary, [tabindex]:not([tabindex="-1"])';
    return $$(sel, root).filter((n) => {
      if (n.getAttribute("tabindex") === "-1") return false;
      if (n.hasAttribute("hidden")) return false;
      if (n.disabled) return false;
      // Ancestor walk: reject if any ancestor (up to root) is hidden via the
      // HTML hidden attribute or CSS display:none. (visibility:hidden is
      // inherited, so the node's OWN computed style already reflects it —
      // checked below.)
      var parent = n.parentElement;
      while (parent && parent !== root) {
        if (parent.hidden) return false;
        if (getComputedStyle(parent).display === "none") return false;
        parent = parent.parentElement;
      }
      // Closed <details>: a descendant of a closed <details> is not rendered
      // (and thus not focusable) UNLESS it is inside that <details>'s
      // <summary> element (the summary is always visible).
      var closedDetails = n.closest('details:not([open])');
      if (closedDetails) {
        var summary = closedDetails.querySelector(':scope > summary');
        if (!summary || !summary.contains(n)) return false;
      }
      if (n.closest("[inert]")) return false;
      const cs = getComputedStyle(n);
      return cs.display !== "none" && cs.visibility !== "hidden" && cs.pointerEvents !== "none";
    });
  }
  // Move focus forward (or backward) within `root`, wrapping at the edges.
  function trapFocusIn(root, forward) {
    const focusables = focusableIn(root);
    if (!focusables.length) { try { root.focus(); } catch (e) {} return; }
    const cur = document.activeElement;
    const idx = focusables.indexOf(cur);
    let next;
    if (idx < 0) next = focusables[0];
    else if (forward) next = focusables[(idx + 1) % focusables.length];
    else next = focusables[(idx - 1 + focusables.length) % focusables.length];
    try { next.focus({ preventScroll: true }); } catch (e) {}
  }
  // Safe focus restoration: validates the saved target is connected, visible,
  // not inside an inert ancestor, and focusable — then uses a deterministic
  // fallback chain: saved → mobile Studio opener → Appearance trigger →
  // first topbar control → #okf-main. Returns true if focus landed somewhere.
  function safeFocus(saved) {
    // Validate saved target: connected, visible, not inert, not disabled,
    // not negative-tabindex (unless it's a programmatic-focus container like
    // #okf-main with tabindex=-1 which IS valid for .focus()). Then call
    // .focus() and verify document.activeElement actually became the target.
    function tryFocus(el) {
      if (!el || !el.isConnected || typeof el.focus !== "function") return false;
      if (el === document.body || el === document.documentElement) return false;
      if (el.closest("[inert]") || el.hasAttribute("hidden")) return false;
      if (el.disabled) return false;
      var cs = getComputedStyle(el);
      if (cs.display === "none" || cs.visibility === "hidden") return false;
      try { el.focus({ preventScroll: true }); } catch (e) { return false; }
      return document.activeElement === el;
    }
    if (tryFocus(saved)) return true;
    // Deterministic fallback chain.
    var sels = [".okf-studio-open-btn", "#okf-theme", ".okf-topbar button", ".okf-topbar a[href]", "#okf-main"];
    for (var i = 0; i < sels.length; i++) {
      if (tryFocus(document.querySelector(sels[i]))) return true;
    }
    return false;
  }
  var _paletteOverlay = null;
  var _paletteFocusTimer = null;
  function openPalette() {
    if (!paletteState.overlay) buildPalette();
    // Cancel any pending focus timer from a previous open.
    if (_paletteFocusTimer) { clearTimeout(_paletteFocusTimer); _paletteFocusTimer = null; }
    paletteState.open = true;
    paletteState.overlay.hidden = false;
    paletteState.input.value = "";
    refreshPaletteList("");
    paletteState._lastFocus = document.activeElement;
    if (!_paletteOverlay) _paletteOverlay = { close: function () { closePalette(); } };
    if (window.OKFOverlayStack) window.OKFOverlayStack.push(_paletteOverlay);
    // Generation guard: if close fires before the timer, the callback no-ops.
    var gen = paletteState._gen = (paletteState._gen || 0) + 1;
    _paletteFocusTimer = setTimeout(function () {
      _paletteFocusTimer = null;
      if (paletteState.open && paletteState._gen === gen) {
        try { paletteState.input.focus(); } catch (e) {}
      }
    }, 20);
  }
  function closePalette() {
    if (!paletteState.overlay) return;
    if (_paletteFocusTimer) { clearTimeout(_paletteFocusTimer); _paletteFocusTimer = null; }
    paletteState.open = false;
    paletteState.overlay.hidden = true;
    if (_paletteOverlay && window.OKFOverlayStack) window.OKFOverlayStack.remove(_paletteOverlay);
    safeFocus(paletteState._lastFocus);
    paletteState._lastFocus = null;
  }
  function togglePalette() { paletteState.open ? closePalette() : openPalette(); }
  function movePalette(delta) {
    const n = paletteState.items.length;
    if (!n) return;
    paletteState.active = (paletteState.active + delta + n) % n;
    renderPaletteList();
  }
  function activatePalette() {
    const item = paletteState.items[paletteState.active];
    if (!item) return;
    closePalette();
    try { item.run(); } catch (e) { console.error(e); }
  }
  function commandItems() {
    const items = [];
    items.push({ label: "Switch view: Rendered", sub: "view mode", run: () => setView("rendered") });
    items.push({ label: "Switch view: Source", sub: "view mode", run: () => setView("source") });
    items.push({ label: "Switch view: Split", sub: "view mode", run: () => setView("split") });
    if (EDIT && isConceptPage()) items.push({ label: "Post a comment / ask the agent", sub: "comment", run: () => openPanel("comments", { focusComposer: true }) });
    items.push({ label: "Open Comments panel", sub: "panel", run: () => openPanel("comments") });
    items.push({ label: "Open Changes panel", sub: "panel", run: () => openPanel("changes") });
    const themeApi = window.OKFLoomTheme;
    if (themeApi) {
      // Concrete picks persist family AND mode; "Auto" persists mode only,
      // keeping the user's family (family and mode are orthogonal).
      items.push({ label: "Theme: Technical Light", sub: "theme", run: () => themeApi.setTheme("technical-light") });
      items.push({ label: "Theme: Technical Dark", sub: "theme", run: () => themeApi.setTheme("technical-dark") });
      items.push({ label: "Theme: Swiss Light", sub: "theme", run: () => themeApi.setTheme("swiss-light") });
      items.push({ label: "Theme: Swiss Dark", sub: "theme", run: () => themeApi.setTheme("swiss-dark") });
      items.push({ label: "Theme: Auto (follow OS)", sub: "theme", run: () => themeApi.setMode("auto") });
    }
    if (window.okfLoomLive && window.okfLoomLive.resync) items.push({ label: "Resync now", sub: "live", run: () => window.okfLoomLive.resync() });
    // Registered panels.
    Object.keys(panels).forEach((id) => {
      const p = panels[id];
      if (p.__builtin) return;
      items.push({ label: "Open panel: " + p.label, sub: "extension", run: () => openPanel(id) });
    });
    return items;
  }
  function conceptItems(q) {
    const nodes = (state.graph && state.graph.nodes) || [];
    const ql = q.toLowerCase();
    return nodes.map((n) => {
      const d = n.data || n;
      return {
        label: d.label || d.id,
        sub: d.id + (d.type ? " · " + d.type : ""),
        run: () => { window.location.href = "/" + d.id; },
      };
    }).filter((it) => !ql || it.label.toLowerCase().indexOf(ql) >= 0 || it.sub.toLowerCase().indexOf(ql) >= 0)
      .slice(0, 12);
  }
  function refreshPaletteList(q) {
    q = (q || "").trim();
    let items;
    if (!q) {
      items = commandItems().concat(conceptItems("").slice(0, 6));
    } else {
      const cmds = commandItems().filter((c) => c.label.toLowerCase().indexOf(q.toLowerCase()) >= 0);
      items = cmds.concat(conceptItems(q));
    }
    paletteState.items = items;
    paletteState.active = 0;
    renderPaletteList();
  }
  function renderPaletteList() {
    const list = paletteState.list;
    list.innerHTML = "";
    paletteState.items.forEach((item, i) => {
      const li = el("li", { class: "okf-palette__item", role: "option",
        "aria-selected": i === paletteState.active ? "true" : "false", dataset: { idx: String(i) } });
      li.appendChild(el("span", { class: "okf-palette__item-title", text: item.label }));
      li.appendChild(el("span", { class: "okf-palette__item-sub", text: item.sub }));
      li.appendChild(el("span", { class: "okf-palette__item-kbd", text: i === paletteState.active ? "⏎" : "" }));
      list.appendChild(li);
    });
  }

  // ====================================================================
  // 9. Slide-over panel + extension registry (§13.6)
  // ====================================================================
  const panels = {}; // id → { id, label, render(container, ctx), __builtin }
  const panelOverlay = el("div", { class: "okf-panel-overlay", hidden: "" });
  // Editorial Workbench Round 2: the studio panel is an OVERLAY that pops OVER
  // the reading column from a rail icon (not auto-opened). It keeps
  // role=complementary and is dismissed on Esc / click-away via the
  // .okf-panel-overlay scrim (no aria-modal, no focus-trap). id="okf-panel" is
  // the aria-controls target for the rail buttons + view-switch.
  const panelShell = el("aside", { class: "okf-panel", id: "okf-panel", hidden: "", role: "complementary",
    "aria-label": "Studio panel", tabindex: "-1" });
  const panelHeader = el("div", { class: "okf-panel__header" });
  const panelTitle = el("h2", { class: "okf-panel__title" });
  const panelClose = el("button", { type: "button", class: "okf-panel__close", "aria-label": "Close panel", text: "Esc" });
  panelHeader.appendChild(panelTitle); panelHeader.appendChild(panelClose);
    // Editorial Workbench: one pop-over with tabs (Comments/Changes/Outline/
    // Metadata) instead of separately-opened panels. Clicking a tab swaps the
    // rendered panel; the active tab is underlined with --okf-accent.
    // Roving tabindex: selected tab = 0, peers = -1. Arrows/Home/End activate.
    const panelTabs = el("div", { class: "okf-panel__tabs", role: "tablist", "aria-label": "Panel sections" });
    const PANEL_TABS = [["comments", "Comments"], ["changes", "Changes"], ["outline", "Outline"], ["metadata", "Metadata"]];
    const panelTabBtns = {};
    PANEL_TABS.forEach(function (t) {
      const b = el("button", {
        type: "button", class: "okf-panel__tab", role: "tab",
        id: "okf-panel-tab--" + t[0],
        "aria-controls": "okf-panel-body",
        "aria-selected": "false", tabindex: "-1", text: t[1],
      });
      b.addEventListener("click", function () { openPanel(t[0]); });
      panelTabs.appendChild(b);
      panelTabBtns[t[0]] = b;
    });
    // Tablist keyboard: arrows wrap+activate, Home/End first/last. Tab exits
    // naturally (roving tabindex → only one tab stop in the tablist).
    panelTabs.addEventListener("keydown", (e) => {
      if (!state.openPanel) return;
      var keys = Object.keys(panelTabBtns);
      var cur = keys.indexOf(state.openPanel);
      if (cur < 0) return;
      var key = e.key;
      if (key === "ArrowRight" || key === "ArrowDown") { e.preventDefault(); openPanel(keys[(cur + 1) % keys.length]); }
      else if (key === "ArrowLeft" || key === "ArrowUp") { e.preventDefault(); openPanel(keys[(cur - 1 + keys.length) % keys.length]); }
      else if (key === "Home") { e.preventDefault(); openPanel(keys[0]); }
      else if (key === "End") { e.preventDefault(); openPanel(keys[keys.length - 1]); }
    });
    const panelBody = el("div", { class: "okf-panel__body", id: "okf-panel-body", role: "tabpanel" });
  panelShell.appendChild(panelHeader); panelShell.appendChild(panelTabs); panelShell.appendChild(panelBody);
  document.body.appendChild(panelOverlay); document.body.appendChild(panelShell);
  // Desktop backdrop click-away: the overlay is a genuine visible scrim on
  // desktop (panel is 360px with real space around it). On mobile the panel
  // covers 100vw so there is no visible backdrop — the close button (labeled
  // "Esc") and the Escape key are the primary mobile dismissal paths. The
  // overlay click handler stays for desktop; mobile dismissal is via the
  // close button + overlay-stack Escape.
  panelOverlay.addEventListener("click", closePanel);
  panelClose.addEventListener("click", closePanel);
  // Escape is handled by the shared overlay stack (capture-phase keydown on
  // document) — no separate document-level handler here.
  function panelBodyEl() { return panelBody; }
  // iter1 CRI-016: remember the trigger so focus is restored on close.
  let panelLastFocus = null;
  // Round 2: the thin rail's icon buttons (set by buildRail); openPanel/
  // closePanel reflect the active tab onto them via aria-pressed.
  var railButtons = [];

  var _panelOverlay = null;
    function openPanel(id, opts) {
      opts = opts || {};
      const p = panels[id];
      if (!p) return;
      // Distinguish initial open (panel was hidden) from tab-switch (already
      // visible). Tab-switches keep focus on the active tab (WAI-ARIA tabs
      // pattern); initial opens manage focus per modal/non-modal rules.
      const isTabSwitch = !panelShell.hidden && state.openPanel;
      state.openPanel = id;
      panelShell.hidden = false;
      panelOverlay.hidden = false;  // overlay: show the click-away scrim
      panelTitle.textContent = p.label;
      panelShell.setAttribute("aria-label", p.label);
      // Reflect the active tab in the pop-over tab bar (aria-selected + roving
      // tabindex + tabpanel aria-labelledby).
      Object.keys(panelTabBtns).forEach(function (k) {
        var btn = panelTabBtns[k];
        var isActive = k === id;
        btn.setAttribute("aria-selected", isActive ? "true" : "false");
        btn.setAttribute("tabindex", isActive ? "0" : "-1");
      });
      panelBody.setAttribute("aria-labelledby", "okf-panel-tab--" + id);
      // Reflect the open tab on the rail icons.
      (railButtons || []).forEach(function (b) {
        b.setAttribute("aria-pressed", b.dataset.railId === id ? "true" : "false");
      });
      // Save the trigger so closePanel can restore focus. Skipped on the
      // boot-time auto-open (opts.noFocus) so the dock doesn't steal focus /
      // scroll on page load.
      if (!opts.noFocus && !panelLastFocus) panelLastFocus = document.activeElement;
      // Register with the shared overlay stack (initial open only).
      if (!isTabSwitch) {
        if (!_panelOverlay) _panelOverlay = { close: function () { closePanel(); } };
        if (window.OKFOverlayStack) window.OKFOverlayStack.push(_panelOverlay);
      }
      // Clear jump context before DOM replacement (card element will be
      // destroyed by innerHTML="" below). Unconditional — even tab-switches
      // and re-renders within the same panel destroy the jumped card.
      _clearJumpContext();
      // Render.
      panelBody.innerHTML = "";
      panelBody._focusComposer = !!opts.focusComposer;
      try { p.render(panelBody, ctx()); } catch (e) { console.error("[okf-studio] panel render", e); }

      // On fresh open (not tab-switch), reset panel body scroll to origin
      // so the user starts at the top of the content.
      if (!isTabSwitch && panelBody) panelBody.scrollTop = 0;

      if (isTabSwitch) {
        // Tab-switch: focus the newly active tab (keyboard activation keeps
        // focus on the tab list per the WAI-ARIA tabs pattern).
        try { panelTabBtns[id].focus(); } catch (e) {}
        return;
      }
      // Initial open: acquire mobile modal or focus panel shell on desktop.
      if (_isMobile()) {
        _acquireModal(opts);
      } else {
        if (!opts.noFocus) { try { panelShell.focus(); } catch (e) {} }
      }
    }
    function closePanel() {
      // Clear any active jump context (timer, transient classes, tabindex).
      _clearJumpContext();
      // Clear abandoned comment draft state (preserve typed draftBody per
      // existing contract — user may reopen the panel and continue typing).
      clearPendingCommentDraft({ preserveDraftBody: true });
      // Release mobile modal ownership BEFORE hiding so focus restoration lands
      // on a non-inert element.
      if (_modalActive) _releaseModal();
      // Unregister from the shared overlay stack.
      if (_panelOverlay && window.OKFOverlayStack) window.OKFOverlayStack.remove(_panelOverlay);
      state.openPanel = null;
      panelShell.hidden = true;
      panelOverlay.hidden = true;
      (railButtons || []).forEach(function (b) { b.setAttribute("aria-pressed", "false"); });
      // Safe focus restoration: validate the saved trigger or use fallback chain.
      safeFocus(panelLastFocus);
      panelLastFocus = null;
    }
    function togglePanel(id) { state.openPanel === id ? closePanel() : openPanel(id); }

    // ---- Mobile (<=900px) modal ownership --------------------------------
    // At narrow viewports the panel becomes a full-screen modal dialog:
    // role=dialog + aria-modal=true, siblings inert, focus trapped, Escape
    // topmost. Desktop stays complementary/non-modal (no inert/trap).
    var _modalActive = false;
    var _modalInerted = [];    // elements we set inert on (for exact restore)
    var _modalPrevRole = null;
    var _modalTrapHandler = null;
    var _modalFocusTimer = null;
    var _mobileMq = window.matchMedia("(max-width: 900px)");

    function _isMobile() {
      return _mobileMq.matches;
    }

    function _acquireModal(opts) {
      _modalActive = true;
      _modalPrevRole = panelShell.getAttribute("role");
      panelShell.setAttribute("role", "dialog");
      panelShell.setAttribute("aria-modal", "true");
      // Inert all body children except panel + overlay (scripts are in <head>
      // or have no visual content). Record prior inert state for exact restore.
      _modalInerted = [];
      var bodyChildren = document.body.children;
      for (var i = 0; i < bodyChildren.length; i++) {
        var child = bodyChildren[i];
        if (child === panelShell || child === panelOverlay) continue;
        if (child.tagName === "SCRIPT" || child.tagName === "LINK" || child.tagName === "STYLE") continue;
        if (child.inert) continue; // already inert — don't double-record
        child.inert = true;
        _modalInerted.push(child);
      }
      // Focus: composer if requested, else active tab, else panel shell.
      // Deferred so the panel render finishes first; cancelable via
      // _modalFocusTimer so close/release can abort if they fire first.
      if (_modalFocusTimer) clearTimeout(_modalFocusTimer);
      _modalFocusTimer = setTimeout(function () {
        _modalFocusTimer = null;
        var focusTarget = null;
        if (opts && opts.focusComposer) {
          focusTarget = panelBody.querySelector(".okf-composer__textarea");
        }
        if (!focusTarget) {
          var activeTab = panelTabs.querySelector('.okf-panel__tab[aria-selected="true"]');
          if (activeTab) focusTarget = activeTab;
        }
        if (!focusTarget) focusTarget = panelShell;
        try { focusTarget.focus({ preventScroll: true }); } catch (e) {}
      }, 0);
      // Tab trap: reuse the canonical focusableIn helper (filters
      // hidden/disabled/inert/negative-tabindex/visibility:hidden).
      _modalTrapHandler = function (e) {
        if (e.key !== "Tab") return;
        trapFocusIn(panelShell, !e.shiftKey);
        // preventDefault for Tab at focus boundaries is handled inside
        // trapFocusIn's wrapping logic; we also preventDefault here so the
        // browser's native Tab doesn't escape the panel before trapFocusIn
        // wraps — but only if focus actually wrapped (focusables exist).
        var focusables = focusableIn(panelShell);
        if (focusables.length) e.preventDefault();
      };
      panelShell.addEventListener("keydown", _modalTrapHandler);
      // Escape is handled by the shared overlay stack — no separate
      // mobile-only Escape handler needed. The panel registers with the
      // stack in openPanel; closePanel unregisters.
    }

    function _releaseModal() {
      if (!_modalActive) return;
      _modalActive = false;
      // Cancel any pending deferred focus.
      if (_modalFocusTimer) { clearTimeout(_modalFocusTimer); _modalFocusTimer = null; }
      // Restore role.
      if (_modalPrevRole) panelShell.setAttribute("role", _modalPrevRole);
      else panelShell.removeAttribute("role");
      panelShell.removeAttribute("aria-modal");
      // Restore inert: only undo what we set.
      for (var i = 0; i < _modalInerted.length; i++) {
        _modalInerted[i].inert = false;
      }
      _modalInerted = [];
      // Remove modal-only listeners.
      if (_modalTrapHandler) panelShell.removeEventListener("keydown", _modalTrapHandler);
      _modalTrapHandler = null;
    }

    // Breakpoint transition: crossing 900px while the panel is open must
    // acquire or release modal ownership without losing the selected panel.
    // addEventListener + addListener fallback for older browsers.
    var _bpHandler = function (e) {
      if (!state.openPanel) return;
      if (e.matches) {
        // Desktop → mobile: acquire modal.
        if (!_modalActive) _acquireModal({});
      } else {
        // Mobile → desktop: release modal (panel stays open, non-modal).
        if (_modalActive) _releaseModal();
        try { panelShell.focus(); } catch (er) {}
      }
    };
    if (_mobileMq.addEventListener) _mobileMq.addEventListener("change", _bpHandler);
    else if (_mobileMq.addListener) _mobileMq.addListener(_bpHandler);

  // Editorial Workbench Round 2: the thin studio rail. Always docked on
  // concept pages (>=900px); each icon opens the matching overlay tab. The
  // ---- Deterministic inline SVG icon factory -----------------------------
  // Replaces font-dependent Unicode glyphs (💬 ↻ ☰ ⓘ) that render as tofu in
  // capture/minimal-font environments. Every icon: viewBox 0 0 16 16, 1em,
  // currentColor, fill none, aria-hidden=true, focusable=false.
  var SVG_ICONS = {
    comments: '<path d="M2 3h12v8H6l-3 3v-3H2z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" fill="none"/>',
    changes: '<path d="M4 8a4 4 0 0 1 7-2.6M12 2v3.5h-3.5M12 8a4 4 0 0 1-7 2.6M4 14v-3.5h3.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    outline: '<path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/>',
    metadata: '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.4" fill="none"/><path d="M8 7v4M8 5v.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/>',
    navCollapse: '<path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/>',
    plus: '<path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/>',
  };
  function svgIcon(name) {
    var inner = SVG_ICONS[name];
    if (!inner) return "";
    return '<svg viewBox="0 0 16 16" width="1em" height="1em" aria-hidden="true" focusable="false" style="display:inline-block;vertical-align:middle;pointer-events:none">' + inner + '</svg>';
  }

  // Comments icon carries a live count badge (synced by updateBadges).
  var railCommentBadge = null;
  function buildRail() {
    // role="group" (not "toolbar") to match the sibling view-switch: the rail
    // has no roving-focus arrow handling, so "toolbar" would over-promise.
    var railEl = el("aside", { class: "okf-rail", role: "group", "aria-label": "Studio" });
    function railBtn(id, icon, label) {
      var b = el("button", { type: "button", class: "okf-rail__btn",
        "aria-pressed": "false", "aria-controls": "okf-panel",
        title: label, "aria-label": label });
      b.innerHTML = svgIcon(icon);
      b.dataset.railId = id;
      b.addEventListener("click", function () { togglePanel(id); });
      railEl.appendChild(b);
      return b;
    }
    var cBtn = railBtn("comments", "comments", "Comments");
    railCommentBadge = el("span", { class: "okf-rail__badge", "aria-hidden": "true", hidden: "", text: "0" });
    cBtn.appendChild(railCommentBadge);
    railBtn("changes", "changes", "Changes");
    railBtn("outline", "outline", "Outline");
    railBtn("metadata", "metadata", "Metadata");
    railEl.appendChild(el("span", { class: "okf-rail__spacer", "aria-hidden": "true" }));
    // Quick-actions jumps to the Comments overlay (its intents toolbar).
    var plus = el("button", { type: "button", class: "okf-rail__btn",
      title: "Quick actions", "aria-label": "Quick actions", "aria-controls": "okf-panel" });
    plus.innerHTML = svgIcon("plus");
    plus.addEventListener("click", function () { openPanel("comments", { focusComposer: false }); });
    railEl.appendChild(plus);
    document.body.appendChild(railEl);
    railButtons = railEl.querySelectorAll(".okf-rail__btn[data-rail-id]");
    return railEl;
  }

  function ctx() {
    return {
      state, boot: BOOT, el, toast, tokenFetch,
      currentConceptId: state.conceptId,
      onLive: (type, fn) => window.okfLoomLive && window.okfLoomLive.on(type, fn),
    };
  }

  // register(kind, impl) - the documented client extension seam (§13.6).
  // iter1 CRI-007: the previously-documented {toolbar, graphDecorator,
  // suggestionRenderer} kinds were inert no-op stubs that over-promised the
  // extension surface. They are now RESERVED (accepted + warned, not wired)
  // and documented as forward-compat in the module header. Only {panel,
  // viewMode} ship wired today: `panel` powers the built-in Comments /
  // Changes / Agent-activity panels; `viewMode` lets an extension register
  // an additional read-only view mode (e.g. "outline") that joins the
  // Rendered/Source/Split switch + the ?view= deep link.
  function register(kind, impl) {
    if (kind === "panel" && impl && impl.id) {
      panels[impl.id] = Object.assign({ __builtin: false }, impl);
      // Add a bar toggle for non-builtin panels. Round 2: paletteBtn (Commands)
      // now lives in leftGroup (actions), not rightGroup — insert alongside it
      // there (opening a panel is an action, same cluster as Commands).
      if (!impl.__builtin && !impl._btn) {
        const btn = el("button", { type: "button", class: "okf-iconbtn", "aria-expanded": "false", "aria-controls": "okf-panel", text: impl.label });
        btn.addEventListener("click", () => togglePanel(impl.id));
        impl._btn = btn;
        leftGroup.insertBefore(btn, paletteBtn);
      }
      if (state.openPanel === impl.id) openPanel(impl.id);
      return impl;
    }
    if (kind === "viewMode" && impl && impl.id) {
      viewModes[impl.id] = impl;
      addViewModeButton(impl);
      return impl;
    }
    // Reserved / forward-compat kinds. Accepted so an extension that targets
    // a future toolkit version doesn't throw, but warned so the author knows
    // the hook isn't wired yet. See viewer/OVERRIDES.md §6 for the full API.
    if (kind === "toolbar" || kind === "graphDecorator" || kind === "suggestionRenderer") {
      console.warn("[okf-studio] register('" + kind + "') is reserved for a future release and is not wired in this version. See viewer/OVERRIDES.md §6 for the documented extension surface.");
      return impl;
    }
    console.warn("[okf-studio] register: unknown kind or missing impl", kind);
  }
  const viewModes = {};
  function addViewModeButton(mode) {
    // Insert a new button into the view switch group. It activates the
    // extension mode; the extension's onActivate is responsible for any
    // custom rendering (e.g. swapping in an outline panel).
    if (!isConceptPage()) return;
    const btn = el("button", { type: "button", class: "okf-viewswitch__btn",
      "aria-pressed": "false", text: mode.label || mode.id });
    btn.dataset.mode = "ext:" + mode.id;
    btn.addEventListener("click", () => {
      try { if (typeof mode.onActivate === "function") mode.onActivate(ctx()); } catch (e) { console.error(e); }
      // Mark only this extension button pressed; clear the built-in trio.
      $$(".okf-viewswitch__btn").forEach((b) => b.setAttribute("aria-pressed", "false"));
      btn.setAttribute("aria-pressed", "true");
    });
    if (viewSwitch) viewSwitch.appendChild(btn);
  }

  // Built-in panels.
  // panels.comments delegates straight to renderCommentsPanel(),
  // which now preserves the composer node across rebuilds (typing guard
  // is internal — see renderCommentsPanel). The previous wrapper-level
  // "skip rebuild if typing" guard is no longer needed: the panel splits
  // into composer / toolbar / list zones and only the toolbar + list
  // rebuild on each event.
  panels.comments = {
    id: "comments", label: "Comments",
    render: function () { renderCommentsPanel(); },
    __builtin: true,
  };
  panels.changes = { id: "changes", label: "Changes", render: (c) => { c.innerHTML = ""; renderChangeList(); }, __builtin: true };

  // Outline: this page's heading structure, as jump links. Reads the rendered
  // prose so it tracks live edits.
  panels.outline = {
    id: "outline", label: "Outline", __builtin: true,
    render: function (c) {
      c.innerHTML = "";
      const heads = $$(".okf-prose h2, .okf-prose h3");
      if (!heads.length) {
        c.appendChild(el("p", { class: "okf-panel__empty", text: "No sections on this page." }));
        return;
      }
      const nav = el("nav", { class: "okf-outline", "aria-label": "Page outline" });
      heads.forEach(function (h, i) {
        if (!h.id) { try { h.id = "okf-h-" + i; } catch (e) {} }
        const label = (h.textContent || "").replace(/[¶#]\s*$/, "").trim();
        const a = el("a", { class: "okf-outline__item okf-outline__item--" + h.tagName.toLowerCase(),
          href: "#" + h.id, text: label });
        a.addEventListener("click", function () { setTimeout(closePanel, 0); });
        nav.appendChild(a);
      });
      c.appendChild(nav);
    },
  };

  // Metadata: the concept's frontmatter. Clones the in-page "All fields"
  // details table when present; otherwise summarises type + tags.
  panels.metadata = {
    id: "metadata", label: "Metadata", __builtin: true,
    render: function (c) {
      c.innerHTML = "";
      const fm = $(".okf-frontmatter");
      if (fm) {
        const clone = fm.cloneNode(true);
        clone.setAttribute("open", "");
        const sum = clone.querySelector("summary");
        if (sum) sum.remove();
        c.appendChild(clone);
        return;
      }
      const type = $(".okf-type-chip");
      const tags = $(".okf-page__meta");
      if (type) c.appendChild(el("div", { class: "okf-panel__section", text: "Type: " + (type.textContent || "").trim() }));
      if (tags) c.appendChild(el("div", { class: "okf-panel__section", text: (tags.textContent || "").trim() }));
      if (!type && !tags) c.appendChild(el("p", { class: "okf-panel__empty", text: "No metadata for this view." }));
    },
  };

  // ---- Built-in extension panel demonstrating register(): "Agent activity" ----
  // iter2 G13 (CRI2-012): enriched with UNIQUE content the presence chip +
  // the Changes panel don't surface, so the panel earns its slot instead of
  // duplicating them. Three sections:
  //   1. The agent's OPEN/CLAIMED comment queue (comments the agent has
  //      claimed but not resolved) — distinct from the Changes panel, which
  //      shows events, not the directive queue.
  //   2. Presence history (recent state transitions) — a small log the chip
  //      can't show because it only carries the current state.
  //   3. iter3 CRI3-007: agent writes in the LAST 5 MINUTES — a unique time
  //      filter the Changes panel doesn't offer. Was a 30-row slice of the
  //      same changeRow() the Changes panel renders, which made the section
  //      a pure duplicate (the impeccable critic flagged: "a user who opens
  //      both panels side by side sees the same rows twice"). Replacing the
  //      30-row dump with a 5-minute window keeps the panel about state
  //      ("what is the agent doing RIGHT NOW"), with a "View in Changes →"
  //      link for the full history.
  register("panel", {
    id: "agent-activity",
    label: "Agent activity",
    render(container, c) {
      container.innerHTML = "";
      const st = state.presence.state || "idle";
      const verb = ({ idle: "idle", watching: "watching", thinking: "thinking about", editing: "editing" })[st] || st;
      container.appendChild(el("h3", { class: "okf-panel__section-title",
        text: "Agent · " + verb + (state.presence.focus ? " · " + state.presence.focus : "") }));

      // Section 1: the agent's claimed/open comment queue (unique).
      const claimed = state.comments.filter((cm) =>
        (cm.state === "claimed" || cm.state === "open") && cm.claimed_by === "agent");
      const q = el("div", { class: "okf-panel__section" });
      q.appendChild(el("h3", { class: "okf-panel__section-title", text: "Claimed queue (" + claimed.length + ")" }));
      if (!claimed.length) {
        q.appendChild(el("p", { class: "okf-empty", text: "No comments claimed by the agent right now." }));
      } else {
        claimed.slice(0, 20).forEach((cm) => q.appendChild(commentCard(cm)));
      }
      container.appendChild(q);

      // Section 2: presence history (unique — the chip carries only current).
      const hist = el("div", { class: "okf-panel__section" });
      hist.appendChild(el("h3", { class: "okf-panel__section-title", text: "Presence history (" + state.presenceHistory.length + ")" }));
      if (!state.presenceHistory.length) {
        hist.appendChild(el("p", { class: "okf-empty", text: "No presence transitions yet." }));
      } else {
        const log = el("ul", { class: "okf-presence-log" });
        state.presenceHistory.slice(0, 12).forEach((h) => {
          const li = el("li", { class: "okf-presence-log__item", "data-state": h.state });
          li.appendChild(el("span", { class: "okf-presence-log__state", text: h.state || "idle" }));
          if (h.focus) li.appendChild(el("span", { class: "okf-presence-log__focus", text: h.focus }));
          if (h.message) li.appendChild(el("span", { class: "okf-presence-log__message", text: h.message, title: h.message }));
          li.appendChild(el("span", { class: "okf-presence-log__ts", text: fmtTime(h.ts) }));
          log.appendChild(li);
        });
        hist.appendChild(log);
      }
      container.appendChild(hist);

      // Section 3 (iter3 CRI3-007): agent writes in the LAST 5 MINUTES.
      // Unique time-boxed filter the Changes panel doesn't offer; reads as
      // "what is the agent doing RIGHT NOW". Capped at 10 rows so the panel
      // stays compact; a "View in Changes →" button opens the full history
      // panel for everything older.
      const AGENT_RECENT_WINDOW_MS = 5 * 60 * 1000;
      const fiveMinAgo = Date.now() - AGENT_RECENT_WINDOW_MS;
      const recentAgent = state.events.filter((e) => {
        if (e.actor !== "agent") return false;
        // Parse the event ts (ISO string) to epoch ms; tolerate missing or
        // malformed ts by treating the row as NOT recent (excluded).
        const t = Date.parse(e.ts || "");
        return !isNaN(t) && t >= fiveMinAgo;
      });
      const act = el("div", { class: "okf-panel__section" });
      act.appendChild(el("h3", {
        class: "okf-panel__section-title",
        text: "Recent writes · last 5 min (" + recentAgent.length + ")",
      }));
      if (!recentAgent.length) {
        act.appendChild(el("p", {
          class: "okf-empty",
          text: "No agent writes in the last 5 minutes.",
        }));
      } else {
        recentAgent.slice(0, 10).forEach((r) => act.appendChild(changeRow(r)));
      }
      // Single link to the full Changes panel — replaces the 30-row dump
      // that previously duplicated the Changes panel verbatim.
      const viewAll = el("button", {
        type: "button",
        class: "okf-studiobtn okf-panel__section-link",
        text: "View full history in Changes",
      });
      viewAll.addEventListener("click", () => openPanel("changes"));
      act.appendChild(viewAll);
      container.appendChild(act);
    },
  });

  // ====================================================================
  // 10. Badges + cross-cutting UI updates
  // ====================================================================
  function updateBadges() {
    const open = state.comments.filter((c) => c.state === "open" || c.state === "claimed").length;
    // Round 2: mirror the live open-comment count onto the rail badge (the
    // footer comment/changes badges were retired with the docked dock).
    if (railCommentBadge) {
      railCommentBadge.textContent = String(open);
      railCommentBadge.hidden = !(open > 0);
    }
  }

  function jumpToActivity(aid) {
    openPanel("changes");
    // Highlight the matching row briefly. Exact match on the row's
    // data-activity-id; the old 6-char-substring scan of row textContent
    // could light up the wrong row.
    setTimeout(() => {
      const rows = $$(".okf-change", panelBody);
      const match = rows.find((r) => r.dataset.activityId === String(aid)) ||
        rows.find((r) => r.textContent.indexOf(shortId(aid)) >= 0);
      if (match) { match.scrollIntoView({ block: "center" }); match.classList.add("okf-pulse"); }
    }, 60);
  }

  // ====================================================================
  // 11. Graph cache (palette + local graph refresh + presence)
  // ====================================================================
  async function loadGraph() {
    try {
      const res = await fetch("/__data/graph.json", { headers: { Accept: "application/json" } });
      state.graph = await res.json();
    } catch (e) { /* palette still works with commands only */ }
  }
  function refreshGraph() {
    // Called by live.js on a `graph` event. Reload graph cache + rebuild
    // local sidebar pills + margin markers.
    loadGraph().then(() => { rebuildMarginMarkers(); });
  }

  // ====================================================================
  // 12. Wire live.js hub → studio surfaces
  // ====================================================================
  function wireLive() {
    if (!window.okfLoomLive) return;
    window.okfLoomLive.on("conn", (d) => {
      connChip.dataset.state = d.state;
      const label = d.state === "online" ? "online" : (d.state === "reconnecting" ? "reconnecting" : "offline");
      connLabel.textContent = d.state === "online" ? "Live" : (d.state === "reconnecting" ? "Reconnecting…" : "Offline");
      connChip.setAttribute("aria-label", "Live updates connection: " + label);
    });
    window.okfLoomLive.on("presence", renderPresence);
    window.okfLoomLive.on("comment", (c) => {
      if (!c || !c.id) return;
      // Clear jump context if this comment was the active jump target and its
      // state changed (agent resolved/dismissed it server-side — the card will
      // be rebuilt by renderCommentsPanel below).
      if (_jumpState.id === c.id && c.state && c.state !== "open") _clearJumpContext();
      upsertComment(c);
      if (state.openPanel === "comments") renderCommentsPanel();
      updateBadges();
      // iter1 CRI-002: sync the mark's state attribute (claimed/resolved
      // re-style the highlight) + rebuild markers over the open concept.
      setCommentMarkState(c.id, c.state || "open");
      applyCommentMarks();
      rebuildMarginMarkers();
      // Also push to events so the timeline reflects comment lifecycle.
      upsertEvent(Object.assign({ type: "comment" }, c));
    });
    window.okfLoomLive.on("activity", (a) => {
      if (!a) return;
      upsertEvent(a);
      if (state.openPanel === "changes") renderChangeList();
      updateBadges();
      // iter1 CRI-010: collapse a burst of activity into one toast. Events
      // that share a group_id (a scoped enrichment pass) are coalesced into
      // "Agent made N changes" with a single group-Undo. Standalone events
      // still get their own toast, but a rapid stream no longer stacks 8.
      scheduleActivityToast(a);
    });
    window.okfLoomLive.on("changed", (d) => { upsertEvent({ type: "changed", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); refreshValidation(); });
    window.okfLoomLive.on("created", (d) => { upsertEvent({ type: "created", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); refreshValidation(); });
    window.okfLoomLive.on("removed", (d) => { upsertEvent({ type: "removed", ids: d.ids, origin: d.origin, rev: d.rev, ts: new Date().toISOString() }); if (state.openPanel === "changes") renderChangeList(); refreshValidation(); });
    refreshValidation();   // Round 2 §6.4: initial validation count (rev-cached server-side, so repeats are cheap)
    window.okfLoomLive.on("resync", () => { loadComments(); });
    // INTENT5-001 / QUA5-002: comment_link consumer — upsert the event into
    // state.events so changeRow's lookup finds it and re-renders the back-link
    // live (without a page reload). Also re-render the changes panel if open.
    window.okfLoomLive.on("comment_link", (d) => {
      upsertEvent(d);
      if (state.openPanel === "changes") renderChangeList();
    });
    window.okfLoomLive.on("agent_conflict", (d) => {
      // §9.4 conflict from the CLI agent path: surface the modal. The SSE
      // event is the FLAT conflict object (update.py append_event), so it
      // rides in as `data`; there is no HTTP request to retry, so no
      // url/opts — showConflictModal hides "Take the agent's edit" for
      // this shape (the agent's payload lives in its process, not ours).
      showConflictModal({ data: d });
    });
    window.okfLoomLive.on("open-removed", (d) => {
      toast(el("span", {}, [document.createTextNode("The open concept “" + d.id + "” was removed. "),
        el("a", { href: "/", text: "Go to index" })]), { tone: "error", sticky: true });
    });
    window.okfLoomLive.on("patched", () => { /* change list already updated via changed */ });
  }

  // ---- activity toast throttle + inline undo (iter1 CRI-010 / CRI-018) -
  // Within a short window (500ms) we coalesce activity events so a single
  // scoped-enrichment pass that writes 8 files produces ONE toast, not 8.
  // Grouped events (shared group_id) collapse to "Agent made N changes"
  // with a group-Undo; standalone events keep their own one-line toast.
  // The toast Undo button performs the undo INLINE (CRI-018) instead of
  // just opening the Changes panel.
  const ACTIVITY_TOAST_WINDOW_MS = 500;
  // iter2 CRI2-005: max inline Undo buttons in a single burst toast before
  // they collapse to one "Undo all (N)". A toast is glanceable; a 5-button
  // toast reads as a panel and the close × drifts from the summary on wrap.
  const ACTIVITY_TOAST_UNDO_CAP = 3;
  let activityToastTimer = null;
  let activityToastBuffer = [];
  function scheduleActivityToast(a) {
    activityToastBuffer.push(a);
    if (activityToastTimer) clearTimeout(activityToastTimer);
    activityToastTimer = setTimeout(flushActivityToast, ACTIVITY_TOAST_WINDOW_MS);
  }
  function flushActivityToast() {
    activityToastTimer = null;
    const batch = activityToastBuffer;
    activityToastBuffer = [];
    if (!batch.length) return;
    // Group the batch by group_id (standalone events share no group).
    const byGroup = Object.create(null);
    const standalone = [];
    batch.forEach((a) => {
      if (a.group_id) (byGroup[a.group_id] || (byGroup[a.group_id] = [])).push(a);
      else standalone.push(a);
    });
    const groups = Object.keys(byGroup);
    // One toast for the whole batch: summary line + grouped undo actions.
    const summary = buildActivitySummary(batch, groups, byGroup, standalone);
    const span = el("span", {});
    span.appendChild(document.createTextNode(summary + "  · "));
    // iter2 CRI2-005: cap inline Undo buttons so a 5-group burst doesn't
    // produce a 5-button toast (a toast is glanceable; a 5-button toast is a
    // panel). Collect the undoable targets (group ids + standalone undoable
    // events), and if there are more than ACTIVITY_TOAST_UNDO_CAP render a
    // single "Undo all (N)" button that undoes them in order; otherwise emit
    // the per-target buttons as before.
    var undoableGroupIds = groups.filter(function (gid) {
      return byGroup[gid][0] && byGroup[gid][0].undoable;
    });
    var undoableStandalone = standalone.filter(function (a) { return a.undoable; });
    var totalUndoable = undoableGroupIds.length + undoableStandalone.length;
    function appendUndoButton(label, handler) {
      var link = el("button", { type: "button", class: "okf-toast__action", text: label });
      link.addEventListener("click", function (e) {
        e.preventDefault();
        handler(link);
      });
      span.appendChild(document.createTextNode(" "));
      span.appendChild(link);
    }
    if (totalUndoable > ACTIVITY_TOAST_UNDO_CAP) {
      // Single coalesced button: undo every group + every standalone, in the
      // order they arrived. The buttons disable as each undo fires so a
      // double-click can't re-trigger.
      appendUndoButton("Undo all (" + totalUndoable + ")", function (btn) {
        btn.disabled = true;
        undoableGroupIds.forEach(function (gid) { undoGroup(gid, btn); });
        undoableStandalone.forEach(function (a) { undoOne(a, btn); });
      });
    } else {
      // Inline undo buttons (CRI-018): undo directly, don't open the panel.
      undoableGroupIds.forEach(function (gid) {
        var members = byGroup[gid];
        appendUndoButton("Undo group (" + members.length + ")", function () { undoGroup(gid); });
      });
      undoableStandalone.forEach(function (a) {
        appendUndoButton("Undo", function () { undoOne(a); });
      });
    }
    // A non-undoable batch still offers a "View" link to the change list.
    const anyUndoable = batch.some((a) => a.undoable);
    if (!anyUndoable) {
      const view = el("button", { type: "button", class: "okf-toast__action", text: "View" });
      view.addEventListener("click", (e) => { e.preventDefault(); openPanel("changes"); });
      span.appendChild(document.createTextNode(" "));
      span.appendChild(view);
    }
    toast(span, { ttl: 5000 });
  }
  function buildActivitySummary(batch, groups, byGroup, standalone) {
    // Browser-proof copy example: "Agent added 2 links to Orders · Undo". We build a
    // compact human line mapping the raw op id to a human verb + noun,
    // resolving concept ids to titles where possible. iter-1 closeout
    // visual review caught the earlier shape that surfaced the raw op id
    // ("add_links") and the raw concept id ("tables/orders") verbatim.
    const actorRaw = (batch[0] && batch[0].actor) || "agent";
    const actor = actorRaw.charAt(0).toUpperCase() + actorRaw.slice(1);
    const titleFor = (id) => {
      // Best-effort: title-case the last path segment of the concept id so
      // "tables/orders" → "Orders". The studio does not carry the bundle's
      // full title map; a CRDT-precise lookup would require an extra round
      // trip per toast, which is not worth the latency for a notification.
      if (!id || typeof id !== "string") return "";
      const seg = id.split("/").filter(Boolean).pop() || id;
      return seg.charAt(0).toUpperCase() + seg.slice(1);
    };
    if (batch.length === 1) {
      const a = batch[0];
      if (a.summary && !/_/.test(a.summary)) return a.summary;
      const hv = humanVerb(a.action, 1);
      const tgt = a.ids && a.ids[0] ? (" to " + titleFor(a.ids[0])) : "";
      return actor + " " + hv.phrase + tgt;
    }
    // Multiple: collapse by action verb.
    const verbCounts = Object.create(null);
    const targetSet = Object.create(null);
    batch.forEach((a) => {
      const verb = a.action || "change";
      verbCounts[verb] = (verbCounts[verb] || 0) + 1;
      (a.ids || []).forEach((id) => { targetSet[id] = 1; });
    });
    const targets = Object.keys(targetSet);
    const parts = Object.keys(verbCounts).map((v) => {
      const hv = humanVerb(v, verbCounts[v]);
      return hv.count + " " + hv.noun;
    });
    const targetText = targets.length === 1
      ? (" to " + titleFor(targets[0]))
      : (" to " + targets.length + " concepts");
    return actor + " added " + parts.join(", ") + targetText;
  }
  // Map raw op ids to human verb + noun forms. The shape is:
  //   {phrase: "<past-tense verb>", noun: "<plural noun>", count: N}
  // `phrase` is used in the singular case ("Agent added a link"),
  // `noun` is used in the collapsed multi case ("3 links").
  // Unknown ops fall back to "changed"/"changes" so we never surface a
  // raw snake_case token to the user (fit-and-finish rule).
  function humanVerb(action, count) {
    const map = {
      add_link:           { phrase: "added a link",     noun: "links"    },
      add_links:          { phrase: "added links",      noun: "links"    },
      remove_link:        { phrase: "removed a link",   noun: "removals" },
      add_relation:       { phrase: "added a relation", noun: "relations"},
      add_entity:         { phrase: "added an entity",  noun: "entities" },
      add_entities:       { phrase: "added entities",   noun: "entities" },
      set_frontmatter:    { phrase: "set a field",      noun: "fields"   },
      set_tag:            { phrase: "set a tag",        noun: "tags"     },
      add_tag:            { phrase: "added a tag",      noun: "tags"     },
      append_body_section:{ phrase: "added a section",  noun: "sections" },
      write_concept:      { phrase: "wrote the concept",noun: "writes"   },
      undo_restore:       { phrase: "undid a change",   noun: "undos"    },
      repair:             { phrase: "ran a repair",     noun: "repairs"  },
      auto_repair:        { phrase: "auto-repaired",    noun: "repairs"  },
    };
    const entry = map[action] || { phrase: "made a change", noun: "changes" };
    return { phrase: entry.phrase, noun: entry.noun, count: count };
  }
  function verbLabel(verb, count) {
    // Crude pluralisation good enough for the known action set.
    if (count === 1) return verb;
    if (verb.endsWith("s")) return verb;
    if (verb.endsWith("y")) return verb.slice(0, -1) + "ies";
    return verb + "s";
  }

  // iter2 G12: burst-coalescing detection. When 10+ standalone events land
  // within 1s, tag them with a shared burst_id so the change list can render
  // them as ONE expandable "Agent made N changes" row instead of N rows at
  // the top. Grouped events (group_id) are already coalesced by the group
  // renderer, so burst detection only applies to standalone events. An OPEN
  // burst keeps absorbing fast arrivals (so a burst of 12 coalesces all 12,
  // not 10 + 2); it closes when an event arrives >1s after the last one.
  const BURST_WINDOW_MS = 1000;
  const BURST_THRESHOLD = 10;
  let _burstArrivalWindow = [];  // [{id, t}]
  let _burstOpenId = null;
  let _burstLastT = 0;
  function maybeTagBurst(ev) {
    if (!ev || ev.group_id || !ev.id) return;
    const now = (ev.ts && !isNaN(Date.parse(ev.ts))) ? Date.parse(ev.ts) : Date.now();
    // Close any open burst if this event arrived after the 1s quiet gap.
    if (now - _burstLastT > BURST_WINDOW_MS) {
      _burstArrivalWindow = [];
      _burstOpenId = null;
    }
    _burstLastT = now;
    if (_burstOpenId) {
      // A burst is open: keep tagging fast arrivals into it directly.
      if (!ev.burst_id) ev.burst_id = _burstOpenId;
      return;
    }
    _burstArrivalWindow.push({ id: ev.id, t: now });
    if (_burstArrivalWindow.length >= BURST_THRESHOLD) {
      _burstOpenId = "burst-" + now;
      _burstArrivalWindow.forEach((a) => {
        const e = state.events.find((x) => x.id === a.id);
        if (e && !e.burst_id && !e.group_id) e.burst_id = _burstOpenId;
      });
      _burstArrivalWindow = [];  // window served its purpose; open burst tags directly
    }
  }

  function upsertEvent(ev) {
    if (!ev) return;
    const id = ev.id;
    if (id) {
      const i = state.events.findIndex((e) => e.id === id);
      if (i >= 0) { state.events[i] = ev; maybeTagBurst(ev); return; }
    }
    state.events.unshift(ev);
    maybeTagBurst(ev);
    // iter2 G9: raised from 4000 to 10000 to align with the change-list
    // virtualization ceiling (CHANGE_TOTAL_CAP). The virtualized list keeps
    // only ~80 rows in the DOM regardless, so a larger in-memory log no
    // longer means a larger DOM. Events beyond the cap rotate out (oldest
    // first); the full history lives in events.jsonl on disk.
    if (state.events.length > 10000) state.events.length = 10000;
  }

  // ====================================================================
  // 13. Boot
  // ====================================================================
  function debounce(fn, ms) {
    let t = null;
    return function () {
      const ctx = this, args = arguments;
      if (t) clearTimeout(t);
      t = setTimeout(() => fn.apply(ctx, args), ms);
    };
  }

  // ====================================================================
  // 9.4. Conflict-UX modal (INTENT-008) — disk-vs-agent write collision
  // ====================================================================
  // When /__apply returns 409 with {conflict: true, concept, expected_rev,
  // current_rev}, surface a modal asking the user how to resolve. Three
  // actions:
  //   * "View diff"     — open a panel that fetches /__diff and renders rows.
  //   * "Keep mine"     — dismiss (the on-disk bytes stay; the agent's write
  //                       is dropped).
  //   * "Take the agent's" — re-submit the apply WITHOUT expected_rev (force
  //                       overwrite). tokenFetch's caller sees the new Response.
  //
  // ARIA (§13.5): role="alertdialog" + aria-labelledby + focus trap + Esc.
  // Reduced-motion aware (no jarring animation; the modal simply appears).
  let conflictState = { open: false, overlay: null, lastFocus: null };

  function showConflictModal({ data, url, opts, originalBodyObj, originalResponse }) {
    // Build the overlay once; reuse across conflicts.
    if (!conflictState.overlay) _buildConflictModal();
    data = data || {};
    const concept = String(data.concept || "");
    // CLI-agent conflicts (SSE `agent_conflict`) carry no retry context —
    // there is no browser-side request to re-submit, so "Take the agent's
    // edit" is meaningless there and stays hidden. HTTP-409 conflicts
    // (tokenFetch) pass url/opts and get all three actions.
    const takeBtnEl = $(".okf-conflict__take", conflictState.overlay);
    if (takeBtnEl) takeBtnEl.hidden = !url;
    const headingId = "okf-conflict-title";
    const heading = $("#" + headingId, conflictState.overlay) ||
      conflictState.overlay.querySelector("." + conflictState.overlay.getAttribute("aria-labelledby"));
    if (heading) heading.textContent = "You edited " + concept + " in your editor while the agent was updating it.";
    // Reset the diff panel + button states.
    const diffPanel = $(".okf-conflict__diff", conflictState.overlay);
    if (diffPanel) {
      diffPanel.innerHTML = "";
      diffPanel.setAttribute("hidden", "");
    }
    const diffBtn = $(".okf-conflict__diff-btn", conflictState.overlay);
    if (diffBtn) diffBtn.disabled = false;
    conflictState.open = true;
    conflictState.overlay.hidden = false;
    conflictState.lastFocus = document.activeElement;
    // Register with the shared overlay stack.
    if (!_conflictOverlayEntry) _conflictOverlayEntry = { close: function () { _closeConflict("keep"); } };
    if (window.OKFOverlayStack) window.OKFOverlayStack.push(_conflictOverlayEntry);
    // Focus the first action button after a tick (let the modal render).
    // Generation guard: if _closeConflict fires before the timer, the callback
    // no-ops. Timer is cancelable via _conflictFocusTimer.
    if (_conflictFocusTimer) clearTimeout(_conflictFocusTimer);
    var cgen = conflictState._gen = (conflictState._gen || 0) + 1;
    _conflictFocusTimer = setTimeout(function () {
      _conflictFocusTimer = null;
      if (conflictState.open && conflictState._gen === cgen) {
        const first = focusableIn(conflictState.overlay)[0];
        if (first) try { first.focus({ preventScroll: true }); } catch (e) {}
      }
    }, 20);
    // Resolve the caller's promise once the user picks an action.
    return new Promise((resolve) => {
      conflictState._resolve = resolve;
      conflictState._originalResponse = originalResponse;
      conflictState._retryArgs = { url, opts, originalBodyObj, data };
    });
  }

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

  function _buildConflictModal() {
    const overlay = el("div", {
      class: "okf-conflict-overlay", hidden: "",
      role: "alertdialog", "aria-modal": "true",
      "aria-labelledby": "okf-conflict-title",
    });
    const card = el("div", { class: "okf-conflict" });
    const title = el("h2", {
      class: "okf-conflict__title", id: "okf-conflict-title",
      text: "Conflict",  // replaced per-show with the concept-named copy
    });
    const lede = el("p", {
      class: "okf-conflict__lede",
      // Honest, non-jargon phrasing. The user just needs to pick a resolution.
      text: "Pick how to resolve this edit.",
    });
    const actions = el("div", { class: "okf-conflict__actions" });
    const viewBtn = el("button", {
      type: "button", class: "okf-studiobtn okf-conflict__diff-btn",
      text: "View diff",
    });
    // iter2 CRI2-008: "Keep mine" is the primary action (the non-destructive
    // default; the user's on-disk edit stays). "Take the agent's" discards
    // the user's edit and applies the agent's, so it is visually distinct
    // (warn-toned) but NOT primary, per platform HIG guidance that
    // destructive options not be the path of least visual resistance.
    const keepBtn = el("button", {
      type: "button", class: "okf-studiobtn okf-studiobtn--primary",
      text: "Keep mine",
    });
    const takeBtn = el("button", {
      type: "button", class: "okf-studiobtn okf-conflict__take",
      // iter3 CRI3-003: was "Take the agent's" (dangling possessive; read
      // as a typo). The full verb-phrase "Take the agent's edit" pairs
      // cleanly with "Keep mine" — both are now complete predicates.
      text: "Take the agent's edit",
      title: "Discards your on-disk edit; the agent's version is applied.",
    });
    const diffPanel = el("div", {
      class: "okf-conflict__diff", "aria-live": "polite",
      "aria-label": "Line diff between your edit and the agent's", hidden: "",
    });
    actions.appendChild(viewBtn);
    actions.appendChild(keepBtn);
    actions.appendChild(takeBtn);
    card.appendChild(title);
    card.appendChild(lede);
    card.appendChild(actions);
    card.appendChild(diffPanel);
    overlay.appendChild(card);

    // "View diff": fetch /__diff?concept=…&from=…&to=… and render rows.
    // iter3 SEC3-001: /__diff requires the per-session X-OKF-Token header
    // (server.py:_handle_diff enforces it via _check_write_auth, returning
    // 403 otherwise). The bare fetch() iter-2 shipped here was missing the
    // token, so every "View diff" click in the §9.4 conflict modal returned
    // 403 and the catch handler rendered the "Diff fetch failed" fallback
    // (which the iter-1 browser test asserted as "non-empty" — a mask).
    // tokenFetch is the studio's write-fetch wrapper that attaches the
    // token from the embedded BOOT payload; using it here matches every
    // other authenticated fetch in the studio (apply, undo, presence,
    // comment).
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

    // "Keep mine": dismiss, the on-disk bytes stay. Resolve with the
    // original 409 Response so the caller sees !ok and knows the write
    // did not land.
    keepBtn.addEventListener("click", () => _closeConflict("keep"));

    // "Take the agent's": re-submit the apply WITHOUT expected_rev.
    takeBtn.addEventListener("click", async () => {
      takeBtn.disabled = true;
      keepBtn.disabled = true;
      viewBtn.disabled = true;
      try {
        const { url: rurl, opts: ropts, originalBodyObj: rbody } = conflictState._retryArgs;
        // Build a fresh body: drop expected_rev from a cloned object.
        let bodyObj = rbody;
        if (bodyObj && typeof bodyObj === "object") {
          bodyObj = Object.assign({}, bodyObj);
          delete bodyObj.expected_rev;
        }
        const rheaders = Object.assign({ "X-OKF-Token": TOKEN }, ropts.headers || {});
        if (bodyObj) {
          rheaders["Content-Type"] = "application/json";
        }
        const newRes = await fetch(rurl, {
          method: ropts.method || "POST",
          headers: rheaders,
          body: bodyObj ? JSON.stringify(bodyObj) : ropts.body,
        });
        _closeConflict("take", newRes);
      } catch (e) {
        // The retry itself failed; resolve with a synthetic 503 so the
        // caller sees an error rather than hanging.
        _closeConflict("take", new Response(JSON.stringify({ ok: false, error: String(e) }), {
          status: 503, headers: { "Content-Type": "application/json" },
        }));
      }
    });

    // Click outside the card dismisses (acts like "Keep mine").
    overlay.addEventListener("mousedown", (e) => {
      if (e.target === overlay) _closeConflict("keep");
    });

    // Global keyboard wiring (registered once).
    document.addEventListener("keydown", _conflictKeydown);

    document.body.appendChild(overlay);
    conflictState.overlay = overlay;
  }

  var _conflictOverlayEntry = null;
  var _conflictFocusTimer = null;
  function _conflictKeydown(e) {
    if (!conflictState.open) return;
    // Escape is handled by the shared overlay stack — no separate handler.
    // Focus trap: Tab/Shift+Tab cycles inside the alertdialog.
    if (e.key === "Tab") {
      e.preventDefault();
      trapFocusIn(conflictState.overlay, !e.shiftKey);
    }
  }

  function _closeConflict(action, newResponse) {
    if (!conflictState.open) return;
    if (_conflictFocusTimer) { clearTimeout(_conflictFocusTimer); _conflictFocusTimer = null; }
    conflictState.open = false;
    if (_conflictOverlayEntry && window.OKFOverlayStack) window.OKFOverlayStack.remove(_conflictOverlayEntry);
    conflictState.overlay.hidden = true;
    // Re-enable buttons for the next conflict.
    $$("button", conflictState.overlay).forEach((b) => { b.disabled = false; });
    // Safe focus restoration: validate saved trigger or use fallback chain.
    safeFocus(conflictState.lastFocus);
    conflictState.lastFocus = null;
    const resolve = conflictState._resolve;
    conflictState._resolve = null;
    if (!resolve) return;
    if (action === "take" && newResponse) {
      resolve(newResponse);
    } else {
      // "Keep" / Esc / outside-click → the original 409 Response.
      resolve(conflictState._originalResponse);
    }
    conflictState._originalResponse = null;
    conflictState._retryArgs = null;
  }

  // ---- sidebar rail: nav + flat Related ----
  // Editorial Workbench §3.2: the persistent Diátaxis nav is the primary rail;
  // the in-page heading list moved to the pop-over Outline tab, so "sections"
  // is retired here. Related (local graph) + Quick Actions stack below the nav.
  // Quick-action "intents" moved OUT of the left nav into the Comments tab of
  // the studio dock (buildIntentsToolbar) — so the left column stays a clean
  // Diátaxis nav and the action buttons sit where they pre-fill the composer.
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

  function buildSidebarPanels() {
    var sidebar = $(".okf-page__sidebar");
    if (!sidebar) return;

    // Capture the server-rendered nodes we must preserve (move the actual
    // nodes, keeping wiki.js event listeners): the primary Diátaxis nav rail
    // and the local-graph widget.
    var existingNav = $(".okf-nav", sidebar);
    var existingGraph = $(".okf-local-graph", sidebar);

    // Clear sidebar.
    sidebar.innerHTML = "";

    // The Diátaxis nav is the persistent wayfinding rail — re-mount it at the
    // top, NOT as a draggable panel, so it always leads the column.
    if (existingNav) sidebar.appendChild(existingNav);

    // Related renders FLAT (a nav-group label + the neighbour list), not a
    // draggable card — one continuous left rail. Build it directly.
    if (existingGraph) {
      var related = el("section", { class: "okf-related", "aria-label": "Related" });
      related.appendChild(el("p", { class: "okf-nav__group", text: "Related" }));
      related.appendChild(existingGraph);   // move the node; wiki.js re-renders it flat
      sidebar.appendChild(related);
    }

    // Re-render the local graph pills inside the new panel location so
    // wiki.js's click handlers (navigation) are properly bound.
    if (window.okfWiki && window.okfWiki.renderLocalGraph) {
      try { window.okfWiki.renderLocalGraph(); } catch (e) {}
    }
  }

  // Editorial Workbench (revised): the quick-action directive buttons live at
  // the top of the Comments tab in the studio dock. Same INTENTS + behaviour
  // as the retired left-nav panel — clicking one pre-fills the composer prompt.
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

  // Editorial Workbench §3.3 (Round 2: functional pin): clicking a commented
  // span (the inline mark) jumps to the mark itself AND opens the Comments
  // overlay scrolled+pulsed to that comment's card — the thread content
  // lives only in the overlay, so the reading page stays a reading page.
  // Delegated once so it survives mark re-creation on live patches.
  function wireCommentMarkClicks() {
    document.addEventListener("click", function (e) {
      const t = e.target;
      const mark = t && t.closest && t.closest(".okf-comment-mark");
      if (!mark) return;
      e.preventDefault();
      const id = mark.getAttribute("data-comment-id");
      jumpToCommentMark(id);         // scroll+pulse the prose mark
      if (id) jumpToCommentCard(id); // open the overlay + scroll+pulse the card
      else openPanel("comments");
    });
  }

    function boot() {
      mountBar();
      mountNavToggle();
      // TEST-ONLY PROBE (post-mount): runs AFTER mountBar() appended the
      // studio bar to document.body and mountNavToggle() toggled the nav-
      // collapse class — i.e. after at least one genuine boot() DOM mutation
      // completed (proving this is a boot() failure, not a module-evaluation
      // failure). See _bootProbe below. Inert in production.
      _bootProbe("post-mount");
      wireCommentMarkClicks();
    wirePaletteKeys();
    if (isConceptPage()) {
      ensureViewWrap();
      setView(state.view); // also deep-links + lazy-loads source if needed
      bindSelectionAffordance();
      buildSidebarPanels();
      // Round 2: always-docked thin rail (>=900px); overlays open on demand
      // (no auto-open dock). The slim reserve keeps content clear of the rail.
      // NOTE: body.okf-has-rail is ALSO server-rendered on concept pages
      // (concept_page.html) so studio.css applies the reserve from first paint
      // and the centered page never recentres at boot; this add() is an
      // idempotent belt-and-suspenders for any path that skips the template.
      if (window.innerWidth > 900) {
        buildRail();
        document.body.classList.add("okf-has-rail");
      }
    } else if (document.getElementById("detail-body")) {
      // Graph page: bind selection affordance for the detail panel.
      bindSelectionAffordance();
    }
    // iter1 CRI-004: stamp data-concept-id on list/search rows so presence
    // focus can highlight them (also runs on index/search pages).
    stampConceptIds();
    loadGraph().then(buildIndexEngagement);
    loadComments().then(buildIndexEngagement);
    wireLive();
    // iter1 CRI-002: apply text-range marks for any pre-existing comments
    // on the open concept (loaded by loadComments above).
    applyCommentMarks();
    rebuildMarginMarkers();
    // Initial presence fetch (best-effort; server may have none).
    tokenFetch("/__presence", { method: "POST", body: { state: "idle", actor: "user" } }).catch(() => {});
    // Apply bootstrap presence highlight if focus present.
    renderPresence(state.presence);
      // Rebuild markers after fonts/layout settle.
      setTimeout(rebuildMarginMarkers, 400);
      // TEST-ONLY PROBE (post-async-kick): runs AFTER all fire-and-forget
      // async tails have been dispatched (loadGraph/loadComments/tokenFetch
      // promises + the 400ms rebuildMarginMarkers timer) but BEFORE boot()
      // returns. Lets a test force boot() to throw at this exact point so it
      // can prove the in-flight late tails cannot overwrite the unavailable
      // settlement. See _bootProbe below. Inert in production.
      _bootProbe("post-async-kick");
    }
  
    // ---- TEST-ONLY boot probe ---------------------------------------------
    // ``_bootProbe`` is a constrained, inert-by-default seam that lets the
    // browser test suite deterministically inject a boot() failure at a named
    // phase. It is the ONLY way to prove two contract-sensitive invariants
    // without guessing fragile DOM-method call orders:
    //   1. boot() genuinely executes (past module evaluation) and mutates the
    //      DOM, THEN throws — distinguishing a boot() failure from a module-
    //      evaluation failure (probe phase "post-mount").
    //   2. Late asynchronous tails (already-dispatched promises/timers) cannot
    //      replace okf-studio-unavailable with okf-studio-booted or hide the
    //      failure banner (probe phase "post-async-kick").
    //
    // Safety contract:
    //   * INERT BY DEFAULT: the typeof guard means production never invokes
    //     the callback — it is only installed by a test's add_init_script.
    //   * NOT A PUBLIC MUTATION PATH: the probe receives only a phase STRING
    //     (no internals, no state). It can do exactly one thing relevant to
    //     boot settlement: throw, which _runBoot catches and converts to the
    //     unavailable terminal state (the correct failure UX). It cannot call
    //     _settleBoot, cannot bypass the catch, cannot mutate boot state.
    //   * CONSTRAINED: called at exactly two named phases inside boot(); no
    //     other call sites exist.
    function _bootProbe(phase) {
      if (typeof window.__okfBootProbe === "function") {
        window.__okfBootProbe(phase);
      }
    }
  
    // Expose the public API.
  window.okfLoomStudio = {
    register,
    applyDoc,
    refreshGraph,
    openPanel,
    closePanel,
    openPalette,
    closePalette,
    setView,
    toggleFocus,
    get state() { return state; },
    get panels() { return panels; },
    ctx,
    // Test/debug helpers.
    _toast: toast, _loadComments: loadComments, _renderChangeList: renderChangeList,
    _changeRow: changeRow,
    _showConflictModal: (payload) => showConflictModal({
      data: payload,
      url: "/__apply",
      opts: { method: "POST" },
      originalBodyObj: { kind: "add_tag", target: payload && payload.concept, args: { tag: "x" } },
      originalResponse: new Response(JSON.stringify(payload || {}), { status: 409 }),
    }),
  };

  // ---- Boot settlement (one-way, event-driven) ---------------------------
  // Stamp okf-studio-booted ONLY after the synchronous boot() body completes
  // without throwing. If boot() throws, stamp okf-studio-unavailable instead
  // so the failure banner is revealed (wiki.css: html.okf-studio-unavailable
  // .okf-studio-fallback-banner--js { display: block }). The settlement
  // classes are ADDITIVE ONLY — neither is ever removed — so a successful
  // ready state and an unavailable state can never race or overwrite each
  // other. Late async results (loadGraph/loadComments/tokenFetch promises and
  // the 400ms rebuildMarginMarkers timer) are fire-and-forget with their own
  // catch handlers; they do not affect the synchronous boot settlement.
  //
  // Execution timeline: studio.js is a deferred module, so it evaluates
  // AFTER parsing completes (readyState "interactive") but BEFORE
  // DOMContentLoaded fires. At evaluation time readyState is already
  // "interactive", so _runBoot() is called immediately — synchronously
  // within module evaluation. By the time DOMContentLoaded fires and
  // theme.js's watchdog checks for okf-studio-booted, boot() has already
  // settled (either okf-studio-booted or okf-studio-unavailable is present).
  // The watchdog is the safety net for "studio.js never loaded at all."
  function _settleBoot(ok) {
    document.documentElement.classList.add(
      ok ? "okf-studio-booted" : "okf-studio-unavailable"
    );
  }
  function _runBoot() {
    try {
      boot();
      _settleBoot(true);
    } catch (e) {
      _settleBoot(false);
      // Surface the error for debugging without re-throwing (a re-throw
      // would be an unhandled module-level exception; the user already sees
      // the failure banner, which is the correct UX for a boot failure).
      if (window.console && console.error) {
        console.error("[okf-studio] boot() threw — marking unavailable:", e);
      }
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _runBoot, { once: true });
  } else {
    _runBoot();
  }
})();
