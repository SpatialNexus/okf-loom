---
type: ImplementationPlan
title: Editorial Workbench hardening implementation plan
description: Execution plan for unifying theme state, fixing accessibility and responsive
  defects, hardening visual behavior, and proving runtime/export parity.
resource: /plans/editorial-workbench-hardening.md
tags:
- editorial-workbench
- theme
- accessibility
- hardening
- testing
timestamp: '2026-07-13T21:02:54Z'
aliases: [theme hardening plan, Editorial Workbench stabilization]
entities:
- label: Editorial Workbench
  kind: interface_system
- label: Theme preference
  kind: runtime_state
relations:
- type: implements
  target: /reference/spec.md
- type: hardens
  target: /explanation/live_studio_design.md
provenance:
- source: feature/new-layout review at b7d7cb1465d6d07ef2a22fc82d476974cdffd84f
  note: Derived from code, browser, accessibility, visual, validation, and evidence
    reviews.
---

# Objective

Harden the Editorial Workbench theme overhaul without replacing its established Swiss-first, deep-teal product direction. The work unifies theme state and configuration, fixes confirmed responsive and accessibility defects, strengthens visual reliability, repairs proof tooling, and completes the optional polish identified during the branch review.

# Baseline and scope

- **Implementation branch:** `feature/editorial-workbench-hardening`
- **Reviewed source range:** `2066013a87d9a06ee523bac2cc7b00b874d1e353...b7d7cb1465d6d07ef2a22fc82d476974cdffd84f`
- **Primary surfaces:** concept, index, search, graph, studio, static build, and single-file build.
- **Theme matrix:** Swiss Light, Swiss Dark, Technical Light, Technical Dark, plus Auto mode, Soft Contrast, and Border On/Muted/Off.
- **Product contract:** preserve the Editorial Workbench visual system and the runtime/build behavior described by the [current specification](/reference/spec.md) and [live studio design](/explanation/live_studio_design.md).

# Findings driving the plan

## Theme and configuration state

1. A configured initial theme is emitted by Python but can be discarded by client boot when no saved preference exists.
2. Auto mode and theme family do not have one authoritative state model. Wiki does not follow OS changes, graph can freeze Auto after the first change, and Technical plus Auto does not persist across navigation.
3. YAML, viewer JSON, runtime allow-lists, and public documentation disagree about valid theme values and legacy migration.
4. Invalid viewer JSON configuration silently falls back instead of returning actionable diagnostics.

## Responsive and accessibility behavior

1. The Appearance popover is clipped within the topbar scroller at widths through 900px.
2. Appearance radiogroups and Studio tabs do not implement composite-widget keyboard behavior.
3. The full-screen mobile Studio panel does not take modal focus ownership or make the obscured page inert.
4. Mobile Studio footer actions and graph topbar controls overflow their containers.
5. Status glyphs use foreground colors that do not maintain sufficient contrast in dark themes.

## Rendering and maintainability

1. Graph legends cover canvas content in current Map and Bridges captures.
2. Platform-dependent rail glyphs render as replacement boxes in the capture environment.
3. Mermaid output does not update after a light/dark Appearance change.
4. Capture tooling and README media do not prove Swiss-first, mobile, static, or single-file parity.
5. Theme lists, glyphs, migration maps, and graph palette contracts are duplicated without an automated parity check.
6. Public docs and handover references are stale.

# Quality risk classification

| Risk | Why it applies | Required evidence |
|---|---|---|
| `state-ownership` | Configured theme, saved preference, family, mode, OS preference, and legacy migration have multiple writers/readers. | State ownership table plus reload, navigation, OS-change, storage-denial, and reset tests. |
| `contract-runtime-parity` | YAML, JSON, Python renderers, JavaScript contexts, documentation, static output, and single-file output must agree. | Contract-to-runtime matrix and browser proof for every output target. |
| `fail-closed-validation` | Viewer configuration accepts public structured input. | Success and invalid-input matrix with diagnostics. |
| `keyboard-focus` | Appearance, tabs, mobile overlays, rail controls, and graph interactions own keyboard and focus behavior. | Keyboard/focus matrix and browser tests. |
| `rendering-capture` | The plan changes CSS, canvas presentation, screenshot tooling, static output, and single-file output. | Semantic readiness matrix, fresh captures, and live/export parity proof. |

# State ownership contract

| State | Authoritative owner | Writers | Readers | Reset or external override | Required proof |
|---|---|---|---|---|---|
| Configured initial family/mode | Validated bundle/viewer configuration | YAML or JSON loader | Renderer and client bootstrap | New build or bundle config reload | Configured themes survive first boot when no user preference exists. |
| User family | Dedicated persisted preference | Appearance family controls and legacy migration | Wiki, graph, studio, static, single-file | Explicit user reset only | Swiss/Technical persists independently of mode. |
| User mode | Dedicated persisted preference: Auto, Light, or Dark | Appearance mode controls and migration | All runtime surfaces | Explicit user reset | Auto survives navigation and does not become a concrete saved mode. |
| Resolved concrete theme | Derived value only | Shared resolver | DOM root, graph palette, renderers | Config, family, mode, or OS preference changes | No component persists this derived value while mode is Auto. |
| Contrast and border | Persisted validated modifier values | Appearance controls | DOM/CSS and graph presentation where supported | Explicit default selection | Modifiers persist and compose across routes and outputs. |

Precedence is: **saved user preference → configured preference → Swiss Auto/OS fallback**. Storage failure disables persistence only; it does not change resolution. Legacy values are migrated once through the same canonical resolver.

# Implementation phases

## Phase 1: Contract and test scaffolding

1. Encode the state contract in tests before broad implementation.
2. Add parity checks for all theme names, glyphs, migration values, configuration documentation, and renderer contexts.
3. Add invalid-input coverage for malformed JSON, non-object JSON, unknown keys, wrong types, unsupported themes/layouts, empty values, and legacy values.
4. Add branch/base stress proof for the Studio readiness race and replace the premature readiness signal with a post-boot contract if confirmed.

**Acceptance proof:** focused tests fail on the reviewed implementation and describe the intended state transitions without relying on implementation details.

## Phase 2: Theme and configuration correctness

1. Introduce one shared theme preference/resolution contract usable by wiki, graph, studio, static, and single-file contexts.
2. Persist family independently from mode; never persist the resolved light/dark value while Auto is selected.
3. Observe `prefers-color-scheme` changes on every live surface while Auto is active.
4. Preserve validated configured defaults when no user preference exists.
5. Make storage-denied behavior deterministic.
6. Reject invalid viewer configuration with contextual diagnostics and provide explicit legacy migration guidance.
7. Reconcile YAML, JSON, generated markup, documentation, and runtime values.

**Acceptance proof:** browser tests cover every family/mode combination, reload/navigation, two OS changes, storage denial, legacy migration, configured defaults, and static/single-file boot.

## Phase 3: Responsive and accessibility stabilization

1. Render or position the Appearance popover outside the horizontal controls scroller.
2. Implement roving tabindex, arrow keys, Home/End where appropriate, checked/selected state, Escape behavior, and focus restoration for Appearance and Studio tabs.
3. Give the mobile Studio panel dialog semantics, focus containment, inert background behavior, and safe close restoration while retaining non-modal desktop behavior.
4. Contain or wrap Studio footer actions without document-level overflow.
5. Give the graph topbar a coherent mobile layout rather than combining wrapped controls with a fixed single-row height.
6. Preserve native browser/editable behavior and visible focus in every theme/modifier.

**Acceptance proof:** keyboard-only workflows and geometry checks at 320, 390, 768, 900, 901, and 1280 pixels, plus 200% and 400% zoom/reflow.

## Phase 4: Visual hardening

1. Add semantic foreground-on-status tokens for success, warning, and error surfaces.
2. Replace font-dependent rail glyphs with deterministic inline SVG or CSS-mask icons and preserve accessible names.
3. Reserve a collision-free graph legend region or provide a reliably collapsible legend.
4. Measure representative prose/search widths, then apply a 65–75ch reading measure with explicit wide-content escape hatches where evidence supports it.
5. Measure dark-graph, search metadata, focus, disabled, and modifier contrast in all four themes.
6. Prevent Border Off from removing the only state cue.

**Acceptance proof:** computed contrast assertions, zoom/reflow checks, and fresh screenshots for all four themes plus Soft Contrast and Border Off.

## Phase 5: Distribution and capture parity

1. Browser-test live, static, and single-file outputs with the same theme-state matrix.
2. Repair capture scripts to resolve an available browser, accept external output directories, and wait on semantic readiness rather than `networkidle` or unconditional sleeps.
3. Refresh README media with explicit route, theme, viewport, and revision metadata.
4. Add semantic diagnostics for hidden, unreadable, unavailable, not-ready, and valid-but-uniform capture states.
5. Run the complete test suite cleanly.

**Acceptance proof:** a capture manifest and current artifacts covering desktop/mobile, Swiss/Technical, light/dark, no-JS fallback, reduced motion, forced colors, and static/single-file parity.

## Phase 6: Optional polish

1. Tokenize Mermaid styling and rerender diagrams after light/dark changes.
2. Improve graph edge disclosure, label collision handling, category restraint, and focused-neighborhood legibility without removing the complete Map lens.
3. Make graph Contrast/Border modifier scope coherent or explain the deliberate limitation in Appearance help.
4. Refine duplicate-title handling, reading/search composition, selected-comment context, and split-action clarity where live proof confirms the issue.
5. Add versioned viewer asset URLs or an equivalent cache-busting contract.
6. Keep every refinement within the existing Swiss-first Editorial Workbench language.

# Parallelization and ownership

- Theme/config state and its tests are one hot integration surface and should remain single-writer.
- Responsive/accessibility implementation may proceed in parallel once the state contract is stable, but `wiki.css`, `wiki.js`, `graph.js`, `studio.js`, and shared browser fixtures must be serialized at integration time.
- Capture tooling and documentation are parallel-safe until their final parity tests consume completed runtime behavior.
- Visual polish follows correctness and must use fresh captures from the final runtime, not the pre-hardening media.

# Definition of done

- All confirmed major findings have direct regression tests or measured browser proof.
- `STATE_OWNERSHIP_TABLE`, `CONTRACT_RUNTIME_PARITY_MATRIX`, `FAIL_CLOSED_VALIDATION_MATRIX`, `KEYBOARD_FOCUS_MATRIX`, and `RENDERING_CAPTURE_MATRIX` are complete.
- The complete pytest suite, strict bundle validation, and JavaScript lint pass.
- Live, static, and single-file outputs agree across the required theme matrix.
- Fresh desktop/mobile captures have no unresolved critical or major visual-review findings.
- Public configuration and user documentation match runtime behavior.
- Optional polish is implemented and verified rather than left as an untracked backlog.
