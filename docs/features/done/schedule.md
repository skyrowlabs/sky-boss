---
status: complete       # rounds 1 and 3 built; round 2 still not scheduled
created: 2026-08-29
updated: 2026-08-30
agent_value: 3         # five dated decisions and a vocabulary, none of it built
key_files: [cli/rollcall.py, cli/schedule.py, cli/view.py, cli/output.py,
            cli/canvas/server.py, cli/canvas/static/render.js, cli/canvas/static/app.js]
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

- [x] `[project.X.schedule]` parsed and validated in `cli/rollcall.py`, unknown keys named the way
      unknown project keys are, a malformed mapping skipped and reported rather than fatal.
- [x] `sb schedule` folds every declared project's rows into one table ordered by `next`.
- [x] Timestamps parsed to an instant for ordering; a naive one is a reported declaration error.
- [x] Provider strings drawn as written, offsets included.
- [x] Projects declaring no schedule are counted in a warning, never drawn as rows.
- [x] `--only NAMES`, matching [[roll-call]]'s flag rather than inventing a second spelling.

### Round 2 — the past tense (not scheduled)

**Before anything here is built, read this.** A status view over `ledger/runs.jsonl` is the obvious
next thing and it has a trap in it that looks like a shortcut. `rc` and `status` **disagree by
design**, and `rc` is the field anyone reaches for first.

A gate job that ran perfectly and found the thing it gates broken exits **zero** — deliberately,
because its monitor is a dead-man switch on *execution*, and a red gate must not take the monitor
down by looking like a crash. The funnel records that as `status: "red"` with `rc: 0`. So `rc` is
structurally unable to carry failure for exactly the jobs whose failure matters most.

Measured against the live ledger on 2026-08-29, 1,051 rows:

| status | rc | rows |
|---|---|---|
| `ok` | 0 | 797 |
| `skipped` | 0 | 215 |
| `failed` | 1 | 20 |
| **`red`** | **0** | **19** |

**19 of the 39 non-nominal rows — 48% — exit zero**, across seven jobs (`agent-fix`, `agent-task`,
`integration`, `ratchet-watch`, `release`, `sentinel`, `test-gaps`). A view keyed on `rc` would
report 20 problems where there are 39, and the ones it dropped would be the `red` half.

This is not a new rule, it is the sharpest instance of the one in § The ruling: **sky.boss may
order; only a provider may judge.** `status` is the provider's verdict and `rc` is a process detail
that resembles one. Read the field that was published as the judgment, never the field that looks
like it. There is no `rc` reference anywhere in `cli/` today and there should not be one.

Found by the skyrow-workspace session on 2026-08-29 while driving `sb data` against a live
agent-fix run; it lives in `skyrow-workspace/strategy/seams/agent-state.md` as the contract's own
warning, because the consumer is the one who hits it and cannot see jam.sense's source comments
from here.

**And the same run showed something sharper, which is that `runs.jsonl` is not the whole verdict.**
That `agent-fix` invocation stood down — `develop` was not CI-green, so it fixed nothing — and its
row reads:

```json
{"job": "agent-fix", "started": "2026-08-29T20:16:57+00:00",
 "finished": "2026-08-29T20:22:55+00:00", "duration_s": 358, "rc": 0, "status": "ok"}
```

`ok`, and correctly so: the job *executed* perfectly. What it did not do — drain two issues — and why
is in **`ledger/decisions.jsonl`**, as `{"kind": "escalation", "job": "agent-fix", "title": "develop
is not CI-green (red) — `agent-fix` stood down"}`. A status view reading only `runs.jsonl` would draw
a clean green run and be right about execution while missing the entire outcome.

**The two files join on `(job, time window)` and nothing else.** The escalation's `at` (20:22:54)
falls inside the run's `started`/`finished`; there is no shared id. That is [[open]] item 6 — job
identity that outlives a window — arriving as a concrete consequence rather than a design worry, and
it is a prerequisite for any view that wants to show a run *and* what it decided.

**And that join is already wrong in the data, not merely fragile.** The skyrow-workspace session
pointed out that time containment holds only until two runs of the same job overlap, which a
hand-run alongside a scheduled fire is. Measured on the same 1,051 rows:

- **6 pairs of same-job runs have overlapping windows**, twice for `agent-fix` itself. The widest is
  a 2h52m `agent-fix` run with a 2-second `agent-fix` run starting inside it.
- **1 decision row already matches two runs.** A `release` decision at 19:20:00 falls inside a run
  that ended `ok` *and* a run that ended `failed`. Whichever a joiner picked, it would be asserting
  an attribution the data does not support — and one of the two answers is the opposite of the
  other.
- **11 decision rows match no run at all**, which is the same absence problem in the other
  direction.

So this is not "a key would be tidier". A time-containment join silently attributes an outcome to
the wrong run, and there is a live instance of it in 1,051 rows. Any view that pairs a run with what
it decided is blocked on item 6, and building one on time containment first would be building the
bug.

Deliberately unopened. It needs [[open]] item 5 (history, on the ledger) and a notion of lateness
that is a judgment. `overdue` is `False` for all 31 jobs today, so there is **no evidence** for a
late-state rendering — the same position items 1 and 5 were in before the ledger landed, and the
same answer: do not draw a state you have never seen.

### Round 3 — the relative view (2026-08-30)

**Numbered after round 2 and built before it.** Round 2 is a ledger view that was specified and
never scheduled; renumbering it to keep the rounds in date order would edit a plan to flatter a
sequence. It stays where it is.

- [x] **`fires` and `ran`** — the provider's instant as a distance from now, `in 26m` / `late 14m`
      / `14h ago`, computed once per invocation so a 31-row table is measured against one moment.
- [x] **An authored view** — five columns drawn, the two absolutes kept and not drawn.
- [x] **The band says `5 of 7`** when a view draws fewer than arrived, in both renderers.
- [x] **`/api/shape` leaves an authored view alone**, and the window remembers it so clearing a
      choice restores it rather than falling back to inference.

## Notes

### 2026-08-30 — round 1, executed

**The doc was right that nothing new was needed from a sibling repo, and it understated by one
step: the rows were being thrown away *twice*.** The operator's `cols = "job,result,last_age,overdue"`
narrows the payload at the view layer, so `schedule` and `next_run` never survive `ask()`. The
schedule view reads through the same reader with that one narrowing removed — `ask(replace(project,
cols=""))` — rather than growing a second subprocess or a second `--from`. Same contract, same
bytes, one fewer opinion applied.

**The ordering test is the one that had to be constructed rather than observed.** The live payload's
31 rows all share an offset, so a lexical sort agrees with an instant sort on every one of them —
which means the fixture had to be built to disagree: `20:00-06:00` is `02:00Z` the *next day* and
falls after `23:00+00:00`, while sorting before it as a string. Without that case the parse could
have been deleted and the suite would still have been green. It is the same shape as [[table-views]]
round 5's width bug — a test that passes only because the data happens to be uniform.

**`name` is the only required field in the mapping**, and it is required for a reason the other
three do not share: everything else has a word for its absence — no `next`, no `last`, no
`schedule` are all states the view can draw honestly — but a row with nothing to call it cannot be
drawn at all.

**A row with no `next` sorts last, not first.** Both were defensible until it was written down: the
undated rows have nowhere honest to sit among rows ordered by time, and putting them at the top
makes the *least* certain thing look the most imminent.

**What is deliberately not in round 1**, restated because it is easy to add by accident: nothing
parses `schedule`, and nothing computes `next` from it. `manual-only` in the fixture has a `last`
and no `next`, and draws exactly that.

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

### 2026-08-30 — round 3, executed

**The complaint was "I do not see the scheduler in the UI" and the command was already there.**
`sb schedule` sets no `sb_surface`, so the palette had been offering it since round 1. It drew
nothing because the operator's `projects.toml` declared no `[project.X.schedule]` table — six lines
sky.boss will not write. Worth recording as the shape of the report rather than as a defect: *a
correct command over an undeclared source is indistinguishable from a missing feature*, and the
existing warning (`0 of 2 projects declare a schedule`) said exactly the right thing to someone
reading stderr, which nobody does in a window.

- **Relative time is arithmetic, and the line held.** Round 1 refused to compute a fire time from a
  cron expression and that refusal is untouched — subtracting two instants invents nothing, where
  parsing `15 5 * * *` would be sky.boss's own opinion about when something runs. `late` is
  borrowed from `chrome.cursor`'s lapsed-`--due` vocabulary rather than coined, so the surfaces
  cannot end up with two words for one idea.
- **A command may author a view; only `data` may have one inferred.** `CLAUDE.md` said *only `data`
  sets one*, and that was **already false** — [[roll-call]] has set a `blocks` view since it
  shipped. The true rule is the narrower one: `shape` is inference and stays `sb data`'s, while a
  command that already knows its columns states them. The widths still come from `cli/view.py`
  through a new public `describe`, because a second opinion about flex would drift.
- **The canvas destroyed the authored view, and the reason generalises.** Every window posts its
  payload to `/api/shape` and installs what comes back — which for an inferred view is the same view
  again, and for an authored one was five columns silently replaced by seven. **A round trip through
  an inference is lossy for anything the inference cannot see.** The fix marks the view `authored`
  and the route passes it through untouched until `cols` is asked for; the window remembers it so
  *clear* restores five rather than widening to seven. Authored is a default, not a lock — the
  operator asking outranks the command's choice.
- **Three renderers of one sentence, and two of them stayed behind.** `_dimensions` grew the
  `5 of 7` form; `render.js` had the string inline at **two** call sites and kept saying `7`. Both
  now go through one `dimensions()`, mirrored deliberately the way `plural` is. Nothing in either
  suite could see this — the Python test asserted Python, the JS tests did not exist for it — and it
  took rendering the page and reading the band back.
- **The band had to say it because the warning could not.** `_dimensions` justified counting every
  arrived column by pointing at the hidden-columns warning as where the difference gets reported.
  That warning ends *"use --cols to choose"*, and `sb schedule` has no `--cols`. A message naming a
  flag that does not exist is the [[workbench]] round 5 failure exactly — behaviour changed, message
  did not — so the count moved into the band instead of the wrong sentence being reused.
- **Four false starts in the headless pass, all mine, all worth the time.** A selector taking the
  *last* element containing "columns" read an ancestor rather than the footer; `document
  .querySelector('input')` found the palette and not the rail because a home with no tools draws no
  filter; and — the one that cost the most — **the server was not restarted after a Python change**,
  so two rounds of "still seven columns" were measuring the old process. `sb ui` hot-reloads
  `static/` and deliberately does not hot-reload Python. The habit that survives: when a headless
  result contradicts a unit that passes, check which process is answering before changing code.
