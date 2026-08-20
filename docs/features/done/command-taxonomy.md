---
slug: command-taxonomy
title: Command taxonomy — grouping by mood
status: complete
created: 2026-08-19
updated: 2026-08-20
agent_value: 3
key_files:
  - cli/__init__.py
  - cli/run.py
  - cli/check.py
  - cli/info.py
  - cli/assets.py
  - tests/test_taxonomy.py
---

# Command taxonomy — grouping by mood

## Why

Fourteen commands exist across three groups, and the seams are already visible:

```
tb doctor            tb assets describe      tb auto list/run/status/log
tb unpushed          tb assets update        tb auto since/prune/install/uninstall/windows
```

> **This block is the layout this doc replaced, not the current one.** `tb assets describe` became
> `tb info assets` and `tb unpushed` became `tb check unpushed`, both in the phases below. It is
> kept because the argument does not read without it. For what the CLI is *now*, see
> `docs/CLI.md`, which is generated from the command tree and cannot fall behind.

`tb doctor` and `tb unpushed` are top-level because nothing else fits them, not because they
belong there. `tb assets` mixes a read verb and a write verb under one word. Three more groups
are specced but unbuilt (`tb home`, `tb brief`, `tb mcp serve`), plus a parked one (`locations`)
and a blocked one (`asset-remote`). Adding them under the current scheme produces a flat list of
eight or nine top-level words with no principle telling you which one a new command joins.

The failure this prevents is the one every operator CLI hits: **the surface grows by accretion,
each command lands wherever it was convenient that day, and after twenty commands nobody — human
or agent — can predict where a verb lives.** jam.sense is at ~24 top-level groups and reaches for
`jam --help` constantly. That is survivable in a repo you are cd'd into all day. `tb` is run from
anywhere, at odd moments, often by a Claude session that has to *guess* the verb from a name.

There is a second, sharper reason. CLAUDE.md commits the MCP surface to **read-only by default,
with writes behind an explicit allowlist**. Under the current grouping that allowlist is a
hand-maintained list of command paths, and every new command is an opportunity to forget to add
one. A taxonomy that puts every mutation behind a single group turns that list into a rule.

## Shape

**The organizing axis is mood — what the command does to the world — not domain.**

| Group | Mood | Answers | Writes? |
|---|---|---|---|
| `tb run` | imperative | *do this now* | **yes**, always through the ledger |
| `tb auto` | temporal | *what runs itself, and what did it do* | schedules only |

Two words. A new command joins by answering one question: does it act, or schedule?

**This said four until Round 2, which retired `info` and `check`.** The rest of this section is
left as written, because the argument for grouping by mood never depended on how many moods there
are — and the two that remain still divide exactly the way it says.

A fifth mood — `tb brief`, *what needs me* — was specced here and **cancelled before
implementation**; see Phase 4. Bare `tb check` absorbed the useful half of it.

### Why mood and not domain

Domain-first (`tb assets`, `tb home`, `tb net`, `tb repos`) is the more common shape and the one
this repo started with. It is rejected because the domain axis is the one that grows without
bound — every new piece of hardware or service is a new group — while the mood axis is closed at
five. Grouping on the closed axis keeps the tree shallow.

The cost is real and is stated here so it is not rediscovered as a bug: **domain discovery gets
worse.** "Everything about my Pis" is spread across `tb info assets`, `tb check drift` and
`tb run asset-refresh`. Mitigation is that `tb info <domain>` is the obvious entry point and its
help text names the sibling verbs. Domain-first has the mirror problem — "everything scheduled"
spread across every group — and since there will be more domains than moods, mood-first is the
shallower of the two.

### `check` is a real group, not a junk drawer

The first draft of this had `tb misc` for the commands that fit nowhere. That is a junk drawer,
and junk drawers only grow.

`doctor`, `unpushed`, and the read half of `assets update` are not miscellaneous — they are the
same shape: **read state, judge it against an expectation, return a verdict, exit 3 when it is
bad.** That shape is already encoded in the output contract, where a row carrying `ok` renders as
a status list rather than a mapping. The group exists implicitly in the renderer; `check` names
it.

Naming it pays for itself immediately. **Bare `tb check`, with no subcommand, runs every
registered check and reports worst-first** — the rollup stops being a feature to design and
becomes a property of the group existing.

### Every mutation is recorded

`tb assets update --apply` writes the inventory. Folding `assets` under `info` as-is would put a
write verb inside the group whose whole value is that it has none.

The resolution is to move the write, not to weaken `info`. Refreshing the register is *already* a
job — `asset-drift` has been running at 09:00 since it was built. So:

- `tb info assets` — read the register
- `tb check drift` — derived vs recorded, verdict only
- `tb run asset-refresh` — the write, through the ledger

The property that falls out is the point of the whole design: **the only path that changes state
is `tb run`, and `tb run` always writes a ledger entry.** Nothing can quietly modify this machine
without leaving a record, because there is no other door.

That collapses the MCP allowlist from a maintained list into a rule: `info`, `check` and
`auto`'s read verbs are unconditionally safe; `run` is the single gate. A command added next year
is safe or gated by virtue of where it lives.

### `run` and `auto` are two moods over one object

A job definition is a noun. `tb run <job>` is the imperative mood over it; `tb auto` is the
declarative. `tb auto run` therefore goes away — it was the imperative hiding inside the
declarative group.

`run` also earns top-level billing by gaining something nothing currently does:

```
tb run -- ./some-long-thing --flag        # ad-hoc, still gets a lane
tb run --lane committing -- ./migrate.sh
```

Ad-hoc work gets the lane lock, timeout, ledger entry and log file that today only *defined* jobs
receive. That is the new capability, not just a rename.

One rule follows: **job definitions invoke leaf verbs, never `tb run`.** A `run:` of
`[tb, run, ...]` would write two ledger entries for one execution.

### What this settles in advance

`tb home` needs no top-level group. CLAUDE.md already forbids actuation — security and locks are
read-only from `tb`, no exceptions — so every Home Assistant command is descriptive or
evaluative: `tb info home` for sensors and armed state, `tb check home` for the
*reports-clear vs cannot-see* distinction that CLAUDE.md calls out. A group that can only read
does not need to be its own group.

`tb mcp serve` stays top-level. It is a daemon, not an operation, and is in none of the five
moods. That is the honest exception rather than a hole in the scheme.

**Does not do:**

- **No aliases beyond `tb doctor`.** One well-known word is kept pointing at `tb check tools`
  because it is a cross-tool convention worth honoring. Every other old path is removed outright,
  not deprecated. This CLI has one user and 24 commits of history; a deprecation layer would
  outlive the muscle memory it protects.
- **No change to the output contract, the ledger format, or the job YAML schema.** This is a
  regrouping of existing commands plus one new verb. If a phase below starts editing
  `cli/output.py`, the scope has slipped.
- **No new domains.** `tb info net`, `tb check home` and friends are named here to prove the
  taxonomy holds, not to be built by this feature.
- **Does not touch installed timers' schedules.** Two job YAMLs get a new `run:` argv; the
  calendar expressions are untouched and reinstall identically.

## Phases

Each phase is independently commitable and leaves the repo working.

### Round 1 — group by mood (2026-08-19)

#### Phase 1 — `check`, and `doctor` and `unpushed` move into it

- [x] Add `cli/check.py` with a `check` group
- [x] Move `cli/doctor.py`'s command under it as `tb check tools`; keep `tb doctor` registered as
      a top-level alias to the same callback
- [x] Move `cli/unpushed.py`'s command under it as `tb check unpushed`
- [x] Bare `tb check` (no subcommand) runs every registered check, worst-first; `--list` names
      them without running. A check that raises degrades the rollup rather than failing it — one
      broken check must not hide the others. Exit code is the worst verdict across all of them
- [x] Update `jobs/unpushed-audit.yaml` `run:` to `[tb, check, unpushed]`
- [x] Update `jobs/doctor.yaml` `run:` to `[tb, check, tools]`
- [x] Reinstall both timers; confirm `tb auto windows` still reports 0 collisions
- [x] Update `tests/test_doctor.py` and `tests/test_unpushed.py` invocation paths

#### Phase 2 — `info`, and the assets split

- [x] Add `cli/info.py` with an `info` group
- [x] `tb assets describe` becomes `tb info assets`
- [x] Split `cli/assets.py`'s `update`: the comparison half becomes `tb check drift`, the
      `--apply` half becomes the callback behind a new `jobs/asset-refresh.yaml`
- [x] `tb check drift` takes no write flag at all — the flag was the seam
- [x] Retire the `tb assets` group registration; `cli/assets.py` stays as the section library
- [x] Update `jobs/asset-drift.yaml` `run:` to `[tb, check, drift]`
- [x] Update `tests/test_assets.py` and `tests/test_assets_update.py`

#### Phase 3 — `run`

- [x] Add `cli/run.py`; move `tb auto run`'s implementation to `tb run <job>`
- [x] Add the ad-hoc form: `tb run [--lane L] [--timeout N] -- <argv>`
- [x] Ad-hoc runs land in the ledger under a synthesized name (`adhoc:<program>`) so
      `tb auto since` shows them alongside defined jobs
- [x] Remove `tb auto run`
- [x] Reject a job definition whose `run:` starts with `tb run` at parse time, with the
      double-ledger reason in the error
- [x] Tests: ad-hoc run acquires the lane, records on timeout, records on refusal

#### Phase 4 — `brief` — **CANCELLED 2026-08-19, not built**

Cancelled before any code was written. The open question below resolved by collapse: the
verdict-rollup half moved into bare `tb check` (Phase 1), and what remained — appending what
`auto` ran overnight and what is overdue — is `tb auto`'s data, not a fifth mood. If that rollup
is wanted later it belongs in `tb auto status`, or in a `tb brief` specced on its own terms. It
does not belong to this feature.

- [x] ~~Add `cli/brief.py`~~ — cancelled
- [x] ~~Append what `auto` ran since yesterday and anything overdue~~ — cancelled
- [x] ~~Decide whether bare `tb check` and `tb brief` stay distinct~~ — resolved by cancelling

#### Phase 5 — settle

- [x] Update the CLAUDE.md scope table to the four groups, replacing the current one
- [x] Record the mood axis and the every-mutation-is-recorded property in CLAUDE.md § Conventions
- [x] Regenerate fish completions
- [x] Full suite green

### Round 2 — strip to two moods (2026-08-20)

`tb info`, `tb check` and the `tb doctor` alias are removed, with everything behind them. What is
left is `tb run`, `tb auto` and the `tb tui` surface.

**This reverses Round 1's central claim, and the reversal is narrower than it looks.** Round 1
argued the organizing axis should be *mood* rather than *domain*. That argument is untouched — it
was never an argument that there are exactly four moods, and the two that remain divide exactly
the way Round 1 says they do. What Round 1 got wrong was treating "describe" and "judge" as
load-bearing peers of act and schedule. `tb info` carried one command. `tb info home` and
`tb info net` appear in this doc's own *"Does not do"* as things "named here to prove the taxonomy
holds, not to be built by this feature" — and they never were. A mood justified by commands that
never arrived is a category with a population of one.

**What it costs, stated plainly, because it is easy to reverse by accident later:**

- Nothing reports what this machine *is*, and nothing judges it. `tb info assets`, `tb check
  drift` and the whole 900-line `cli/assets.py` collection layer are gone, along with the
  `asset-seed` and `asset-refresh` tasks. The machine inventory is not stale; it is simply not a
  thing tb does.
- **Watches are gone entirely.** This is the coupling worth understanding: `cli/watch.py` enforced
  that a watch may only name a read verb, and the read groups *were* `check` and `info`. Remove
  both and no valid watch command can exist. Watches could have been pointed at `auto`'s read
  verbs instead; the decision was to remove them rather than relocate them. The rail keeps LANES,
  NOW and RECENT.
- `tb doctor` goes with `tb check tools`. There are no aliases left.

**The write property is unchanged and now trivially true.** `tb run` was the only door that
writes; `auto`'s `install`, `uninstall` and `prune` are its declared write verbs and everything
else in `auto` reads. The MCP story simplifies with it — the read surface is `auto`'s read verbs,
and `run` is the gate. `tests/test_taxonomy.py` still asserts all of it, and gained a test that
the retired modules are really *gone* rather than merely unregistered: a leftover module keeps
importing, keeps passing its own tests, and reads to a future session as a command that exists.

**Five feature docs were deleted rather than archived**, on the reasoning that a doc for a
subsystem that no longer exists is a map of a demolished country: `machine-baseline`,
`asset-drift`, `asset-remote`, `pinned-watches`, and `bookmarks` (which proposed `tb info
bookmarks`). `locations` survives — it is about tidying `~/Downloads`, never depended on any of
this, and now has no group to live in.

- [x] Delete `cli/info.py`, `cli/check.py`, `cli/doctor.py`, `cli/unpushed.py`, `cli/assets.py`,
      `cli/watch.py` and their six test files
- [x] Unregister `info`, `check` and the `doctor` alias
- [x] Drop `asset-seed` and `asset-refresh` from the run registry
- [x] Strip watches from the surface: rail pane, launch cards, reload, expansion
- [x] `init_home` scaffolds `jobs` only; delete the inventory and watch templates
- [x] `MOODS` is two; add a test that the retired modules are gone, not just unregistered
- [x] Delete the five obsolete feature docs
- [x] CLAUDE.md, README.md and `docs/CLI.md`; regenerate both generated blocks

**Does not do.** Does not remove `tb tui` — it is a surface, not a mood, and it renders what is
left. Does not relocate any removed capability: this is a deletion, not a migration. Does not
touch the ledger, the output contract, the job schema, or `$TB_HOME/jobs`.

## Notes

**Round 2 — the strip (2026-08-20).** The blast radius was mapped before anything was deleted, and
two couplings were not visible from the command list.

*Watches.* `READ_GROUPS = ("check", "info")` meant deleting both groups silently invalidated every
watch definition — the feature would not have errored, it would have become unusable while looking
fine. Worth remembering as a shape: **a rule expressed as an allowlist of other things dies when
those things do**, and nothing in its own module says so.

*The home scaffold.* `init_home` seeded `inventory/`, `jobs/` and `watches/`. Two of the three had
nothing left to hold, so it seeds `jobs/` alone and their templates went with them.

`cli/assets.py` was 901 lines but only ~13 belonged to `tb info assets`; the rest served
`tb check drift` and the two run tasks. So "delete the info command" never implied deleting the
subsystem — that was a separate decision, taken once the inventory would otherwise have been
write-only.

About 35 tests failed at the midpoint, and most were not testing the deleted features at all: they
used `check --list` or `info assets` as a *convenient real command* to dispatch. That is a
reasonable thing for a test to do, and it means the suite's coupling to the command surface is
much wider than the tests explicitly about the command surface. They point at `auto list` and
`auto status` now.

**Phase 1.** The check bodies had to be split from their Click commands
(`check_tools`, `check_unpushed`) so the rollup can invoke them without a Click context. Both keep
default arguments, and a test asserts that every registered check is callable with none — a check
whose body required a parameter would otherwise break the rollup at runtime rather than at import.

`tb doctor` and `tb check tools` share one Command object, so they cannot drift. They *do* report
different `command` names in the envelope ("doctor" vs "check.tools") because `emit` derives the
name from the invocation path. That is correct rather than a wart: an MCP consumer wants the verb
it called, not the implementation underneath. Tested both ways.

The existing `tests/test_doctor.py` needed no change at all — it invokes through the root group as
`["--json", "doctor"]`, which the alias still serves. That is the deprecation layer this feature
said it did not want, arriving for free on the one word worth keeping.

**Phases 2 and 3 were built in the order 3 then 2.** Phase 2 moves the inventory writes out of
`tb info`, and they have nowhere to go until `tb run` exists. Building Phase 2 first would have
left `--seed` and `--apply` unreachable, which breaks the rule that every phase leaves the repo
working.

**Phase 3 needed a way to run tb's own writes.** A job's `run:` is argv, so an internal write has
to be argv too — which meant either a hidden write verb in the Click tree (a hole in the exact
property this feature exists to create) or a schema change (excluded by *Does not do*). Neither
was needed: `tb run` grew an **internal-task registry**, Python callables invoked in-process with
the same lane, ledger shape and log as a subprocess job. `asset-seed` and `asset-refresh` are the
first two. Nothing in the Click tree can write.

Internal tasks deliberately have **no timeout**. A timeout bounds a foreign process whose runtime
you cannot know; an internal task is tb's own code, and `rewrite_derived` does textual surgery on
a YAML file where a SIGALRM halfway through leaves the inventory truncated. Finishing is safer
than bounding.

**Ad-hoc mode is selected by `--lane`, not by a bare `--`.** Click consumes the separator, so it
cannot be detected reliably from inside the callback. Requiring an explicit lane turned out to be
the better rule anyway: the whole value of routing loose argv through tb is the lane lock, and
defaulting to `read-only` is precisely the guess that lets an ad-hoc migration run underneath a
committing job.

**`jobs/asset-refresh.yaml` was specced and not created.** Applying inventory drift stays manual.
The git diff of `inventory/` *is* the maintenance log — a timer that silently rewrote the derived
block would erase the history the file exists to keep. `tb check drift` is the scheduled half and
reports; the human applies.

**A test failed and was right.** `test_adhoc_name_cannot_collide_with_a_job_name` asserted that
`adhoc:` was a reserved namespace because a job name must equal its filename stem. A colon is
legal in a Linux filename, so `jobs/adhoc:echo.yaml` loaded fine and would have sat in the ledger
indistinguishable from an ad-hoc run. `parse_job` now refuses a colon in a job name, which makes
the claim true instead of incidental.

**`tests/test_taxonomy.py` is the ratchet.** It asserts the top level is exactly the four moods
plus the alias, that no command under `info` or `check` exposes a write flag (`--apply`, `--seed`,
`--fix`, …), that no internal task leaked into a read group, and that every `check` subcommand is
in the rollup registry. The taxonomy is only worth having if drifting out of it fails a test.

**One stale fact fixed in passing:** CLAUDE.md § Conventions still documented partial as exit `2`.
It has been `3` since the output contract shipped, for the reason recorded there — Click uses 2
for usage errors.

**Phase 4 (`tb brief`) was cancelled before implementation.** The open question the spec carried
— whether `brief` was distinct from a bare `tb check` — was answered by dropping it. Two commands
that agree 80% of the time is how a CLI teaches people not to trust its distinctions.

The consequence, decided here rather than left implicit: **bare `tb check` runs every check**
rather than listing them. Listing moved to `tb check --list`. Something had to fan out across all
checks, and with `brief` gone the check group is the only sensible home for it.

CLAUDE.md's scope table still lists `tb status` / `tb brief` as a read-only fan-out. Phase 5
replaces that table; the fan-out survives as bare `tb check`.
