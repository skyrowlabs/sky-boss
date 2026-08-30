---
status: draft
created: 2026-08-29
updated: 2026-08-29
agent_value: 2
key_files: [cli/data.py, cli/agentstate.py, cli/view.py]
---

# History — how did this go the last seven nights

## Why

Every observe sky.boss has is *now*. `run`, `read`, `follow`, `data` and `roll-call` all answer a
question about the present, and the one question an operator asks about a nightly job is about the
past: **did this work last night, and the night before?** A single green row says the last run was
fine and says nothing about whether that is normal.

The mockup carries a `history` affordance with nothing behind it, and this item sat blocked for
weeks on the honest grounds that nothing had run twice.

**That changed on 2026-08-29, and from outside this repo.** jam.sense scaffolded its state into the
agent-state root, and `<root>/jam-sense/ledger/runs.jsonl` is **1,055 rows** of exactly what was
missing — one record per run, with `decisions`, `queue_deferrals` and `implement_ready_plans` beside
it. sky.boss can already read it: [[jsonl-reads]] parses a file of records and [[state-root]]
addresses it by project, so `sb data jam-sense:ledger/runs.jsonl --from jsonl` works today.

## Shape

**The item splits, and the split is the decision this doc exists to make.**

- **A provider's history is unblocked and nearly free.** The ledger exists, the reader exists, the
  address exists. What is missing is that nobody would find it: you have to know the project has a
  ledger, know its filename, and know the `--from` and `--cols` that make it legible.
- **sky.boss's own history does not exist and is not close.** Its runs are anonymous and die with
  their window — `docs/open.md` item 6, the primitive the plan and the tower are also waiting on.
  Nothing about reading someone else's ledger supplies it.

**The mockup's affordance was drawn for the second.** So this doc builds the first and says
plainly that it is the first, rather than shipping a `history` button that answers a narrower
question than its label.

**The mechanism is a declared mapping, not a new reader.** Same shape [[schedule]] uses over the
same config file, for the same reason: the operator asserts where the facts are and sky.boss does
not infer them.

```toml
[project.jam-sense.history]
path = "ledger/runs.jsonl"     # resolved under the state root, as an address
from = "jsonl"
when = "started_at"
name = "job"
outcome = "status"
```

**`outcome` is drawn, never judged.** The provider's word is shown as written and never totalled,
ranked or coloured into a verdict — [[roll-call]]'s refusal, which bites here in a way it did not
bite [[schedule]]: a schedule row says *when*, and a history row is exactly the *how it went* that
sky.boss is not entitled to interpret. What sky.boss may do is **order** and **count occurrences of
a string it does not understand**, which is arithmetic rather than opinion.

**A field that disagrees with itself is reported, not resolved.** Measured on the live ledger:
**19 of 39 non-nominal rows exit zero**, because the gate jobs' monitors are dead-man switches on
execution rather than on outcome. So `rc` and `status` genuinely disagree and neither is wrong.
sky.boss draws the declared field and does not reconcile two.

**Does not do:**

- **No sky.boss-run history.** Explicitly. That is item 6 and this doc does not pretend to it.
- **No joining across ledgers.** `runs.jsonl` and `decisions.jsonl` look joinable on `(job, time
  window)` and are not: measured on the live files, there are 6 overlapping same-job run pairs, 1
  decision matching both an `ok` and a `failed` run, and 11 matching none. A join that is wrong 1
  time in 39 is worse than no join, because it is right often enough to be believed.
- **No verdict, no streaks, no "flaky" label.** Counting is arithmetic; naming a pattern is a
  judgment.
- **No retention, no writing, no compaction.** The ledger is the provider's file. sky.boss reads it
  and never touches it — the rule `projects.toml` already lives under.

## Phases

### Round 1 — a project's ledger, addressable and legible (2026-08-29)

- [ ] `[project.X.history]` parsed and validated in `cli/rollcall.py`, unknown keys named the way
      the schedule block's are.
- [ ] `sb history <project>` reads the declared path under the state root and returns the envelope,
      newest first.
- [ ] `--last N` — the only reason to read a 1,055-row file is to look at the tail of it.
- [ ] A project declaring no history is counted in a warning, never drawn as an empty table.
- [ ] Timestamps parsed to an instant for ordering and drawn as the provider wrote them, including
      the offset — the [[schedule]] ruling, which is the same file and the same trap.

### Round 2 — more than one project (not scheduled)

A fold across projects is [[roll-call]]'s shape again, and it needs a second project with a ledger
to be worth anything. jam.sense is the only one today.

### Round 3 — sky.boss's own runs (blocked on item 6)

Named so nobody mistakes round 1 for it.

## Notes

### Round 1 — drafted, awaiting the word (2026-08-29)

Unblocked by something no one in this repo did. The item had said *blocked on evidence — needs jobs
that have run twice* since it was written, which was the right call and would still be the right
call if jam.sense had not scaffolded its state on 2026-08-29. Worth noticing as a pattern rather
than a one-off: **the seam supplied the evidence, and the item's owner was not watching the seam.**

The two measurements that shaped the *Does not do* list were taken against the live ledger while
[[schedule]] was being written, and are recorded there too. Both say the same thing in different
words: the file has more structure than it has *consistent* structure, and every tempting
derivation over it — a join, a verdict, a reconciliation of `rc` against `status` — is wrong often
enough to mislead and right often enough to be trusted.
