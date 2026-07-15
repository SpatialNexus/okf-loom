---
type: Explanation
title: Editorial Workbench hardening
description: Why the viewer now keeps theme, layout, boot status, navigation, and
  wide tables stable and accessible.
resource: /explanation/editorial_workbench_hardening.md
tags:
- editorial-workbench
- viewer
- accessibility
- navigation
- hardening
timestamp: '2026-07-15T18:09:16Z'
---

# Overview

Editorial Workbench hardening makes the rendered knowledge space stable before the first meaningful frame, accessible across JavaScript and no-JavaScript contexts, and predictable during ordinary document navigation. It records the completed behavior rather than the historical execution plan.

# Theme availability

The shared Appearance control is ready to use in live, static, and single-file output. It provides Auto, Swiss Light, Swiss Dark, Technical Light, and Technical Dark modes from one state owner, with saved preferences and operating-system preference resolving before the first body paint. See the [theme configuration reference](/reference/config_yaml.md) for the accepted configuration values and the [current specification](/reference/spec.md) for the binding behavior contract.

# Stable first paint

The viewer resolves its effective theme before the body paints. The live server provides the inert studio configuration before the shared theme resolver, which combines configured theme, saved Appearance preferences, and the operating-system light or dark preference without a wrong-theme flash.

Studio boot has one terminal state. A successful synchronous boot marks the page ready only after its required setup completes. A blocked module, evaluation failure, or boot failure settles unavailable and exposes one accessible fallback banner. Later asynchronous work cannot turn unavailable into ready or make a ready page appear unavailable.

# Native navigation and layout

Internal concepts remain ordinary Markdown anchors. Browser Back and Forward, Enter on a focused link, and Ctrl or Cmd new-tab behavior remain native. On JavaScript-enabled desktop concept pages, rail space is present from first layout, so mounting the studio rail does not recenter the reading column. Mobile and no-JavaScript pages do not reserve unused rail space.

# Accessible wide tables

Wide tables stay semantic and locally scrollable. Without JavaScript, the server renders a focusable named table scrollport so keyboard users can reach every column without widening the document. With JavaScript, overflowing tables receive a labelled scroll region, visible cue, focus treatment, and edge state; fitting tables keep no unnecessary tab stop. Resize and live body patches reclassify tables without stale affordances.

# Graph and mutation hardening

The first-visit graph tour participates in overlay focus ownership, so it never steals focus from Appearance controls and restores focus correctly. Graph LOD proof verifies the capped initial collection and one-shot layout settlement. Default link additions now appear before a terminal body Citations appendix, preserving visibility when duplicate body citations are rendered separately.

# Verification evidence

The checked-in closeout proof set covers first-paint frames, ready and unavailable boot states, native navigation, responsive and no-JavaScript tables, graph focus and layout lifecycles, and strict bundle validation. The date-stamped capture matrix records the closeout state; reproducible post-closeout boot-settlement captures live in the repository alongside provenance. Re-run the relevant browser proof when changing rendered theme, boot, navigation, or table behavior.

# See also

- [Why the live studio exists](/explanation/live_studio_design.md)
- [Architecture](/reference/architecture.md)
- [Current specification](/reference/spec.md)
- [Use the live studio](/tutorials/live_studio_basics.md)
- [Editorial Workbench hardening implementation plan](/plans/editorial-workbench-hardening.md)
