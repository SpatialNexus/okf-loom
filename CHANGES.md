# Changes

This file records user-visible changes. No release version or date has been
assigned to the current work.

## Unreleased

### Changed

- Hardened the Editorial Workbench across live, static, and single-file views.
  Theme resolution now happens before first paint and remains stable across
  native link navigation; browser Back/Forward, keyboard activation, and
  modified clicks retain native behaviour.
- Made wide tables safe on mobile and without JavaScript. Tables remain within
  the document, expose a labelled keyboard-focusable horizontal scroll area
  when needed, and show a visible focus indicator.
- Improved graph readability and interaction stability. Labels remain
  available after search, lens, and focus changes, while the first-visit tour
  owns focus as an accessible dialog, defers to an open Appearance menu, and
  restores focus when dismissed.
- `link-add` keeps default links out of citation blocks, preserving valid
  citation structure while still adding the requested relationship.

### Fixed

- Settled studio startup into truthful terminal states: successful boots do
  not flash the unavailable banner, while blocked scripts and genuine boot
  failures reveal a single fallback. Desktop rail and mobile page geometry no
  longer shift during startup or native navigation.
- **Test/proof reliability only (`6627614`):** added diagnostic, test-only
  in-page timing and layout node-count metadata, then used it to stabilize the
  browser level-of-detail proof around the graph-owned init-to-frame interval.
  The metadata does not change layout behavior or ownership.
- **Test reliability only (`44b2f70`):** made the startup-timeout cleanup test patch the
  timeout path deterministically; this does not change user-facing runtime
  behaviour.

### Added

- Added committed first-paint and mobile-table proof with revision, capture
  environment, command, and scenario-to-test provenance. Existing README media
  and the final Workbench matrix are explicitly retained as historical
  pre-closeout evidence rather than relabelled as current captures.
