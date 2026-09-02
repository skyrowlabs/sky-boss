# Open — decided to build, not yet decided how

A running list of questions the sky.boss direction has raised and not answered. It exists because
the design pass of 2026-08-26 produced more decisions than the mockup could hold, and losing them
in a chat log is how the same argument gets had twice.

**Three lists, one test each. Keep them apart:**

| File | The question it holds |
|---|---|
| `docs/ideas.md` | *Should we build this at all?* Deleted when spec'd or shelved. |
| `docs/design/fundamentals.md` | *What is this, at the level of primitives?* Decisions accrete, dated, reversals left visible. |
| **this file** | *We are building it — how?* Items move out by being answered somewhere else. |

An item leaves this file when a feature doc, a fundamentals decision, or a deliberate rejection
takes ownership of it. **Record where it went** rather than deleting the line — the pointer is the
useful half, same rule as a feature doc's Notes.

---

## Surface

**1. The failure screen.** Every state drawn so far is nominal or gracefully degraded. There is no
rendering for a job that died mid-flight, a working-tree claim that was actually violated, or a
timer that fired outside sky.boss and left the plan wrong. [[fundamentals]] already ruled that a
dead stream goes dead visibly; nothing draws it. *Blocked on evidence — this is answered by
looking at real failures, not by drawing one.*

**2. Where the queue strip lives.** The console's per-run strip (`1082 1084 1086 …`, with dashed
slots for the deferred) was the only widget anywhere showing one run's shape at a glance. It died
with the console. It probably belongs in the tower; nothing has claimed it. See [[workbench]] Notes.

**3. The floating canvas: ~~keep the metaphor or let it go~~ — it was never let go.** *Mostly
answered 2026-08-27 by building the workbench, and the wording below was wrong from the day it was
written.*

The item said "removing the console removed it entirely". That was true of the **mockup** and never
of the product: `tiled / floating` has been in the top bar since [[canvas]] round 1 and still is —
`position: absolute`, `begin_move_drag` on the bar, a resize grip, z-order on focus, all working.
The item read as though a shipped feature had been dropped, which is the one thing a list like this
must not do.

**The reversal it feared did not happen, because [[workbench]] was added *beside* the canvas rather
than instead of it.** The three artboards were drawn as three screens; what got built is a nav with
two entries, one of which is the canvas, unchanged. A primitive is only reversed by something
replacing it.

And the case the item names as the argument for keeping it was checked rather than assumed: a
shaped table, a verbatim `git log`, and a live file cursor, overlapping and independently draggable
on one canvas. That is the thing structured views cannot express, and it works today.

**What is actually still open is narrower**: when the tower arrives with its own `merged / split`,
does the canvas screen stay? That is a question about a screen that does not exist yet, and it
should be asked then rather than pre-answered now.

**4. The secondary label tier's contrast.** *Closed 2026-08-27 → [[fundamentals]] § the label
tier: a border token is not a text token.* Ruled not a contrast question at all: `TEXT_3` is
defined as *"structure, not reading text"* and is what `BORDER` is, so the mockup used a border
token as a text token. Reading text takes `TEXT_2`; the exemption is not widened. The measurement
in this item was also wrong — 1.81:1, not 2.5:1.

**5. History.** The mockup carries a `history` affordance with nothing behind it. Once a saved
command has run more than once, *how did this go the last seven nights* is the obvious question,
and the ring buffer plus the file of record already exist. Nobody owns it. ~~*Blocked on evidence —
needs jobs that have run twice.*~~

*Specced 2026-08-29 → [[history]]; **round 1 built 2026-09-01** as `sb history <project>`. The provider half only, with the sky.boss half named as round 3 so nothing mistakes one for the other. Building it closed the fourth of the tower's five bands: `COMPLETED` now has a command behind it, after [[fundamentals]] § the tower is an observatory ruled that every band reads a provider. What is left with no source at all is `LOADED PLANS`.*

**Unblocked 2026-08-29, and by something outside this repo.** The evidence arrived when jam.sense
scaffolded its state into the agent-state root: `<root>/jam-sense/ledger/runs.jsonl` is **1,055
rows** of exactly what this item was waiting for, plus `decisions`, `queue_deferrals` and
`implement_ready_plans` beside it. [[jsonl-reads]] already reads them and [[state-root]] already
addresses them, so *how did this go the last seven nights* is a question sky.boss can ask today with
no new primitive — `sb data jam-sense:ledger/runs.jsonl --from jsonl`.

What that does **not** supply is history of sky.boss's *own* runs, which is what the mockup's
affordance was drawn against and which still needs item 6. So the item splits: reading a provider's
ledger is unblocked and cheap; remembering what sky.boss itself did is still downstream of job
identity. Worth deciding which one the affordance is for before either is built.

**19. The tools rail does not scale past a handful.** Raised by the operator 2026-08-29,
watching the live agent-fix run. The rail is a fixed-width column down the left of the canvas and a
tool name longer than it gets clipped — `jam-agent-fix-log` renders as `jam-agent-fix-l…`. Four
tools today, so it reads as cosmetic; it is the shape of the problem rather than its size.

*Half-answered 2026-08-29 → [[tools]] round 7: the rail is a width you can drag, clamped 18–160rem
and remembered in `$SB_STATE`.* *The second half answered 2026-08-30 → [[tools]] round 8: a text
filter over name, description, tags and expansion, with tags as a new declared field. That is the
"different listing" candidate below, taken in its cheapest form — the rail stops being the complete
index without becoming a second surface. What is left open is only the **expandable** candidate,
and a filter may have removed the need for it.* That is the first of the two candidates below, taken because it was
small. The second is untouched and is still probably right — dragging lets you see a long name, it
does not stop the rail from being the complete index.

Two candidate answers and they are not the same feature. **Expandable** — the rail widens, or a tool
expands in place to show its full name and expansion — keeps the rail as the address and costs
canvas width, which is the thing windows are competing for. **A different listing** — a
palette-driven picker, a searchable overlay, the groups from [[tools]] round 6 doing real work —
stops treating the rail as the complete index and makes it a shortcut bar. The second is much the
larger change.

Two constraints that are already known and would bite here:

- `--scale` **is a geometry, not a preference**, and `CLAUDE.md` is explicit that a layout verified
  at one value of it has been verified once. Every fixed `rem` width grows with the scale while the
  window does not. Whatever this becomes has to be checked across the sweep, not at 1.15 — the
  workbench lost a step to exactly this for three rounds.
- **Groups already exist and are empty.** [[tools]] rounds 5 and 6 gave a group a `[group.NAME]`
  table and the rule that *a group exists if any command names it, or if it is declared*. The
  catalog reports `groups: 0` today. A grouped rail may be most of the answer already built, and
  should be tried before anything new is designed.

Not urgent: four tools fit. It becomes real at roughly a dozen, or the first time a name is long
enough that two tools clip to the same string — which is the actual failure, since the rail is how
you tell them apart.

**20. Five tweaks to the followed line's tint.** *Closed 2026-08-29 → [[highlight]] rounds 5 and 6.* Round 5 answered everything **weight** could
answer — glyphs widened and emphasised, ALL CAPS split into an identifier and a shout, and the
bench given a picker and a legend instead of a text box. Round 6 then answered the rest with
**ground** rather than deferring it: `#123` takes the brand on a wash of itself, and the
delimiters of `()`/`{}`/`[]` dim so their contents stand out — the timestamp's argument applied to
punctuation. **The hue question is closed rather than open**: the design system holds four hues and
sky.boss spends all four, so a fifth is a decision for the brand and not for this tool.
*~~Quoted text is the one ask nothing answered.~~ **Closed 2026-08-30 → [[highlight]] round 7**,
along with the `weight` key this item called the smallest change on the list. Neither needed a
hue: a quote is a **delimiter**, so it takes round 6's answer — the marks dim and the contents
keep whatever claimed them — and the collision this item warned about disposes of itself, since
the delimiter pass claims single characters and runs last, after the operator's rules. The
apostrophe hazard was measured rather than reasoned about: 15 spans naive against the live log,
two of them the documented failure, 13 guarded and neither.*

 Raised by the operator 2026-08-29, reading the
live agent-fix drain through `--highlight jam`. Verbatim: symbols emphasised or given a different
colour; quoted text differentiated; `#123` in a unique colour; text wrapped in `[]`, `()` or `{}` in
a different colour; and *escalate* emphasised. Owned by [[highlight]] when it reopens — this is
round 5's raw material, not a design.

**~~Check the first one before designing anything.~~** *Done, and it was right: the gap was weight,
not colour. `weight = "bold"` on a declared rule as of [[highlight]] round 7 — it rides the same
`loud` range a built-in emphasis does, so it composes rather than doubling.* `escalat(e|ed|es|ing|ion|ions)` is already in the
operator's own `[highlight.jam]` ruleset at `role = "warn"`, and the tool being watched names
`--highlight jam`, so the word *is* tinted. If the ask is that it stand out **more**, the gap is not
a colour: **a declared rule may name a colour and never a weight.** `_emphasise` grants bold only to
markdown `**…**` and to headings, so there is no spelling an operator can write to ask for it. That
is the smallest change on this list and probably the one to do first, because a `weight` key answers
*emphasised* for every future word instead of for one.

**`#123` already tints — as `sb.num`, the same role every other number takes.** So the ask is
precisely the collision, and it is where four of the five land.

**Four of the five want a colour that does not exist.** `STYLES` has eight roles and every one
already means something: `accent`, `label`, `muted`, `ok`, `fail`, `warn`, `num`, `path`. A ninth is
a palette change, and `cli/highlight.py` records the last attempt in its own comments — a violet for
code spans was prototyped, looked good, and was rejected as *"exactly how a second palette starts"*.
So the question this item actually holds is **not which shapes to tint, but where a new colour comes
from**, and there are only three honest answers: reuse a role and accept the collision; reach for
weight or dimming instead of hue, since bold already composes without taking the colour slot; or add
a role to the design system, which is an edit to the vendored `colors_and_type.css` and therefore
not a sky.boss decision at all.

**Brackets were refused deliberately, and only `[]` was ever considered.** The tag rule is
positional — *a bracket mid-prose is prose* — because a leading `[job]` is the boundary the eye
scans in a multi-job log and a mid-line `[1]` is not. `()` and `{}` have no rule at all, and the
brace is the one to think about hardest: an agent log carries JSON, so a `{…}` rule tints whole
objects and becomes the loudest thing on the screen.

**Quotes need the false-match pass the number rule already failed once.** A single-quote rule
matches the apostrophe in `don't` and runs to the next apostrophe on the line. That is the same
class as the version of `_NUMBER` that tinted `8 issue` and `104 archive` — invisible in a unit test
and unmissable in a rendered log, which is why the round 2 rules were prototyped against a real one.
Note also that `handing to '…'` in the operator's ruleset already claims a quoted string, and a
built-in rule would claim it first: built-ins run before declared rules and declared rules only take
unclaimed text.

**"Symbols" needs the operator before it needs a design.** Glyphs already tint — round 4 does ✓, ✗,
⚠ and the colour words. If the ask is punctuation (`->`, `=>`, `::`, `|`) that is a new shape and a
cheap one; if it is that the existing glyphs should read stronger, it is the same weight-not-hue
answer as *escalate*. Worth asking which rather than guessing, since the two cost very different
amounts.

**21. A wrap toggle in the canvas header, with a hanging indent under the timestamp.** *Closed 2026-08-29 → [[wrap]] rounds 1 and 2, built the same day. Round 2 made it the default, and only for a follow: `read` is verbatim by declaration, so wrapping it by default would be sky.boss inferring that its output is prose — the same inference it refuses when it declines to make columns of it.* Built as specced, with one correction the doc records: the offset could not be read off `marks` as phase 1 proposed — a `sb.muted` mark at offset zero is a timestamp *or* a dimmed opening bracket, so picking one is inference. `highlight.hang` exposes it instead. Asked for
by the operator 2026-08-29, reading the live agent-fix drain. A window's body scrolls sideways
today ([[chrome]]: *"it scrolls sideways instead, the way the table does"*), and a long agent line
is then half off-screen. The ask is a header control that wraps to the window instead — **and one
special case that is the whole point of the item**: a line beginning with a timestamp should wrap
**indented to the first character after the stamp**, so the continuation sits under the text rather
than under the clock, and the timestamp column stays a clean column. The stamp is not repeated on
the wrapped rows.

*Not yet designed. What is already known and would shape it:*

- **The indent is derivable and must not be guessed.** `cli/highlight.py`'s `_TIMESTAMP` already
  matches a leading stamp and returns its end offset — the same number a hanging indent needs. So
  this is `text-indent`/`padding-inline-start` computed from a mark sky.boss already produces, not
  a new parse. A line with no stamp wraps flush, by the same rule and with no special case.
- **Wrap is a property of a window, not of the surface.** Two windows on one canvas may want
  different answers — a wide table wants the scroll, a prose log wants the wrap — so this is
  per-window state like `pinned` is, and the header is where a window's own controls live. Whether
  it also has a default that persists in `$SB_STATE` is the same question `rail` answered in
  [[tools]] round 7.
- **Marks are offsets into the text and wrapping does not move them.** Wrapping is a CSS decision
  about a `<pre>`; the payload is unchanged and `markedLine` needs no opinion. Anything that
  reflowed the *text* would break that and is the wrong implementation.
- **The terminal is a separate question and probably a no.** `sb follow`'s ring is a fixed-height
  frame and a wrapped line changes how many rows a record occupies, which is what the ring counts.
  Do not assume this crosses over.
- **Check it at more than one `--scale`.** A hanging indent is a length derived from a character
  count, and a character is a different width at 1.15 and at 2.4. `ch` units are the obvious answer
  and the obvious answer is what has to be measured.

## Primitives the plan and the tower need, none of which exist

*Superseded 2026-09-01 → [[fundamentals]] § the tower is an observatory. The heading is wrong and
is left standing because the reversal is the useful part: **the tower needs none of these.** All
four were named on the assumption that the tower draws jobs sky.boss runs. It does not — fourteen
of the fifteen job names in the mockup are jam.sense's own, so every band reads a provider, and
three of the four have a shipped or specced source today (`sb agents`, `sb schedule`, a project's
ledger). Items 8 and 9 were already answered; 6 and 7 are still open and are no longer blocking
this screen.*

These four are why [[workbench]] is buildable now and the other two screens are not. Each is
probably its own feature doc, and they are ordered by how much the others depend on them.

**6. Job identity that outlives a window.** `--label` in the mockup. Today a run is anonymous and
dies with its window. A plan, a claim, a budget and a governor all need to name the same thing
across restarts.

**Partly supplied 2026-09-01 by [[agent-sessions]], and demoted the same day by [[fundamentals]]
§ the tower is an observatory.** `sb agents` hands over identity that outlives every window sky.boss
ever drew — a stable id, a name, a `cwd`, a start time — for sessions sky.boss did **not** start,
which is the population the tower actually draws. So this stopped being a blocker without being
closed: sky.boss's own runs are still anonymous, and nothing about reading someone else's registry
fixes that.

**And the item asks two questions, which is why it sat.** *A record of a finished run surviving its
window* crosses the **federation** rule (`cli/rollcall.py`: no ledger, no history, no cache) and
not the execution one — and the staleness argument behind federation does not obviously reach it,
since sky.boss is the authority for what sky.boss ran. *A job running with no window open* crosses
execution, squarely. Whoever reopens this should say which they want; the answers are different
sizes.

**7. The claim.** Several agentic jobs contending for one working tree is a real fact with no
vocabulary in sb. The mockup renders it as a glyph and a contested band; what it *means* — advisory
label, or something that actually blocks a departure — was undecided, and those are very different
features.

**Ruled 2026-09-01, on the operator's word: advisory, never blocking.** sky.boss draws what it can
observe about tree contention and never holds a lock, refuses a departure, or arbitrates between
two jobs. Three things follow and each is worth more than the ruling itself:

- **It needs no new act**, so the observe/act split is untouched and nothing crosses the daemon
  line item 10 guards. The blocking reading would have needed both — a second command that acts,
  and a lock that outlives the window that took it, which is item 6 first.
- **It is the reversible direction.** An advisory label can be made binding later; a lock that
  jobs have started depending on cannot be made advisory again without breaking whatever learned
  to trust it. Same asymmetry that put a per-project state-root override behind the derivation
  rather than in front of it.
- **A provider that publishes contention is drawn as it wrote it**, and sky.boss never computes a
  rival — [[schedule]]'s `overdue` rule and [[agent-sessions]]'s thin record, arriving at a third
  field.

**And then the evidence was checked, which reshaped the item rather than closing it.** Measured
2026-09-01 against the live payload: `jam report status --json` returns **16 leaf keys and not one
of them is about a working tree** — no claim, no lock, no branch, no worktree, no conflict. So the
mockup's `▸ needs the working tree` has **no provider behind it**, and building the ON DECK half
today would be drawing a field nobody publishes. That is item 1's parking condition, and it applies
here.

**The evidence does exist — on the other band.** `sb agents` shipped the same day and publishes
`cwd` per live session, and `git worktree list` in jam.sense reports **four checkouts of one
repository** — `jam-sense` plus `jam-pool-0/1/2`, all at the same commit — with live sessions
sitting in two of them while this was written. So contention is observable **today**, on
**IN FLIGHT** (sessions that are running) rather than on **ON DECK** (jobs that are scheduled),
which is the opposite band from where the mockup drew it. The claim's first real subject is not the
grid; it is the agents item 16 went and found.

**Two ways to derive it, and they are not the same feature:**

- **Same directory** — compare the `cwd` strings `sb agents` already returns. No subprocess, no new
  rule touched, and strictly weaker: it misses the jam-pool case exactly, which is the case that
  motivates the item.
- **Same repository** — ask git which object store a `cwd` belongs to (`rev-parse
  --git-common-dir`). Catches the worktrees, and it is the first time sky.boss would run a command
  **nobody declared**. `CLAUDE.md` binds that rather than forbidding it: output from a command
  sky.boss runs on its own initiative must never reach `data`. A derived boolean is not that
  command's output, so the rule is satisfiable — it has to be satisfied on purpose rather than
  noticed afterwards.

**Still open:** which of those two, and whether an advisory claim is worth building before there is
a band to draw it in. Not blocked on a decision any more — blocked on wanting it.

**8. The budget.** ~~A wall-clock ceiling on a run.~~ **Answered 2026-08-29: the supervisor owns
it and sky.boss displays it.** The mockup put `--budget` on `follow`, which is a contradiction —
follow observes, and a budget that kills the child makes it act — and the mockup's own header line
already resolved it. The operator confirmed that reading.

So there is **no new act**, the observe/act split is untouched, and the budget is a *fact read from
a foreign supervisor* like every other fact on a followed stream. That makes it the same class of
work as [[agent-sessions]] rather than a change to `run`, and it inherits that doc's rule: a
provider's field is drawn as the provider wrote it and never recomputed.

What is *not* settled and does not need to be yet: whether sky.boss ever grows a ceiling on a child
it spawned itself. `run --budget` would be a coherent feature and a different one; it does nothing
for the jobs the operator actually watches, which are the ones sky.boss did not start.

**9. The clock source.** sky.boss clock / crontab / systemd timer, chosen per job. Two open halves:
whether to cross the line at all (below), and **read-back drift** — every cron/systemd manager rots
where the model and the machine disagree. The mockup's `timers read 20:44` footer is a hint that
wants to become load-bearing: a per-row read-back age and a visible *drifted* state for a unit
disabled outside sky.boss.

## Boundaries

**10. The scheduler/daemon line.** *Closed 2026-09-01 → [[fundamentals]] § the tower is an
observatory, on the operator's ruling: **neither line moves.*** The item asked for a dated
fundamentals decision and got one — but the answer was that the crossing it was built around never
happens. Its stated subject, the clock-source selector, had already been disposed of by
[[schedule]] round 1 (*sky.boss picks no clock, it reads the one each provider stamped*), and the
tower turned out to be an observatory over a provider's grid rather than a picture of sky.boss's
own jobs.

**What the decision is actually worth is the separation, not the ruling.** "The daemon line" was
one name for two rules — **execution** (§ Cadence: nothing keeps running) and **federation**
(`cli/rollcall.py`: no copy of another project's state) — and a proposal could not be argued with
while it invoked both at once. A record is not a process; a copy of one's own work is not a copy of
someone else's. The next proposal has to name which of the two it crosses.

[[fundamentals]] § Cadence: *nothing survives the last window — that is what makes this a scheduler
and not a daemon, and crossing that line is only ever done on purpose.* The clock-source selector
crosses it deliberately and, as drawn, honestly: per job, explicit, with the consequence written
under each option. It still needs a dated fundamentals decision, not just a radio button in a
mockup.

**11. jam.sense keeps its own scheduler.** `CLAUDE.local.md` says sky.boss never manages, generates
or edits its cron entries — and the mockup's original cast *was* that scheduler. The cast has since
been mixed on purpose ([[workbench]] Notes), but the underlying question is untouched: does
sky.boss **observe** those entries, or does the boundary move? Defensible either way; currently
unstated, which is the one thing it should not be.

**12. `--save` invoked from a surface.** *Closed 2026-08-27 → [[workbench]] Notes, ratified as
proposed, and **built** the same day in round 3.* Stronger than the item assumed: the bench adds no execution path ([[canvas]] already
runs subprocesses) and `--save` already composes with a cadence, so the bench composes a one-liner
the CLI supports rather than teaching it anything. Held by a test — no route writes `tools.toml`.
Two consequences of `--save` writing *before* it runs became round-3 items there, and building
them found a third: a usage error raised *below* the write left a tool on disk under a name that
could not be reused, then reported a failure. Fixed in `cli/output.py`.

**18. A schedule viewer, over schedules sky.boss did not write.** *Closed 2026-08-30 → [[schedule]] round 1: `sb schedule` folds every declared project's rows into one table ordered by the parsed instant. The ruling that licensed it — **sky.boss may order; only a provider may judge** — is the test to apply to the next case, and it disposes of the clock-selector half of item 9: sky.boss picks no clock, it reads the one each provider stamped.* Raised by the operator
2026-08-29. **The boundary half needs no decision** — it is item 11 answered in the direction it was
always leaning, and `CLAUDE.local.md` already binds it: sky.boss never manages, generates or edits
another project's cron entries, and that rule was written to bind *whatever scheduler sky.boss grows
next*. A viewer does not move the line; it is the line being used.

**What makes this smaller than it looks: the data already arrives.** `jam report status --json` is
the source `projects.toml` already declares, and it sends 31 job rows carrying `schedule` (the cron
expression), `next_run` **already computed**, `last_run`, `overdue`, `scheduled_in_cron`,
`intentionally_off` and `unscheduled_reason`. The operator's `cols = "job,result,last_age,overdue"`
discards most of it at the view layer. So there is no new source contract to negotiate with a
sibling repo, and nothing here is blocked on jam.sense.

**Answered 2026-08-29, not built.** Five questions, and the first was misframed. What follows is
the recommendation on each; the boundary above is unchanged.

**~~It is a narrowing of a stated refusal.~~ It is not — the refusal does not apply.** The original
argument, kept because it is the one a reader will reach for and it is weaker than it looks:

> `cli/rollcall.py`: *"sky.boss folds sources, not semantics. No common status vocabulary, no
> cross-project verdict."* A schedule view needs exactly that. The distinction that would license a
> narrow one: roll-call refuses to decide what another tool's **word** means, and a cron expression
> and an ISO timestamp are not words, they are measurements.

That asks a reader to accept a new distinction. None is needed. Read what roll-call refuses: *no
common **status** vocabulary, no cross-project **verdict**, no totalling of anyone's `red`* — three
clauses, all of them about producing a judgment sky.boss is not entitled to make. **A schedule row
makes none.** It says when, not how bad. The rule is about verdicts and a schedule is not one, so
this is a question the refusal never covered rather than an exception to it. Still to be written
down and dated if built, because "no common vocabulary" reads at a glance as forbidding it.

The test to carry forward: **sky.boss may order; only a provider may judge.**

**The vocabulary: `name`, `schedule`, `next`, `last`.** Everything else stays the provider's and is
drawn in its own block — item 17b, still open, now in its second place.

- **`schedule` is opaque and never parsed.** Parsing `15 5 * * *` puts a second implementation of
  cron semantics beside the real one, and it will be wrong about DST before it is wrong about
  anything else. Shown verbatim, which is the `sb read` rule.
- **`next` is provider-supplied or absent — sky.boss never computes it from `schedule`.** Deriving
  it is that same second implementation wearing a helpful face. Nothing needs deriving today:
  jam.sense supplies `next_run` for all 31 jobs.

**A project with no schedule is counted, never drawn.** It does not appear in the rows and the view
reports the arithmetic — *"2 of 3 projects declare a schedule"*. Not a blank row, because rows sort
by time and a row with no time has nowhere honest to go. roll-call's *one project down is partial,
never blank* is the same instinct: report the absence, do not render it. breeze-brain is the case,
today.

A **second** absence is already in the data and wants a different word: `test-gap-drain` has no
`last_run` at all — a job that has never run, which is not the same as a project that declares no
schedule, and neither is an empty cell.

**The time axis: build the future, leave the past.** *What fires next across all projects* is one
sort over provider-supplied timestamps — no new primitive, no history, no clock of sky.boss's own.
This matters because sky.boss has **no time axis anywhere**: `run`, `read`, `follow`, `data` and
`roll-call` are all *now*, so this is the first future tense in the tool.

*What should have fired and did not* stays out. It needs history (item 5) **and** a notion of
lateness, and lateness is a judgment — the one place the roll-call refusal genuinely does bite.
jam.sense already computes `overdue`; display that field and never compute a rival. Note it is
`False` for all 31 jobs today, so the late-rendering has **no evidence behind it** — the same shape
items 1 and 5 were in before the ledger arrived, and the same answer: do not draw a state you have
never seen.

**Whose clock: parse to an instant, never compare strings.** `next_run` arriving pre-computed is the
provider's answer to item 9 rather than a convenience, and the payload already carries the trap. One
response, the same jobs, two fields:

```
next_run    all -05:00      2026-08-30T05:15:00-05:00
last_run    all +00:00      2026-08-29T10:19:15+00:00
```

A lexical sort of `next_run` is correct today *only* because those 31 values happen to share an
offset. It breaks the moment two projects disagree, or the moment anything sorts those two fields
together. So an offset is required, a naive timestamp is a declaration error rather than something
to guess a zone for, and sorting is on the parsed instant.

**Never normalize for display.** Show each provider's own string with its own offset. Two projects
disagreeing about what time it is should be visible rather than merged into a resolution nobody
made. That also disposes of item 9's selector half: sky.boss does not pick a clock, it reads the one
each provider stamped.

**The mechanism: a declared mapping over the source that already exists.** No second command, no
second subprocess.

```toml
[project.jam-sense.schedule]
rows = "jobs"
name = "job"
schedule = "schedule"
next = "next_run"
last = "last_run"
```

The operator asserting structure, exactly as `--rows`, `--cols` and `--from` already have them do. A
separate schedule *source*, for a project whose schedule does not ride its status payload, is easy
to add later and hard to take back — the argument that settled one state root rather than one per
project.

**Specced 2026-08-29 → [[schedule]], round 1 drafted and not built.** The answers above are the
doc's Shape, and the ruling that this is not the vocabulary roll-call refuses is stated there
with its date. Round 2 — the past tense — is deliberately unopened for the reason below.

**Still open after all that:** whether it is worth building now, given items 5–9 sit underneath it
and jam.sense is the only project that would populate it.

**Cheap and independent of all of it:** widen that `cols` and look at a real schedule table before
designing one. The rows are already there.

## The Governor

**13. What it costs, and what it does when it cannot run.** The governor is LLM narration over a
log — the strongest idea in the mockup and the only panel doing something a terminal cannot. Open:
who calls it, on what cadence, against what budget, and what the panel shows when the model is
unavailable. It must degrade to the raw events rather than going blank. Also unsettled: it is the
only *mechanical* metaphor in an otherwise clean aviation set, though it does describe the
budget-limiting function accurately.

---

## Going public, and stopping being one person

*Closed 2026-08-30: the repo is public.* Both items below are answered, and what the flip itself
needed — a green suite, a first tag, a machine-neutral tree, a disclosure route, branch protection —
is done and recorded where each belongs. Two lessons are worth carrying past this section, because
neither is about publishing:

- **A pre-flight audit that lives outside the repo is not a pre-flight audit for anyone but its
  author.** The half that could become a test did: `tests/test_publication.py`, checking shapes
  rather than names, for the reason its docstring gives. Four hand-run audits had called the tree
  clean; the shape patterns found five leaks in a minute, three of them in prose that argued the
  rule correctly while breaking it in the same paragraph.
- **Order the irreversible step first.** Adopting `dependabot.yml` before rewriting history meant
  three bot pull requests opened against the old history within a minute, and a pull-request ref is
  permanent — nothing a later force-push does can reach it. The rewrite still ran and every branch
  and tag carries it; what it could not reach was ruled acceptable by the operator. The general
  form: **when one step of a plan cannot be undone, it goes before every step that can create a
  reference to what it is undoing.**

Opened 2026-08-27, when the repo's audience changed from *the operator* to *whoever clones it*.
Several decisions in `CLAUDE.md` were made against a one-contributor repo and were correct for it;
they are not automatically correct for a public one, and this is where that gets argued rather
than drifted into. What was *done* that day — MIT, CI, the slug-resolution test, the history
scrub — is recorded in `CLAUDE.md` and `CLAUDE.local.md` § Publication status; only the two
questions below are still open.

**14. Lint for the JavaScript.** *Closed 2026-08-27 → `eslint.config.js` and `package.json` at
the repo root, gated by the `lint` job in `.github/workflows/ci.yml`.* Adopted because [[workbench]]
is the "something needs them" the item was waiting for — `app.js` is ~1000 lines and the bench adds
a screen, and a ratchet retrofitted afterwards baselines the bugs you just wrote. Clean on arrival:
9 files, 0 errors, 0 warnings, so `--max-warnings=0` starts at zero and may only go down.

Three constraints held. **No Prettier**, and none on `cli/canvas/static/` ever — the `htm` comment
hazard is a formatter's bug with authority behind it. **Config lives at the root, never in
`cli/canvas/static/`**, which is served wholesale and has a declared inventory a stray config would
break. **Vendored code is exempt**, the same rule the hex scan uses. The Electron files are not
split by process: `preload.js` bridges both by design, so a strict split would flag correct code.

**15. Which of skeletor's governance the second contributor actually needs.** *Closed 2026-08-30,
on the operator's ruling, in the pass that flipped the repo public.* Deliberately not answered on
2026-08-27, because the honest answer depended on whether a second contributor arrives — and
"preparing for additional contributors" is that question answered. What each row became is in the
last column; the reasoning that declined them is left standing beside it.

The ones whose *justification changes* the moment a contributor arrives — each declined on
2026-08-27 on single-contributor grounds, and that ground is now gone:

| From skeletor | What it is for | Why it was declined | Ruling |
|---|---|---|---|
| PR + issue templates, `CODEOWNERS` | Shaping an outside contribution into something actionable | Nobody outside to shape | **Adopted.** `CODEOWNERS` auto-requests a review; it gates nothing, because the branch protection does |
| Draft-PR discipline, the CI gate job | Keeping Actions minutes off abandoned iterations | One person, one branch, a 5s suite | **Split.** Drafts are a sentence in `CONTRIBUTING.md`; the gate job is **declined again**, on a new ground — runners are free on a public repo, so the cost it saved does not exist |
| `dependabot.yml` | Bumps that run the suite before auto-merge | No PR flow to run in | **Adopted**, grouped one PR per ecosystem. Review cost is per-PR, not per-bump |
| Conventional-commit hook | The log already reads this way — a hook makes it hold for someone new | Habit sufficed | **Declined**, and the original reasoning was beside the point: **a git hook is not cloned with the repository**, so it could never have reached the contributor it was for. Documented in `CONTRIBUTING.md` instead |
| Coverage / skip ratchets | Catching a suite that quietly stopped testing | Nobody to catch | **Declined.** *Test the decisions, not the ceremony* — a coverage number over 1,083 tests measures lines, and what this suite is for is the silent failures |

**Three things were adopted that this table never listed, and one of them matters more than
anything on it.** `SECURITY.md`: `sb ui` is remote code execution bound to a port, and a public
repo shipping that owes a private disclosure route rather than an issue tracker where a report *is*
a disclosure. Branch protection on `main`, which is what actually gates — everything went straight
to `main` until today. And a **CI matrix over 3.11–3.14**, because `README.md` promised a range CI
did not test; it found a real break on its first run, and the break was a PEP 701 f-string in
`tests/test_naming.py` — a file that had been checked against 3.11 with `ast.parse(feature_version=…)`
and passed, because that argument cannot see a tokenizer change. **A syntax check is not a run.**

`CONTRIBUTING.md` is sky.boss's own rather than skeletor's, and that was forced rather than
preferred: skeletor's names `check pre-push`, the `docs/TODO/` ↔ `docs/implementations/` move and
Release Please, none of which exist here. Copying it would have documented a workflow the repo does
not have — the palette's rule (*never offer a screen that is not there*) arriving in a text file.

**Not on that list, and still declined for reasons a contributor count does not touch:** the docs
lifecycle machinery — generated indexes, `TODO/` ↔ `implementations/`, frontmatter, merge drivers.
`CLAUDE.md`: *"No index machinery yet. There was a generated one; it went with the docs."* The
split this repo uses instead — [[open]], `ideas.md`, [[fundamentals]], one doc per feature — is a
different design, not a smaller one. Also still out: `release-please` and a `VERSION` file, because
the version comes from `git describe` and `cli/banner.py` prints it; a tracked `VERSION` is a
second source of truth that can disagree with the tag, and the mark would be where it showed.

---

## Watching the agents on this machine

Opened 2026-08-28. The tower's `IN FLIGHT` band is drawn for jobs sky.boss started. The jobs the
operator actually wants to watch right now are the ones it did not: several Claude Code sessions
running side by side across sibling repos, each holding a working tree, each burning a context
window nobody can see the bottom of. That is the tower's subject arriving early, from outside.

**16. The tower shows live agent sessions.** An observe, in the tower, listing what is running now.

*Specced 2026-08-29 → [[agent-sessions]]; **round 1 built 2026-09-01** as `sb agents`.* Items 16 and 17 became one doc: the seam and its first adapter are the same decision, and splitting them would have described an interface with nothing behind it. Building it moved item 6 without closing it — the tower's `IN FLIGHT` band can have real rows now, because someone else is persisting the identity. Two things round 1 found that the spec had not: liveness needs a third answer (*cannot tell*, where there is no `/proc` to ask), and an empty table needs a sentence saying which of three empties it is.

The mechanism exists and was verified on this machine rather than assumed: `~/.claude/sessions/`
holds one JSON file per live session, `<pid>.json`, written by the session itself and carrying
`sessionId`, `cwd`, `name`, `status` (`busy` / `idle`), `kind`, `entrypoint`, `startedAt`,
`version`, `procStart`, and a messaging socket path. Five were live when this item was written,
one per sibling repo. `ps` finds the same processes and can tell you none of that.

Three things are already known about it, and each is the kind of detail that costs a round if it
is rediscovered:

- **Liveness is two fields, not one.** A record outlives the process that wrote it, so `pid` alone
  lies twice — once for a crashed session, once for a recycled PID. The record pins `procStart`
  (field 22 of `/proc/<pid>/stat`) for exactly this, and a row is live only when both agree. A
  reader that trusts the PID reports dead sessions as running, which is the "wrong but looks right"
  failure this repo keeps naming.
- **It is an internal format with no contract.** Undocumented, versioned per record, free to change
  under a client update. So an absent, renamed or unparseable registry degrades to *nothing
  declared* — the rule an absent `$SB_HOME` already lives under — and never to a raised error or an
  empty band that reads as "nothing is running".
- **Reading it is a read; touching it is not.** `messagingSocketPath` is a live socket into another
  agent's session, and a stop button or a send-a-message affordance would put a *write* into a
  panel built as an observe. Not forbidden — [[fundamentals]] would just have to say so on purpose,
  the way the clock-source selector crosses the daemon line on purpose. Undecided, and currently
  out.

**What this quietly supplies is item 6.** *Job identity that outlives a window* is the primitive
the plan and the tower are blocked on, and a session registry hands it over for free — a stable
`sessionId`, a derived `name`, and a start time that survives every window sky.boss ever drew. It
does not *close* item 6, because sky.boss's own runs are still anonymous and that is the harder
half. It does mean the tower's `IN FLIGHT` band can have real rows in it before item 6 lands, which
is the first time any of those four primitives has had a path that does not start with the other
three.

**It needs a command, not just a panel.** The surface is a consumer of the envelope and never a
second CLI ([[canvas]]), so this is a `sb` command the tower renders — and its shape is already in
the tree: [[roll-call]] asks every declared project how it is and folds the answers. This asks
every provider who is running and folds the answers. Same fold, different population. **Do not name
it `fleet`** — that word is bbrain's rental fleet and the collision has already cost clarity once.

**17. Providers, modularly — Claude first, and only Claude verified.** *Specced with item 16 → [[agent-sessions]], and **built 2026-09-01**. The row-shape half is ruled there: **thin common record, no extras bag**, on the argument that a common vocabulary with an escape hatch will not survive its second provider — and the debt it named arrived the same day, since the live registry answers four status words and one `null` rather than the two the spec listed. Where the adapter list lives is round 2 there and still open; so is whether `agents` should be offered over [[mcp]], which round 1 declined to take silently.* The operator's ask is that
this not be Anthropic-shaped in its bones, and the honest position is that only one registry has
been read. So: one adapter interface, one adapter written against a format that was actually
inspected, and no speculative adapters for tools whose on-disk state nobody here has opened. A
second provider is a second adapter and a day of reading, not a refactor — which is the whole
point of deciding the seam now.

The seam that makes that true: an adapter answers *what agent sessions are live*, returns records
in one vocabulary — provider, id, name, cwd, status, started, pid — and an adapter that finds
nothing is **silent**, not an error. Nobody has five agent CLIs installed at once, so "not present"
is the common case and must not print anything. The envelope carries the provider on every row,
because a tower that shows five rows without saying which are which is worse than one that shows
four.

Two halves are genuinely open:

- **Where an adapter lives.** Parsing a format is code, so adapters are probably modules in `cli/`.
  But *which are enabled* looks like operator content — `projects.toml` is the precedent, and it is
  outside the repo and never written by sky.boss. Splitting it that way means shipping code for a
  provider the operator has turned off, which is fine, and lets a machine with nothing installed
  stay silent without a config file existing at all.
- **What a row shows when the provider knows more than the interface does.** `status: busy` is
  Claude's word. Context used, model, token spend, the branch a session is sitting on — some of
  that exists per-provider and none of it generalises. A lowest-common-denominator record that
  drops it is honest and thin; a per-provider extras bag is useful and is how a common vocabulary
  rots. Undecided. Whichever wins, the tower must render a row from a provider it has never heard
  of without special-casing it, or the modularity was decorative.

**Not in scope, and worth writing down before someone proposes it**: managing these sessions,
starting them, routing work between them, or reading their transcripts. sky.boss watches what other
tools do. An agent's transcript is the operator's conversation, and a panel that surfaced it would
put someone else's prompts on a canvas that also has an [[mcp]] surface. The band shows that a
session exists, where, and whether it is working.

---

## Where a follow ends, when nobody is watching a terminal

**Half of this is settled.** `sb follow` down a pipe rendered *nothing*: `rich.Live` owns a cursor,
a non-terminal console has none, so it suppressed every frame while the loop ran perfectly — a
working follow drawing to a surface that discards it. The operator ruled on 2026-08-29 that the
non-TTY path **degrades to verbatim lines**: chrome, bands and liveness clock suppressed, lines
printed as they arrive. Not a new product — [[file-follow]]'s "verbatim lines only, no parsing, no
judgment" already described it, and this is that rule with the rendering removed. Built the same
day; `hold` takes an `emit` and the two forms supply one over the `fresh()` delta reader the canvas
already used. Refusing loudly and streaming the `--json` envelope were both turned down — the first
closes non-interactive use, the second makes `follow` a second data-producing command beside
`sb data`.

**~~`sb data --refresh` has the same bug, and the fix that closed it for `follow` did not touch it.~~**
*Closed 2026-08-29 → [[refresh]] round 3, built as recommended below: `refuse_resident_pipe` in
`cli/output.py` raises a usage error naming the fix.* **Reversed for `data` 2026-08-30 →
[[refresh]] round 4, on the operator's ruling out of the morning review: off a terminal — or under
`--json` — it emits one envelope per tick as NDJSON instead of refusing. The round-3 objection was
answered rather than dismissed: a resident render has no *single* envelope, and a stream of
envelopes is not one. `read` still refuses, having no envelope worth streaming.* *(round 3 text:)* The precedent held — it asks `_out()` rather
than a fresh console, so the suite's redirection is what answers, and stdout specifically, because
`reside` draws there and a terminal on stderr is no help.* The diagnosis is kept below because the
argument for refusing rather than degrading is the transferable half.

**The bug, as it was.**
Found 2026-08-29 by the skyrow-workspace session driving `sb` against a live job — reported as
*probably a resident TUI declining to render to a pipe rather than a defect*, which was the right
caution and the wrong conclusion. Measured:

```
timeout 6 sb data --from jsonl --refresh 2 --cols job,status <file>   piped  →  0 bytes, exit 124
same command under `script`                                          tty    →  14,237 bytes
```

Identical to the follow case above: `rich.Live` owns a cursor, a pipe has none, every frame
suppressed while the loop runs perfectly. The `emit` spill went onto `resident.hold` — the streaming
path — and `resident.reside`, which `data --refresh` and `read --refresh` both use, was never given
one.

**But the answer is probably not the same.** A follow's content *is* a stream of lines, so verbatim
was the obvious degrade. A refreshing table has no sensible pipe reading: repeating a whole table
every N seconds is not a document, and silently rendering once while ignoring `--refresh` is the
"wrong but looks right" failure. **The recommendation is to refuse**, which has a precedent already
in the code rather than needing a new argument: `refuse_resident_json` refuses `--json --refresh` on
the grounds that a resident render has no single envelope. A resident render also has no screen
here. `sb data --refresh` down a pipe should say so and name the fix — drop `--refresh` for a single
read — instead of producing nothing for as long as you let it run.

**And the consumer's version of that argument is stronger than the renderer's.** The alternative —
render once and ignore `--refresh` — is not merely untidy: an automation that pipes this does not
get a wrong answer, it **hangs**, because the command is resident and never exits. Refusing turns a
hang into a sentence. That is `CLAUDE.md` § *Worked fine, told nobody*, which this is one of the
five instances of.

**What is still open is termination, and the two forms may not answer it alike.** The ruling was
about rendering. On a terminal, a dead stream keeps drawing: "a corpse on screen is information."
A pipe has no screen to keep it on, so the question is what the *last bytes* are.

**Answered 2026-08-29: one line, naming the death, on stderr.** [[follow]] round 4 is emphatic
that any exit is a death including zero, and silence makes a death indistinguishable from a stream
that has merely gone quiet — which is the exact failure `--due` exists to prevent, arriving through
the one door that had no band to say it. **stderr is what disposes of the objection below**: stdout
stays verbatim log output byte for byte, so a consumer piping it is unaffected, and the sentence
lands on the channel that already carries every other thing sky.boss says about a stream. The same
split that keeps warnings off stdout.

The two arguments as they stood, kept because the second is the one that had to be answered:

- A **process** that exits has an exit code, and [[follow]] round 4 is emphatic that a follow's
  exit — zero included — is a **death**, not an answer. Saying so costs one line. ~~But a line that
  is not log output, on a stream that promised verbatim log output, is the parsing problem this
  whole ruling avoided.~~ *Not once it is on stderr.*
- A **file** has no exit code at all. It stops growing, which is not an event; it is the absence of
  one, and the `--due` clock exists because "quiet" and "dead" are different words. Off a terminal
  there is no band to say which. Does `--due` print a line when it lapses? That is a judgment, and
  the verbatim rule was chosen partly to have none. **Still open** — the ruling above answers the
  process case, and a file's silence is genuinely a different question. Note the ruling narrows it:
  once stderr is established as where sky.boss speaks about a stream, "would this be a judgment"
  is the only objection left, and `--due` is a threshold the operator declared rather than one
  sky.boss chose. *Closed 2026-08-30 → [[unwatched]] round 1: one line on stderr, once per
  lapse, computed by asking `chrome_.cursor` rather than a second implementation — so the piped
  sentence and the drawn band cannot disagree about the same file. The judgment objection is
  answered as this note anticipated: `--due 15m` is a number the operator wrote, and saying it
  has elapsed is arithmetic on their own declaration.*
- And **when does it return?** Resident-by-nature has no natural end off a terminal. Today it runs
  until killed, which is right for `tail -f` and wrong for a script that wants the backfill and
  out. *Closed 2026-08-30 → [[unwatched]] round 1: `--ticks N` on `data` and `read`, meaning N
  refreshes, refused without `--refresh`. The round found `ticks` already meant two things — one
  second in `resident.loop`, one snapshot in the NDJSON loop — so the flag maps to a new `runs`
  bound and a test asserts the two paths agree. `follow` refuses it and names why: it has no
  refresh to count, and "the backfill and out" is one pass rather than N of anything, which is
  round 2 there.*

**Worth keeping from the diagnosis:** `cli/follow.py:219` already asked `console.is_terminal` and
used the answer to pick a display width, throwing the rest away. `cli/banner.py:151` asked the same
question and handed the decision up. The fix was not "add a check" but "use the check that was
already there for the thing it was actually telling you" — which is the shape to look for in
whatever answers the above.

## Where sky.boss learns the agent-state root

*Closed 2026-08-29 → [[state-root]] round 1, built the same day.* Settled as proposed below, with one correction the doc records: the file level was argued here on the canvas — a launcher-started webview inherits no shell environment — and that is true in general but hypothetical on this machine, where no `.desktop` file exists. The reason that held is the one the precedence bullet below already gestures at: **a variable is a snapshot and a file is not**, so an env-only knob would be frozen at launch for every long-lived window, terminal-started ones included. The operator declared `state_root` on 2026-08-29; `SL_AGENT_LOGS` is set nowhere on this machine, so the file is what resolves.

**Decided that it should; not decided how it is told.** `~/src/sl-agent-logs/<slug>/` is the
state root the sibling repos' automation writes to, and its layout was designed so a log path is
derivable from a project sky.boss already knows: the directory under it is the project's **slug**,
deliberately the same key `projects.toml` uses. See `skyrow-workspace/strategy/seams/agent-state.md`.

That derivation does not work today, because sky.boss knows the slug and not the root, and
`projects.toml` declares no root. The writers each carry a default — a fixed path under `$HOME`, in
whatever directory that operator keeps their checkouts in — and **sky.boss must not copy it.** A
writer may hardcode that path because it lives there; sky.boss ships to machines with no such directory, and a workspace layout baked into a
published tool is the same class of leak as a host name in a tracked file.

The shape that fits the house pattern — `SB_HOME` and `SB_STATE` are both `environ.get(...) or
<default>` — is two levels and no default:

1. `SL_AGENT_LOGS` in the environment, **the same name the writers honour**, so one knob points the
   producers and the reader at the same scratch directory. That is the whole value of matching it.
2. A root declared in `$SB_HOME/projects.toml`, operator-authored and hand-edited.
3. Neither → *nothing declared*, which degrades to no state root rather than raising. Same rule as
   an absent `$SB_HOME`.

**Both levels rather than one, for a reason specific to this tool.** An env-only knob is invisible
to the canvas: `sb ui` opens a native webview, and a window started from a desktop launcher inherits
no shell environment — so the knob would work in a terminal and silently not in the surface. That is
the failure mode this file exists to catch.

`projects.toml` rather than a new file, because `$SB_HOME` holds three and `prefs.json` is already
deliberately shaped so it cannot become a second config file. A fourth for one string is worse than
a key in the file that already declares the projects the root is keyed by.

**Open, and both need the operator:**

- **The file is operator-owned and sky.boss never writes it**, so adding a key is a request, not a
  task this repo can take.
- **One root or one per project?** One, on the seam's own argument: repeating the root per project
  rebuilds the hand-maintained table the slug convention exists to remove. A per-project override is
  easy to add later and hard to take back.
- **Precedence is not free.** If the environment wins, a long-lived `sb ui` holds whatever was set
  when it launched while a fresh shell sees a new value — both correct, mutually inconsistent, and
  invisible.
- **A declared project may have no state directory.** `projects.toml` declares `jam-sense` and
  `breeze-brain`; only one has logs. That has to read as *nothing to follow*, never as an error —
  and see the section below, which is about telling that case apart from a mistake.

### Getting from a project to its directory

*Closed 2026-08-29 → [[state-root]] rounds 1 and 2.* Built as proposed — derive from the key, verify by listing `<root>/*`, three states with the sibling listing in the middle. Round 2 then found the same invisible failure in three shapes the proposal did not anticipate, each outside the derivation itself: an undeclared prefix reported as a missing *file*, the same reference with no separator reported as a missing *command*, and `sb follow` waiting in silence forever on a path that could never exist. The listing was the easy half.

The root is half the derivation. The other half is the directory *under* it, which the seam
specifies as the project's **slug** — deliberately the same key `projects.toml` uses, so nothing
maintains a second table. Taking the key at face value is the obvious implementation and it has one
failure worth designing around.

**The failure is not the derivation, it is that its failure is invisible.** An operator who writes
`[project.jam]` for brevity gets a lookup in `<root>/jam/`, which is not there, which reports
*nothing to follow* — the exact sentence a project that genuinely has no logs yet gets. Same shape
as the three defects found the day this was written: not wrong output, but output whose wrongness
cannot be told from a normal state.

**The seam already refused this derivation from the other end**, and its reasoning is worth reading
before deciding, because the conclusion does not transfer:

> `STATE_SLUG` is written in rather than taken from the directory name … deriving the slug from the
> checkout would hand each of them a private state root.

Every writer *declares* its slug because derivation was judged unsafe. But a writer runs inside one
tree and cannot see the others, so it has no way to check a guess. **A reader sees the whole root**,
so it can afford to derive *and verify* — an asymmetry that means copying the writers' conclusion
here would be importing a constraint that does not apply.

So: derive from the key, and close the gap by listing `<root>/*`, which is a directory read with no
schema knowledge in it. Three states, and the middle one is the whole point:

- **Directory exists** → use it.
- **Absent, but the root holds other directories** → name them. *"no state directory `jam`; the root
  holds `jam-sense`, `breeze-brain`"* makes a naming mismatch self-evident in one line.
- **Root absent or empty** → silent. A fresh machine has no root, and saying so every invocation is
  the noise an absent `$SB_HOME` already declines to make.

An optional per-project override then becomes the escape hatch rather than the mechanism: you reach
for it because the diagnostic named it, not because you remembered. That ordering matters — an
optional field that is usually redundant gets omitted, so it cannot be the primary answer.

**Blocked on the root existing**, since the middle case needs a root to enumerate. Not blocked on
anything else, and the listing is cheap enough that it needs no cache.

**Related and already shipped:** the same class of silence in the *parser* — a typo'd table name
returning zero projects and zero problems — was closed on 2026-08-29 in `cli/rollcall.py`, which is
where the state root would have been swallowed next. That fix stands alone and is not a prerequisite
for any of the above.


---

## Known defects

**A hole the three lists left, and the smallest thing that fills it.** A defect that is known, not
yet fixed, and not large enough to reopen a feature doc for had nowhere to live: it is not an idea
(the *whether* is settled — it is broken), and it is not a fundamentals decision. It was landing in
chat logs, which is the loss this file opens by naming. It goes here rather than in a fourth file
because the question is unchanged — *we have decided this should work; how do we make it* — and a
list cut by **kind** would be the first one not cut by a question, which stops composing the moment
a defect also needs a design decision.

The same exit rule applies: an entry leaves by naming where it went, and the pointer is the useful
half.

**22. A dropped session stream never comes back, and the window keeps saying `quiet`.** *Closed 2026-08-30 → [[canvas]] round 10, fixed the same day. The round found a second failure behind the same symptom: the token is minted per launch, so a page whose server restarted can never reconnect at any backoff, and **wait** and **reload** are opposite remedies that had to be told apart.* Reported by
the operator 2026-08-30 — *"it looks like the monitor cut off after some time and stopped showing
new data"* — against `jam-agent-fix-log`, which is `follow --highlight jam jam-sense:log/cron.log`.
The file cursor is not at fault; rotation, truncation and disappearance are all handled and none of
them is what happened.

`stream()` in `cli/canvas/static/api.js` opens the session stream once and calls `onDown()` when it
ends. `app.js` turns that into `setDown(true)` and **nothing else** — the effect that opened it has
an empty dependency list, so it runs once per page load. Once the stream drops, for any reason, it
is down until a manual reload.

Reproduced end to end against a scratch server and a live follow window:

```
append while healthy    → arrives in ~1s
server killed           → down flag set, footer says so
append while down       → never arrives
server back + append    → still down, still nothing        ← never recovers
```

**Two things make this worse than a hang.** The reconnect logic *already exists and is unreachable*:
the `hello` branch re-registers every pinned watcher and re-follows every resident window, with a
comment explaining why a reconnect needs it — someone wrote the hard half and never wired the
trivial half. And the window's own band still reads **`quiet`**, which is the cursor's verdict
meaning *the file was stated and nothing changed*. Nothing is being stated. So the surface does not
merely fail silently, it renders the healthy word over a dead stream — *worked fine, told nobody*
with the extra step of an affirmative false claim. The only true signal is one line in the footer,
at the bottom of the screen, nowhere near what the operator is looking at.

Whatever answers the band here answers the alert half of the docked-window idea in `docs/ideas.md`,
which has the same shape and is strictly harder: a docked window is by definition the one nobody is
watching.
