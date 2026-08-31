---
status: complete       # draft | active | complete — the directory follows this
created: 2026-08-29
updated: 2026-08-29
agent_value: 3         # three rounds shipped; the path form, the kind and the variance rule
key_files: [cli/data.py, cli/capture.py, cli/view.py, tests/test_data.py, tests/test_view.py]
---

# Reading a file of records as data

## Why

The richest artifact sky.boss can currently see is one it cannot read.

`~/src/sl-agent-logs/<slug>/ledger/` holds the structured record of what a
project's automation did — for jam.sense, `runs.jsonl` is 1,042 rows and growing daily,
one JSON object per line, already shaped exactly like a table:

```
{"job": "release", "started": "2026-08-29T14:10:43+00:00",
 "finished": "2026-08-29T14:10:44+00:00", "duration_s": 1, "rc": 0, "status": "skipped"}
```

Six fields, every row, no nesting. `job` and `status` are the two columns anyone would
scan; `duration_s` is the one that answers "is this getting slower"; `started` sorts it.
This is not a log that happens to be parseable — it is a table that happens to be stored
one row per line, and it is the artifact the whole state-root convention exists to
protect.

sky.boss has no way to open it. `sb data` takes an **argv that prints JSON**, and a file
is neither. The two routes available today are:

```bash
sb data -- jq -s . ledger/runs.jsonl      # spawn jq to turn 1042 lines into one array
sb read -- cat ledger/runs.jsonl          # verbatim bytes, no columns, no view
```

Both make the operator wrap a file in a command to satisfy a contract rather than a
need. The first also quietly asserts that `jq -s` is a *read* — true here, and true only
because the operator happened to pick a safe argv. The second discards the structure that
made the file worth reading.

The gap is sharper than it looks because `sb follow` already settled the principle. A
path is a first-class subject there: `sb follow <path>` runs a native stat cursor and
`cli/follow.py` owns the dispatch between a path and an argv. Following a file needed no
argv; reading one should not either.

**What it unlocks, concretely.** `sb data` already has the machinery — a view that picks
columns, a header that says what arrived, and the refresh cadence a window needs. Point
it at a ledger and "which jobs ran last night, how long did they take, which came back
red" becomes a table that a canvas window can keep fresh. Today that question needs `jq`
and an eye.

## Shape

`sb data <path>` — the same dispatch `follow` already performs, extended to the one other
command that consumes structured input.

**A path is inherently a read, and that is the load-bearing part.** `cli/data.py` explains
at length why `data` is a separate command from `run`: `run` acts, so it may never be
given a refresh cadence, and `data` is *"the operator's declaration that the argv is a
read, which is what makes it safe to pin."* A file cannot be executed. The declaration
that justifies the whole command is satisfied by the argument's type rather than by the
operator's promise — which makes the path form **more** defensible than the argv form,
not a relaxation of it.

**JSONL is a parsing contract, not a guess.** `--from` already names the contract, and
`cli/data.py` is emphatic that *"the contract does not move: parsed data or a failed
contract, never carried bytes."* So `--from jsonl` is the honest spelling, with a
malformed line counted and named the way a missed capture already is — never silently
skipped.

That last point is not a detail. A ledger row that fails to parse and is silently dropped
does not read as corruption; it reads as *"that job never ran"*, which is
indistinguishable from a job that genuinely did not fire, and is the precise question the
ledger exists to settle. Whatever this feature does with a bad line, it must not be
silent about it.

**Does not do:**

- **Not a tail.** `sb follow <path>` owns watching a file change. This opens one and
  returns rows. If a window wants both, that is composition, not one command.
- **Not a query language.** No filtering, no aggregation. `--cols` picks columns and the
  view decides how to draw them, exactly as it does for argv reads today.
- **Not schema-aware.** It does not know what a "run" is, and must not. The state-root
  contract is a *layout* convention — six class directories — not a schema, and a reader
  that learned jam.sense's field names would be reading one repo rather than a shape.
- **Not an inference engine for the row container.** JSONL is a bare sequence of objects,
  so `--rows` has nothing to point at. If a `.json` file with a wrapping mapping is ever
  in scope, it takes the existing `--rows` rules unchanged.
- **Not a splitter.** A file of variant records is reported as variant and drawn whole. A
  `--where kind=run` would be the query language the bullet above rules out, arriving
  through a side door.

### Variance — when the union is a shape nothing has

`columns_of` already unions keys across every row rather than reading them off the first,
and `ledger/runs.jsonl` is the case it was written for: 1,047 of its 1,048 rows carry six
fields and **exactly one** carries three more — `reason`, `refusal_streak`,
`ungated_commits`, the record of a refusal. Reading columns from the first row would drop
all three from the one row anyone would go looking for.

The union stops being an answer when the shapes genuinely disagree. `ledger/decisions.jsonl`
is an event log with a `kind` discriminator — four kinds, **ten distinct key-sets, thirty
union keys** — and `shape()` returns **25 visible columns**: a table no renderer can draw and
no operator can read.

The discriminating question is not *do the rows differ* but **is the union a row that
exists?** In `runs.jsonl` the rare shape is a *superset* of the common one, so the union is
nine columns and every one is a field some real record carries. In `decisions.jsonl` the
widest single record has sixteen fields and the union has thirty — the header describes a
record that was never written.

So the rule is `union > widest single shape`. Measured against all six row-bearing files in
the tree, it fires on `decisions.jsonl` and stays silent on every other. A warning that also
fired on `runs.jsonl` would be worse than none: it would teach the operator to skip the line
that matters.

**This reports; it does not fix.** Splitting by discriminator is filtering, and `--cols` is
already how a wide table gets narrowed. What the operator cannot do today is understand
*why* it is wide.

### The ruling — `sb data <path>`, same verb

**Settled 2026-08-29 by the sky.boss session, which owns it.**

`data`'s docstring does make the operator's choice of command the assertion, but it gives a
*reason* for it: **"sky.boss cannot tell the difference by inspection and does not try."** The
assertion has to live in the verb because an argv is opaque — nothing about `jq -s .` tells you
whether it reads or writes.

A path is not opaque. It is not executed, so there is no write to be uncertain about, and the
premise the rule rests on does not obtain. This form needs no exception carved for it; the rule's
own justification retires it. That is a narrower claim than "the argument's type satisfies the
declaration", and it is the one that holds — inspection works here, so the reason for refusing to
inspect is gone.

`cli/follow.py:46`'s `is_file_form()` is the dispatch model, and the precedent is *stronger* for
`data` than it was for `follow`. Follow's two forms run genuinely different machinery, which is why
[[file-follow]] has to say "the file cursor owns files; the process stream owns commands" to keep
them apart. Both `data` forms produce the same thing: parsed rows and a view. One verb covers less
ground here, not more.

## Phases

### Round 1 — the path form, one contract (2026-08-29)

- [x] Settle the verb question — `sb data <path>`, ruled above.
- [x] Dispatch a path argument to a file reader, mirroring `cli/follow.py`'s split.
- [x] `--from jsonl`: one object per line, blank lines skipped, malformed lines counted
      and named in `warnings` rather than dropped.
- [x] A file whose lines *all* fail to parse is a failure, not an empty table — the rule
      `capture` already follows. An **empty** file is not: `Captured.matched_nothing` is
      `total > 0 and not rows` precisely because "the tool printed nothing" is a real
      answer, and so is a ledger with no runs in it yet. Corrected mid-round; see Notes.
- [x] `--cols` and the existing view path work unchanged against the result.

### Round 2 — the cadence, settled (2026-08-29)

- [x] A path read on a cadence **re-reads the whole file** each tick, and says so.

Re-reading is the answer rather than a concession to one. A partial re-read means holding a byte
offset between ticks, and a cursor held across ticks is precisely what `sb follow <path>` already
is — building one into `data` would put the same mechanism in two commands and blur the line the
"Not a tail" bullet draws. `data` stays stateless: every tick is a whole read that stands alone,
which is also what makes pinning one safe.

The cost is real and bounded: `runs.jsonl` is 150 KB at 1,042 rows. If a ledger ever outgrows what
a tick can afford, the answer is a bound on rows read — `MAX_ROWS` has a precedent — not a cursor.

### Round 3 — a union no record has (2026-08-29)

- [x] `shape()` counts distinct record shapes and records the count only when the union is
      wider than any single shape — the key is omitted otherwise, so an unremarkable
      payload's envelope is unchanged.
- [x] `warnings_for` says how many shapes there are and points at `--cols`.
- [x] Silent when one shape nests inside another, which is the common case and the one
      where the union is still a real row.

## Notes

### 2026-08-31 — round 4: the torn-read ruling, and why the overnight run could not have answered

**A concurrent append does tear, routinely, and sky.boss already reports it. No change here.**

The question was whether `sb data --from jsonl` can read a ledger while jam.sense is appending to
it and get a truncated final line. Two overnight detectors were run against the live ledger — 46
appends on 2026-08-29, then 91 more across 22h48m ending 2026-08-31 — and both returned `torn: 0`.
The second was built to fix the first's defect (it counted how often it *caught* the file
mid-record, not just how often it looked) and returned `partials: 0` as well. The carry-over had
pre-committed to reading that as *no evidence* rather than *safe*, and that was right — but it
under-stated the problem. **The run was not merely inconclusive; it was structurally incapable of
concluding anything**, and the arithmetic below says by how much.

**What settled it was a forcing test with a positive control**, not more sampling. Two changes make
a null readable. Records are a **fixed** length, so any observed size that is not a multiple of it
is proof the reader caught a write in flight — with real variable-length records, a size that is
not a record boundary is unrecognisable, which is why the overnight detector could not count its
own looking. And a **control arm** writes torn on purpose — the record in one `write`, the newline
in a second — so a zero from the real arm becomes evidence that the mechanism is atomic rather than
evidence that the reader is too slow to see it. Both arms ran on the same filesystem as the state
root, at 8,209 bytes per record, straddling the 8,227-byte maximum append actually measured on
`decisions.jsonl`.

The real arm writes byte-for-byte what jam.sense writes — `open("a")` then one `write` of
`json.dumps(entry) + "\n"`. Twenty seconds each:

| Arm | appends | caught mid-write | unparseable tail |
|---|---|---|---|
| control — torn on purpose, two `write` calls | 22,469 | 25,164 | **4,803** |
| real — one buffered `write`, as the ledger does | 22,649 | 23,251 | **4,833** |

**The two arms are indistinguishable.** A single `write(2)` of 8 KB tears exactly as readily as a
deliberately split one: the kernel makes the file grow in sub-record steps and a reader between
them sees a truncated JSON line. The one tearing mode that *was* ruled out is a second syscall —
the buffer is 128 KiB here, confirmed by checking the on-disk size before the handle closes, so
everything under that goes out in one call. It does not help, and that is the finding.

**The odds the overnight run was up against.** The torn state persists **0.80 µs per append**
(measured as a duty cycle: 24,447 of 26,954,633 stats landed off a record boundary). Against a
500 Hz sampler that is a 1-in-2,500 chance per append. Round 2 saw 91 appends, so its expected
catch count was **0.036** — it would have had to run about **26 nights** at that append rate to
expect a single one. Both nights together expected 0.055. `partials: 0` was overdetermined, and no
amount of the same measurement would ever have moved it.

**What sky.boss does with a torn line, verified by running it rather than by reading it.** A file
whose last line is cut mid-record:

```
● data  table · 4 rows · 3 columns
⚠️  1 of 5 lines not a JSON object — first: '{"job": "j4", "status": "ok", "at": "2'
```

The row is counted, sampled and warned about, the warning rides the envelope, and the exit is 0.
That is `parse_jsonl` behaving exactly as its docstring argues it must — a dropped ledger row *"does
not read as corruption, it reads as that job never ran"* — and the argument was written against a
hypothetical. It is not hypothetical.

**A settle-and-retry is rejected**, and it is the change someone will propose. It would convert a
counted, sampled, visible warning into a silent success, which is *worked fine, told nobody*
installed deliberately: sky.boss cannot tell a line that is 0.8 µs from complete from one that is
corrupt, and the two want opposite conclusions. The warning also costs nothing in practice — at
this duty cycle a real ledger read hits one about once in 27,000 nights.

**`sb follow` answers the same bytes differently, and both are right.** `cli/filefollow.py` holds a
partial final line until its newline arrives and never emits half. The asymmetry is the contract,
not an inconsistency: a follow's next read is guaranteed to come, so waiting costs nothing, while a
`data` read *is* the answer and has nothing to wait for. See [[file-follow]].

**Nothing is owed to jam.sense either**, and this is worth saying so nobody fixes it. Its writer is
already the right shape; an `os.write` on an `O_APPEND` descriptor would not help, since a single
syscall is what was just measured tearing. The only remedy that works is write-to-temp-and-rename —
which `decision_ledger` already does for its trim — and buying it for every append would cost the
producer real work to spare the consumer a warning the consumer wants.

**Confirmed independently from the other end, which is the part that makes it a seam result.**
jam.sense had installed warn-and-skip in its own reader before this test existed — `read_jsonl`
returning `(entries, skipped)` with one definition imported rather than copied, and a `warn_skipped`
on stderr — reasoning from the producer side while this reasoned from the consumer side. Neither was
reading the other. What the measurement added, in their words: they knew a bad last line was
*possible* and had it filed as tolerable-but-notable; the numbers establish it is the **normal** case
at these record sizes, which upgrades the warning from *something odd happened* to *you read this
ledger while a job was appending*. They reject the writer-side remedy for a reason of their own that
is better than the one above — no write in `decision_ledger` may raise, because it instruments the
agent stage itself.

**Their dedupe is right for them and would be wrong here, so the difference is now a test rather
than an accident.** `warn_skipped` keys a module-level set on the path, so a process warns once per
file and goes quiet about every later tear — correct for a short-lived job, and incorrect for a
resident consumer, where a warning that fired only on tick 1 would tell a watcher the ledger had
gone clean. sky.boss is on the right side of it today only because nothing in the read path holds
state: `_once` builds a fresh `Result` per tick, verified on both residency paths — three NDJSON
envelopes down a pipe each carried the warning, and the terminal render redrew it every tick.
**That is inherited from process lifetime, which is exactly the kind of property that changes when
someone makes a reader long-lived for performance**, so `test_a_torn_tail_is_reported_on_every_read_not_once_per_file`
pins it: both reads run in one process, so a `_WARNED` set of ours would survive between them.

**Whether the producer also warns is not knowable from the file, so the account is never redundant
by design.** Where a producing reader warns, sky.boss's count duplicates it; where it does not,
sky.boss's count is the whole account — and which of those holds flips per file, from the
producer's own routing, with nothing in the bytes to say which. That is the case `parse_jsonl`
sharing `Captured`'s account was built for, and it does not depend on any particular producer's
state.

*This paragraph first named three of jam.sense's ledgers as skipping silently —
`queue_deferrals.jsonl`, `implement_ready_plans.jsonl` and tree_lock's `history.jsonl`. They closed
all three in `02c598fc7` about an hour later (five readers now share `read_jsonl` +
`warn_skipped`), so the sentence was false within the hour and never shipped. Left visible because
the correction is the more useful half: **the instances were the staleable part and the property was
not**, which is § Feature workflow's own rule about linking rather than copying, arriving from the
direction of a fact instead of a doc.*


### 2026-08-29 — three rounds, and two things the suite decided

**The file-form rule is not `follow`'s, and the suite is what said so.** Reusing
`cli/follow.py`'s `is_file_form` outright broke
`test_a_missing_command_fails_rather_than_raising` immediately: follow treats a bare word that no
executable answers to as a *file*, because `sb follow new.log` has to be legal before the log's
first write. That reasoning does not survive the trip. A file with no records has no rows to
return, so there is nothing to wait for, and `no such command` is the true sentence where
`no such file` is a confident wrong one. `data` keeps the two rules the commands agree on — a
separator means a path, an executable beats a bare word — and diverges on the fallback only.

Worth noting *how* it was caught. The collision was invisible in the diff and obvious the moment
the suite ran, which is the case the CLAUDE.md line about testing decisions rather than ceremony
is describing: the test existed because someone decided a missing command should be named, and it
held that decision against a change made two features later.

**"Zero rows is a failure" was over-broad, and Round 1 said it in its own words.** The bullet cited
`capture`'s rule as its justification while stating something wider than that rule: `matched_nothing`
is `total > 0 and not rows`, and the `total > 0` is deliberate — "the tool printed nothing" is a
real answer. For a file it is *more* obviously real, because a ledger with no runs in it yet is
what every project has on its first day. Corrected in the bullet, with the reasoning, rather than
quietly implemented the other way.

### 2026-08-29 — round 3, and the number that made it a rule

The variance warning started as "warn when the rows disagree" and would have been noise. jam.sense's
`runs.jsonl` has two shapes across 1,048 rows, and firing on it would have trained the operator to
skip the warning line — on the file where the rare shape is the record of a refusal.

What made it a rule is a measurement rather than a judgement. Across all six row-bearing files in
the state root:

| File | rows | shapes | union | widest | fires |
|---|---|---|---|---|---|
| `decisions.jsonl` | 411 | 10 | 30 | 16 | **yes** |
| `runs.jsonl` | 1048 | 2 | 9 | 9 | no |
| `implement_ready_plans.jsonl` | 23 | 1 | 7 | 7 | no |
| `queue_deferrals.jsonl` | 31 | 1 | 6 | 6 | no |
| `memory/agent_task_queue.json` | 12 | 1 | 6 | 6 | no |
| `product/decisions.json` → `records` | 11 | 1 | 19 | 19 | no |

`union > widest single shape` separates them exactly, and it says something rather than fitting the
data: it fires when the header describes a record that was never written. Where one shape nests
inside another the union is still a real row, which is the `runs.jsonl` case and the reason that
file is the one this must stay quiet about.

**A second suppression arrived from rendering it, not from designing it.** With `--cols kind,job,at`
the warning read *"10 record shapes here, so these 3 columns are a union no single record has"* —
false, and recommending the flag the operator had just typed. `cli/view.py` already refuses to name
a column back at someone who typed `--drop` for it, and this is the same rule. The count stays on
the view, where a surface can still draw it; the prose goes.

### 2026-08-29 — what did not need building

The audit that opened this doc looked at all six state classes and only `ledger/` warranted code.
`input/` is 2.1 MB of what jam.sense feeds its jobs rather than a record of what happened, and
reading it would be reading a sibling's internals rather than its published state. `memory/` is
four different things in one directory — row lists, state objects, bare SHA files, pip freezes —
and its one table-shaped member arrives free through the path form. `product/` needed nothing:
`find_rows` already refuses `decisions.json` correctly, naming both candidate lists rather than
picking one.

Two things were checked *because they looked wrong* and turned out right, which is worth recording
so nobody re-opens them. `_is_prose` sends `title` out of the table for jam.sense's task queue,
which looks like it is hiding the one scannable column — median title there is 88 characters and
the classification is correct, and it is correct because the rule measures values rather than
trusting the name. And the chrome's `N columns` counts the payload's columns while the table draws
the view's; that predates this work and is the intended split.

### 2026-08-29 — where this came from

Raised by the sky.boss session as **S1** while auditing `~/src/sl-agent-logs/`,
the day jam.sense migrated its reporting state out of its checkout. It was one of five
suggestions and the only one on sky.boss's own side that it ranked first, having dropped
two earlier candidates — a highlight rule for the `[job-name]` prefix, and status-line
wording — on the grounds that both were about how output *looks* rather than whether the
richest artifact in the tree can be consumed at all.

Two facts from that audit belong here because they are the reason this is worth building
now rather than later. `ledger/` has **live writers** — four call sites in jam.sense
resolve into it — so the file is growing, not a one-off dump. And the state root is keyed
by the same project slug `~/.sky-boss/projects.toml` already uses, so a ledger path is
derivable from a project sky.boss knows, **once** that file declares a state root; it does
not today, and that is an open request to the operator rather than work either repo can
take.

Deliberately not blocked on it. `sb data <path>` is useful with a path typed by hand and
does not need the registry to exist.

### 2026-08-29 — the constraint that shaped § Does not do

The bullet about not being schema-aware is not caution, it is a finding. The same audit
turned up `state_dir(INFLIGHT, "inflight")` in jam.sense, producing `<slug>/inflight/inflight/`
— a writer that was entirely self-consistent, green in its own suite, and archived
faithfully by the workspace snapshot. It was visible only to a consumer reading the
*published* layout. sky.boss is that consumer, and it is worth being deliberate about it:
a reader that follows the documented shape catches what the producing repo structurally
cannot, and a reader that learned the producer's actual field names would have caught
nothing.

The rule that came out of it, now in `skyrow-workspace/strategy/seams/agent-state.md`: a
listing proves presence, an extraction proves recoverability, and only a consumer proves
the shape.
