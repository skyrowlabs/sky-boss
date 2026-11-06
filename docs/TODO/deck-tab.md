---
title: "The deck as a tab in the canvas"
slug: deck-tab
category: surfaces
agent_value: 3
shelf_status: planned
priority: medium
updated: 2026-11-06
tags: [deck, canvas, surfaces, tmux]
summary: Embeds the whole running deck in the canvas as a nav tab, a second tmux client that follows the terminal's size. It is the first step of fusing the two surfaces.
created: 2026-11-06
key_files: [skyboss/canvas/server.py, skyboss/canvas/static/app.js, skyboss/canvas/static/api.js, skyboss/deck.py]
---

# The deck as a tab in the canvas

> **Status**: 🔴 Planned
> **Shelf-Status**: planned
> **Priority**: Medium — the first step of the long-term goal in [[open]] item 25
> **Updated**: 2026-11-06

## Problem

The canvas and the deck are two surfaces, and an operator working in one cannot see the other.
Jeston set the goal of fusing them on 2026-11-06 and ruled the first step: embed the whole deck as a
tab, keep tmux, and leave remote access out. [[fundamentals]] has the decision that allows it.

## Approach

The tab is a terminal in the page attached to the deck's running tmux session. tmux keeps doing all
the deck's work, so tab clicks, popups, the `+` and column moves arrive unchanged and nothing in the
deck is rebuilt. Closing the tab detaches and the agents keep running.

**Does not do:** rebuild any deck pane as web UI, start a deck, change `skyboss/deck.py`'s behaviour,
reach beyond loopback, or change colours. The theme makeover is a separate piece of work, and the
tab draws with today's roles until it lands.

**Transport.** Both directions stay behind the existing guard:

- Output is a second streaming `fetch` on its own route, carrying the pty's raw bytes. It cannot
  ride `/api/stream`, because that loop drains on a 0.5s tick and a terminal would lag by that much.
- Keys and resizes are guarded POSTs, sent one at a time so their order holds.
- No route takes an argv or a session name. The session comes from `deck.toml`, so the routes can
  reach the deck and nothing else.

**Sizing.** The browser attaches with `tmux attach -f ignore-size`, so the terminal client leads
while it is attached and the browser leads when it is alone. Measured on a plain session, see
[[open]] item 25. While it follows, the page draws at the window's size, not at its own.

**The act rule.** A terminal cannot confirm each keystroke, so this tab is a declared exception to
*an act is confirmed before it runs*. The page says so where the tab opens. Opening the tab is not
itself an act, since attaching changes nothing while `ignore-size` holds. This is a proposal, and
Phase 1 does not start until it is ruled.

## Phase 1 — the bridge

- [ ] Rule the act exception above (~operator)
- [ ] A pty holding `tmux attach -f ignore-size` for the deck's session, started with `child_env()`
      and with `TMUX` removed, so a canvas launched inside tmux still attaches
- [ ] `/api/deck/stream`, `/api/deck/keys` and `/api/deck/size`, each behind `canvas.authorised`
- [ ] The attach dies with its stream, and a page holds at most one
- [ ] Bounded reads, so a burst of output cannot hold the server's loop
- [ ] Tests: every new route refuses an unauthenticated request, and the attach argv is fixed

## Phase 2 — the tab

- [ ] Vendor xterm.js and the addons it needs, and add them to the served inventory
- [ ] A `deck` nav entry, drawn only while a deck is running, per *a nav entry may only name a
      screen that is there*
- [ ] Colours from the injected variables, with no hex in `static/`
- [ ] States that say what happened: no deck running, deck ended, stream lost and reattaching
- [ ] A hidden tab stops drawing, and scrollback is bounded, per *no single result may render
      unbounded*

## Phase 3 — following the terminal

- [ ] Read the window's size, and draw at it while a terminal client leads
- [ ] Letterbox or scale when the page is smaller or larger, chosen by looking at a render
- [ ] Take the page's own size when the browser is the only client

## Phase 4 — proof on a real deck

- [ ] Re-run the sizing measurement on a real deck with its nested tab session
- [ ] Keys in all three shells: Ctrl-Q, the deck's Alt keys, Shift+Enter, Ctrl-C
- [ ] Clipboard and wide characters in all three shells, WebKitGTK especially
- [ ] Real clicks on a tab, a popup, the `+` and a column move, through the page
- [ ] Measure typing delay under agent output, and record it
- [ ] Check the tab at more than one `--scale`
- [ ] Starting a deck from the tab (~deferred)

## Acceptance

- [ ] `./dev test unit` green, with the new routes in the unauthenticated-request test
- [ ] A terminal client's window size does not change while the browser attaches, types or leaves
- [ ] Closing the tab leaves every agent session running, read from `sb agents --scope deck`
- [ ] The deck's mouse bindings work through the page on a real deck, shown by a headless render
- [ ] Any key that cannot work in a shell is listed in [[command-deck]] by shell

## Dropped, and why

- **Output through `/api/stream`.** It was the first suggestion, and the loop's 0.5s tick rules it out.
- **A WebSocket.** It cannot carry the required header, so it would sit outside the guard, and it
  needs a dependency uvicorn lacks here. Reopen only if Phase 4 measures typing as too slow, and then
  with Origin and token checks at the handshake.
- **`ttyd` in an iframe.** It is the quickest demo, but it is a second port with no guard on it.
- **Rebuilding the panes first.** Ruled against: the whole deck embeds first.
- **Retiring tmux, and remote agents.** Ruled out of the initial plan.
