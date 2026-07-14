# OKF Viewer — Extension & Override Points

The viewer supports five extension mechanisms. All override files live under
`<bundle_root>/.okf-loom/viewer/`, so a bundle can be self-contained without
forking okf-loom.

> **Precedence:** bundle overrides win over the built-in assets, every time.

---

## 1. Template overrides

Drop a file at `.okf-loom/viewer/templates/<name>.html` to replace the built-in
template of the same name. Recognised names:

| Name                | Used by                          |
|---------------------|----------------------------------|
| `single_file.html`  | `render_single_file`             |
| `concept_page.html` | serve / spa / static concept page|
| `index_page.html`   | serve / spa / static index       |
| `search_page.html`  | serve search results             |
| `graph_page.html`   | `/__graph` full-page graph       |

Templates use **`str.replace` placeholders** (NOT `string.Template`), because
concept bodies frequently contain literal `$`. Each template documents its
placeholders in a leading HTML comment. Example — a custom concept page
footer:

```html
<!-- .okf-loom/viewer/templates/concept_page.html -->
...
<footer>© Acme Corp — internal OKF mirror</footer>
```

## 2. Static asset overrides

Drop a file at `.okf-loom/viewer/static/<file>` to replace a built-in asset.
Both the live server (`/__static/...`) and the static-site builder honour
overrides. **Only built-in viewer asset names are overridable** — the single
explicit scope (the on-disk built-in set, currently):

```text
graph.css   graph.js   live.js   renderers.js   static-search.js
studio.css  studio.js  theme.js  wiki.css       wiki.js
```

(derive the current set from `list_builtin_static()` / `STATIC_ASSET_NAMES`;
an override for any other name is ignored, and loading/serving an unknown
name is rejected.)

```text
.okf-loom/viewer/static/wiki.css   ← replaces the bundled stylesheet
```

External asset URLs carry a content-derived `?v=` cache-busting query
(see `http_routes.md` › `/__static/<file>`). The version is the SHA-256 of
the *resolved* asset, so editing an override changes its version and
invalidates browser/CDN caches automatically — no manual cache-clear and no
server reload needed. The version is recomputed from the override's current
bytes on every render, so a saved stale value can never be served. When the
active-code gate is closed the override is ignored and the version falls
back to the builtin's.

## 3. Type palette overrides

`.okf-loom/viewer/palette.json` maps a concept type to any CSS colour. It is
**merged over** the auto-generated palette (which hashes each type name to
a stable HSL hue — no BigQuery-specific hardcoding).

```json
{
  "BigQuery Table": "#3b82f6",
  "Reference": "#10b981",
  "custom_type": "#a855f7"
}
```

**Security (P1-41).** Palette values are interpolated into inline
`style="background:<color>"` attributes in the rendered HTML. HTML-escaping
alone does not stop CSS injection (a value like
`red;position:fixed;top:0` has no HTML-unsafe characters), so two layers
of defence apply:

1. **Gate.** Palette overrides are only loaded when the **effective
   active-code gate** (see §5) is open — i.e. the bundle declares
   `allow_active_code: true` AND the operator consents. When the gate is
   closed, only the auto-generated palette is used; a bundle cannot
   recolour the UI on its own.
2. **Validation.** Even with the gate open, every value must match a strict
   CSS-colour allowlist (`#rgb` / `#rrggbb` / `#rrggbbaa` hex,
   `rgb()` / `rgba()` / `hsl()` / `hsla()`, or a named CSS colour).
   Values that do not match (e.g. `red;position:fixed;top:0`,
   `url(data:...)`, `javascript:...`) are dropped fail-closed; the key is
   not emitted. A benign palette should not ship broken CSS anyway.

## 4. Viewer config

`.okf-loom/viewer/config.json` controls display defaults. All keys optional:

| Key              | Type    | Default   | Effect                                         |
|------------------|---------|-----------|------------------------------------------------|
| `name`           | string  | bundle dir name | Display name for the viewer / browser title. |
| `default_layout` | string  | `"cose"`  | Initial Cytoscape layout: `cose` / `concentric` / `breadthfirst` / `circle` / `grid`. |
| `theme`          | string  | `"technical-light"` | Concrete initial colour theme: `"swiss-light"` / `"swiss-dark"` / `"technical-light"` / `"technical-dark"`. A saved user preference takes precedence. |
| `cdn`            | bool    | `true`    | If `false`, omit the Cytoscape.js CDN `<script>` tags from the single-file viewer and the `/__graph` page (for fully offline packaging — supply your own copy in that case). Markdown is rendered server-side by okf-loom's own stdlib renderer, so there is no client-side markdown parser to gate. |

`config.json` is strict: malformed JSON, a non-object top level, unknown keys,
wrong types, empty values, and unsupported enum values stop the operation with
a file-and-field diagnostic. Retired theme names are not silently interpreted.
Replace `light` with `technical-light`, `dark` or `midnight` with
`technical-dark`, and `pastel` or `sepia` with `swiss-light`. This explicit
configuration migration is separate from the one-time migration of returning
users' saved browser preferences. Display names may contain ordinary special
characters; renderer escaping remains mandatory and prevents interpolation.

```json
{
  "name": "Acme OKF",
  "default_layout": "breadthfirst",
  "theme": "dark",
  "cdn": true
}
```

## 5. Plugin hook (entry-point loader; current spec §15)

A `ViewerPlugin` is any object exposing:

```python
class ViewerPlugin:
    def on_concept_render(self, concept: Concept, html: str) -> str: ...
    def on_index_render(self, html: str) -> str: ...   # optional
```

`on_concept_render(concept, html)` runs after a concept-page body is rendered
and returns possibly-modified HTML (e.g. to inject a widget, badges, or
telemetry). `on_index_render(html)` is the same hook for index pages and is
optional — plugins that omit it are silently skipped on index pages.

### Discovery: Python entry points

Plugins are discovered via the **`okf_loom.viewer_plugins`** entry-points
group. Register one in `pyproject.toml`:

```toml
[project.entry-points."okf_loom.viewer_plugins"]
badge = "my_pkg.viewer:BadgePlugin"      # a class — instantiated once
make = "my_pkg.viewer:make_plugin"       # or a factory returning an instance
```

Either form is accepted: an entry point may point at a class (instantiated
with no args) or a factory callable that returns a plugin instance. An
already-constructed instance is also accepted. Plugins load in entry-point
registration order.

### Active-code gate (current spec §14)

Plugins **execute arbitrary Python** (module import alone runs code), so they
run ONLY when **both** of the following are true:

1. The bundle's `okf-loom.config.yaml` declares:

   ```yaml
   viewer:
     allow_active_code: true
   ```

2. **The operator has explicitly consented** by setting the
   `OKF_LOOM_ALLOW_ACTIVE_CODE` environment variable to `1` / `true` / `yes`, OR
   by passing `--allow-active-code` to `scripts/okf-loom serve` / `scripts/okf-loom build`.

The effective gate is `bundle_cfg.allow_active_code AND operator_consent`.
The default for both is `false`.

**Why two layers (trust model).** A bundle is an untrusted artifact from the
consumer's point of view: it ships `.okf-loom/viewer/templates/*.html`,
`.okf-loom/viewer/static/*.js`, and (via entry points) plugin Python that all
execute on every page view. If `allow_active_code: true` in the bundle were
sufficient on its own, a bundle could ship a malicious template that strips
the CSP and injects arbitrary JS — and every visitor to `scripts/okf-loom serve` would
run it with no operator warning. The operator-consent layer makes the
decision explicit: the operator looks at the bundle, decides whether they
trust its override/plugin sources, and only then opens the gate. A bundle
with `allow_active_code: true` and no operator consent produces the
built-in (safe) viewer — overrides silently ignored, no warning printed
(the closed gate is the safe default).

When the effective gate is open, `scripts/okf-loom serve` and `scripts/okf-loom build` print a
prominent stderr warning:

```
WARNING: active code (viewer overrides + plugins) is ENABLED for bundle <root>.
WARNING: Only run this for bundles whose override/plugin sources you trust.
WARNING: A malicious override can execute arbitrary JavaScript in every visitor's browser.
```

The same gate governs **template overrides**, **static asset overrides**,
**type palette overrides**, and **plugin discovery** uniformly — see
`okf_loom.viewer.assets._overrides_allowed` /
`effective_allow_active_code`.

When the gate is closed, **no entry-point discovery happens at all** —
`scripts/okf-loom serve` and `scripts/okf-loom build` do not even import plugin modules.

### Failure handling

A plugin that raises during load OR during a hook call is **logged to stderr
and skipped** — the viewer keeps serving. A failing plugin never crashes the
page render; the worst case is that the page is served without that plugin's
contribution.

### Manual attachment (still supported)

For embedders that do not want to use entry points, attach a plugin instance
(or a `CompositeViewerPlugin`) directly to the server after construction:

```python
from http.server import ThreadingHTTPServer
from okf_loom import Bundle
from okf_loom.viewer import OKFWikiHandler, CompositeViewerPlugin

class BadgePlugin:
    def on_concept_render(self, concept, html):
        return html.replace("</body>",
            '<div class="badge">Internal</div></body>')

plugin = CompositeViewerPlugin([BadgePlugin()], allow_active_code=True)
httpd = ThreadingHTTPServer(("127.0.0.1", 8787), OKFWikiHandler)
httpd.bundle = Bundle.load("path/to/bundle")
httpd.plugin = plugin    # ← explicit; bypasses entry-point discovery
httpd.serve_forever()
```

`okf_loom.viewer.plugins.build_viewer_plugin(bundle_root)` is the helper
that performs entry-point discovery + active-code gating in one call; it is
what `scripts/okf-loom serve` and `scripts/okf-loom build` use by default.

---

## 6. Client-side extension API: `okfLoomStudio.register(kind, config)` (current spec §15)

The studio client (`viewer/static/studio.js`) exposes a small JavaScript
extension registry on `window.okfLoomStudio`. It mirrors the server-side
`ViewerPlugin` seam's intent (let a bundle or harness grow the UI without
forking core) but runs **fully client-side**, after the page has booted.
Unlike the bundle `.okf-loom/viewer/` overrides (sections 1 to 5, which replace
whole files), `register()` is **additive** — you hand it a config object and
the studio wires it into the existing chrome.

```js
// CSP-safe (script-src 'self'): load this from a .okf-loom/viewer/static/*.js
// override, or eval it from your harness after the studio boots. No inline
// handlers; the studio owns every addEventListener.
window.okfLoomStudio.register(kind, config);
```

### Kinds

| Kind                 | Status                      | What it does                                                                 |
|----------------------|-----------------------------|------------------------------------------------------------------------------|
| `panel`              | **Ships, wired**            | Adds a slide-over panel + a studio-bar toggle button.                         |
| `viewMode`           | **Ships, wired**            | Adds a button to the Rendered/Source/Split view switch on concept pages.      |
| `toolbar`            | **Reserved (forward-compat)**| Accepted + warned, not wired. Planned: a studio-bar action button.           |
| `graphDecorator`     | **Reserved (forward-compat)**| Accepted + warned, not wired. Planned: a per-Cytoscape-node style hook.      |
| `suggestionRenderer` | **Reserved (forward-compat)**| Accepted + warned, not wired. Planned: a custom renderer for `/__apply` previews. |

The three reserved kinds are accepted so an extension that targets a future
toolkit version does not throw today; `register()` logs a clear
`console.warn` naming the kind and stating it is not wired, so an author
discovers the gap immediately rather than debugging a silent no-op.

### `panel` (ships) — worked example

A panel is a slide-over that joins the built-in **Comments**, **Changes**,
and **Agent activity** panels. It gets a toggle button in the studio bar
(right cluster), focus-trap + Esc handling, and a render callback that
receives a context object with the live studio state.

```js
// .okf-loom/viewer/static/my-panel.js  (loaded after studio.js)
window.okfLoomStudio.register("panel", {
  id: "coverage",                 // unique; used as the open-panel key
  label: "Coverage",              // the studio-bar toggle button label
  // render(container, ctx) is called whenever the panel opens. Wipe
  // container and rebuild; the studio owns the slide-over chrome, focus
  // trap, Esc, and the bar toggle's aria-expanded.
  render(container, ctx) {
    container.innerHTML = "";
    const open = ctx.state.comments.filter(c => c.state === "open").length;
    container.textContent = "Open comments: " + open;
    // ctx.onLive("activity", fn) subscribes to the live event bus, so the
    // panel can update in real time as the agent acts.
  },
});
```

The built-in panels are registered the same way (see the `panels.comments`,
`panels.changes`, and the demo `agent-activity` registrations in
`studio.js`). The context object (`ctx`) exposes:

- `ctx.state` — the live studio state (view, conceptId, comments, events,
  presence, openPanel, filters). Treat it as read-only; mutate through the
  studio's own actions.
- `ctx.el(tag, attrs, children)` — the studio's element helper (sets
  attributes, including `dataset` and `style` objects).
- `ctx.toast(msg, opts)`, `ctx.currentConceptId`, `ctx.boot`, `ctx.tokenFetch`.
- `ctx.onLive(type, fn)` — subscribe to the live event bus
  (`window.okfLoomLive`) for `activity`, `changed`, `created`, `removed`,
  `comment`, `presence`, `conn`, `resync`, … (§7.3 / §12).

### `viewMode` (ships) — worked example

A view-mode extension adds a button to the Rendered/Source/Split switch on
concept pages. It is read-only by design (the studio's directing model is
"the user comments, the agent edits"; §1.4). The extension's `onActivate`
is responsible for any custom rendering.

```js
window.okfLoomStudio.register("viewMode", {
  id: "outline",
  label: "Outline",
  onActivate(ctx) {
    // Build an outline from the headings and swap it into the view area.
    // The studio marks only this button pressed (aria-pressed) and clears
    // the built-in trio; deep-linking via ?view= stays on the built-ins.
  },
});
```

### Reserved kinds (forward-compat)

`toolbar`, `graphDecorator`, and `suggestionRenderer` are reserved for a
future release. They are documented here so the intended surface is
discoverable, but the studio does not yet call them. If you register one
today, the studio:

1. Accepts the call (does not throw) so an extension written against a
   future version degrades gracefully today.
2. Logs `console.warn("[okf-studio] register('<kind>') is reserved for a
   future release and is not wired in this version.")`.
3. Returns the config object unchanged.

Track wiring against the current spec; do not depend on reserved kinds until they are documented as current.

### When to use `register()` vs the `.okf-loom/viewer/` overrides

- **Replace a whole template or stylesheet** (e.g. a custom concept-page
  footer, a recoloured wiki.css): use sections 1 to 4 (file overrides).
  Those are the coarser-grained, replace-the-file mechanisms.
- **Add a panel / view mode / live-driven widget without forking core**:
  use `register()`. It is additive and survives toolkit upgrades because
  it depends only on the documented `ctx` shape.
- **Run server-side Python during render** (e.g. inject a badge into every
  concept page at build time): use the `ViewerPlugin` hook (section 5).

All three mechanisms compose: a bundle can ship a custom `wiki.css`, a
`ViewerPlugin`, and a `register("panel", …)` extension at the same time.
