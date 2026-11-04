---
title: "The deck: a tmux command center for agent sessions"
slug: command-deck
priority: medium
shelf_status: in-progress
updated: 2026-11-04
tags: [agents, act, tmux, surfaces]
summary: Adds `sb deck`, a tmux session holding one window per agent, plus a queue of sessions waiting on the operator, read by both surfaces. It is the first act surface beside the observe-only canvas.
---

# The deck: a tmux command center for agent sessions

> **Status**: 🟡 In progress
> **Shelf-Status**: in-progress
> **Priority**: Medium. Round 3: profiles, tab states, scoping, fitted tables and the theme, on the operator's ruling.
> **Updated**: 2026-11-04

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
read. `sb agents` already shows the same `waiting` word there today. Jumping to a window stays on the deck, because the
canvas is observe-only.

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

- [ ] **Profiles in `deck.toml`.** A `[profile.<name>]` table carries `primary` (an agent name) and
      `tabs` (agent names, in order). `sb deck --profile <name>` opens the primary as the first tab
      and every listed tab after it, each a live `claude`. On an existing deck it opens only the
      missing tabs. A name resolves exactly as `open` resolves it (`[agent.*]`, then a
      `projects.toml` `cwd`). A name repeated in a profile is one tab and a warning; an unresolvable
      name is a warning and no tab. A profile key outside `primary` and `tabs` is named as a problem.
- [ ] **No fixed left pane.** Window 0 is the tab area plus the tools in both layouts. The `pin`
      key keeps working and means the same as a profile with a primary and no tabs.
- [ ] **Tabs say what each agent is doing.** Each tab is drawn with the registry's word for its
      session: `busy` as working, `waiting` as needs you, `idle` as quiet, and no record as
      unregistered. The state reaches tmux within a few seconds. Whatever writes it acts and says
      so; it keeps no process per tab and spawns no Python per tab per tick. The order is the
      profile's: primary first.
- [ ] **`--scope deck|outside|all`** on `sb agents` and on `sb deck queue`, default `all`. `deck`
      means sessions running in a deck pane, and `outside` means every other live session.
- [ ] **Tables fill their pane and never wrap.** In the deck's tool panes, columns widen to use the
      room the pane has and shrink with ellipsis when it has none. A row is always one line, at every
      width, re-measured each render because panes are dragged.
- [ ] **A sky.boss theme for the deck's own bars.** The tab row and the outer status bar take their
      colours from `skyboss/theme.py`, replacing tmux's default green, and are set as options on the
      deck's own sessions only. Nothing outside `theme.py` names a colour, so tmux style strings are
      generated there.
- [ ] Tests on `FakeTmux`: profile parsing and its problems, opening order and idempotence, the
      state marks, the scope filter, the no-wrap fit at several widths, and the theme options set on
      the deck's sessions only. A smoke test on a throwaway socket covers the clicks and the marks.

## Dropped, and why

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
