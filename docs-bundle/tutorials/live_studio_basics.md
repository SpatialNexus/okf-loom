---
type: Tutorial
title: Use the live studio
description: Bring up scripts/okf-loom serve, navigate the viewer (rendered, source, split, graph, search), post a comment, and watch it land in directives.jsonl.
resource: /tutorials/live_studio_basics.md
tags: [viewer, studio, serve, comments]
timestamp: "2026-06-29T00:00:00Z"
---

# Use the live studio

This tutorial brings up the OKF live studio in your browser and walks you
through every reading surface it offers, then shows you how a comment you
post becomes a directive the agent can act on.

The studio is the same viewer in every reading mode (rendered, source,
split, graph, search) plus a live-update layer and a comment channel.
You do not need an agent running to follow this tutorial — the studio
works on its own.

This tutorial assumes you have a small bundle to point at.
If you do not, finish [Author your first bundle](/tutorials/first_bundle.md)
first, or use the sample at `okf-loom/samples/demo_bundle`.

# What you will have at the end

By the end of this tutorial you will have:

- Served a bundle with `scripts/okf-loom serve`.
- Navigated the root index, a concept page, the source and split views,
  the graph view, and search.
- Changed Appearance settings, exercised native link navigation, and used the
  keyboard and mobile table affordances.
- Posted a comment from the studio.
- Found that comment on disk in `directives.jsonl`.

You will be able to serve the studio and direct work via comments.

# Step 1: Serve the bundle

Point `scripts/okf-loom serve` at your bundle and open it without auto-launching a
browser (so you can control the URL yourself):

```bash
scripts/okf-loom serve ~/my-first-bundle --no-open
```

The studio prints a URL like the one below and then runs in the
foreground of that terminal:

```text
serving bundle on http://127.0.0.1:8787/
```

By default the studio binds to `127.0.0.1` only — your loopback
interface — so only you can reach it.
Binding to the network requires an explicit `--public` flag and an
acknowledgement, which this tutorial does not need.

Leave that terminal running.
Open a second terminal for the rest of the steps, and open the URL in
your browser.

# Step 2: Open the root index

The studio's landing page is the bundle root index.

In your browser, visit:

```text
http://127.0.0.1:8787/
```

You should see a dashboard: the bundle name with stat chips (concepts,
types, links) and an **Explore the graph** button, the bundle
description, then every concept as a card grouped by type — each card
carries its type icon, a short description, outgoing/incoming link
counts (→ / ←), and tag chips.
While the studio runs you also get a **Recently changed** rail (the last
few edited concepts with relative times) and live comment-count chips on
cards that have open threads.

The route behind this page is `/`, documented in
[HTTP server routes](/reference/http_routes.md).

# Step 3: Open a concept page

Click any concept — for example **Orders**.

The page opens with a type-tinted header band: the type chip and icon, a
reading-time estimate, the description as a lede, alias subtitles, entity
chips, and any typed relations. Below the full-width rendered body you
get **Links to** and **Cited by** as connection cards (type icon +
directional relation chips). The left rail holds the Related list, a
Sections outline that highlights where you are as you scroll, and Quick
actions; hovering a heading reveals a ¶ deep-link anchor.

The route is the concept id with the `.md` stripped — for example:

```text
http://127.0.0.1:8787/tables/orders
```

Try editing the file on disk while the studio is running and saving it.
The page updates in place without a full reload — that is the live-update
layer at work.

Open **Appearance** in the top bar. Choose a family (**Swiss** or
**Technical**), a mode (**Auto**, **Light**, or **Dark**), and, if useful, the
contrast or border modifiers. Arrow keys move within an option group; Home and
End jump within it; Tab moves between groups; Enter or Space chooses an option;
Escape closes the menu and returns focus to its trigger. Auto follows your OS
light/dark preference while retaining the chosen family.

Now follow an ordinary concept link. The studio deliberately leaves it as a
native browser link: Back and Forward traverse document history, Enter activates
a focused link, and Ctrl/Cmd-click opens it in a new tab. The chosen Appearance
state is resolved before the destination paints.

# Step 4: Switch to source and split view

The concept page has a view-mode switcher with three options:

| Mode | What it shows |
|---|---|
| Rendered | The markdown rendered as HTML. |
| Source | The raw markdown file, exactly as it sits on disk. |
| Split | Rendered on one side, source on the other. |

Switch to **Source** to see the frontmatter and body verbatim — useful
when you want to copy the exact text of a link or a schema row.

Switch to **Split** to compare the rendered view against the source side
by side.
This is the mode most authors settle into during a session.

# Step 5: Open the graph view

The studio renders the whole bundle as a live force-directed graph
(fCoSE layout).

Visit:

```text
http://127.0.0.1:8787/__graph
```

Each node is a concept drawn with its type's icon; colour carries the
**detected themes** (community detection), and node size carries real
influence (PageRank) — so the picture answers questions instead of
restating the schema. On your first visit a three-step tour points out
the essentials. The controls live in a **lens bar pinned at the top of
the right-hand pane**; each lens answers one question and ranks its
answers in the pane below:

| Lens | The question it answers |
|---|---|
| **Map** | How does this knowledge fit together? |
| **Themes** | What are the main topic areas — and which barely touch? |
| **Flow** | What feeds into what? (dependency layers, left → right) |
| **Bridges** | Which concepts hold the areas together? |
| **Recent** | What is fresh, what is going stale? |
| **Focus** | What surrounds the selected concept? |

The collapsed **Advanced** disclosure holds the fine-tuning (spacing
sliders, type filter, relationship labels, and a colour-by-theme
toggle).

Ways to explore:

- **Hover** a node: its neighbourhood stays lit while the rest fades,
  and a preview card shows the description and link counts.
- **Click** a node: its full page renders in the right pane, beneath the
  pinned lens bar — diagrams, math, and code render there just like on
  the wiki pages.
- **Shift-click** a second node to trace the shortest path between the
  two; the chain lights up and the status line reads it out.
- **Double-click** (or press Enter) to open the concept's wiki page.
- **Keyboard**: `f` fits the view, `/` focuses search, arrows walk the
  selection along edges, Esc clears.
- **Legend chips** (bottom-left) toggle a type's visibility; alt-click
  solos it.

Concepts with no links sit apart with a dashed "not yet linked" outline —
this view is still the fastest way to spot orphans and clusters that
ought to be connected. If a file changes on disk while you watch, the
canvas updates in place and a "Graph updated" chip offers a re-layout.

The first-visit tour is a modal keyboard surface. Focus stays inside it, and
Escape closes only the topmost open surface. If you open Appearance before the
graph finishes loading, the tour waits rather than stealing focus; closing
Appearance allows the tour to begin once. If Appearance is opened over an active
tour, the first Escape returns focus to the tour and the second dismisses the
tour. Dismissing or finishing it records completion so it does not reopen.

On a narrow viewport the node index appears before the canvas with an
**Explore map** action. Activate it to move keyboard focus to the graph and fit
the map; reduced-motion preferences are respected. Large bundles may initially
show a reduced level of detail. Selecting a hidden item from the node index
reveals and lays it out; **Show all** reveals the complete overlap-free grid.

If a concept contains a wide table, narrow the browser window. The table stays
inside the article rather than widening the whole page. With JavaScript, Tab
reaches the labelled horizontal-scroll region only when it actually overflows;
use Left/Right to reach off-screen columns and follow the visible edge cue. A
table that fits adds no extra tab stop. With JavaScript disabled, Tab reaches the
bare table itself and the same arrow-key scrolling remains available.

# Step 6: Search

The studio has a built-in search bar.

Type a word that appears in your bundle — for example `customer` — and
press Enter.
The results page lists matching concepts ranked by relevance, with the
matched snippet shown for each.

Behind the scenes the route is:

```text
http://127.0.0.1:8787/__search?q=customer
```

Search runs dependency-free out of the box.
The default mode is lexical; other modes (semantic, hybrid, tag, entity,
relation) are described in [Search modes](/reference/search_modes.md).

# Step 7: Post a comment

The studio's right-hand panel is the **Comments** panel — your primary
way to direct work without leaving the browser. (The **Commands** button
in the studio bar — shortcut `Ctrl+K`, `⌘K` on a Mac — opens a palette
that jumps to any page or panel.)

Open the panel and type a short directive, for example:

```text
Add a link from orders to the checkout service.
```

Post it.
The comment appears in the panel as an open thread.

You have just written the only kind of studio input a human makes: a
comment.
Everything else (edits, links, entities) is authored by the agent
through the mutator commands, driven by the comments you post.

# Step 8: Watch the comment land in directives.jsonl

Every comment you post is appended to a JSON Lines file inside the
bundle's session directory.

From your second terminal, list the open directives:

```bash
scripts/okf-loom comment-list ~/my-first-bundle --state open
```

You should see the comment you just posted, with an id, a concept anchor,
a state of `open`, and the body you typed.

The same record lives on disk:

```bash
cat ~/my-first-bundle/.okf-loom/session/directives.jsonl
```

Each line is one comment object.
This file is the contract between the studio (where you write comments)
and the agent loop (which consumes them).

The comment states and the rules for moving between them are documented
in [Comment lifecycle and archive rules](/reference/comment_lifecycle.md).

# Step 9: Stop the studio

When you are done, return to the first terminal and stop the server with
`Ctrl-C`.

The session directory (`.okf-loom/session/`) stays on disk, so the comments
you posted are preserved.
The next `scripts/okf-loom serve` picks them back up.

# Where to go next

You can now serve the studio and direct work via comments.

The comments you posted are consumed by the agent loop — the canonical
shape is `scripts/okf-loom wait` → claim → write → resolve:

* [Direct the agent loop](/tutorials/author_with_agent.md) — drive the comment-to-resolve loop end to end.

When threads start to pile up, you will want to triage them:

* [Archive and resolve comment threads](/how-to/archive_threads.md) — the archive and resolution rules.

The machinery behind every route above is documented in:

* [HTTP server routes](/reference/http_routes.md) — every URL the studio serves.
* [CLI command reference](/reference/cli.md) — `scripts/okf-loom serve`, `scripts/okf-loom comment-list`, and friends.

For the design rationale behind the studio's comment-driven model, see
[Why the live studio exists](/explanation/live_studio_design.md).

Return to [Tutorials](/tutorials/index.md).
