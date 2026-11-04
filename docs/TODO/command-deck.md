---
title: "The deck: a tmux command center for agent sessions"
slug: command-deck
shelf_status: blocked
priority: medium
updated: 2026-11-04
tags: [agents, act, tmux, surfaces]
summary: "Adds `sb deck`, a tmux session holding one window per agent, plus a queue of sessions waiting on the operator, read by both surfaces. It is the first act surface beside the observe-only canvas."
---

# The deck: a tmux command center for agent sessions

> **Status**: 🔴 Blocked
> **Shelf-Status**: blocked
> **Priority**: Medium. The proposal is the workspace's, and the scope rule it rests on is not yet in `CLAUDE.md`.
> **Updated**: 2026-11-04
> **Blocked-On**: owner-ops

The gate: `CLAUDE.md` § Scope changes only on Jeston's word in this repo's own session, not on a relay.

## Problem

Several Claude Code sessions run at once across the sibling repos. [[agent-sessions]] can say which
ones are live, but not which one is **waiting on the operator**, and it gives no way to get to that
one. Today the operator finds a blocked agent by walking terminals. An agent waiting on a
permission prompt costs wall-clock time, and nothing reports that it is waiting.

## Approach

The skyrow-workspace session proposed this on 2026-11-04 and relayed an owner ruling with it. Its
four parts are ruled one at a time below.

**The relayed ruling, recorded as relayed.** *"`sb run` is the single top-level command that acts"*
is dropped. Observe versus act is now a property of the **surface**: `sb ui` stays observe-only, and
its per-command `acts` bit is unchanged; the deck is an act surface. sky.boss has not received this
from Jeston directly, so `CLAUDE.md` § Scope is untouched until he confirms it here. Note that the
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
  scopes. `window-size latest` and `allow-passthrough on` can be set on the deck's own session and
  windows, so the deck sets them there. `extended-keys` is a **server** option, so the deck
  reports it when it is off and does not set it. That is the KWin rule again: a desktop belongs to
  whoever runs it.
- **Names and paths come from `projects.toml`**, never from tracked code (the publication rule).
  The pinned workspace pane is a declared entry, not a special case in code.

### The waiting queue: the hook writes, and sky.boss owns the writer, not the install

- **Measure the registry first.** `~/.claude/sessions/<pid>.json` already carries `status`. On
  2026-11-04 it read `busy` or `idle` on all seven live sessions. Whether Claude Code writes a
  distinct value while waiting on a permission prompt is unmeasured. If it does, the queue is a
  read of a file sky.boss already parses and needs no hook. Phase 1 settles this before anything is
  built.
- **If a hook is needed, the writer is sky.boss code.** It is a hidden command that reads the
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

The queue is a JSONL ledger, so `sb data --from jsonl <path>` and `sb follow <path>` already open it
on the canvas with no new code ([[jsonl-reads]]). Jumping to a window stays on the deck, because the
canvas is observe-only.

## Phase 1: measure

- [ ] Hold one session at a permission prompt and read its `~/.claude/sessions/` record. Record the
      `status` value, or record that there isn't a distinct one.
- [ ] Read the `Notification` and `Stop` hook payloads on the running Claude Code version. Record
      their fields here.
- [ ] Jeston confirms the scope ruling directly, and `CLAUDE.md` § Scope is rewritten.

## Phase 2: the deck

- [ ] `sb deck` and `sb deck open <project>`, with `acts` asserted on every subcommand ([[jobs]]
      round 1's lesson).
- [ ] Session-scoped tmux options set, and `extended-keys` reported.

## Phase 3: the queue

- [ ] The source Phase 1 chose (the registry status, or the hook writer plus the printed fragment).
- [ ] A queue pane in the deck, with jump-to-window.

## Dropped, and why

- **Typing into an agent pane.** See Scope: it would be a second permission path.
- **Writing `~/.claude/settings.json` or `~/.tmux.conf`.** Operator-owned, like `projects.toml`.
- **Scraping the TUI for task lists.** The workspace ruled it out too; screen text is not a contract.

## Notes

### 2026-11-04: drafted from the workspace's proposal

Ruled here: the name, the scope, the hook's ownership, and the deferred task lists. The only
measurement so far is the registry's `status` (two values, seven sessions) and the absent todo
directories. The relayed scope ruling is recorded but not applied.
