---
status: draft          # draft | active | complete — the directory follows this
created: 2026-08-29
updated: 2026-08-29
agent_value: 3         # five dated decisions and a vocabulary, none of it built
key_files: [cli/rollcall.py, cli/schedule.py, cli/view.py]
---

# The schedule view

## Why

The operator runs several projects whose automation fires on its own clock, and has no way to see
what is about to happen. `CLAUDE.local.md` records the consequence as an instruction to a human:

> jam.sense's committing jobs occupy roughly **00:00–02:45** plus several evening slots. The rules
> for coexisting are in `CLAUDE.md`; this is the schedule they apply to. **Derive it by reading
> `crontab -l` — never copy it into a file, here or there.**

That instruction is right and it is also the whole problem. The fact matters — starting a long job
at 00:30 collides with a grid that will rewrite the working tree — and the only sanctioned way to
learn it is to read a crontab and hold the answer in your head, because writing it down creates a
copy that goes stale. A *view* is the third option: derived on demand, never stored, correct because
it is re-read rather than remembered.

**The data already arrives, and sky.boss discards it.** `jam report status --json` is the source
`~/.sky-boss/projects.toml` already declares for roll-call, and it returns 31 job rows carrying:

```
job, cadence, schedule, last_run, last_age, result, duration_s, overdue,
intentionally_off, unscheduled_reason, scheduled_in_cron, kuma_configured,
report, report_exists, next_run
```

`schedule` is the cron expression. **`next_run` is already computed by the producer.** The
operator's declared `cols = "job,result,last_age,overdue"` throws the rest away at the view layer.
So this needs no new contract with a sibling repo, no new subprocess, and nothing from jam.sense —
the rows are on the wire today and land in `/dev/null`.

**Why this is not [[roll-call]].** Roll-call asks *how is each project* and answers in one block per
project, each in its own words, deliberately refusing a common vocabulary. This asks *what fires
next* and has to answer in **one table across projects**, ordered by time. That is the output shape
roll-call was built not to produce, and the reason it is a separate doc rather than a round.

## Shape

`sb schedule` — an observe, `acts: false`, so a canvas window may pin it and give it a cadence.

### The vocabulary — four fields, and only one of them is sky.boss's business

`name` · `schedule` · `next` · `last`.

Everything else stays the provider's. A row shows what the interface names and the provider's extra
fields are its own — which is [[open]] item 17b arriving in a second place, still unanswered, and
this doc does not answer it either.

**`schedule` is opaque and never parsed.** `15 5 * * *` is displayed exactly as the provider wrote
it. Parsing it means a second implementation of cron semantics living beside the real one, and it
will be wrong about DST before it is wrong about anything else. Same rule as `sb read` showing bytes
verbatim and saying that is what it is doing.

**`next` is provider-supplied or absent. sky.boss never computes it from `schedule`.** Deriving it
is that same second implementation wearing a helpful face — and a *wrong* next-fire time is worse
than none, because it looks like an answer. A project whose source does not carry one has no `next`,
and the view says so rather than filling it in. Nothing needs deriving today: jam.sense supplies
`next_run` for all 31 of its jobs.

### The declaration — a mapping over the source that already exists

```toml
[project.jam-sense.schedule]
rows = "jobs"
name = "job"
schedule = "schedule"
next  = "next_run"
last  = "last_run"
```

The operator asserting structure, exactly as `--rows`, `--cols` and `--from` already have them do.
No second command and no second subprocess: the schedule rides the payload roll-call already
fetches, because for jam.sense it is literally the same response.

A project with no `[project.X.schedule]` table declares no schedule. That is the common case and it
is not an error.

### Time — parse to an instant, never normalise for display

**Sorting is on the parsed instant, never on the string.** The payload already carries the trap. One
response, the same jobs, two fields:

```
next_run    all -05:00      2026-08-30T05:15:00-05:00
last_run    all +00:00      2026-08-29T10:19:15+00:00
```

A lexical sort of `next_run` is correct *today* only because those 31 values happen to share an
offset. It breaks the moment two projects disagree, or the moment anything sorts those two fields
together — which a "when did this last run vs when does it next" view does by construction.

**An offset is required.** A naive timestamp is a declaration error, reported as one, rather than
something to guess a zone for. Guessing is how a view is confidently six hours wrong.

**Display keeps the provider's own string and offset.** Two projects disagreeing about what time it
is should be *visible* rather than merged into a resolution nobody made. This also disposes of the
selector half of [[open]] item 9: sky.boss does not pick a clock, it reads the one each provider
stamped.

### Absence has more than one word

Three states that must not collapse into an empty cell, because each wants a different fix:

- **A project declares no schedule.** Counted, never drawn — it does not appear in the rows at all,
  and the view reports the arithmetic: *"2 of 3 projects declare a schedule"*. Not a blank row,
  because rows sort by time and a row with no time has nowhere honest to go. [[roll-call]]'s *one
  project down is `partial`, never blank* is the same instinct: report an absence, do not render it.
- **A job that has never run** has no `last`. Already in the data — `test-gap-drain` — and it is not
  the same thing as a project with no schedule.
- **A job with no `next`**, because its provider supplies none. Distinct again, and the only one of
  the three that sky.boss could paper over by computing, which is exactly why it must not.

**Does not do:**

- **Does not schedule, generate, or edit anything.** [[roll-call]] already says this and
  `CLAUDE.local.md` binds it to *whatever scheduler sky.boss grows next*: the agents that own a
  project own its grid. A viewer does not move that line; it is the line being used.
- **Does not judge lateness.** jam.sense computes `overdue`; sky.boss displays that field and never
  computes a rival. Lateness is a judgment, and it is the one place roll-call's refusal genuinely
  does bite — see the ruling below.
- **Does not parse a cron expression, or a systemd calendar, or anything else in `schedule`.**
- **Does not keep history.** *What should have fired and did not* needs a past, which is [[open]]
  item 5 and rides the ledger. Round 1 is the future tense only.
- **Does not normalise time zones**, and does not have a clock of its own.
- **Does not reach a machine.** Same boundary roll-call drew: local sources only.

### The ruling — this is not the vocabulary roll-call refuses

**Settled 2026-08-29 by the operator and the sky.boss session, and worth stating because it looks
like a contradiction at a glance.**

`cli/rollcall.py` is emphatic: *"sky.boss folds sources, not semantics. No common status vocabulary,
no cross-project verdict, no totalling of anyone's `red`."* This doc defines a shared row across
projects, which reads like the thing being refused.

It is not, and the reason is in the sentence itself. All three clauses are about producing a
**judgment** sky.boss is not entitled to make: what another tool's *word* means, whether one
project's `red` outranks another's `degraded`. **A schedule row makes no judgment.** It says *when*,
not *how bad*. This is a question the refusal never covered rather than an exception carved into it.

The test that survives, and the one to apply to the next case: **sky.boss may order; only a provider
may judge.** Ordering two timestamps is arithmetic nobody invented. Ranking two status words is an
opinion, and it stays the provider's.

An earlier draft of this argument licensed the vocabulary by distinguishing *measurements* from
*words* — a cron expression and an ISO timestamp being measurements. It is kept in [[open]] item 18
because it is the argument a reader reaches for first, and it is weaker: it asks for a new
distinction to be accepted, where the one above only asks the existing sentence to be read closely.

## Phases

### Round 1 — what fires next (2026-08-29)

- [ ] `[project.X.schedule]` parsed and validated in `cli/rollcall.py`, unknown keys named the way
      unknown project keys are, a malformed mapping skipped and reported rather than fatal.
- [ ] `sb schedule` folds every declared project's rows into one table ordered by `next`.
- [ ] Timestamps parsed to an instant for ordering; a naive one is a reported declaration error.
- [ ] Provider strings drawn as written, offsets included.
- [ ] Projects declaring no schedule are counted in a warning, never drawn as rows.
- [ ] `--only NAMES`, matching [[roll-call]]'s flag rather than inventing a second spelling.

### Round 2 — the past tense (not scheduled)

Deliberately unopened. It needs [[open]] item 5 (history, on the ledger) and a notion of lateness
that is a judgment. `overdue` is `False` for all 31 jobs today, so there is **no evidence** for a
late-state rendering — the same position items 1 and 5 were in before the ledger landed, and the
same answer: do not draw a state you have never seen.

## Notes

### 2026-08-29 — where this came from, and what checking changed

Raised by the operator while looking at what sky.boss should do with the agent-state root, quoted
as a literal because it is a record of what was asked and rewriting it to satisfy the naming rule
would make it a record of nothing — the same reason `CLAUDE.md` keeps `tb wrap -- jam …` spelled the
way it was actually run:

```
I'm wondering if sb should have a job schedule viewer that includes jobs it
didn't schedule. jam sense will probably maintain its own schedule and sb
would be used for viewing. others might be different.
```

The boundary half needed no work — `CLAUDE.local.md` and [[open]] item 11 already had it, and it was
answered in the direction it had been leaning since the item was written.

**Checking the payload changed the size of the feature.** The expectation going in was a new source
contract to negotiate with jam.sense. Instead `jam report status --json` already carries `schedule`,
`next_run`, `last_run`, `overdue` and `scheduled_in_cron` for 31 jobs, and sky.boss has been
receiving and discarding them since roll-call shipped. That is why round 1 is a mapping and a sort
rather than an integration.

**And it turned up the trap that shaped § Time.** `next_run` arrives at `-05:00` while `last_run`
arrives at `+00:00` — in the same response, for the same jobs. Nothing is wrong with that; both are
offset-aware and unambiguous. But it means a lexical sort is correct only by accident, and the
accident holds exactly as long as one field from one project is all anyone sorts. A view whose whole
job is ordering across projects would have been the thing that broke it.

**The three absences were found in the data, not designed.** `test-gap-drain` has no `last_run`
because it has never run; breeze-brain declares no scheduler at all; and a provider with no
`next_run` is the one sky.boss could paper over. Three different fixes, and one empty cell would
have described all three.
