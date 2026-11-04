---
title: "The deck: a tmux command center for agent sessions"
slug: command-deck
shelf_status: in-progress
priority: medium
updated: 2026-11-04
tags: [agents, act, tmux, surfaces]
summary: Adds `sb deck`, a tmux session holding one window per agent, plus a queue of sessions waiting on the operator, read by both surfaces. It is the first act surface beside the observe-only canvas.
---

# The deck: a tmux command center for agent sessions

> **Status**: 🟡 In progress
> **Shelf-Status**: in-progress
> **Priority**: Medium. Round 2 builds the deck out into a workspace layout, on the operator's ruling.
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

- [ ] **Window 0 is the controller.** Left: the pinned workspace agent (about 45% wide). Middle:
      one pane attached to an inner tmux session, `<session>-agents`. Its windows are the project
      agents, and its status bar is the tab row. Right column (about 25%): `sb deck queue` (NEEDS
      YOU) over `sb deck messages`. Both refresh on a cadence (constants, not keys).
- [ ] **Tabs only for agents you activate.** `sb deck open <name>` adds an inner window running
      `claude` (or selects it), and `sb deck jump <name>` selects it. Clicking a tab works through
      tmux's mouse support.
- [ ] **`sb deck layout columns|stack`** switches window 0 between the two shapes by moving panes.
      It never restarts a pane, so every `claude` keeps its process (asserted: no `kill-pane`,
      `respawn-pane` or `kill-window` in the switch).
- [ ] **Resizable by dragging:** `mouse on` set on both deck sessions (a session option, so the
      operator's config is untouched).
- [ ] **`sb deck messages`**, an observe with `--refresh`/`--ticks`. One row per message exchanged
      between agent sessions: time, sender → receiver, and the body's first line. Newest at the
      bottom, the last 50, de-duplicated by `msg_id`. Source, measured on Claude Code 2.1.318: each
      live session's transcript (`~/.claude/projects/<slug of cwd>/<sessionId>.jsonl`) records every
      message it **received** as a `user` entry whose `origin.kind` is `peer`, carrying `name`,
      `msg_id` and `body`. A transcript that cannot be found or read is counted in a warning, never
      skipped silently. Message bodies are drawn on the operator's terminal and written nowhere.
- [ ] `sb deck queue` finds deck agents in the inner session's windows.
- [ ] Tests on `FakeTmux` and on synthetic transcripts: both layouts' commands, the switch moving
      panes without restarting any, `mouse on` on both sessions, the messages parse (peer entries
      only, dedupe, first line, unreadable transcript counted), and `--ticks` parity with `sb data`.

**Task lists stay deferred.** Recent transcripts on this version carry no to-do or task-creation
tool calls, and `~/.claude/todos/` and `~/.claude/tasks/` do not exist. So window 0 has no TASKS pane:
a pane with nothing behind it would be the nav rule broken in a smaller font.

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
