---
title: "The deck: a tmux command center for agent sessions"
slug: command-deck
priority: medium
category: surfaces
agent_value: 3
shelf_status: in-progress
updated: 2026-11-06
tags: [agents, act, tmux, surfaces]
summary: Adds `sb deck`, a tmux session holding one window per agent, plus a queue of sessions waiting on the operator, read by both surfaces. It is the first surface built to act, and the long-term goal is that it fuses with the canvas.
---

# The deck: a tmux command center for agent sessions

> **Status**: 🟡 In progress
> **Priority**: Medium. Round 5: the right column — a DECISIONS pane, a pane chooser, collapsing, the footer, and TODOS by recency.
> **Updated**: 2026-11-06

## Problem

Several Claude Code sessions run at once across the sibling repos. [[agent-sessions]] can say which
ones are live, but not which one is **waiting on the operator**, and it gives no way to get to that
one. Today the operator finds a blocked agent by walking terminals. An agent waiting on a
permission prompt costs wall-clock time, and nothing reports that it is waiting.

## Approach

The skyrow-workspace session proposed this on 2026-11-04 and relayed an owner ruling with it. Its
four parts are ruled one at a time below.

**The ruling, relayed and then confirmed.** *"`sb run` is the single top-level command that acts"*
is dropped. Observe versus act is now a property of the **surface**: `sb ui` stays observe-only, and
its per-command `acts` bit is unchanged; the deck is an act surface. Jeston confirmed it in this repo's session
on 2026-11-04, and `CLAUDE.md` § Scope now says it. Note that the
per-command split the rule protected survives the ruling: the canvas still reads `acts` to refuse a
cadence, and that does not depend on which top-level commands may act.

### The name: `sb deck`

It is short and names the thing rather than the mechanism: `sb tmux` would be the wrapper this repo
refuses. It has no collision on this machine (checked 2026-11-04) and none among sibling CLIs. It is
not `fleet` (breeze.brain's word) and not `tower` (the canvas's plan screens). It is Jeston's to
overrule.

### Scope: what the deck does and does not do

- **It acts, and says so.** `sb deck` creates or attaches one tmux session. `sb deck open <project>`
  starts the real `claude` in a new window, with the project's `cwd` taken from `projects.toml`.
  Every pane is the real `claude`, so nothing in Claude Code is lost.
- **It never types into an agent.** No `send-keys` into a `claude` pane, ever. Answering a prompt is
  the operator's, and a deck that could answer one would be a second permission path. Jumping to a
  window is `select-window`; it moves the operator, not the agent.
- **It never edits the operator's tmux config.** The options the workspace named have different
  scopes. `window-size latest` and `allow-passthrough on` are both window options in tmux 3.8, so
  the deck sets them on each of its own windows. `extended-keys` is a **server** option, so the deck
  reports it when it is off and does not set it. That is the KWin rule again: a desktop belongs to
  whoever runs it.
- **Names and paths come from `projects.toml`**, never from tracked code (the publication rule).
  The pinned workspace pane is a declared entry, not a special case in code.

### The waiting queue: the hook writes, and sky.boss owns the writer, not the install

- **Measured 2026-11-04: the registry is the source, and no hook is needed.** A session held at a
  permission prompt writes `status: "waiting"` to `~/.claude/sessions/<pid>.json`, the file
  [[agent-sessions]] already parses; it returns to `idle` when its turn ends. So the queue is a
  read of that file. See Phase 1 for the full measurement.
- **The one gap the registry leaves is the trust prompt.** A session stopped at Claude Code's
  "do you trust this folder" dialog has only a `<pid>.*.key` file and no `<pid>.json`, and no hook
  fires there either, because hooks wait for trust. The deck knows which `claude` it started in
  each window, so a window whose process has no record is shown as **unregistered**, never left
  out. That is the same *could not see* as [[agent-sessions]]' third liveness answer.
- **If a hook is ever needed, the writer is sky.boss code.** It is a hidden command that reads the
  hook's stdin JSON and appends one normalised line. One author for the line format, with tests,
  and the real seam is where it should be: Claude Code's hook payload is the producer, and it
  changes between versions.
- **The install is user config, written by the operator.** sky.boss prints the `settings.json`
  fragment and never writes `~/.claude/`. Same rule as the KWin rule and `projects.toml`.
- **The line is a seam.** Once it settles, the contract goes to the workspace's `strategy/seams/`,
  which the workspace has offered to keep. Where it lives under the state root is decided there,
  not here.
- **A null queue must say whether it looked.** An empty queue with the hook uninstalled is the same
  bytes as an empty queue with nobody waiting. The deck shows whether any event has *ever* arrived.

### Task lists: deferred, with no source to read

There is no `~/.claude/todos/` or `~/.claude/tasks/` on this machine (checked 2026-11-04 on the
Claude Code version running here). Nothing gets built on a guessed path. This reopens when a source
exists and has been read.

### The canvas gets the queue read-only

The queue is `sb deck queue`, an observe returning an envelope, so the canvas can pin it like any
read. `sb agents` already shows the same `waiting` word there today. Jumping to a window stays on the
deck for now. The reason given here until 2026-11-06, that the canvas is observe-only, no longer
stands: see the Notes entry of that date.

## Phase 1: measure

- [x] Held a probe session at a permission prompt (Claude Code 2.1.318), with hooks supplied by a
      one-off `--settings` file so no user config changed. The registry read `waiting` at the
      prompt and `idle` after the turn. At the trust dialog there was no `<pid>.json` at all.
- [x] Hook payloads on 2.1.318. Both carry `session_id`, `transcript_path`, `cwd`,
      `hook_event_name` and `prompt_id`. `Notification` adds `message` and `notification_type`
      (`permission_prompt`, then `idle_prompt` after the turn). `Stop` adds `permission_mode`,
      `effort`, `stop_hook_active`, `last_assistant_message`, `background_tasks` and
      `session_crons`. Not used: the registry suffices.
- [x] Jeston confirmed the scope ruling directly on 2026-11-04, and `CLAUDE.md` § Scope is rewritten.

## Phase 2: the deck

Config is `$SB_HOME/deck.toml`, operator-written and absent by default. It holds `session` (the
tmux session name, default `sb`), `pin` (an agent name), and `[agent.<name>]` tables with `cwd`
and an optional `args` list for `claude`. A name not under `[agent.*]` falls back to a
`projects.toml` project's `cwd`. Every tmux call goes through one runner function, so the suite
never needs a tmux binary.

- [x] `sb deck`: create the session if absent (with the pinned agent in window 0), set
      `window-size latest` and `allow-passthrough on` on each deck window (both are window
      options in tmux 3.8), then attach
      (`switch-client` inside tmux, `exec tmux attach` outside). Acts.
- [x] `sb deck open <name>`: a window named `<name>` running `claude` in that agent's `cwd`, or a
      `select-window` if it already exists. Acts.
- [x] `extended-keys` read from the server and reported on stderr when it is off; never set.
- [x] `acts` asserted with `sb_acts` on every subcommand, and a test that each one chose
      ([[jobs]] round 1).
- [x] No subcommand calls `send-keys`, and a test greps the module for it.

## Phase 3: the queue

- [x] `sb deck queue`: an observe. One row per deck window: window name, the `claude` pid running
      in it, and that pid's registry `status`, or `unregistered` when there is no record. Sessions
      reading `waiting` sort first. The word is the provider's, compared literally, so sky.boss
      orders and does not judge. Live sessions outside the deck are listed after, so none is hidden.
- [x] `sb deck jump <name>`: `select-window`. Acts.
- [x] `sb deck` puts a queue pane in the pinned window (`sb deck queue` on a refresh).

## Phase 4 (round 2): the controller layout

Jeston's own description, from the skyrow-workspace session on 2026-11-04: the workspace agent at
about half the screen, *"a sub-tabbed representation of the different project specific agents that
I can choose to activate"*, and tools for *"human actions that are needed"*, task lists, and the
messages agents exchange. He chose the three-column layout below, asked for the stacked one as well
(switchable), and asked for panes resizable by dragging.

```
columns (default)                                  stack
+--------------+-[jam]-[mind]--+-----------+       +-----------------------+-----------+
| WORKSPACE    | project agent | NEEDS YOU |       | WORKSPACE claude      | NEEDS YOU |
| claude       | (active tab)  |-----------|       +-[jam]-[mind]----------+-----------|
|              |               | MESSAGES  |       | project agent         | MESSAGES  |
+--------------+---------------+-----------+       +-----------------------+-----------+
```

- [x] **Window 0 is the controller.** Left: the pinned workspace agent (about 45% wide). Middle:
      one pane attached to an inner tmux session, `<session>-agents`. Its windows are the project
      agents, and its status bar is the tab row. Right column (about 25%): `sb deck queue` (NEEDS
      YOU) over `sb deck messages`. Both refresh on a cadence (constants, not keys).
- [x] **Tabs only for agents you activate.** `sb deck open <name>` adds an inner window running
      `claude` (or selects it), and `sb deck jump <name>` selects it. Clicking a tab works through
      tmux's mouse support.
- [x] **`sb deck layout columns|stack`** switches window 0 between the two shapes by moving panes.
      It never restarts a pane, so every `claude` keeps its process (asserted: no `kill-pane`,
      `respawn-pane` or `kill-window` in the switch).
- [x] **Resizable by dragging:** `mouse on` set on both deck sessions (a session option, so the
      operator's config is untouched).
- [x] **`sb deck messages`**, an observe with `--refresh`/`--ticks`. One row per message exchanged
      between agent sessions: time, sender → receiver, and the body's first line. Newest at the
      bottom, the last 50, de-duplicated by `msg_id`. Source, measured on Claude Code 2.1.318: each
      live session's transcript (`~/.claude/projects/<slug of cwd>/<sessionId>.jsonl`) records every
      message it **received** as a `user` entry whose `origin.kind` is `peer`, carrying `name`,
      `msg_id` and `body`. A transcript that cannot be found or read is counted in a warning, never
      skipped silently. Message bodies are drawn on the operator's terminal and written nowhere.
- [x] `sb deck queue` finds deck agents in the inner session's windows.
- [x] Tests on `FakeTmux` and on synthetic transcripts: both layouts' commands, the switch moving
      panes without restarting any, `mouse on` on both sessions, the messages parse (peer entries
      only, dedupe, first line, unreadable transcript counted), and `--ticks` parity with `sb data`.

**Task lists stay deferred.** Recent transcripts on this version carry no to-do or task-creation
tool calls, and `~/.claude/todos/` and `~/.claude/tasks/` do not exist. So window 0 has no TASKS pane:
a pane with nothing behind it would be the nav rule broken in a smaller font.

## Phase 5 (round 3): profiles, live tabs, scope, fit and theme

Ruled by Jeston on 2026-11-04, after using the round 2 controller. Three answers: the workspace
lives in the tabs, so there is no fixed left pane; a tab shows the live `claude`, so its prompts are
answered there; a name repeated in a profile is one tab and a warning.

```
columns (default)                          stack
+-[workspace]-[stash]-[mind]-+-----------+  +-[workspace]-[stash]-[mind]-[sky]-+
| the selected tab's claude  | NEEDS YOU |  | the selected tab's claude        |
|                            |-----------|  +----------------+-----------------+
|                            | MESSAGES  |  | NEEDS YOU      | MESSAGES        |
+----------------------------+-----------+  +----------------+-----------------+
```

- [x] **Profiles in `deck.toml`.** A `[profile.<name>]` table carries `primary` (an agent name) and
      `tabs` (agent names, in order). `sb deck --profile <name>` opens the primary as the first tab
      and every listed tab after it, each a live `claude`. On an existing deck it opens only the
      missing tabs. A name resolves exactly as `open` resolves it (`[agent.*]`, then a
      `projects.toml` `cwd`). A name repeated in a profile is one tab and a warning; an unresolvable
      name is a warning and no tab. A profile key outside `primary` and `tabs` is named as a problem.
- [x] **No fixed left pane.** Window 0 is the tab area plus the tools in both layouts. The `pin`
      key keeps working and means the same as a profile with a primary and no tabs.
- [x] **Tabs say what each agent is doing.** Each tab is drawn with the registry's word for its
      session: `busy` as working, `waiting` as needs you, `idle` as quiet, and no record as
      unregistered. The state reaches tmux within a few seconds. Whatever writes it acts and says
      so; it keeps no process per tab and spawns no Python per tab per tick. The order is the
      profile's: primary first.
- [x] **`--scope deck|outside|all`** on `sb agents` and on `sb deck queue`, default `all`. `deck`
      means sessions running in a deck pane, and `outside` means every other live session.
- [x] **Tables fill their pane and never wrap.** In the deck's tool panes, columns widen to use the
      room the pane has and shrink with ellipsis when it has none. A row is always one line, at every
      width, re-measured each render because panes are dragged.
- [x] **A sky.boss theme for the deck's own bars.** The tab row and the outer status bar take their
      colours from `skyboss/theme.py`, replacing tmux's default green, and are set as options on the
      deck's own sessions only. Nothing outside `theme.py` names a colour, so tmux style strings are
      generated there.
- [x] Tests on `FakeTmux`: profile parsing and its problems, opening order and idempotence, the
      state marks, the scope filter, the no-wrap fit at several widths, and the theme options set on
      the deck's sessions only. A smoke test on a throwaway socket covers the clicks and the marks.

## Phase 6 (round 4): exit, scrolling, agent colours, keys

Ruled by Jeston on 2026-11-04, after the first real run of round 3 (*"it works"*). He asked for a
double Ctrl-C exit and was shown the conflict: Ctrl-C is claude's own (one press interrupts a turn,
two exit it), so binding it would put every press through the deck. He chose Ctrl-Q plus a
clickable ✕ instead, kept agent colours on the brand-step rule, and asked for four shortcuts.

- [x] **Bindings live in the deck's own key table.** Both deck sessions set `key-table` to a table
      only they use, so the operator's other tmux sessions see no new binding. Measured before
      relying on it: the prefix still works there, an unbound key still reaches the pane, and a
      session outside the deck is unaffected.
- [x] **Exit.** Ctrl-Q, or clicking a ✕ at the right of the status bar, opens a tmux confirm that
      names what ends ("end the deck and its N agent sessions?"). Confirming runs `sb deck exit`,
      an act that stops the marks loop and kills both deck sessions and nothing else. `kill-session`
      is allowed in that command only; the layout switch still never kills anything. Ctrl-C is
      never bound.
- [x] **Messages scroll.** The messages pane takes an offset: arrows, PgUp/PgDn and the wheel when it
      is focused, plus a deck shortcut when it is not. The band says how far back it is
      (`↑ 12 older shown`, or `newest`) and returns to newest on a key.
- [x] **Each agent has its own colour.** The colour is a step along the brand, by tab order with the
      primary first (CLAUDE.md: never a new hue, never a borrowed role), and is assigned once in
      `theme.py` so the tab row and the messages pane cannot disagree. A tab's label is drawn in its
      agent's colour, and in MESSAGES each name in `sender → receiver` is drawn in that agent's
      colour. A sender outside the deck stays the plain text colour. Each step clears the CLI
      contrast floor, checked by a test.
- [x] **Shortcuts, shown in the status bar.** Hide or show outside agents in NEEDS YOU and MESSAGES
      (a toggle stored as an option on the deck session, which the panes read each frame); switch
      layout; next and previous tab; and scroll messages. The keys are chosen to collide with none
      of Claude Code's own keybindings or tmux's defaults; the choice and its check are recorded
      in Notes.
- [x] Tests on `FakeTmux`: the key table is set on the deck's sessions only and nothing is bound
      globally; Ctrl-C is never bound; `exit` kills exactly the two deck sessions; the scroll
      offset and its band; colour assignment by tab order, shared by both renderers, above the
      floor; the outside toggle read by both panes. A smoke test on a throwaway socket covers the
      popup, the ✕ click, the keys and the scroll.

## Phase 7 (round 5): the right column

Requested by Jeston on 2026-11-05: items relayed by the skyrow-workspace session, and the tab boxes,
asked for directly.

- [x] **The outside count moves to the footer band.** NEEDS YOU and MESSAGES say
      `N outside hidden · M-h shows` in the bottom band, muted, with no ⚠️ and no warn colour: it
      is information, not a fault. The count stays, because a hidden row must not read as no row. `--json` is
      unchanged, since hiding is the pane's view state and never reaches the envelope.
- [x] **TODOS orders by recency, still grouped by agent.** Groups sort by their list's `updated`,
      newest first, and every add, done and rm moves it, so a new task lifts that agent's list
      to the top. Items keep their numbers. An agent with no list yet keeps the tab order below
      every list.
- [x] **Each tab is a box, and its ground says what the agent is doing.** Added by Jeston directly
      on 2026-11-05. The tab bar is three rows (`status 3`, one `status-format[i]` each), and a
      tab's edges are its name with every character replaced, so a box always fits its name. The
      words `working`, `needs you` and `quiet` are gone. A busy tab is lit with `WORKING_GROUND`,
      a tint of the brand made in `theme.py`. A waiting tab is the warn block, and anything else is
      plain. The current tab's edge is drawn in its agent's hue. Every row carries the window's
      `range`, so a click anywhere on a box selects the tab.
- [x] **A DECISIONS pane**, grouped by agent, the same recency order. Agents declare their own
      decisions with `sb deck decide add` and `sb deck decide done <n> "<ruling>"`; nothing is
      inferred (ruled 2026-11-05).
- [x] **A chooser for which right-column panes show, and in what order.** A popup in the deck's key
      table. The choice is machine state under `$SB_STATE`, because sky.boss never writes
      `deck.toml`. Applying it moves and resizes panes only.
- [x] **Each pane collapses to a thin row** drawing one consolidated line. In the stack layout it
      is a thin column with the same line shortened to fit (ruled 2026-11-05).
- [x] **The bar's label is not cut.** tmux's default `status-left-length` of 10 drew
      `sky.boo…`; each bar now sets it to its label's visible width.
- [x] **NEEDS YOU sorts by activity**: needs you, busy, shell, idle, unregistered, deck rows before
      outside ones. The pane draws the deck's word (`needs you` for `waiting`) in a `state` column;
      the provider's word stays in `status`. The tab row keeps its fixed order (Jeston, 2026-11-05).
- [x] **A window name in NEEDS YOU takes its tab's hue**, as MESSAGES and TODOS already draw an agent.
- [x] **`sb deck reload`** re-dresses both sessions and restarts each tool pane through the
      hide/show path, killing nothing.
- [x] Tests on `FakeTmux` and the pure renderers, plus a smoke on a throwaway socket.

## Phase 8 (round 6): the mark, and one countdown

Ruled by Jeston on 2026-11-05.

- [x] **The SL mark at the top left of the tab bar.** The favicon (`skyrowlabs.com/favicon.svg`,
      a brand-blue L with a white block S in its corner) redrawn in half-block glyphs across the
      tab bar's three rows, the L's base running the full width under the S as in the favicon,
      then `skyrow.labs` in the brand colour, then the `tabs` label. A status bar cannot draw an
      SVG, so this is a redraw, made in `theme.py` like every other colour.
- [x] **One countdown in the footer, for one shared cadence.** Every tool pane refreshes on the same
      interval, and the deck's footer shows the single countdown to it; each pane's own countdown
      goes. Jeston chose a shared cadence over showing the soonest of several.

## Phase 9 (round 7): the bar's left end, pane headers, clearing todos, reading a message

Asked by Jeston on 2026-11-05, relayed by the workspace; he answered the two open questions himself.

- [x] **The mark at half its size, padded.** Four cells wide rather than eight, two blank cells each
      side. It still spans the bar's three rows: the S needs five pixel rows and the L's base a
      sixth, so there is no room above or below it for vertical padding.
- [x] **The wordmark in two colours.** `skyrow` white and `.labs` brand blue, both bold.
- [x] **A separator, and no `tabs` label.** A `│` on all three rows between the wordmark and the first tab.
- [x] **A ground on each right-column pane's label row**, so a reader sees where each table starts.
- [x] **M-x clears the done todos, every agent's** (Jeston's choice over only the focused tab's).
      `sb deck todo clear`; the key says how many lists it cleared, 0 included.
- [x] **Clicking a message opens it whole in a popup**, with a header of from, to and when it was
      sent (Jeston's choice of fields), the body drawn as Markdown, q to close.

## Phase 10 (round 8): a centred mark, a smaller popup, a scrolling tab row

Asked by Jeston on 2026-11-05, typed in skeletor's tab and relayed.

- [x] **The mark centred in the bar and not stretched, the L as thick as the S.** Sextant glyphs,
      2×3 pixels a cell, so a pixel is near square. Every stroke is one pixel, and a blank pixel
      row above and below centres it.
- [x] **A smaller message popup**: 60% by 50% of the client, from 80% by 80%.
- [x] **The tab row scrolls when it overflows, with a thin scrollbar under it shown only then.**
      tmux keeps the current tab in view, and a fourth bar row draws where the view sits.
- [x] **A lighter ground on the pane label rows**: the brand at 28% over the void, from 20%.

## Phase 11 (round 9): each tab's console in its agent's colour

Asked by Jeston on 2026-11-05, relayed by the workspace. He chose a deck setting over per-repo
settings files, and chose that `sb deck` writes the theme files itself.

- [x] **`themes = true` in `deck.toml`** gives each tab's Claude Code a custom theme whose accent
      (`claude`, the spinner and assistant label, and `promptBorder`, the input box) is that
      agent's deck hue. So the console matches its tab, NEEDS YOU and MESSAGES.
- [x] **`theme_base`** names the preset under it. Absent, it is the operator's own `theme` when that
      is a preset, else `dark`.
- [x] **Only deck tabs change.** A tab selects `custom:sb-<agent>` with `--settings` for its own
      session; Claude Code opened anywhere else keeps the operator's theme.

```toml
themes = true             # optional; off unless set
theme_base = "dark-ansi"  # optional; dark, light, dark-daltonized, light-daltonized, dark-ansi, light-ansi
```

## Phase 12 (round 10): M-x clears decisions too, and an emptied list leaves the pane

Reported by Jeston on 2026-11-05: skyrow-workspace's items stayed after a clear. They were its five
decided items in DECISIONS, which M-x did not touch. He ruled on both fixes.

- [x] **M-x clears decided items as well as done todos** (`sb deck decide clear`), in every agent's list.
- [x] **A list emptied by a clear drops out of the pane** instead of keeping its heading over
      "nothing open". An agent's own `todo list` still says "nothing open".

## Phase 13 (round 12): the footer carries the names

- [x] **The wordmark moves to the footer's left corner.** The tab row keeps the mark and its separator.
- [x] **A `│` between the wordmark and the deck's name.**
- [x] **The deck's name is its profile.** `sky.boss deck` is what a deck from no declared profile says.
- [x] **No window list in the footer.** The outer session has one window, so `0:deck*` said nothing.

## Phase 14 (round 13): colours by default, decisions by click, a grid

- [x] **Colours are the standard.** Console themes are on unless `themes = false`, and the controller's
  active border takes the current tab's colour. `colour = "<hue>"` on an `[agent.NAME]` overrides.
- [x] **A clicked decision opens a popup** of its `--option` choices, or a typed ruling.
- [x] **The ruling reaches the agent**, typed into its tab once idle, by the marks loop.
- [x] **`grid`, a third layout**: the four panes two by two. M-l cycles it, and so does ▦ in the footer.
- [x] **No deck job exits non-zero**, as tmux prints that over the current pane.
- [x] **TODOS draws only agents with a list.**

## Phase 15 (round 14): padding, and what a session has running

- [x] **The tool panes are padded**: a cell each side and a row above. tmux has no pane padding, so the
  Claude tabs stay edge to edge, as Jeston wanted. A folded pane stays one full line.
- [x] **NEEDS YOU counts each session's sub-agents and shells** in `bg`, and a click unfolds them.

## Phase 16 (round 15): free columns for the right-side panes

Requested by Jeston on 2026-11-06, relayed by skyrow-workspace: any number of panes per column, such
as MESSAGES alone in one column and the other three stacked in the other, and switchable. It builds on
`sb deck layout grid`.

- [x] **An arrangement is declared** as a profile setting in `deck.toml`, plus a command to change it
  live (ruled 2026-11-06).
- [x] **"Switchable" means swapping a pane across columns,** not cycling saved arrangements (ruled
  2026-11-06).
- [x] **A swap is reached by mouse:** click a pane's title bar, then click any pane in the column to
  send it to (ruled 2026-11-06). The picked-up pane says `moving`, the others `click to send here`
  at their next refresh, and a click on the picked-up pane puts it down.
- [x] **`grid` becomes the free layout:** same spot in M-l, starts two and two, and panes can move
  (ruled 2026-11-06).
- [x] **Built:** `columns = [[...], [...]]` on a profile, `sb deck column move PANE N`, and the saved
  columns in `column.json`, which win over the profile's. Panes land ahead of the one clicked.
- [x] **A column never empties by mouse:** a pane alone in its column swaps with the pane clicked
  instead, or a click could leave no column to send a pane back to.
- [x] **Outside the grid a title click says so,** as `M-l to grid to move`, rather than doing nothing.
- **Does not do:** reorder within a column by click. The chooser's J/K sets the starting order only
  until a pane has been moved.

## Phase 17 (round 16): add tabs from the bar, a terminal tab, and where they can start

Requested by Jeston on 2026-11-06: a `+` in the tab row that adds an agent, prompted, and that joins
the profile; a tab that is a plain terminal rather than a `claude`, listed after the agents; and a
setup naming the repos and folders an agent can start from. **Bring him the shape before building.**

**Today.** `sb deck open NAME` is the only way to add a tab, and NAME must already be an `[agent.NAME]`
or a `projects.toml` project with a `cwd`. Every tab is a `claude`: `Agent.argv`, `start()` and
`Agent.launch()` assume it. The tab row is one tmux window list, so it draws nothing that is not a
window. Nothing writes `deck.toml`, and that is a stated rule.

**Ruled by Jeston on 2026-11-06, in DECISIONS:**

- [x] **The `+` writes `deck.toml`,** as `tools.toml` already works: one small in-place edit, with a
  backup first. This reverses "sky.boss never writes `deck.toml`", stated in Phase 7, and
  `CLAUDE.md`'s table has to change with it.
- [x] **The prompt asks** for a folder, a name (filled in from the folder), a role (optional), and "add
  to this profile" or "this deck only".
- [x] **The start list is** `roots = ["~/src"]` in `deck.toml`, where every directory under a root is
  offered, plus the declared agents and `projects.toml`'s `cwd`s. A root over a whole workspace also
  offers worktrees and loose folders.
- [x] **The terminal is offered by the `+`,** a profile can declare one to open, and a deck can hold
  several.
- [x] **A terminal on restore** reopens in its saved directory with a fresh shell. A shell's history
  and running jobs are not kept.

**Built:**

- [x] **The start list.** `roots` in `deck.toml`, and `sb deck places`, an observe saying where each
  entry came from. A folder that cannot be a tab says why.
- [x] **The terminal tab.** `sb deck terminal`, a `terminal` pane role running the operator's shell,
  named `term`, `term-2` and on. It stays last by `swap-window` and joins no roster. `terminals` on a
  profile opens some at the start.
- [x] **The `+` cell and prompt.** A box after the window list, a click or M-n opening `sb deck plus` in a
  popup. `sb deck add` does the same by hand.
- [x] **The write to the profile.** `skyboss/deckplus.py` splices the file, parses the result to prove
  it changed only what it should, and backs up through `tools.keep_copy`. A list it cannot read
  safely, such as one ending on a comment, is refused.

**Measured on a throwaway deck, real clicks through a viewer client:**

- [x] **The `+` opens the popup on a real click,** and a tab click selects. Round 5 left that unmeasured.
  Overflow was not smoked: the list scrolls within the room left by `ADD_WIDTH`.
- [x] **A terminal's environment** holds no `PYTHON*` variable.
- [x] **A "this deck only" agent** comes back from `Tab.cwd` through `restored()`. Unit tested only,
  because a stand-in `claude` registers no session to save.
- [x] **A dotted folder name as a tab.** Tmux targets here are window ids, so a `.` in the name is safe.

**Does not do:** edit or remove an agent or profile from the bar, change `projects.toml`, or type into
a terminal tab. Running agents are not told about a new tab, as with `sb deck open` today.

## Phase 18 (round 18): every ask of the operator in one queue

Planned, nothing built. Jeston asked whether the deck needs a commit, push and actions window, or
whether DECISIONS can hold it all. The workspace counted how agents ask over three days, across 11
repos, in `deck-requests/operator-asks-20261106.md` in its own state directory, and recommended one
queue. Its counts are its own, and its prose counts are an upper bound.

**The problem.** Of ten ways agents ask, only `sb deck decide` has a state. The rest are text in a
tab or a file. A question at the end of a prose turn is the largest channel, at up to 540, and
`decide` the smallest but one, at about 37. Worse, a ruling can close while its work stays open:
"Jeston pushes it by hand" closed a decision and left a push nothing tracks.

**The shape: one queue, no second window.** A separate window would split the same attention and
give the operator two places to check. HUMAN DECISIONS stays the one place, and each row has a kind.

| Kind | What it is | How it closes |
|---|---|---|
| `choice` | Today's decision: the operator picks and the agent acts | A ruling, told in the tab |
| `action` | An exact command only the operator may run | Observed, or marked done by a click |
| `asked` | A tab blocked on a prompt, mirrored in by a hook | When the tab answers or moves on |
| `notice` | Worth knowing, with nothing to do | A click dismisses it |
| *held* | Computed and never written by an agent | When the state stops being true |

Rows sort `choice`, `action`, `asked`, then `notice`, so a notice can never push a choice out of
view. Held state is one folded line at the foot, `HELD 4`, which a click unfolds, for the same reason.

**What exists to build on, read from the code:**

- A ruling typed for a busy tab waits safely. `tell_rulings` types only into an idle tab that is not
  scrolled, `untold` stays set until then, and `clear` keeps an untold item. Action rows reuse this
  to tell their agent the work happened, so it needs nothing new. An operator part-way through
  typing in that idle tab is the one gap, and it exists today.
- A click is first-hand, and an agent cannot forge one: `sb deck decide rule` refuses inside a tab.
  The action row's click needs the same guard.
- Hooks need no write to `~/.claude`. Every tab already loads `--plugin-dir`, so hooks shipped in
  `plugin/` reach deck tabs only, and the rule that the operator owns the install still holds.
- The registry says `waiting` and nothing about why, on 2.1.319. Saying what a tab waits on needs a
  hook's `message`.

**Does not do:** parse a prompt to judge it, answer a prompt from the pane, or let an agent close an
action on its own word when the state can be observed. The largest channel stays a matter of
discipline unless the question below rules otherwise.

### Questions for Jeston

- [ ] **May a click run an action, or only show it?** A command an agent wrote would run with the
      operator's authority, which is how a permission denial could come back as one click. Suggested:
      a click shows the exact command and folder and asks once, then runs it in a visible popup. The
      command is stored as an argv, never a shell string, and there is no batch run.
- [ ] **Should a tab that ends its turn on a question be flagged?** Prose is the largest channel and
      the hooks cannot see intent. The `Stop` hook has the last message, so a turn ending in `?` could
      raise an `asked` row. Suggested: yes, as a mark on the tab and a low row, knowing it will
      sometimes be wrong. The alternative is the brief alone.

### Phase work

- [ ] **Measure first, on a probe session.** Which hook events fire for `AskUserQuestion`, a
      permission prompt, and an auto-mode denial, and whether each says when it ended. The rows below
      depend on it, so nothing is built on a guess. Report anything a hook cannot see as a gap.
- [ ] **Kinds in the store.** `Item` gains a kind, defaulting to `choice`, so files on disk still read.
- [ ] **Action rows.** `sb deck decide add "<what>" --run <argv> --cwd <dir> --until <test>`. A ruling
      can leave an action row behind, so "pushes it by hand" stays open.
- [ ] **Closing by observation.** `--until` names one of a closed set: a PR merged, a SHA on a branch,
      a branch gone. A pinned command whose head has moved reads `stale`, and an action with no test
      closes by a click and says that nothing checked it.
- [ ] **Hook mirrors.** A hidden `sb deck ask` reads the hook's JSON, as the Approach above requires,
      and writes `asked` rows, including what a `waiting` tab waits on. Permission denials land as
      `action` rows with the denied command, for the operator to rule on.
- [ ] **Notices.** `sb deck decide note "<text>"`, drawn below the rest.
- [ ] **Held state.** Unpushed commits and local branches from git, and green unmerged PRs and open
      alerts from `gh`, for each deck repo. On a slow cadence and off the draw path, and a repo it could
      not read says so, because *could not see* must not read as *clear*.
- [ ] **The brief.** "Anything you need from the operator goes through `sb deck decide`; a question
      in prose is not an ask." Round reports' FOR-JESTON items become rows, in the workspace's skills,
      which the workspace has offered to change.
- [ ] **Proof on a real deck:** each kind drawn, sorted and closed with real clicks, a pane short
      enough to overflow, and a busy tab receiving a ruling once it goes idle.

## Dropped, and why

- **Binding Ctrl-C for exit.** It is claude's interrupt, and forwarding it would put every
  press through the deck; Jeston chose Ctrl-Q and a ✕.
- **Typing into an agent pane.** See Scope: it would be a second permission path.
- **Writing `~/.claude/settings.json` or `~/.tmux.conf`.** Operator-owned, like `projects.toml`.
- **The hook writer and its ledger.** Phase 1 found the registry already says `waiting`.
- **Scraping the TUI for task lists.** The workspace ruled it out too; screen text is not a contract.

## Notes

### 2026-11-04: drafted from the workspace's proposal

Ruled here: the name, the scope, the hook's ownership, and the deferred task lists. The only
measurement so far is the registry's `status` (two values, seven sessions) and the absent todo
directories. The relayed scope ruling is recorded but not applied.

### 2026-11-04: the scope ruling confirmed

Jeston confirmed the ruling directly, so the plan is unblocked. `CLAUDE.md` § Scope, the README and
fundamentals' Decisions now say that act versus observe is decided by the surface.

### 2026-11-04: Phase 1 measured, and the hook is not needed

The probe ran in a detached tmux session against an empty scratch directory, with hooks from a
`--settings` file. Claude Code writes `waiting` to its own registry while a permission prompt is
open, so the queue reads the file sky.boss already parses. The hook writer, the settings fragment
and the ledger seam are all dropped. The trust dialog is the one waiting state with no record,
and the deck covers it by showing what it started.

### 2026-11-04: Phases 2 and 3 built

`sb deck`, `open`, `queue` and `jump` shipped in `skyboss/deck.py`. Decided while building:
- The deck finds its own windows by tmux user options (`@sb-agent` on a window, `@sb-deck` on a
  pane), not by name, so a renamed window is still found.
- Bare `sb deck` always refuses `--json`. Inside tmux it could return an envelope, but one that
  exists only sometimes is worse than none. With no terminal, it creates the session and says how
  to attach.
- `unregistered` is shown only for a window the deck started an agent in. A shell the operator
  opened gets no row, because the word would mislead there.
- The tester found that warnings were rendered as rich markup, so `[agent.<name>]` in a message
  vanished and a `[/x]` crashed. That had been true of every command's warnings. It is fixed in
  `skyboss/output.py`, and `skyboss/follow.py` now shares the one escaped path.

A deck row reading `waiting` was exercised only in unit tests, against a fake `claude`; the probe
in Phase 1 is the live evidence that the registry writes the word.

### 2026-11-04: round 2 reopened

The round 1 deck built only window 0 and opened projects on demand, which read as a display rather
than a command center. Reopened on Jeston's ruling, with the three answers recorded in Phase 4.

### 2026-11-04: round 2 respecced from the operator's own words

The first round 2 spec (all agents at startup, roll-call and agents panes) was written from a
relay. It was stopped before any code, and Phase 4 was rewritten from Jeston's own words plus three
answers: the columns layout, switchable to stack; resizable panes; tabs only for the agents he
activates; messages shown as time, sender to receiver and first line.

### 2026-11-04: the controller layout built

`sb deck layout` and `sb deck messages` shipped; `ensure`, `open`, `jump` and the queue moved to
two sessions. Decided while building:
- The inner session's first window is a `shell` tab in `$HOME`. A tmux session cannot have zero
  windows, and the nested client needs something to attach to before any agent is opened.
- `plan()` is a pure function of four pane ids, so each shape's tmux calls are tested directly.
  It only joins and resizes; `layout` also puts back a missing tool pane by splitting a new one.
- A bare `sb deck` on an existing deck redraws only when it had to put a pane back, so the
  operator's own dragging survives it. `sb deck layout` always redraws.
- `set-option -t` reads a pane target and refuses a bare `=sb`, so session options target `=sb:`.
  The real tmux found this; the fake now refuses the bare form too.
- Run from a pane inside either deck session, `open` and `jump` never switch the client. Switching
  the nested client to the outer session would draw the deck inside itself.
- Both sessions share one server and its key bindings, so the outer client sees the prefix first:
  prefix then a key acts on the controller. Pressing the prefix twice passes it to the nested
  client, which then acts on the tabs. Clicking a tab, and `sb deck jump`, need neither.
- The tool panes run with `--screen`. Inline frames left stale copies above the live one after a
  resize, which the mouse now invites.
- `sb deck messages` keys a peer entry without a `msg_id` (a subagent's handback) by its entry
  `uuid`. The slug rule held for every live session's directory on 2026-11-04.

### 2026-11-04: round 2 built

The controller shipped in sky-boss@d672d9c, and the tool panes were fitted to their height in
sky-boss@ee1742f. The queue keeps its top rows, because waiting sorts first, while messages keep the
newest; what does not fit is counted on a band line. Checked on a throwaway tmux socket with a fake
`claude`: both layouts, the switch keeping every pane's process, the tab row, and the fit
re-measured after a resize. Not observed, because no keys were sent: a mouse click on a tab, and
the outer/inner prefix (prefix twice reaches the tabs). Task lists remain deferred.

### 2026-11-04: round 3 reopened

Jeston, after using the controller, asked for profiles (a skyrow-core set of five repos with the
workspace first), tabs that show when an agent is working, a deck/outside filter, tables that fill
their pane without wrapping, and a theme in place of tmux's green. Recorded in Phase 5.

### 2026-11-04: round 3 built

Profiles, live tabs, `--scope`, the fill and the theme shipped. Decided while building:
- **Tab state is a window option, `@sb-state`, written by one loop.** Measured on tmux 3.8: a
  window option is drawn about 5 ms after `set-option`, at any `status-interval`. `#()` in a tab
  format forked once per tab per interval (30 forks in 10 s for 3 tabs). `monitor-activity` flags
  output only on non-current tabs, cannot tell waiting from working, and clears only on a visit.
- The writer is `sb deck marks --every 3`, an act. `sb deck` starts it once, as a tmux background
  job, so it ends with the server; it writes only what changed and exits when the deck is gone.
  Its pid is a session option, so a second loop yields. The tab row's right end shows when it last
  wrote, so a dead writer reads as stale rather than as calm.
- `window-status-format` is a window option in tmux 3.8, so tab formats are set on each tab. Only
  it is set, never `status-format`, so tmux's `range=window` still makes a click select the tab.
- A round 2 deck's pinned pane moves into the tabs with `break-pane`, process and all.
- The profile's tabs are put in its order with `swap-window`, ahead of any tab the operator
  opened. On a live deck, missing tabs are opened and nothing else is touched.
- The queue keeps its first rows when trimmed, because `waiting` sorts first; messages keep
  the newest.

The `deck.toml` schema after this round:

```toml
session = "sb"          # optional; the tabs session is "<session>-agents"
pin = "workspace"       # optional; the same as a profile with this primary and no tabs

[agent.workspace]
cwd = "~/src/workspace"
args = ["--model", "opus"]   # optional

[profile.core]
primary = "workspace"   # the first tab
tabs = ["jam", "mind"]  # in order; a name may also come from a projects.toml cwd
```

### 2026-11-04: round 3 built

Shipped in sky-boss@09ef614, sky-boss@97c15d3 and sky-boss@5c9bf1d, with the schema and decisions
recorded in sky-boss@20079d8. Tab states are a window option written by one `sb deck marks` loop:
`#()` forked once per tab per tick, and `monitor-activity` cannot tell waiting from working. Seen
on a throwaway socket: a mouse click selecting a tab, all four states drawn, and a state change
reaching its tab within three seconds. Not yet seen with a real `claude`; fake ones wrote the
registry records. The skyrow-core profile was added to the operator's own `deck.toml` by hand, not
by sky.boss.

### 2026-11-04: round 4 reopened

After the first real run, Jeston asked for an exit, scrolling messages, an agent colour shared by the
tabs and the messages, and visible shortcuts including hiding outside agents. Recorded in Phase 6.

### 2026-11-04: round 4 built

Shipped in sky-boss@0e7e5ee, sky-boss@d14a1cf and sky-boss@ebba8f5. Measured and decided:
- **A session's `key-table` does not fall back to root.** Measured on tmux 3.8, throwaway socket:
  the prefix still works and an unbound key still reaches the pane, but root's mouse bindings are
  never consulted, so tab clicks, border drags and the wheel all stopped. The deck therefore copies
  `list-keys -T root` into its own table, `sb-deck-<session>`, with any Ctrl-C binding dropped, and
  binds its keys over that. Root is unchanged and a session outside the deck sees none of them.
- **The keys.** Checked against Claude Code 2.1.318's own key strings and its input's Meta switch
  (`b`, `d`, `f`, `y`), plus the listed `alt+o/p/t/v/w`, `meta+j/m/o/p/t/w` and `meta+up/down`;
  tmux's root table has no Meta binding by default. Chosen: `C-q` exit, `M-h` outside, `M-l`
  layout, `M-,` and `M-.` previous and next tab, `M-u` older messages, `M-e` newest. Not checked:
  any `keybindings.json` the operator has written, which sky.boss does not read.
- Exit asks with `confirm-before`, whose prompt names the count from `@sb-agent-count` (kept by
  the marks loop). `sb deck exit` stops that loop and kills the two sessions; `kill-session`
  appears only in `end_sessions`, which a test recomputes from the source.
- The panes write no option. A shortcut sets one; the pane adopts a changed sequence number on its
  next frame, and its own keys move only its own offset.
- **A bug the scroll exposed:** `sys.stdin` buffered `ESC [ A`, so Up read as Esc and left every
  resident view, `sb follow` included. A test had pinned that behaviour; it now pins Up.
- An agent's colour is a step of the canvas's project ramp, recomputed in OKLab and moved in
  lightness until it clears 3.5:1 on white, the void, and both tab-row grounds. A test reads
  `sb.css`, so the two ramps cannot part.

### 2026-11-04: round 4 built

Shipped in sky-boss@0e7e5ee, sky-boss@d14a1cf and sky-boss@ebba8f5, with the measurement, the keys
and the decisions in sky-boss@17139d6. One ruling was made in the orchestrating session rather than
by Jeston: tmux 3.8 does not fall back to `root` from a session's `key-table`, so mouse clicks, drags
and the wheel died in the deck. The deck now copies `root` into its own table, minus Ctrl-C, and
binds over it. That is accepted because it changes nothing global. Its cost is that a root binding
added later reaches the deck only on the next `sb deck`. Every behaviour was seen on throwaway
sockets with fake `claude` scripts; none has been run against a real one yet. A side fix:
`skyboss/keys.py` now reads unbuffered, so an arrow key in any resident view, `sb follow` included,
is no longer taken for Esc.

### 2026-11-04: every agent the deck starts is told it is in a deck

Asked by Jeston after the workspace agent could not say what "the deck" was. Each `claude` the deck
starts now runs as `claude -n <tab name> --append-system-prompt <brief> …args`. The brief names the
agent and the tmux session, says the others are peers reached by name with SendMessage, points at
`sb agents --scope deck` and ListAgents, lists the roster at launch (name and directory, primary
first and marked), says tabs come and go so the live list wins, and says the operator reads MESSAGES
and answers prompts by clicking a tab. The primary gets one more line saying it coordinates.
- Built at launch from `deck.toml` and tmux only, never from a transcript; a test makes every
  transcript and registry read fail and the brief is still built. The paths are the operator's,
  computed at runtime and written nowhere.
- The operator's own `-n`/`--name`, or appended system prompt, wins over the deck's.
- The primary is recorded as `@sb-primary` on the tabs session, so a tab opened later is briefed
  with the roster as it stands then, primary marked. **Agents already running are not updated**:
  the only way would be typing into them, which stays banned, and the brief says to check the
  live list instead.
- Seen on a throwaway socket: a fake `claude` dumped its argv, and the brief arrived intact as one
  argument through tmux. `sb agents --scope deck` run from inside a tab found the deck's server
  through `TMUX` and listed all five agents. Not yet run against a real `claude`.

### 2026-11-04: message endpoints by session, and the operator's words in the brief

Two live sessions were both named `skeletor`, one a deck tab and one not, and MESSAGES painted the
outside one's messages in the tab's colour, because senders were looked up by name. Now neither
end of a message is identified by name:
- The receiver is the session whose transcript holds the entry. The sender is the live session
  that `verifiedPeerPid` with `verifiedPeerProcStart` names in Claude's registry, else the one whose
  `messagingSocketPath` is the entry's `from: "uds:…"`. A sender with neither, or naming a session
  that is not live, is never a deck agent and stays plain.
- A name held by one live session is shown bare. Of several, the one deck agent keeps it bare and
  every other is shown `name·<first 8 of its session id>`; an unverifiable sender sharing a live
  name is shown `name·?`.
- The queue, the marks and `sb agents --scope` already placed a session by its pane's process
  tree, never by name; a test now pins that for two same-named sessions.

`deck.toml` takes two more optional keys, both strings and both checked like the rest:

```toml
[agent.skeletor]
cwd = "~/src/skeletor"
role = "the scaffold generator; upgrades flow from here"   # one line, beside it in every roster

[profile.skyrow-core]
primary = "skyrow-workspace"
tabs = ["stash-flow", "mind-head", "sky-boss", "skeletor"]
brief = '''Extra text appended, unedited, to every brief this profile launches.'''
```

The primary's hardcoded "coordinating agent" line is gone: the roster still marks `(primary)`, and
what it does comes from its `role`. The fifteen-line limit covers sky.boss's own lines only, never
the operator's `brief`. A tab opened later with `sb deck open` is not launched under a profile, so
it gets the roster and roles but no profile `brief`.

### 2026-11-04: todo lists, the TODOS pane, and the profile brief on a later tab

Claude Code's main sessions have no todo tool sky.boss can read, so each agent keeps its own
list through the deck: `sb deck todo add "<text>"`, `done <n>` and `rm <n>` act, and `list`
observes. A list is one JSON file per agent, `$SB_STATE/deck/<session>/todos/<agent>.json`: never
in a repo or `$SB_HOME`, keyed by deck session and agent name, stamped with `updated` on every
write, and written through a rename. The brief gains one line asking the agent to keep it; the
generated part is still fifteen lines for a five-agent profile.

- **The owner is the caller's tab, by the process tree.** `caller_tab` walks this process's
  parents up to an agent pane's pid in `<session>-agents`. There is no name argument, so a
  same-named session outside the deck reaches no tab and is refused with the sentence saying why.
  `list` inside a tab shows that tab's list; elsewhere, or with `--all`, every list.
- **The TODOS pane** is a third tool pane, role `todos`, below MESSAGES in columns and beside it in
  stack. A switch moves it, and a bare `sb deck` on an older deck puts it back. It is grouped by
  agent in tab order, primary first. Each heading is the agent's name in its tab colour, plus how
  long ago the list changed. A list whose agent has no tab follows, marked `(no tab)`. An agent that
  never wrote a list reads `no list kept`, and one with nothing left reads `nothing open`. Done items
  stay **dimmed, with a ✓**, rather than hidden, so the operator sees what moved. It refreshes every
  5s on the `--screen` repaint, and it scrolls from the **top** with its own keys (arrows, PgUp/PgDn,
  wheel, Home/End) once focused. There is no global shortcut, so the bar hints are unchanged.
- **Two fixes the third pane exposed.** On a new detached deck the first join landed the tool
  column in the tab pane's share of the stack, and the third join then hit a one-row pane and was
  refused. The first join is now full-window (`-f`). Separately, `fitted`'s grow-back left a pane
  remembering a page one row larger than it drew, so End stopped one row short of the last row (in
  MESSAGES too). The fit now sees the `keep` it drew last.
- **A tab opened later gets the profile's brief.** `sb deck --profile NAME` records `@sb-profile`
  on the inner session beside `@sb-primary`, and `sb deck open` reads it back. This reverses the
  last line of the previous entry.

Smoke-tested on a throwaway `-L` socket with a fake `claude` and scratch HOME, SB_HOME and SB_STATE.
`add` and `done` from inside one tab wrote that tab's list and nothing else. The same command from a
`claude -n sky-boss` outside the deck was refused and left the list untouched. Both layout switches
kept the TODOS pane's pid.

### 2026-11-04: `sb deck brief`, a way for a running agent to catch up

- **A brief is fixed at launch.** An agent started before briefs existed, or before a peer opened,
  has no way to learn the current deck, and the deck never types into a running agent. `sb deck
  brief` is an observe that rebuilds the calling tab's brief now: the live roster, the roles and the
  loaded profile's `brief`. The caller is found by the process tree, as for `todo`. A NAME previews
  another agent's brief from anywhere, and outside a tab with no NAME it refuses with a sentence.
  The `--json` data also carries `peers` as a list.
- **The operator brings an agent in by typing, not by sky.boss typing.** A user-level skill that
  runs `sb --json deck brief` and introduces the agent to the primary is the intended trigger. It
  lives in the operator's own skills directory, not in this repo. The brief now names the command.
  *(Reversed the same day; see the next entry.)*
- **The brief's cap counts fixed text only** (`BRIEF_LIMIT = 12`). The roster grows by one line
  per declared agent and the profile's `brief` is the operator's own, so counting either would let
  a sixth agent break a cap meant for sky.boss's own wording.

### 2026-11-04: the skill ships with sky.boss, as a plugin every tab loads

- **A project skill would not reach the agents.** `.claude/skills/` loads for sessions whose
  directory is this repo, and a deck's tabs run in other repos. A user-level copy reaches them, but
  it is unversioned and is a write into the operator's Claude Code configuration.
- **So `plugin/` is a Claude Code plugin, and every tab loads it with `--plugin-dir`**, for that
  session only. The skill moves with the sky.boss that started the tab, and nothing is installed.
  Measured on Claude Code 2.1.318: `claude --plugin-dir plugin plugin details sky-boss` lists the one
  skill at about 100 tokens a session.

### 2026-11-05: round 5 reopened, and half of it built

- **The outside count is a footer note, not a warning.** `Chrome` gained a `note`, drawn muted after
  the warning count, and a `Control` supplies it from its last `shape`. So the hidden count stays on
  screen without the ⚠️ and without inflating anything that counts warnings.
- **TODOS sorts on `updated`**, which `save` now stamps in microseconds. In seconds, two writes in
  one second tied, and the newest list did not reliably rise.
- **The tab bar now sets `status-format`, which round 3 avoided on purpose.** The reason given then
  was that tmux's own `range=window` keeps a click selecting a tab. Each row now carries that range
  itself, and `MouseDown1Status` (`switch-client -t =`, mirrored into the deck's table) resolves its
  target from it. Rendered on a throwaway server through a nested client: the boxes align and each
  state draws its ground. **A real click is not yet measured.**
- **Needs-you stays warn yellow.** It had been called orange in conversation. The only orange is
  stash.flow's hue, and stash-flow's own tab is drawn in it, so Jeston kept the warn colour.

### 2026-11-05: round 5 built

- **One store, two books.** `skyboss/todos.py` keeps each agent's list per *book*: `todos`, or
  `decisions` under `$SB_STATE/deck/<session>/decisions/`. A closed decision carries its ruling,
  drawn as `✓ question → ruling`. DECISIONS lists only agents that recorded one, since ten
  `none recorded` rows would bury the one that did. When none has, it says so in a row rather than
  drawing nothing.
- **The column's choice is `skyboss/column.py`**: order, hidden and folded, saved per deck session
  under `$SB_STATE`, with `panes = [...]` in `deck.toml` as the starting order. A role the file never
  named joins at the end, so a pane added later still appears in an older deck. `M-s` opens
  `sb deck column pick` in a popup, and `M-c` runs `sb deck column fold` on the focused pane's
  role; anything that isn't a tool pane gets a message rather than nothing. Both keys were checked
  free against Claude Code 2.1.318's Meta strings, the same list round 4 measured.
- **A hidden pane closes itself; the deck still kills nothing.** Killing a tool pane would have been
  safe, since it is a read, but it broke the source-wide rule that the deck never kills or respawns
  a pane, and the rule is cheaper kept than excepted. So the hidden set is a session option, a pane
  that finds its role there raises `resident.Leave` (ended as quietly as q), and `arrange` waits up
  to `HIDE_WAIT` for it before laying out. Showing it again opens a fresh one.
- **A folded pane draws one line**, its label and counts from `column.summary`, in place of both
  bands and the body. In stack it is a `FOLDED_WIDTH` strip with the same line elided.
- **Found by the smoke, invisible to the suite: `repaint` ended every frame with a newline.** A full
  frame never noticed, because the fit always leaves a spare row. A one-row pane scrolled its only
  line away and showed blank. A screen-tall frame now ends without one. The chooser had the same
  fault, losing its title in a popup sized exactly to it.
- **Smoked on an isolated tmux server** (`TMUX_TMPDIR`, a scratch `SB_HOME` and `SB_STATE`, a
  200×50 client attached through a second server and captured). Fold, hide, show again, the stack
  strip, `M-s` driven to a reorder and Enter, and `M-c` on a focused pane were all read back. **One
  lesson for the next smoke from inside a deck: unset `TMUX`**, or `tmux` talks to the live deck
  whatever `TMUX_TMPDIR` says. One read here went to the real server by that route; it changed
  nothing.

### 2026-11-05: the label, activity order, queue colours and reload

- **`shell` is a registry word, not a description.** Claude Code reports it for a session running a
  shell command, and that is the word in Jeston's "busy, then shell, then idle". The first build
  mapped `unregistered` to `shell`, which a live read of the queue showed colliding with the real
  word. `unregistered` keeps its own word and sorts last.
- **`reload` cannot reach a pane from before this round**, because only the new code reads the
  hidden set. It waits `HIDE_WAIT` for such a pane, names it, and says to press q in it. The first
  upgrade of a running deck therefore needs q in each old tool pane, then `sb deck`.

### 2026-11-05: round 6 built

- **The mark is the favicon, redrawn.** `theme.MARK_PIXELS` holds six rows of pixels, two to a
  half-block cell, so the mark fills the tab bar's three rows: the blue L, the white S in its
  corner, and the base run one column past the S at Jeston's request, as the favicon's does.
  `tab_lefts` pads the rows above and below to the middle row's width, so every row's boxes still
  start in one column (tested by stripping the styles and measuring).
- **Bold leaked in tmux, twice.** A colour change does not end tmux's `bold`, so the wordmark's
  bold ran on into `tabs`, and a current tab's bold edge ran on into "marks not running" (the
  latter since round 5). Each now ends with `nobold`. Only a coloured capture shows it.
- **One countdown is only true if the panes refresh together.** A shared interval alone would leave
  four clocks started at four instants. So a deck pane's residency is *aligned*: it is due at each
  multiple of `TOOLS_REFRESH` on the clock, and its band draws no countdown of its own. The footer's
  countdown is tmux's own arithmetic, `#{e|-:5,#{e|%%:%s,5}}`, which works because tmux expands
  strftime's `%s` before the format, with `status-interval 1`. Nothing writes it, and it cannot
  drift from the panes, since both read the same clock. Smoked: four panes `ran 09:56:45`, and one
  countdown on screen. MESSAGES moved from 10s to the shared 5s.

### 2026-11-05: round 7 built

- **The mark is drawn in quadrant blocks**, four pixels to a cell, which is what halves it. A
  quadrant cell takes two colours, its glyph's and its ground, so a cell holding blue, white and
  blank cannot be drawn. The round-6 pixels had two such cells. The new layout uses a one-pixel L
  stem, a one-pixel gap and an S six pixels wide, and every cell holds two colours at most.
  `_quadrant` raises on a third, so a future redraw cannot lose one silently.
- **The header ground is the brand at 20% over the void** (`HEAD_GROUND`), registered as a painted
  role and so held to the painted-role checks: text measures 13.1 on it and text-2 4.64. It is
  laid *under* the band's spans (`stylize_before`), so each span keeps its own colour. It is a
  `Control.head` role, so nothing outside the deck grounds its band.
- **A click is a key.** The reader decodes an SGR left press as `click:<x>:<y>`, and a resident
  control may ask for each frame's plain lines (`clicks`, `framed`). The MESSAGES pane maps a
  line to a row by counting from the table's rule, against the rows its fit last drew. The popup
  runs `sb deck message --page <key>`, an observe: the message found by the `key` its row now
  carries, searched past the pane's last 50, paged through `less -R -c -+F`. Here `-+F` matters,
  because an operator's `LESS` may quit at once on a short page and close the popup unread. `-c`
  starts the page at the top. Smoked on a throwaway server: a real SGR click opened the
  workspace's message with the header, Markdown lists and `q closes`, and q closed it.
- **M-x prints its count from the envelope.** It greps one `"cleared"` per list in `--json`, so it
  reads none of the human output. A list with nothing done is not rewritten, so its place in the
  newest-first TODOS order holds.

### 2026-11-05: round 8 built

- **Quadrants made the mark tall.** A quadrant pixel is half a cell wide and half a cell tall,
  so twice as tall as it is wide. That made round 7's mark fill its rows with an L thinner than
  the S's horizontals. A sextant pixel is a third of a cell tall, near square, which centres the
  mark in nine pixel rows with one blank each side. The L's base sits in a cell row of its own,
  behind a gap row, so no cell needs three colours. Konsole draws sextants, through Noto Sans
  Symbols 2 if not natively; a font without them would show boxes.
- **The scroll is tmux's, and only the scrollbar is ours.** `#[list=on]` / `#[list=focus]` let
  tmux trim the tab list around the current tab with no latency. Each status row trims alone, so
  rows 0 and 2 carry the name row's right end in the bar's own colour (`unseen`). All three then
  get the same room and the same trim; without it the boxes would split. The scrollbar mirrors
  tmux's rule from `format_draw_put_list` (centre the focus, clamp at either end).
  `sb deck scroll` computes it and toggles `status` between 3 and 4. It runs on tmux hooks
  (client-resized, session-window-changed, window-linked/unlinked) and on every marks tick as a
  backstop. Smoked at 140 and 300 columns with eight tabs: the thumb followed the current tab
  within 1.5s, and widening hid the row.
- **`set-hook` refuses a bare `=name` target, like `set-option`.** The first smoke showed no
  hooks and a thumb moved only by the marks loop. The hooks now target `scope()`.
- **The lighter ground costs the band's muted text some contrast**: `sb.muted` on it measures
  about 2.9 (3.4 at round 7's 20%). The label and its text hold above 11. Jeston asked for lighter.

### 2026-11-05: round 9 built

- **The one write into Claude Code's configuration, by the operator's ruling.** sky.boss writes
  `sb-<agent>.json` in `$CLAUDE_CONFIG_DIR/themes` (else `~/.claude/themes`) and nothing else
  there. It writes only when `themes = true`, only when the content would change, and through a
  rename. Claude Code reloads a changed theme file, so a tab whose slot moves gets a recoloured
  console from the same `write_colours` that recolours its tab. The file is written before the tab
  launches, so the console finds it at start: Claude Code watches the directory only if it existed
  at launch, and a deck's first themed tab is the one that creates it.
- **`--settings` scopes it to the session.** The operator's own `--settings` in an agent's `args` wins,
  as `-n` and the appended prompt already do. Open tabs change only on restart.
- **The suite redirects `CLAUDE_CONFIG_DIR`** in `conftest.py`, beside `SB_HOME`, so no test can
  write the operator's themes.
- **Not yet seen in a real console.** Verifying needs a theme file in the operator's real Claude Code
  directory, which this round would not write outside a deck Jeston starts. The file format and the
  `--settings` key come from Claude Code's docs (terminal-config, settings), read on 2026-11-05.

### 2026-11-05: round 10 built

- **One key, both books.** The workspace measured TODOS already empty and five decided items under
  skyrow-workspace in DECISIONS, so the leftover rows were decisions. M-x now runs `todo clear`
  and `decide clear` and says both counts. A separate key and an age-out were offered; Jeston chose one key.

### 2026-11-05: sent messages take the header ground

- **A sent message is drawn on `HEAD_GROUND`**, the right column's label ground, on Jeston's ask: on
  the `dark-ansi` base Claude Code paints it `ansi:blackBright`, too bright under white text. The
  theme overrides `userMessageBackground`, on dark bases only, because that ground under a light
  base's dark text would be unreadable. The token and its preset values were read from the installed
  Claude Code binary (2.1.318), not from its docs.

### 2026-11-05: one clock, in the footer

- **The marks time moved to the footer, beside the countdown, on Jeston's ask.** `@sb-marked` is now
  written on the deck session, because the outer bar reads it there; the tab rows end at their list,
  so the tabs get that room and `unseen`, which only padded the off-name rows, is gone.
- **A deck pane draws no timing of its own**: `shared` drops `· refresh Ns` and `· ran HH:MM:SS` as
  it already dropped the countdown. A pane that stalls no longer shows a stale `ran`; the footer
  speaks for the marks loop and the cadence, not for each pane.
- **`sb deck reload` restarts the marks loop.** An old loop would have gone on writing the tabs
  session, and the footer would have said `not running` over a live one.

### 2026-11-05: round 11 built, save and resume

- **Why:** Jeston's session saver idea, split in two on his ruling. This is the half that loses
  nothing; `sb deck compact` waits, because it types into a tab and cannot see a draft there.
- **Shape:** `$SB_STATE/deck/<session>/saved.json` holds each tab's agent, session id and cwd, plus
  the primary and profile. `sb deck` on a stopped deck reopens the saved tabs; `--profile` opens its
  own tabs and resumes those it can; `open` resumes too; `--fresh` forgets. A running deck is never
  restored over.
- **Three writers.** The marks loop saves on change and never drops a tab, because at shutdown the
  tabs die before it does, and that is what covers a reboot. So a closed tab stays saved until
  `sb deck save` or `sb deck exit`, which write exactly what is open.
- **Measured on Claude Code 2.1.318, with a control:** `--resume` keeps the session id, so a save
  does not go stale by being used. A session keeps the `--append-system-prompt` it started with and
  ignores a new one, so a resumed tab has its launch roster and `sb deck brief` is how it catches up.
  A lost id prints `No conversation found` and ends the tab, so the transcript is checked first.
- **Smoked in a throwaway deck:** a real tab told a word, `sb deck exit`, `sb deck`: same session
  id, same name, the word recalled, the brief still known.
- **Does not do:** compact, or save a tab whose `claude` never registered. A session open elsewhere
  is not resumed twice: the tab starts new and says so.

### 2026-11-05: round 12 built, the footer carries the names

- **Why:** Jeston's ruling, relayed by skyrow-workspace.
- **Shape:** the name is read from `@sb-profile` when the bars are dressed, so `sb deck reload` and
  `--profile` both redraw it, and `status-left-length` stays the exact width. `status-format[0]` on
  the outer session replaces tmux's default, which is where the window list lived.
- **Renaming a profile under a running deck:** `@sb-profile` and `saved.json` keep the old name, and
  a name no longer declared gives no brief to a new tab. Set the option, then `sb deck save`.

### 2026-11-05: round 13 built, colours, decisions, grid

- **Why:** Jeston's rulings, in the tab. A ruling typed into a tab can join a draft sky.boss cannot
  see; he took that over an idle agent never hearing. This is the risk that held `sb deck compact`
  back, accepted here because the operator has just clicked in the popup, not typed in the tab.
- **`colour` names a theme hue, never a hex.** A hex would have no Rich role for the messages pane
  and no floor. `hue_names` is the list.
- **Why a job says `|| true`:** tmux prints a non-zero `run-shell` exit into view-mode on the current
  pane, redirected output or not. Reproduced on a throwaway server after a tab was found stuck in
  view-mode. Which job did it there is not known.
- **`rule` is not a list command.** It needs a terminal and refuses inside a tab, so an agent cannot
  rule on itself. A ruling not yet told survives M-x.
- **Does not do:** tell an agent while its tab is busy or scrolled; the ruling waits, marked `untold`.

### 2026-11-05: round 14 built, padding and background jobs

- **Why:** Jeston's rulings, in the tab.
- **`skyboss/background.py` is a second reader under `~/.claude/projects`, beside MESSAGES, on his
  ruling.** It reads `meta.json` and `stat`s the transcript, and never opens a conversation.
- **Measured on Claude Code 2.1.318:** no field says a sub-agent finished, and finished ones ended on
  a `user` entry, so the last entry is no signal either. So `up` says how long ago it wrote, it is
  never called running, and after ten quiet minutes it leaves.
- **A foreground and a background shell look alike** in the process tree, so both are drawn.

### 2026-11-06: round 15 opened, free columns, nothing built

- **Why:** Jeston's request, relayed by skyrow-workspace; his words: "id like to be able to put as many
  or few as i want windows in a column".
- **Status:** recorded only. How it is configured and switched is his to rule on, in Phase 16.

### 2026-11-06: round 16 opened, add from the bar and a terminal tab, nothing built

- **Why:** Jeston's request, made directly. It is one round rather than three because the `+`, the
  terminal and the start list share one question: what the deck may open, and from where.
- **The cost to weigh:** the `+` as asked reverses "sky.boss never writes `deck.toml`". That reversal
  is his to make. If he makes it, Phase 7's line stays and this note records the change.

### 2026-11-06: round 17 opened, tab padding and pane titles, nothing built

- **Why:** Jeston's request, made directly. His "r" at the start of the bar is read as the band's `┌`,
  and "the cli tabs" as the agent tabs. He wrote `TODOs` inside all caps, and it is kept as he wrote it.
- **The reversal:** on 2026-11-05 he wanted the tabs edge to edge. That reasoning stays in Phase 15.
- **Same day, added:** remove the top text and the secondary titles. "Top text" is read as the scroll
  line, so `newest` in MESSAGES goes with `top`; the count it carries is the one thing to keep.

### 2026-11-06: round 17 built, all but the side padding

- **Pane titles:** `Control.title` replaces the top band's text and corners, and `Control.place` takes
  the fit's count into the band's right slot. A bare `top` or `newest` now draws nothing.
- **The shortened counts drop their key hints,** such as `End or M-e: newest`, to fit beside the title.
- **`fitted` had a stale-count path:** after the overshoot it reran `fit` without keeping the marker.
  It now redraws the `keep` it settled on, so the count matches the rows on screen.
- **Tried for the side padding, and failed on a real tab:** tmux's `pane-scrollbars` with a blank style
  gives a clean one-cell gutter, and it measured right on a stand-in `claude`. tmux shows no scrollbar
  on the alternate screen, and every real `claude` tab and the tab pane's `tmux attach` report
  `alternate_on=1`. A smoke stand-in has to enter the alternate screen, or it proves nothing here.
- **What is left is spacer panes,** two more per tab, with hidden borders. Each gap is two cells, a
  click on one takes focus from `claude`, a spacer holds a closed tab's window open, and every pane
  reader has to skip them. That cost is why it went to Jeston rather than being built.

### 2026-11-06: rulings on rounds 15, 16 and 17

- **Why:** Jeston ruled in DECISIONS. Each ruling is written into its phase above.
- **Round 17:** the count at the right of the band stays, only while rows are hidden, and the tabs'
  sides stay edge to edge.
- **Round 16:** all five questions settled, including the reversal of "never writes `deck.toml`".
- **Round 15:** all four settled. Two were reasked in plainer terms after he asked for more information.

### 2026-11-06: rounds 15 and 16 built

- **Why:** Jeston's word to build both, once every question was ruled.
- **Measured with real clicks** on a throwaway deck through a viewer client: `tmux send-keys -H` with
  the SGR bytes reaches the deck's mouse bindings, where `send-keys -l` does not.
- **`deck.toml` is written now,** so Phase 7's "never writes" is history. Only `sb deck add --keep` and
  the `+` do it. The file's other readers are unchanged.
- **A hand-run restore showed a gap:** a save holding terminals and no agent tabs reopened no terminal,
  because `restored()` returns nothing without tabs. The terminals are now read on their own.

### 2026-11-06: the canvas stops being a monitoring surface

- **Why:** Jeston set a long-term goal that this deck and the canvas fuse into one surface, and
  dropped the monitoring declaration to allow it. [[fundamentals]] has the decision, and [[open]]
  item 25 has what it adds and rebuilds.
- **Superseded here:** "`sb ui` stays observe-only" in the opening ruling. It is left as written,
  because it records what was ruled on 2026-11-04.
- **Nothing in the deck changed.** It stays the place agents are driven from until a later round
  says otherwise.

### 2026-11-06: round 18 opened, one queue for every ask, nothing built

- **Why:** Jeston reported asks getting lost and asked whether an actions window was needed. The
  workspace collected the channels and recommended one queue, leaving the shape to this repo.
- **The answer to the window question is no.** Phase 18 agrees with the workspace on one queue. It
  adds the `asked` kind, folds held state so it cannot crowd choices, and uses `--plugin-dir` for the
  hooks, which keeps "the install is the operator's" intact.
- **Two questions went to DECISIONS,** and nothing is built until Jeston has seen the plan.
