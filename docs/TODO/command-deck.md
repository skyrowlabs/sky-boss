---
title: "The deck: a tmux command center for agent sessions"
slug: command-deck
shelf_status: planned
priority: medium
updated: 2026-11-04
tags: [agents, act, tmux, surfaces]
summary: "Adds `sb deck`, a tmux session holding one window per agent, plus a queue of sessions waiting on the operator, read by both surfaces. It is the first act surface beside the observe-only canvas."
---

# The deck: a tmux command center for agent sessions

> **Status**: 🔴 Planned
> **Shelf-Status**: planned
> **Priority**: Medium. The proposal is the workspace's; the scope rule it rests on was confirmed 2026-11-04.
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

- [ ] `sb deck`: create the session if absent (with the pinned agent in window 0), set
      `window-size latest` and `allow-passthrough on` on each deck window (both are window
      options in tmux 3.8), then attach
      (`switch-client` inside tmux, `exec tmux attach` outside). Acts.
- [ ] `sb deck open <name>`: a window named `<name>` running `claude` in that agent's `cwd`, or a
      `select-window` if it already exists. Acts.
- [ ] `extended-keys` read from the server and reported on stderr when it is off; never set.
- [ ] `acts` asserted with `sb_acts` on every subcommand, and a test that each one chose
      ([[jobs]] round 1).
- [ ] No subcommand calls `send-keys`, and a test greps the module for it.

## Phase 3: the queue

- [ ] `sb deck queue`: an observe. One row per deck window: window name, the `claude` pid running
      in it, and that pid's registry `status`, or `unregistered` when there is no record. Sessions
      reading `waiting` sort first. The word is the provider's, compared literally, so sky.boss
      orders and does not judge. Live sessions outside the deck are listed after, so none is hidden.
- [ ] `sb deck jump <name>`: `select-window`. Acts.
- [ ] `sb deck` puts a queue pane in the pinned window (`sb deck queue` on a refresh).

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
