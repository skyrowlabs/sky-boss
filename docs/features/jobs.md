---
status: draft
created: 2026-09-01
updated: 2026-09-01
agent_value: 3
key_files: [cli/jobs.py, cli/schedule.py, cli/rollcall.py, cli/helpers.py]
---

# Jobs — sky.boss issues a schedule of its own

## Why

**sky.boss reads six schedules and owns none.** [[schedule]] folds every declared project's rows
into one table, and every one of those rows belongs to somebody else's cron. That is the right
answer to *what fires next* and no answer at all to *make this fire* — so the one thing an operator
cannot do from the tool that watches every grid is add a line to one.

**The operator asked for both, and both is the point.** A provider's schedule stays observed and
untouched; beside it, a schedule sky.boss issues and owns. A job moves from one side to the other
by the operator deactivating it in cron and declaring it here — a handover they perform, not one
sky.boss performs for them.

**This is the redesign the 2026-08-20 strip was for.** `cli/jobs.py`, `jobs/*.yaml`,
`templates/job.yaml` and `docs/features/done/jobs.md` were deleted in `051333c` — *"deletes the job
layer and everything that depended on it, **to design that half over from a clean base**"* — with
all five phases shipped and running. It was not removed for being wrong. What has arrived since is
the base it was to be redesigned on: the `Result` envelope, `$SB_HOME`, `projects.toml`,
[[state-root]], [[schedule]], [[agent-sessions]], [[history]] and the canvas. **Read the deleted doc
before reopening a question** — `git show 051333c^:docs/features/done/jobs.md` — because most of the
mechanism below is its reasoning, re-verified rather than re-derived.

**And it is the answer to a rule that has been quietly waiting.** `CLAUDE.md`: *only a read may be
given a cadence, because re-running a read is a refresh and **re-running a write is a scheduler
nobody asked for.*** That sentence has always described this feature. It is not repealed here — see
Shape.

## Shape

### The line this crosses, and the one it does not

**Execution.** [[fundamentals]] § Cadence: *nothing survives the last window — that is what makes
this a scheduler and not a daemon, and crossing that line is only ever done on purpose.* An
installed job fires with no window open. **This is the crossing, and it is done on purpose**, with a
dated decision beside this doc.

**But sky.boss does not become a daemon, and that is the whole design.** systemd is the daemon.
sky.boss *generates and inspects units*; it does not stay resident, hold a clock, or supervise
anything — the relationship breeze.brain has to Docker. Nothing of sky.boss's own outlives a run.

**The cadence rule is unchanged and was always about windows.** A window may not refresh a write
because a *window* is the wrong owner for a repeating write: it is attention-keyed, it pauses when
you close it, and it would make a scheduler out of something you opened to look at. A job is the
right owner, declared once and installed deliberately. So the rule keeps its force and gains its
missing half: **a repeating write is not forbidden, it is simply not a window's to own.**

**Federation is crossed too, narrowly.** `cli/rollcall.py` keeps *no ledger, no history, no cache*
because a copy of another project's state goes stale without announcing it. A job's ledger is not a
copy of anyone's state: sky.boss is the authority for what sky.boss ran. That is the crossing left
undecided on 2026-09-01 morning, arriving the same day because something now wants it.

### The substrate is systemd, and nothing here reimplements a scheduler

Re-verified on this machine 2026-09-01, not inherited: the user manager runs, `Linger=yes` so units
survive logout, `systemd-analyze calendar` normalises and validates, and `~/.config/systemd/user/`
already holds **five foreign unit files** and three live timers.

That last number is the important one. **`~/.config/systemd/user/` is shared space, not sky.boss's
directory.** Every generated unit is `sb-<job>.service` / `sb-<job>.timer`, and sky.boss never
enumerates, modifies, stops or reports on anything outside that prefix.

**A schedule is validated by systemd, never parsed here.** `schedule = "daily 06:00"` becomes
`OnCalendar=` and is checked by `systemd-analyze calendar`. This is the same refusal [[schedule]]
already makes from the reading side — *a cron expression is opaque and never parsed* — arriving on
the writing side: sky.boss does not own calendar semantics in either direction, and it will not be
wrong about DST because it has no opinion about DST.

### A job

`$SB_HOME/jobs.toml`, a fourth operator-owned file beside `tools.toml`, `formats.toml` and
`projects.toml`.

```toml
[job.asset-drift]
description = "Ask every project how it is, nightly"
argv        = ["run", "--", "sb", "roll-call"]
schedule    = "06:00"            # OnCalendar; systemd validates it
                                 # ("daily 06:00" is NOT valid — systemd said so)
lane        = "read-only"        # advisory mutex; two jobs in a lane never overlap
timeout     = 300
```

**In `$SB_HOME`, not in the repo — and that is a documented reversal.** The deleted design put
definitions in `jobs/*.yaml` *"versioned, so the schedule has a source and the git diff says why it
changed"*. `CLAUDE.md` names that exact argument as the one that was repealed: operator content
lived in this repo and *"carried a tailnet address into every commit, so the tool could not be
published without publishing the operator."* A schedule names what runs on somebody's machine and
when. It is operator content.

**Not a tool with a schedule key**, ruled 2026-09-01. A job has a lifecycle a tool has not —
generated, installed, enabled, drifted — and an outcome history. Sharing `tools.toml` would put
things that *fire on their own* in the rail beside things you *type*, and `--save` writes a tool by
example from a read, where a job is a write with no example to save.

**`argv` starts with a sky.boss command, exactly as a tool's does**, so a job cannot become a second
`sb run` that skips the act/observe split. A job that acts is the normal case and the point; it says
so by starting with `run`.

**`argv` is a list and a shell string is a validation error.** Accepting `sb roll-call | grep x`
would give every job a shell, with its globbing, quoting and injection surface, for no benefit.
Inherited from the deleted design, which had already made this mistake's cost explicit.

### Layering — every row says who owns its clock

`sb schedule` gains sky.boss's own rows beside the providers'. **A row that sky.boss will fire must
never look like a row it merely watched**, so the vocabulary gains one column — `clock`, reading
`cron`, `timer`, or `sb`. Without it the fold is a table of times with two incompatible meanings in
it, which is *worked fine, told nobody* wearing a schedule's clothes.

The rest of [[schedule]]'s rules are unchanged and now apply to two populations: ordering is on the
parsed instant, `next` is provider-supplied — and for a sky.boss job it is **systemd-supplied**,
read back from `systemctl --user list-timers`, never computed here.

### Drift is the safety feature, and it is round 1 rather than a later phase

The handover the operator performs has two silent failure modes, and both are worse than the thing
this feature adds:

- **Double-fire** — sky.boss owns a job and the provider's cron still has it. Two agents on one
  working tree, from one line nobody removed.
- **Never-fires** — cron was deactivated and sky.boss's timer is not installed or not enabled.
  Silence, which looks exactly like a job that ran and found nothing to do.

**So `sb job install` refuses a collision and names it** (ruled 2026-09-01), reading `crontab -l`
and the foreign user units as **opaque text** — never parsed for meaning, never written. `--force`
installs alongside. Refusing is the default because a double-fire in an agentic grid is not a
cosmetic fault.

**The collision is on the *command*, not the clock**, which corrects how this was first written.
*Two things fire at 02:00* is not the hazard; *the same work runs twice* is, and that is what a
half-finished handover leaves behind. Comparing commands also needs no calendar parsed on either
side, where comparing times would need cron parsed on one — so the honest check is the cheaper one.
A payload too short to be distinctive reports **cannot check** rather than clean, because a detector
that counts what it caught and never counts whether it could look answers `0` for both.

**And installed-state is read back, never remembered.** `sb job list` compares what `jobs.toml`
declares against what `systemctl --user` actually reports, and a job that disagrees reads
**`drifted`** — a unit disabled outside sky.boss, a definition edited since it was generated, a
timer that exists with no definition. This is item 9's *read-back drift*, which every cron manager
gets wrong by trusting its own model.

**Never-run and overdue are their own words.** A job that has never run does not read as passing,
and a job whose window has passed does not read as passing. Silence looking like success is the way
a pull-based surface fails, and it is worse than no surface because it is quietly reassuring.

### The ledger

`$SB_STATE/jobs/ledger.jsonl`, append-only, one object per run, plus a captured log per run.
Written from the very first run — a run with no line is indistinguishable from a run that never
happened.

**Five outcomes, not two**: `ok`, `partial`, `failed`, `timeout`, `refused`. The last two are
*recorded outcomes rather than exceptions*, for the reason above.

**Exit codes are the interface**: `0` ok, `1` failed, `3` partial — the envelope's own contract,
finally load-bearing rather than tidy. A job wrapper that had to parse output to decide whether
something needs attention would be the signal that the contract was wrong.

**This is what [[history]] round 3 was blocked on**, and `docs/open.md` item 6 with it: a job's name
is an identity that outlives every window, and the ledger is keyed by it. Round 1 writes the ledger;
reading it back through `sb history` is round 3 there and a round here.

**Lanes are enforced by an advisory `flock`, not by systemd `Conflicts=`.** Verified reasoning from
the deleted design and the single most expensive thing in it: `Conflicts=` *stops* the conflicting
unit rather than waiting or refusing, so a scheduled job would kill a running one — preemption, not
mutual exclusion. A lock in `$XDG_RUNTIME_DIR` also protects a manual `sb job run`, which a unit
directive never would. A job that cannot take its lane records `refused` and does not wait.

This is `docs/open.md` item 7 — the claim — arriving with a mechanism, and it stays inside that
item's **advisory** ruling: sky.boss declines to start *its own* job. It never stops anyone else's.

**Does not do:**

- **Never writes the crontab.** Not a line, not a reorder, not a removal. `CLAUDE.local.md` binds
  this and the boundary does not move: the operator deactivates their own entries. Read as opaque
  busy windows and nothing more.
- **Never touches a unit it did not generate.** `sb-` prefix only, asserted by a test. Five foreign
  unit files sit in that directory today.
- **No remote execution.** Jobs run on this machine.
- **No retry, no backoff.** A failed job is reported, not re-run. Retries hide flapping.
- **No notifier in round 1** — and therefore the ledger *is* the notification surface, which makes
  reading it an obligation of this feature rather than a later nicety.
- **No job authoring by an agent, and no `jobs.toml` write from the surface.** [[tools]] round 4
  argued a surface write is safe because *persistence was already on that side of the boundary* —
  a page past the guard can already append to `tools.toml` via `/api/run`. That argument does not
  transfer: a job fires **unattended and forever**, so writing one is not a command an attacker
  gets once. The canvas may list, inspect and show drift; it may not create, edit, install or
  enable.
- **No parsing of anyone's calendar syntax.** Not cron, not `OnCalendar`. Opaque in, validated by
  systemd, read back from systemd.
- **No sky.boss job for a jam.sense job.** The grid stays jam.sense's until the operator moves an
  entry themselves, one at a time.

## Phases

### Round 1 — a job that runs, records, and cannot double-fire (2026-09-01)

- [ ] `$SB_HOME/jobs.toml` parsed and validated in `cli/jobs.py`: unknown keys named and ignored,
      one bad definition never costing the others, `argv` refused as a string.
- [ ] `sb job list` — every job with its lane, schedule, installed state and **drift**, read back
      from `systemctl --user` rather than remembered.
- [ ] `sb job run <name>` — foreground, honouring `timeout`, mirroring the job's exit code, taking
      its lane's `flock` and recording `refused` if it cannot.
- [ ] Every run appends to `$SB_STATE/jobs/ledger.jsonl` with a captured log beside it — including
      failures, timeouts and refusals. Nothing runs unlogged, in any phase.
- [ ] `sb job install <name>` / `uninstall` — generates `sb-<name>.service` and `.timer`,
      `OnCalendar` validated by `systemd-analyze calendar`. Generating never enables.
- [ ] `install` **refuses a collision** against `crontab -l` and the live timers, naming the
      entry; `--force` installs alongside.
- [ ] A test asserting no generated unit ever references a unit outside the `sb-` prefix.

### Round 2 — layering it into the schedule (not scheduled)

`sb schedule` folds sky.boss's own rows beside the providers', with `clock` saying which is which
and `next` read back from systemd. Separate because round 1 must be correct on its own — a job that
fires wrongly is worse than a job that is hard to see.

### Round 3 — the ledger read back (not scheduled)

`sb history` over sky.boss's own runs — [[history]] round 3, which this unblocks by giving a run a
name that outlives its window.

### Round 4 — the surface (not scheduled)

The canvas lists and inspects, and never writes. See *Does not do*.

## Notes

### Round 1 — drafted, awaiting the word (2026-09-01)

**Opened by the operator, hours after a ruling that said neither line moves.** That ruling is not
wrong and is not being overturned: it answered *what the tower requires*, and the tower requires
nothing — every band reads a provider. This is a separate decision to build something the tower
never needed, and it is the honest reading of the same day's other sentence, that whether sky.boss
may keep a record of its own runs was *"left undecided until something wants it"*. Something wants
it.

**The prior art was found rather than reinvented, and it is unusually good.** All five phases of the
deleted design were shipped and running before the strip, and three of its decisions are load-bearing
here for reasons that were *measured* at the time: `Conflicts=` preempts, a shell string in `run`
buys nothing and costs a shell, and a run with no ledger line is indistinguishable from a run that
never happened. Reusing those is not deference — it is declining to re-learn them.

**One of its decisions is reversed outright**, and the reversal is recorded rather than quietly
applied: job definitions moved from the repo to `$SB_HOME`, because the argument that put them in
the repo — *the git diff is the maintenance log* — is the exact argument `CLAUDE.md` records as
repealed when operator content carried a machine into every commit.

**The riskiest thing here is not the scheduler, it is the handover.** Everything sky.boss runs on a
timer, systemd already does well. What nothing does well is the window in which a job exists on both
sides — and that window is opened by design, since the operator deactivates their own cron. Drift
detection and a refusing `install` are therefore round 1 rather than polish; a layered schedule
without them is a machine that silently runs the same agent twice on one working tree.
