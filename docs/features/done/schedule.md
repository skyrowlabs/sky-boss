---
status: complete       # rounds 1, 3-8 built; round 2 still not scheduled
created: 2026-08-29
updated: 2026-09-01
agent_value: 3         # eight rounds; the CLI contract, the screen, and five reversals with
                       # their original reasoning left standing beside them
key_files: [cli/rollcall.py, cli/schedule.py, cli/view.py, cli/output.py,
            cli/canvas/server.py, cli/canvas/static/render.js, cli/canvas/static/app.js,
            cli/canvas/static/schedule.js, cli/canvas/static/sb.css]
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
- **Does not colour-code a project** (round 6). The design system holds four hues and sky.boss
  spends all four — `--sb-brand`, `--sb-ok`, `--sb-warn`, `--sb-danger`. A fifth is a brand
  decision and not this tool's, so more than one project on one chart is told apart by *position*,
  never by colour.
- **Does not reveal anything the envelope is not already carrying** (round 6). Hover shows the
  absolutes the chart had no room for; it does not fetch, compute, or enrich.
- **Does not let the screen be rearranged** (round 8). The three panels have one arrangement, and
  it is the one the operator asked for. A draggable or collapsible layout needs somewhere to
  remember itself, and remembering anything about this screen is deliberately deferred — round 6's
  first open question, answered *"skip remembering the state or prefs till the UI is more
  complete."* A control that hides a panel is the tab bar this round removed.

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

### Round 4 — the screen (2026-08-30)

The read-only half of the drawn flight plan, as a third nav entry. Named `schedule` and not
`plan`, because the rest of that mockup — CLAIMS, CLOCK SOURCE, IN FLIGHT, LIMITS — still needs
[[open]] items 6, 7 and 9.

- [x] **A nav entry beside canvas and workbench**, and the rule that forbade one answered rather
      than overridden.
- [x] **Grouped by project**, in the order the command returned, with a `next up` band.
- [x] **Projects declaring no schedule are named**, not silently absent.
- [x] **The screen states its own age** — no browser-timer cadence.

### Round 5 — a source, a project, and two charts (2026-08-30)

- [x] **Provenance on the screen** — `/api/projects`, an introspection route: which argv, in which
      directory, and which payload field became which column.
- [x] **One project at a time** — a selector that offers every declared project, including the one
      that produced no rows.
- [x] **A timeline** — one lane per job on a real time axis, span 6h / 24h / 7d.
- [x] **An hour-of-day chart** — 24 buckets, for the shape of the grid rather than what is next.
- [x] **`at` on the row** — the parsed instant as epoch seconds, so the page never parses a
      timestamp.

### Round 6 — context on hover, and more than one schedule at a time (scoped 2026-08-30)

**Scoped and built the same day**, with three amendments from the operator recorded below.

#### Why this round

Two things the first three views cannot do.

**The charts hid the very fields they are drawn from.** A mark at 50% of a 24-hour axis says
*roughly half a day*, and the exact instant, the cron expression and the last run are nowhere on
that screen. They are on the row — `next`, `last` and `at` are hidden columns, not absent ones —
so nothing needs fetching. What exists today is four native `title` attributes: delayed by about a
second, unstyled, single-line, and invisible to a keyboard.

**The selector is single-valued.** `all`, or exactly one project. The question that actually
arises when several projects share one machine — *do these two grids collide?* — has no answer
between "one project" and "all of them".

#### Shape

**A hover card, one component, all three views.** Anchored to the thing hovered, showing what the
row already carries:

```
release · jam-sense
fires    in 2h 41m        2026-08-30T15:20:00-05:00
ran      1h ago           2026-08-30T16:20:01+00:00
cron     20 3,7,11,15,19,23 * * *
source   jam report status --json
```

- On a **table row** it adds the two hidden absolutes and the source.
- On a **timeline mark** it adds everything — that view draws a name and a dot.
- On an **hour bucket** it lists the jobs in that hour, which is the one thing the bar cannot say.
- **Clamped to the viewport.** The confirm dialog fell off the right edge at scale 2.4 and that is
  the specific failure to design against, so the card's position is measured against the window,
  at more than one scale, before it is believed.
- **Focus shows it too.** A hover-only affordance does not exist for a keyboard, and the card is
  the only place some of these fields appear at all.

**Multi-select projects.** Chips toggle rather than replace; *nothing selected* means all, which
keeps the current default with no extra control.

- **The timeline bands by project** — a labelled group of lanes each — because colour is not
  available. This is the constraint worth stating loudly: the palette has four hues, sky.boss
  spends four, and inventing a fifth is a brand decision. Position is free; hue is not.
- **`sb schedule --only` already takes a list**, so the CLI needs nothing. This is a surface round.

#### Two open questions, both answered by the operator

1. **Does the selection survive a launch?** ~~Undecided.~~ **No** — *"skip remembering the state or
   prefs till the UI is more complete."* `prefs.KEYS` is untouched, and the screen arrives with
   everything open every time.
2. **What does the hours chart do with two projects?** ~~Small multiples or a merged strip.~~
   **Stacked segments** — *"they should stack rather than render on top of each other."* Which
   settles the third amendment too, because a stack needs a colour per project, and that is what
   the operator asked for next.

#### The amendment this round turns on

**Each project gets a colour when it is declared.** This round was scoped saying colour was *not
available* — the design system holds four hues, sky.boss spends all four, and a fifth is a brand
decision. The operator overruled the conclusion without touching the premise, and the resolution is
that identity is drawn as **steps along the brand**, never as a new hue and never as a borrowed
role. `ok` is green, `warn` is what a late job on this very screen already is, and `danger` is red:
a project drawn in one of those would either read as broken or be indistinguishable from lateness.
`color-mix` against an injected role is the tint mechanism the stylesheet already uses, so nothing
outside `cli/theme.py` names a colour and `tests/test_theme.py` stays green.

The step is assigned in `rollcall.parse`, **by declaration order**, and shipped by `/api/projects`
so the CLI and the surface cannot disagree about which project is which colour. It is not a
declarable key — `shade` is sky.boss's answer, and letting `projects.toml` set it would let the
file argue with the assignment.

#### Phases

- [x] **The card.** One component, the three anchors, viewport clamping measured at 1.15 and 2.4,
      and focus parity. Replaces all four `title` attributes.
- [x] **Multi-select.** Toggle chips, empty-means-all, each carrying its project's swatch.
- [x] **A colour per project**, assigned at declaration as a step along the brand.
- [x] **Stacked hour buckets**, one segment per project, never overlaid.

### Round 7 — the empty bucket (2026-08-30)

- [x] **An empty hour opens no card**, and stops being a tab stop.
- [x] **The render-time lookup is guarded too**, because a throw there takes the whole tree.

### Round 8 — one screen (2026-09-01)

**Asked for by the operator**, verbatim: *"I would like to combine the UI schedule into a single
view. The hours bar chart I would like to display up top like it already does. And then I'd like to
have the table and the timeline graph side by side."*

#### Why this round

**Three views of one grid, and you could only ever hold one of them.** Rounds 4 and 5 built the
table, the timeline and the hour chart as mutually-exclusive tabs, which is the shape a *window*
has — one command, one result, one drawing. A screen is not a window, and the question this screen
exists to answer is a comparison: *does what fires in the next few hours collide with the shape of
the grid?* That question needs two of the three drawn at once, and the tab switcher made it a
memory exercise.

**The tab bar was the only reason to hide anything, and it was never a space argument.** Nothing
about the three views competes for the same pixels — the hour chart is 24 short columns and wants
width more than height, the table is a list, the timeline is a list. They were exclusive because
`ui.mode` was a single string, not because the screen was full.

#### Shape

One screen, in the operator's stated order:

```
next up · read 4s ago · ⟳
projects: [all] [jam-sense] [breeze-brain]        span: [6h] [24h] [7d]
------------------------------------------------------------------------
HOURS      ▁▃█▆▂ … 24 buckets, full width, exactly as it drew before
------------------------------------------------------------------------
TABLE                              |  TIMELINE · 24 hours
  jam-sense · 31 jobs              |    release      ──●────────
    NAME  FIRES  RAN  SCHEDULE     |    sentinel     ────●──────
    …                              |    …
  breeze-brain · declares none     |    17 jobs fire beyond 24 hours
```

- **The tabs are gone, and their words survive as panel headings.** A control that hides two of
  three panels on a screen built to show three is the thing being removed, wearing a new name.
  Keeping them as a *focus* control was considered and rejected on the same ground — see the
  reversal in Notes.
- **The two panels split the remaining width evenly, and wrap rather than starve.** `flex-wrap`
  with a `rem` basis, **not a media query**: a breakpoint in `px` puts the threshold at the same
  viewport width at every `--scale`, which is precisely the class of bug `--scale` exists to warn
  about. A `rem` basis means *narrower than a panel is legible at this scale*, and the threshold
  grows with the scale by construction. Below it the panels stack, in the same order.
- **Truncating the cron expression is acceptable now and was not in round 4.** Round 4 fought for
  an unbounded `SCHEDULE` track because the cron was clipped *and nowhere else on the screen*.
  Round 6 put it on the hover card. The constraint was discharged by a later round rather than
  overridden by this one — which is the only reason a half-width table is allowed to ellipsis.
- **The span selector is always drawn**, because the timeline is always drawn. It was conditional
  on `ui.mode === "timeline"`, and that condition no longer names anything.
- **The charts are drawn only when there are rows to draw.** Round 5 established that *nothing
  fires within 24 hours* is a correct sentence that misleads when the project declares no schedule
  at all. With three views on one screen the same trap has a wider mouth — an empty timeline beside
  an empty hour chart beside a "declares no schedule" panel is the sentence said three times. When
  the selection yields no rows, the declaration panels are the whole answer and neither chart is
  drawn.
- **The two charts describe different sets, and the screen says which.** The hour chart plots every
  datable row; the timeline plots only what falls inside the span. On one screen those two counts
  are visible together and a reader could reasonably conclude they disagree. The timeline panel
  heading carries its span (`timeline · 24 hours`) so the difference in scope is a label rather
  than an inference.

#### Phases

- [x] **One screen.** Hours full width on top, table and timeline side by side beneath, tabs
      removed and `ui.mode` with them.
- [x] **The split wraps rather than starves** — `rem` basis, no media query, swept across scales.
- [x] **The screen stays coherent with no rows** — declaration panels are the whole answer, the
      charts are not drawn, and the quiet panels still inherit the selection.
- [x] **Verified by rendering**, with both `error` and `unhandledrejection` installed first, real
      pointer input across all three anchors, and the app proved still live by clicking afterwards.

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

### 2026-08-30 — round 4, executed

**"I do not see a visible schedule button next to workbench" is the report round 3 should have
anticipated.** Round 3 made `sb schedule` render well in a window; the operator had approved *both,
in that order*, and a window is not a button. Worth keeping as a phrasing lesson rather than a
defect: *"it works in the palette"* answers a question nobody asked when what was approved was a
screen.

- **The no-nav-entry rule was answered, not overridden.** It held that a nav offering a screen that
  is not there is the palette's own failure wearing different clothes — *it has already told you the
  thing exists*. The objection was to **offering something absent**, so building the screen
  discharges it. What would have broken the rule is calling the entry `plan`: the drawn flight plan
  is mostly blocked, and a nav entry reading `plan` above a table of fire times is the same
  over-promise in a smaller font. The control tower is still not offered.
- **`display: contents` is what makes the columns align.** Each `.pl-row` was its own grid, so the
  columns lined up only because every row carried an identical fixed template — and a fixed track
  clips a cron expression, which has no bound. The rows share the group's grid now: three columns
  size to their own widest cell, `schedule` takes the remainder, and the alignment is structural
  instead of coincidental. Measured at three scales: nothing clipped, and header and row cells share
  the same four x-offsets to the pixel.
- **The fixed widths were wrong at every scale and looked right at one.** `minmax(0, 26rem)` for the
  cron truncated it at 2560px, which is the *original complaint* reintroduced by the fix for it — and
  `in 3h` and `33m ago` were clipped in 8rem and 9rem tracks the whole time. Guessed numbers in a
  `rem` grid are the trap `--scale` exists to warn about; content sizing has no number to be wrong.
- **The screen has no cadence, and says so instead.** Every relative string on it was computed by
  Python at read time and does not move; without a visible age they would rot silently while looking
  identical to fresh ones. A browser timer was **rejected rather than skipped**: a hidden page has
  its timers clamped to roughly one fire a minute, so a cadence would quietly become a different
  cadence exactly when you stopped being able to see it. `read 4s ago` is honest at any rate,
  including none. A Python-side clock keyed to the connection is what a real cadence would need, and
  that machinery is keyed to a *window* — the screen is deliberately not one.
- **`project` is dropped from the rows, and only on this screen.** The grouping heading already
  names it, so drawing it again spends the narrowest column on a constant. This is a decision about
  *drawing*, not a view: the envelope still carries the field, the window form still draws it, and
  round 3's authored view is untouched.
- **The bar already overflows at scale 2.4 in a small window, and the third button did not cause
  it.** Measured by hiding buttons: 1830px minimum with *zero* nav buttons against a 900px viewport,
  because `.bar > *:not(.spacer):not(.barpal)` is `flex: none` on purpose. My button takes it from
  2176 to 2357. Left alone — it is a pre-existing property of running 2.4 in a window too small for
  it, the schedule entry is visible from about 1900px up, and shrinking the bar's controls is the
  thing that rule exists to prevent.

### 2026-08-30 — round 5, executed

- **Shipping `at` is what keeps this file out of the timestamp business.** The charts need a
  position and `fires` is deliberately too coarse for one, so the obvious move was `Date.parse` on
  `next` in the browser. That would have been a second opinion about the one thing round 1 exists to
  keep single: Python **requires** an offset and refuses the naive rows, where `Date.parse` silently
  assumes local for exactly those. The epoch ships instead, empty when Python could not order the
  row — so `plottable` defers to the parse that already happened rather than re-litigating it.
- **The two sides agreeing was checked, not assumed.** Python's hour histogram of `next_run` is
  `{0:7, 1:6, 2:1, 3:1, 5:2, 6:3, 7:3, …}` and the rendered `hours` chart read back
  `7 6 1 1 . 2 3 3 …`. Same for the timeline: 14 lanes and 17 beyond at 24h, against Python's
  *within 24h: 14, beyond: 17*. Two independent paths over one field, compared — which is the seam
  rule from the workspace guide applied inside one repo.
- **Neither chart shows recurrence, and the screen says so.** A bar repeating every four hours is
  the cron parse round 1 refused, arriving as a picture. One job, one mark: the next occurrence its
  provider published. The `hours` view carries the sharper caveat in its own footer — it puts a
  weekly job in the same column as a nightly one, which is honest about it being a picture of
  *shape* rather than of *what happens next*.
- **Beyond the window is counted, never clamped.** A mark pinned to the right edge reads as "fires
  at the end of the window", which is a different and false claim. `17 jobs fire beyond 24 hours —
  not drawn rather than pinned to the edge` is round 1's *counted, never drawn* applied to an axis.
  A *late* row is the one thing clamped, to 0% — it has already fired, so the left edge is where it
  belongs rather than off the chart.
- **Provenance is a route, not a key on the envelope.** `sb schedule`'s `data` is a bare list and
  stays one — wrapping it would change the payload every existing consumer reads, its own authored
  view included. And provenance is a fact about the *declaration*: true whether or not the command
  has been run, which is why it survives a partial answer. The two fetches are deliberately not
  chained for that reason.
- **A correct sentence that misleads is the same failure as a wrong one.** Filtered to breeze-brain,
  the timeline said *"nothing fires within 24 hours"* — true, and it implies there are jobs that
  fire later. A project that declares nothing now says so in all three views. This is the *worked
  fine, told nobody* family with the polarity flipped: the words were right and the reader would
  still have concluded something false.
- **The selector is built from declarations, not from rows.** One built from the rows could not
  offer the project that produced none — which is the one you go looking for when the screen is
  emptier than you expected.

### 2026-08-30 — round 6, executed

- **`display: contents` has no box, and that is how the card pinned itself to the corner.** Round 4
  made every `.pl-row` one so a whole group could share a single grid — which is why the columns
  align structurally rather than by coincidence — and an element with no box returns **zeros** from
  `getBoundingClientRect`. No error, no warning: the card simply rendered at (12, 12) with correct
  content, which is the failure mode this repo keeps naming. `boxOf` unions the children when the
  node has no rect of its own. The same fact bites the stylesheet: `.pl-row:hover` cannot paint a
  background either, so the highlight moved to the cells.
- **Flipping is not clamping, and only one of them is the contract.** The card flipped above an
  anchor near the bottom — and `.plan` scrolls, so an anchor can sit at y=1226 in a 1000px
  viewport, where *above* is still off-screen. Preferring a side is a layout choice; staying inside
  the window is the guarantee, and it is now enforced unconditionally rather than on the paths that
  happened to need it. Reachable without contriving it: hover a row, then scroll.
- **The suite caught two things the same afternoon, both worth having.** `test_theme.py` rejected an
  `rgb(0 0 0 / 45%)` box-shadow — exactly the drift that scan exists for, and `var(--lift)` was
  already there. And `test_rollcall.py` failed because `shade` became a dataclass field: the test
  asserts `PROJECT_KEYS` covers every field a project can carry, so a *derived* field has to be
  named as derived rather than quietly admitted as a declaration.
- **Stacked, and sorted by name rather than by size.** A segment order that followed the count would
  reshuffle every column and make the same project a different band in each one — which is the one
  thing a stacked bar exists to let you read across.
- **Two halves of one screen must describe the same set.** With two projects picked, the
  "declares no schedule" panels were still drawn for projects that were *not* picked. Filtering them
  by the same selection the rows use is the fix; the general form is that any second list on a
  filtered screen inherits the filter or contradicts the first.
- **Verified by rendering, at two scales.** All three anchors — table row, timeline lane, hour
  bucket — measured inside the viewport at 1.15/1500x1000 and 2.4/2200x1300, the hour card listing
  its 7 jobs, 14 stacked segments, and every selection state checked against what the group headings
  actually said. No handler errors, with the `window.onerror` listener installed first, because a
  silent no-op after a click is almost always a handler that threw.

### 2026-08-30 — round 7, executed

Reported as *"the schedule hours display locked up the controls and the app became
unresponsive."* Exactly that, and reproduced in a minute once the right thing was asked.

- **Ten of twenty-four buckets are empty, and hovering one killed the app.** `cardState` did not
  exist; `show` stored `{rows: [], anchor}` and `Plan` then read `card.rows[0].project` to look up
  the source. `rows[0]` is `undefined`. The throw landed **inside Preact's render**, so the
  component tree stopped updating — every control stayed drawn and none of them did anything, which
  is precisely what "locked up" looks like from the outside.
- **`addEventListener("error", …)` did not see it, and that is the lesson worth more than the fix.**
  `CLAUDE.md` already records installing that listener before a click, because a handler error does
  not reach a CDP exception drain. This one did not reach the listener either: `setCard` schedules
  the re-render in a **microtask**, so a throw during render surfaces as an **`unhandledrejection`**,
  not an `error`. The first sweep across the buckets came back clean and the app was already dead.
- **So the assertion had to change, not just the listener.** *No error was reported* is not evidence
  the app is alive. The check that actually catches this is **does the app still update** — click a
  control afterwards and read the DOM back. That found it immediately: `table` clicked, tab still
  `hours`, `rows = 0`.
- **Returning `null` rather than an empty card is the behaviour, not just the guard.** Moving from a
  full bucket to an empty one should *close* the card; leaving the previous one standing over a
  bucket it does not describe is a smaller version of the same lie.
- **Verified with real pointer input this time**, not synthetic events: 236 mouse moves across the
  hour buckets, 88 down the timeline lanes, controls still live and nothing thrown. The synthetic
  `dispatchEvent` sweep in round 6 had passed while the bug was there — it never crossed an empty
  bucket, because it only visited elements the query had already found interesting.

### 2026-09-01 — round 8, executed

**The tab bar was a reversal, and the reasoning it reverses is worth keeping.** Rounds 4-7 built
these as three exclusive views and never argued for the exclusivity — it arrived because `ui.mode`
was a single string and a *window* is a thing that draws one result. The nearest thing to an
argument is round 5's own framing of the hour chart as *"a second view rather than a replacement
for the first"*, which is true and does not imply you may only hold one at a time. Nothing about
the three competes for the same pixels: the hour chart is 24 short columns wanting width, and the
other two are lists. They were exclusive by accident of state, not by design.

**Keeping the tabs as a *focus* control was considered and rejected.** It is the same control with
a kinder name — on a screen built to show three panels, a button that hides two of them is the
thing being removed. And it would need somewhere to remember which panel you had focused, which is
round 6's first open question answered the other way.

**A wrap threshold belongs in `rem`; a media query would have been the `--scale` bug in its purest
form.** A `px` breakpoint puts the point at which two panels stop fitting at the same viewport
width whether the surface is drawn at 0.9 or 2.4 — so at high scale it would keep them side by side
in a window where neither is legible, and at low scale it would stack them with room to spare. A
`rem` basis makes the threshold *"narrower than a panel is legible at this scale"*. Measured rather
than argued: at 2.4 the panels stack in a 2200px window and sit side by side in a 2900px one, and
at 1.15 they sit side by side in 1500px. The stylesheet has **no media query at all** and this
round deliberately did not introduce the first one.

**Round 4's unbounded cron track was discharged by round 6, not overridden by round 8.** Round 4
fought hard for a `SCHEDULE` column with no fixed width, because a clipped cron expression was the
original complaint and the string was nowhere else on the screen. Round 6 put the full expression
on the hover card. That is the only reason a half-width table is allowed to ellipsis, and it is
worth stating as a shape: **a constraint can be retired by a later round giving its content another
home, and that is different from deciding it no longer matters.** In practice it barely bites — one
cell of 31 clipped, at one of the five scales swept.

**The numbers were right and the picture was wrong, which is a sharper thing than it sounds.** The
sweep reported a correct track width, correct panel widths, correct column alignment and zero
errors at every scale. The render showed `in 1h` wrapped onto two lines in the narrowed timeline:
that lane became two lines tall and pulled every mark below it out of line with the axis. **A
container measuring correctly says nothing about the text inside it wrapping** — `getBoundingClientRect`
on the lane returns the height the wrap *caused*, so the measurement agrees with the bug. Nothing
in the probe would have caught it; looking at the screenshot did, in one glance. The fix is
`white-space: nowrap`, so a too-narrow value can only ever **clip** — which is visible as wrong —
rather than wrap, which reads as a broken chart with no clue where the fault is. The probe now
asserts the property directly: every lane is one height, and no `when` cell is clipped.

**The axis inset and the lane label width were two numbers that had to be equal, and now are one.**
The comment above them has said since round 5 that *"two different insets is how a chart ends up
quietly off by the width of a label"* — and they were two independent literals that happened to
match. A half-width timeline wants both narrower, which is exactly the edit that would have broken
them apart. `--pl-lane-w` and `--pl-when-w` are the same rule as [[tools]] round 6's `set_field`:
if two places must agree, make them one place rather than trusting an edit to touch both.

**"Nothing fires within 24 hours" gets worse on a combined screen, and had to be answered again.**
Round 5 found that sentence misleads for a project declaring no schedule — correct, and it implies
there are jobs firing later. With three panels drawn at once the same falsehood would be stated
three times side by side: an empty timeline, an empty hour chart, and a "declares no schedule"
panel. The rule is now simply that **the charts are drawn only when a row survived the selection**,
which is more general than the `only && quiet.includes(only)` test it replaces — that one asked
whether *exactly one* project was picked, where the question is whether anything was found.
Verified across five selection states: `breeze-brain` alone draws one panel and no charts,
`jam-sense` alone drops the quiet panel, and both together draw everything.

**Two charts over different sets, with their counts side by side.** The hour chart plots every
datable row; the timeline plots only the window. Nothing was wrong with either, but on one screen
`17 jobs fire beyond 24 hours` sits a few centimetres from a chart showing all 31, and a reader can
reasonably read that as a disagreement. The timeline heading carries its span — `timeline · 24
hours` — so the difference in scope is a label rather than something to work out. This is the
*correct sentence that misleads* family again, arriving from a third direction: neither sentence
changed, only what sits next to it.

**Verified by rendering, at five scales, with both listeners installed first.** 0.9/1500x1000,
1.15/1500x1000, 1.6/1800x1200, 2.0/2000x1300, 2.4/2200x1300, plus 2.4/2900x1400 for the wrap
boundary. Read back: header and row cells sharing four x offsets exactly at every scale (round 4's
`display: contents` grid survives being halved), exactly one `.pl-card` in the DOM and inside the
viewport for all three anchors, an empty hour bucket closing the card rather than leaving a stale
one, no document or panel horizontal overflow, and zero `error` or `unhandledrejection` events. The
app was proved **alive** rather than merely quiet — clicking `6h` afterwards and reading the DOM
back showed the heading change to `timeline · 6 hours` and the lanes drop from 14 to 3, which is
round 7's assertion and the only one that would have caught round 7's bug.

**The probe read the rows and got zeros, which is round 6's trap on the tooling side.** The first
alignment check indexed the children of `.pl-rows` — the `.pl-row` elements — every one of which is
`display: contents` and returns a zero rect. The check reported four identical zeros and *passed*.
A verification that cannot fail is not a weak verification, it is not one; the probe descends to
`.pl-c` now. Worth recording because the bug was in the instrument, not the code, and the failure
mode was a green result.

**No new test in `tests/js/`, deliberately, and this is the honest version of that.** Round 8 added
no pure function — it is a layout round, and `rows.length > 0` extracted into an exported predicate
would be ceremony rather than coverage. The runner still passes 41 and the Python suite 1087; what
actually verified this round is the headless pass above, which is the division `CLAUDE.md` already
draws between the two.
