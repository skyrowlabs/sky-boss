---
status: complete
created: 2026-08-21
updated: 2026-08-23
agent_value: 3
key_files:
  - cli/chrome.py
  - cli/output.py
  - cli/resident.py
  - cli/canvas/server.py
  - cli/canvas/static/app.js
  - tests/test_chrome.py
  - tests/test_canvas_stream.py
---

# Chrome — what a window knows about its output

## Why

Two presentation layers exist in this design and only one of them has a home. **The view** is
in-band — how the data itself is drawn — and it is owned by [[table-views]] and `cli/view.py`.
**The chrome** is out-of-band: everything the surface *knows about* the output that the output
itself does not say. The source argv or keyword. The temporal shape. When it ran and how long it
took. The countdown to the next refresh. The liveness clock. The exit that made a stream go
dead. The warnings count. Nothing owns this set, and the specs now in flight are about to
scatter it: [[refresh]] adds a running-since clock and a countdown, [[follow]] adds a last-line
clock and a dead state, [[file-follow]] adds a stat clock, a size, and rotation announcements —
four status-line implementations, in two renderings each, written separately. That is the exact
drift the one-source pattern everywhere else here exists to prevent: one palette in `theme.py`,
one view heuristic in `view.py`, one catalog off the live tree. The chrome deserves the same
treatment before it diverges, not after.

It also gives the Rule primitive its landing site in advance. The escalation ladder's first
rungs — tint the window, badge it — are chrome reacting to a rule. If the chrome is one
contract, escalation later changes one thing; if it is four status lines, escalation is a
four-file retrofit.

## Shape

**The chrome is a fact set, computed once in Python, drawn twice.** A pure structure in
`cli/chrome.py`, assembled from what the envelope says (`ok`/`partial`, duration, warnings) plus
what the surface knows (interval, last run, liveness, ring occupancy). Both renderers — the
terminal's status lines and the canvas window's title bar and footer — draw what they are told,
exactly as they do for a view. The deciding half lives where pytest reaches it; neither renderer
grows an opinion.

What a window wears, by temporal shape:

| Shape | Chrome facts |
|---|---|
| snapshot, one-time | source · shape · ran-at · duration · ok/partial/failed · warnings count |
| resident refresh | the above · interval · countdown to next run · running-since while in flight |
| process stream | source · last-line clock · ring occupancy · **dead** (exit code, when) |
| file cursor | source · last-write clock (stat) · size · ring occupancy · absent / rotated / quiet |
| act (`run`) | source · ran-at · duration · exit — stamped once, never a countdown |

Sketch of the two renderings, same facts:

```
┌ jam-prs · data · refresh 30s ─────────── ⟳ next in 12s ┐
└ ok · 0.4s · ran 19:04:12 · 1 warning ──────────────────┘

┌ cron.log · follow ─────── quiet 3m · last write 19:01 ─┐
└ 198 KB · showing last 200 ─────────────────────────────┘
```

**The countdown rule is inherited, not re-decided.** [[canvas]] already ruled that a progress
bar shows time to the next refresh and nothing else — a running subprocess has no percentage,
and a bar that animates to look busy is decoration reading as information. The chrome contract
feeds that bar the same `interval` and `last_run` it reads today; the label-clock throttling
trade-off recorded there stands.

**An `attention` slot, reserved and mechanical.** The chrome carries one state field —
`running · ok · partial · failed · dead · quiet · absent · rotated` — populated only by
*mechanical* facts in this round. No judgments: "dead" is an exit code, "quiet" is a stat
comparison, and neither involves reading the output. This is the slot the escalation ladder's
tint and badge will occupy when the Rule branch arrives; reserving it now is one field, and it
is the difference between escalation landing in a contract and landing in a retrofit.

**Chrome consumes the envelope; it never feeds it.** `ok`, `duration` and `warnings` are already
envelope facts and stay so. Everything surface-side — clocks, countdowns, occupancy — stays
surface-side. Nothing chrome-shaped enters `data` or the envelope, so `--json` output is
untouched by this feature existing, byte for byte.

**Does not do:**

- **No spinners, no percentages, no busy animation.** The [[canvas]] argument, restated once:
  decoration that reads as information.
- **No rules, no thresholds, no judgments.** The attention slot is populated by mechanics only.
  Conditional states (a rule matched, a value crossed a line) are the Rule branch's to add.
- **No operator configuration.** Chrome is uniform per shape — no flags to hide it, reorder it,
  or extend it. A knob here would be a third rendering to test. If a real need appears, argue it
  as its own round.
- **No new envelope fields.** Stated above; a test holds the line.

## Phases

### Round 1 — one contract, two renderings (2026-08-21)

- [x] **The facts, pure.** `cli/chrome.py`: the per-shape fact set assembled from envelope +
      surface state over an injectable clock. Tests cover every shape and every mechanical
      attention state; no real time anywhere.
- [x] **The terminal rendering.** Status lines for the one-time and resident forms; [[refresh]]'s
      resident loop renders through it from birth rather than growing its own.
- [x] **The canvas rendering.** Title-bar and footer band from the same facts; the existing
      progress bar re-pointed at the contract's `interval`/`last_run` unchanged in behavior.
- [x] **The envelope boundary test.** An envelope produced with chrome active is byte-identical
      to one produced before this feature existed.

### Round 2 — the facts wear their own roles (2026-08-22)

Rendered against the live cron.log, the round-1 bands are correct and illegible in exactly the
common case: the whole band takes the attention color, so a *quiet* window — the normal state,
for hours — draws its most useful facts (`quiet 22m · last write 03:46:52`) in the dimmest grey
on screen. One color per band was the cheap first rendering, not a decision worth keeping.

The polish: **each fact in the band wears its own theme role, and the frame stays dim.**
Corners and fills are always muted — they are furniture. The source is the strongest thing in
the band (bold), the shape words stay muted, clocks and stamps take the label role, counts take
the number role, and only the *state-bearing* fact takes the attention color: the countdown in
accent, a death in danger, a rotation in warn, a verdict word in its verdict's color. Quiet's
clock renders in label — readable and calm — because quiet is the state the band exists to
make legible, not to hide.

Still one contract: the spans are computed in `cli/chrome.py` as `(text, role)` pairs — the
deciding half where pytest reaches it — and `status_lines` keeps returning the same plain
strings by joining them, so every width and truncation property already proven stays proven.
Renderers assemble spans into styled text; none of them grows an opinion. No new colors: every
role named already lives in `cli/theme.py`, and the no-hex scan does not move.

- [x] **Spans, pure.** `status_bands()` beside `status_lines()`: the same band layout as
      `(text, role)` spans, width-exact, left side truncating by span. Tests: roles per fact,
      fills always muted, plain-join identical to `status_lines`.
- [x] **Renderers assemble.** `cli/output.py` gains the span-to-Text assembler; the resident
      loop, both follow forms and the run/read exit stamps render through it. The whole-band
      role styling is retired.

### Round 3 — a snapshot wears its chrome too (2026-08-23)

The fact table above has carried a `snapshot, one-time` row since round 1 — *source · shape ·
ran-at · duration · ok/partial/failed · warnings count* — and `chrome.snapshot()` builds it. But
only a **resident** window draws bands. A one-shot `sb data` prints `● data  53 rows` and stops.
So the facts exist, are tested, and are never shown for the most common invocation in the CLI.

Raised by the operator as a sketch for a richer result header, and it turned out to be asking for
exactly this: a top block of facts and a bottom rule closing the output. That is `status_bands()`,
drawn once instead of on a tick.

```
┌ jam report status --json · data ─────────── ran 20:02:53 ┐

  generated   2026-08-23T20:02:53+00:00
  jobs        table · 15 × 27
  …

└ ok · 0.4s · 27 rows ─────────────────────────────────────┘
```

**The bottom rule is the point, and it is not decoration.** Today a truncated result says so
(`N more rows not shown`) and a complete one says nothing — so silence means both *"that was
everything"* and *"the output stopped early"*. A terminator makes completion visible, which is the
only thing that lets truncation mean something. It matters more with [[mcp]] specced: an agent
reading a result needs a frame boundary it did not have to infer from the absence of one.

**Earned by size, not printed always.** A three-row result between two rules of chrome is ceremony
outweighing content, and a band on every `sb read` of a two-line command is the thing an operator
would want a flag to turn off — and this feature refuses flags. The band draws when the result is
large enough to have a middle, or when the window is resident and already wears one. The threshold
is a number to measure at a terminal, not to decide here.

**No leading gutter.** The sketch drew a `|` down the left of every line. Rejected: a gutter breaks
copy-paste of the content, which is a specific cost for a tool whose job is showing what a command
printed — and `sb read` is verbatim *by contract*, so a gutter would make it not verbatim. Bands
are top and bottom only, which is what both existing renderings already do.

**What does not move here.** The payload's own type and dimensions — `table · 15 × 27` — are a
fact the output *states*, so they are in-band and belong to [[table-views]] round 4, not to this
doc. This feature's Why is doing real work for the first time: chrome is what the surface knows
that the output does not say. `ran-at` and `duration` are chrome. `27 rows` is chrome quoting a
count it was handed. The shape of the data is not.

Two facts from the sketch are **rejected for the snapshot form**: `last modified` and `size`. They
are file properties, and the sketch showed them over a command (`ip -j -br addr`), which has no
mtime and no size on disk. They are already correctly specified — on the `file cursor` row of the
table above, where they belong.

**Does not do** gains:

- **No gutter, no side rules, no box.** Top and bottom bands only.
- **No band on a small result.** Chrome costing more lines than it explains is decoration.

- [x] **Snapshot bands, pure.** `status_bands()` accepts the snapshot and act shapes; the spans
      exist already, so this is the layout call and its tests. No new facts.
- [x] **The terminal draws them**, above and below the rendered value, at the same width
      arithmetic the resident bands already use. Behind the size threshold.
- [x] **The threshold, measured.** Pick it at a real terminal against real results, and record the
      number and its reasoning in Notes rather than in a constant's name.
- [x] **The canvas draws them** for a non-resident window, which today has a title bar and no
      footer. Verified headless per [[canvas]], the frontend still having no runner.
- [x] **The envelope boundary test extends** to the snapshot form — an envelope produced with
      snapshot chrome active stays byte-identical. Round 1 holds this line for resident; it must
      hold here too, or the feature has grown a field it promised not to.

## Notes

### Round 3 — shipped, and the canvas never needed a band (2026-08-23)

The terminal half landed as specced. The canvas half turned out to be a smaller and more
interesting question than the round assumed.

**A canvas window already has a frame, so the frame *is* the band.** The doc said the canvas
"draws them for a non-resident window, which today has a title bar and no footer" — wrong on the
last clause: every window has had a `.foot` since [[canvas]], carrying the verdict, the warning
count, the attention word and the duration. The terminal needed two rules because it has no frame
to hang those on; adding rules inside a window that already has a border would have been drawing
the same idea twice. So the canvas half became *make the footer say what the terminal band now
says* — which is one fact, the payload's size.

**And that turned up dead code.** `summarise()` reported `${view.rows.length} rows`, but `unwrap`
only returns `kind: "rows"` for `run`'s wrapped stdout; a plain `sb data` payload comes back as a
value. So the row count in the footer had never once fired for the command that footer sits above
most often. Found only by rendering it. That is the third defect this week whose whole lifetime was
"looks implemented, never ran" — and all three were found by pointing the thing at real data rather
than by reading it.

**The duration had to come from somewhere that is not the envelope.** Round 1's boundary says
chrome consumes the envelope and never feeds it, and `Result` has no `ran_at` or `duration_s`. The
answer was already in the shape of the feature: `emit` wraps every command, so it can time the call
and build the source from the live context, and both are *render-time* facts. `--json` output stays
byte-identical, which a test now asserts for the snapshot form as round 1 does for resident.

**The threshold, measured** at 80 columns rather than chosen: a body of 8 lines is plainly outweighed
by two rules of chrome, 14 plainly earns them, and 12 is where the header stops being readable
alongside the footer. `_body_lines` estimates from the data rather than the rendering — the question
is only *does this have a middle*, and an answer that had to render first would mean rendering twice.

**`run` resolved itself.** It stamps its own act band and sets `data = None`, so it scores zero
lines and never acquires a second pair. Worth a test rather than a comment, since the next command
that returns no data will land in the same branch.


### Round 1 — written as spec, from spec review (2026-08-21)

Born from the operator's question during review of the first three specs: can output be
"reimaged" — portrayed in a window annotated with additional info, metadata, timers. The answer
was that the design already implied the layer and three specs were about to implement it three
ways. Consolidated here *before* divergence — the cheapest moment — on the same argument that
put the view heuristic in Python and the palette in one file. Build order places this right
after [[refresh]], which creates the first resident terminal rendering to hang it on;
[[follow]] and [[file-follow]] then render through it rather than migrating onto it.

### Round 1 — executed (2026-08-21)

The first two phases were pulled *inside* [[refresh]]'s execution, between its renames and its
`--refresh` phase, so the resident loop rendered through `status_lines` from birth. What the
execution argued back:

- **The transport was already the right seam.** The canvas never shipped bare envelopes — the
  runner's `Run.to_dict()` wraps one — so `chrome` attaches beside `envelope` in the frame and
  the run response, and the envelope inside stays byte-identical without any migration. The
  boundary test pins the envelope's exact key order instead of asserting a negative.
- **The watcher's monotonic clock never ships.** `last_run` in the contract is stamped in epoch
  seconds at result time — the same moment the page stamped `ranAt` before — because a
  monotonic reading means nothing to another process. The bar reads the contract's number with
  identical behavior, falling back to the local stamp for a window that has not heard from the
  server yet.
- **`acts` comes through the catalog at assembly time**, never from `argv[0] == "run"` alone —
  a saved tool's first word is its own name, and the catalog is the one place that knows what
  it expands to. Same inheritance rule as the cadence control, applied a third time.
- The cursor constructor takes the *loop's* state verbatim and refuses any word outside its
  vocabulary — chrome carries verdicts, it never re-derives them, and the ValueError is what
  keeps a future caller from inventing a tenth attention word without meeting this doc first.

### Round 2 — executed (2026-08-22)

Prompted by the operator rendering the round-1 bands against the live cron.log and asking for
color and aesthetics. Scoped deliberately to band polish: line-level tinting (timestamps, job
tags, ⚠ lines) was offered and not chosen — it crosses [[file-follow]]'s "does not parse"
boundary and belongs to the Rule branch's highlight rung when it comes.

`status_lines` survived as the spans joined, so the whole round changed zero plain-text bytes —
every width and truncation test proved the styled rendering by construction, and the suite's
only new tests are about roles. `ROLE[attention]` still exists and still drives the canvas dot
and the theme mapping; what retired is only the terminal's whole-band application of it. The
verdict word wears `ROLE[word]` directly, which quietly guarantees the bottom band and the
canvas dot can never disagree about what color a verdict is.

### Round 3 — the fact table was ahead of the renderer (2026-08-23)

Worth recording because it is the second time this month a doc turned out to have already
specified the thing being asked for. The operator sketched a result header — type, dimensions,
when, size, a terminator — as a new idea. Four of the five facts were already in this doc's round
1 table, two of them on the wrong row for the example given, and the fifth belonged to
[[table-views]].

What was actually missing was not a fact. It was that `snapshot` never draws. The round 1 table
was written by reasoning about all five temporal shapes at once, and the two that had windows on
the canvas got renderers; the one that only ever appears as CLI output did not, and nothing
noticed because the tests test the fact set.

The general lesson is the one this repo keeps relearning from a different direction: **a contract
with a tested producer and no consumer looks exactly like a finished feature.** [[table-views]]
round 4 is the same shape — three rounds of rules tested against a payload structure no real tool
returns.
