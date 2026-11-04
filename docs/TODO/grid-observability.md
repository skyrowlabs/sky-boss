---
title: "Grid observability"
slug: grid-observability
shelf_status: planned
priority: medium
updated: 2026-11-03
tags: [schedule, roll-call, agents, history]
summary: "What sky.boss misses about skeletor's agentic grid: off jobs drawn as if they fire, no agent-hours rollup, no stagger view, no category grouping. Each gap has a ruling."
---

# Grid observability

> **Status**: 🔴 Planned
> **Shelf-Status**: planned
> **Priority**: Medium — the grid is arriving in several trees at once, and the first gap misleads today
> **Updated**: 2026-11-03

## Problem

skeletor's agentic tier gives every tree that adopts it a reporting grid behind
`<cli> report status --json`. This repository adopted it on 2026-11-03. Pointing
[[schedule]] at the real envelope, using a scratch `SB_HOME`, turned up these
gaps. The workspace session found them and this repository owns them:

1. **A job its provider switched off is drawn as if it fires.**
   - The envelope says `intentionally_off: true`, `next_run: null` and gives an
     `unscheduled_reason` for the two lane drainers.
   - `sb schedule` still shows them with `clock` set to `watched` and their cron
     string, under a blank FIRES. The reader concludes that something fires on
     that cron line, and nothing does.
   - This is the failure [[schedule]] already names: *a correct sentence that
     misleads is the same failure as a wrong one*.
2. **No agent-hours rollup across projects.** The operator budgets automation in
   agent-hours per day per repository, and nothing here can answer that. Each
   project's ledger is readable one at a time through [[history]]. The total is
   not.
3. **No overlap or density view for staggering agent jobs on one host.** Several
   grids share a machine. Spacing them out was done by reading a crontab by hand.
4. **No grouping by the operator's project categories** (primary, internal, side
   project) in [[roll-call]] or [[schedule]].
5. **Whether `sb agents` sees a headless grid run was unverified.**

## Rulings

| Gap | Ruling | Why |
|---|---|---|
| 1. Off jobs drawn as live | **Build** (phase 1) | The provider has already judged it. Drawing that judgement is ordering, which sky.boss may do, not judging, which it may not. |
| 2. Agent-hours rollup | **Build the hours, defer the cost** (phase 3) | A sum of durations the ledger already carries is arithmetic nobody invented. No template ledger records cost yet, so cost waits for a provider to publish it. |
| 3. Stagger and density view | **Decline as asked; open the provider-published shape** | A density view needs recurrence, and sky.boss never parses cron. See `docs/open.md` item 24. |
| 4. Category grouping | **Build as a declared field** (phase 2) | The category is the operator's label, so it is declared. sky.boss does not query a hosting API for it. |
| 5. `sb agents` and headless runs | **Measured: it sees them.** Re-check under cron (phase 4) | See below. |

**Gap 5, measured on 2026-11-03.** A headless `claude -p` session, the same
invocation the grid's runner uses, writes a session record. `sb agents` listed it
as `busy`, with the right working directory, while it ran. What has not been
measured is a run started **by cron**, whose environment differs from a shell's.
A grid that sets `<PREFIX>_AGENT_CMD` to another provider is also outside this
measurement: [[agent-sessions]] has no adapter for one.

## Approach

All four builds read what a provider already publishes, or what the operator
declares. None of them adds a judgement. Phases 1 and 2 are small and
independent. Phase 3 is a new read across ledgers. Phase 4 waits for cron to be
installed somewhere.

## Phase 1 — honour a provider's "off"

- [ ] The schedule mapping in `projects.toml` gains an optional `off` key, naming
  a boolean field such as `off = "intentionally_off"`, and an optional `why` key,
  naming the reason field.
- [ ] A row whose `off` field is true draws FIRES as `off`, keeps its schedule
  string, carries the reason in the hover and `--json`, and sorts after the
  unscheduled rows. It is never counted as overdue or as firing in a window.
- [ ] The span filter and the "nothing fires within" sentence count off rows
  separately, so a project whose jobs are all off does not read as quiet.
- [ ] A test, against the real `dev report status --json` shape, that a
  switched-off drainer never reaches the timeline.

## Phase 2 — declared project category

- [ ] `[project.NAME]` gains an optional `category`: a free word, a label the
  surfaces sort under, never part of an address. This is the same rule as a
  tool's `group` in [[tools]].
- [ ] `sb roll-call` and `sb schedule` group by it when any project declares one.
  Undeclared projects sit under no heading, not under an invented "other".
- [ ] `--json` carries the field as declared.

## Phase 3 — agent-hours from the ledgers

- [ ] An observe that reads each declared project's run ledger, the same reader
  [[history]] uses, and sums `duration_s` per project per day over a window.
- [ ] A row whose duration is absent is **counted as unmeasured**, not as zero.
  A rollup whose missing rows read as idle hours is this repository's *worked
  fine, told nobody* failure.
- [ ] Cost (~deferred) — waits until a provider's ledger records it. sky.boss
  never estimates a price.

## Phase 4 — headless runs under cron

- [ ] (~operator) Once a grid's cron is installed on this machine, run
  `sb agents` while a scheduled agent job is in flight, and record what it shows.

## Acceptance

- [ ] `./dev test unit` green.
- [ ] `sb schedule` against a real grid envelope draws a switched-off job as
  `off`, and its timeline never places it.
- [ ] `sb roll-call --json` carries a declared `category`, and the table groups
  by it.
- [ ] The agent-hours rollup reports unmeasured rows by count, checked against a
  ledger with a deliberately missing duration.

## Dropped, and why

- **Parsing cron to draw recurrence or density.** [[schedule]] refuses it: a
  wrong fire time is worse than none, because it looks like an answer. If the
  density view comes, it comes from a provider publishing its own occurrences
  (`docs/open.md` item 24).
- **Reading the category from the hosting platform's API.** It would put
  sky.boss in a credential path for a label. It would also fail for a declared
  project that is a machine rather than a repository. The declared copy can
  drift from the source, and that is the accepted cost.
- **Treating "off" as a sky.boss judgement.** This means inferring "off" from a
  null `next_run`. A null `next_run` also means "could not compute", and only
  the provider knows which one it is.
