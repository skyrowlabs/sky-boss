---
status: done
created: 2026-08-26
updated: 2026-08-28
agent_value: 3
key_files:
  - cli/canvas/server.py
  - cli/canvas/static/bench.js
  - cli/canvas/catalog.py
  - cli/canvas/static/app.js
  - cli/canvas/static/render.js
  - cli/view.py
  - cli/chrome.py
  - cli/tools.py
  - docs/design/Workbench.dc.html
  - cli/canvas/static/sb.css
---

# Workbench — where a command gets made

## Why

The palette is a one-line composer: type a command, it runs, a window opens. That is the right
shape for invoking something you already trust and the wrong shape for **authoring** something you
do not. Every knob that makes an invocation correct — which contract, which columns, which
cadence, which working directory — is currently either typed blind or discovered by running `sb`
in a second terminal and pasting the result back into the first.

`--cols` is the clearest case. `jam pr list --json` returns fourteen columns; the useful table is
four of them. Today you learn which four by running the command, reading the shaped table, reading
the warning that names what was hidden, and typing a comma-separated list from memory. The
envelope already knows every column and says so — `view.columns`, `view.details`, `view.hidden` —
and no surface has ever shown that set to anyone. **It is a flag you get wrong by typing and right
by looking, and there is nowhere to look.**

The second diagnostic came from the design pass. On a canvas whose every pane is a stream of
timestamped lines, three of the four output contracts have nowhere to appear: the shaped table, the
verbatim block, the file cursor with its stat row. They are built, tested, and invisible. The
workbench is the one screen where all four are visible at once, **because it is the only screen
where you choose between them** — and the choosing is the thing sky.boss says no parser can do for
you.

The console the mockup started from was two screens wearing one. It carried a job rail and a live
tail (watching, which the tower already does better) bolted to a composer (authoring, which
nothing else does at all). Splitting them is what makes room for any of the above. See
`docs/design/Workbench.dc.html`.

## Shape

**The contract selector is the spine, and it is the first thing on the screen.** Four entry
points, with `run` set apart under *acts* and the other three under *observes*. It is not a
convenience: it is the operator asserting the one bit no parser can infer, and the assertion gates
everything below it. Changing it changes the result renderer, the view controls, whether a cadence
may be offered, and whether a trial run is possible at all.

**An observe is drafted by running it; an act is not.** *Trial run* executes the argv in a
subprocess exactly as the canvas already does and draws the envelope in the renderer it will
really use — the shaped table, the verbatim block, the ring, the file cursor — wrapped in the
[[chrome]] band for that temporal shape, top and bottom. Nothing is re-implemented: this is the
existing execution path pointed at a page that has room for the result.

For `run` there is no trial. sky.boss will not execute a write to show you what it would print, so
the bench offers what it *can* check without running — the argv parses, the executable resolves, the
`--cwd` exists — and a single button that runs it for real, labelled as such. The asymmetry is not a
limitation to apologise for; it is the act/observe split appearing a third time, after `--help` and
after the missing `--refresh` flag.

**The view controls are per contract, and the column checklist is built from the run.** For `data`,
every key the trial returned is a chip — selected ones in order, unselected ones dim — assembled
from `view.columns + view.details + view.hidden`, which the envelope already carries. Clicking a
chip rebuilds three things together: the table, the warning naming what is hidden, and the argv
the bench is about to save. `--from` and `--rows` sit beside it. For `read` there are no view
controls, because a view describes rows and that contract returns none; for `follow`, `--due` and
`--highlight`; for `run`, the panel says why there is nothing to shape.

**The job strip is the last step and it reads left to right**: the `--save` name, the cadence, and
the argv the bench will run. **It is pinned to the bottom of the bench and is always on screen**
(round 4) — the panel that may grow without bound is the *result*, and that is the one that
scrolls inside itself. Cadence offers only `0 · 5 · 30 · 60 · 300` — the values [[tools]]
actually accepts — and it is **absent** on `follow` (resident by nature) and on `run` (a cadence on
a write is a scheduler nobody asked for). Absent, not disabled: a greyed control invites an
argument the design already had.

**`--save` stays the only writer of `tools.toml`.** The bench composes
`sb data --cwd … --cols … --refresh 30 --save prs -- jam pr list --json`, shows it, and runs it as
a subprocess. The surface still has no writer of its own, no route that touches the file, and the
append-only, refuse-a-duplicate behaviour is unchanged because it is the same code path. On `run`
there is no save at all — `--save` saves by example and the example ran — so the bench renders the
`[tool.name]` block to paste instead.

**The reference rail follows the contract**, drawn from the live Click tree like the palette, so
the help that serves `--help` in a terminal serves the bench with no second copy to drift. It
carries the contract's own *acts* or *observes* badge, because a rail that lists `run` beside
`data` with no visual difference loses the bit the whole design turns on.

**Does not do:**

- **No second writer of `tools.toml`.** Stated above; a test should hold the line the way
  [[canvas]]'s no-CORS test does.
- **No editing or deleting a saved tool.** `--save` appends and refuses a name that exists.
  Editing and deleting stay `$EDITOR`'s, unchanged by a surface existing.
- **No dry run, ever.** There is no `--what-if` for an act and inventing one would mean sky.boss
  modelling what a foreign command does.
- **No inferring the contract from the argv.** The selector is the assertion. A bench that guessed
  `data` from a trailing `--json` would be the act/observe split undone by a heuristic.
- **No job identity, claims, budget or clock source.** Those are the plan's and the tower's, they
  need four primitives that do not exist, and none of them is required for the bench to be worth
  opening. See `docs/open.md`.
- **No history.** A saved tool has no run log yet. When it does, that is its own doc.
- **No page-level scroll.** The bench is a screen, not a document: its panels are sized against
  the viewport and the one that can outgrow it scrolls internally. Round 4 rejected making
  `.bench-main` a scroll container for this reason.
- **Does not replace the palette's one-line path.** Typing a foreign argv and getting
  `read -- <argv>` stays exactly as it is; the bench is where a line that took three tries goes to
  get made.

## Phases

### Round 4 — the last step fell off the bottom (2026-08-28)

Reported from use: *"we are missing a way to save the command on the workbench UI."* It is not
missing. `JobStrip` renders for every contract, including `run`, where it carries the name field
and the `[tool.NAME]` block round 3 built. **It is unreachable**, and nothing on the screen says so.

Measured at the operator's window rather than inferred, with `--scale 1.6` in a 756px-tall window:

```
.bench-job    top 608 → bottom 987        viewport height 669
.bench-main   scrollHeight 881, clientHeight 474
```

`.bench-main` is a flex column carrying `min-width: 0` and **no `overflow` and no `min-height: 0`**,
so its children overflow and are clipped instead of scrolling. There is no scrollbar anywhere on
the bench. At the default `--scale 1.15` in a tall enough window everything fits, which is exactly
why this survived three rounds — **the bench was only ever looked at in the geometry it was built
in.**

**The act path is the worst case, which is why it was `run` that found it.** `.bench-blank.act`
drops the `max-width` every other contract's blank state has, so the refusal paragraph, three
checks and the button together are the tallest thing the result panel ever holds — and
`.bench-result` is `flex: 1`, so it takes precisely the space the job strip needed. The panel
explaining *why there is no trial run* pushed off the panel you go there to reach.

### Pin the last step; scroll the panel that can grow

Making `.bench-main` a scroll container was considered and **rejected**. It is the smaller change
and it turns the bench into a document you scroll, which puts the last step of a top-to-bottom flow
somewhere you have to go looking for — a weaker version of the defect being fixed. Worse, it would
scroll the *contract selector* off the top, and Shape calls that "the spine, and the first thing on
the screen".

So: the job strip is pinned to the bottom of `.bench-main`, and the **result** panel scrolls inside
itself. That is not a new idea — it is [[canvas]]'s rule for a window body arriving on the second
screen, where the frame is fixed and the output is what overflows. It also puts the scrollbar on
the one panel whose height genuinely depends on what a foreign command printed.

**Does not do:**

- **No page-level scroll**, per the rejection above. The bench is a screen, not a document.
- **No responsive breakpoints, no collapsing panels.** ~~The reference rail keeps its fixed
  width; this round is about the vertical axis only, which is the one that broke.~~ *Half reversed
  while building: the rail gains a `max-width: 34%` and nothing else. Its width is in `rem`, so it
  scales with `--sb-scale` while the window does not — at `--scale 2.4` it wanted 1037px of a
  1416px window and left the bench 340px, where every note wrapped into a column and the strip
  measured 1895px. The vertical overflow was partly the horizontal starvation. Still no
  breakpoints and still no collapsing.*
- **Nothing about `--save` on `run`.** Round 3's asymmetry is intact and is not what this was.
  The block was always being rendered — it was being rendered off-screen.

- [x] **`.bench-main` stops clipping**, and a `.bench-scroll` group takes everything between the
      spine and the last step. `min-height: 0` so a flex child may be smaller than its content;
      the contract selector and the job strip stay `flex: none` at the two ends.
- [x] **The job strip is pinned, capped, and scrolls inside** — all three, because each of the
      first two alone fails. The name row sticks to its top and the save row to its bottom, so the
      step and the act stay put while the block and the notes scroll between them.
- [x] **The panels that can grow own their overflow.** `.bench-result` keeps `flex: 1` with a
      floor; the act blank state gets a bounded `max-width` back; the reference rail gains a
      `max-width` so it cannot starve the column it annotates.
- [x] **Verified by rendering at five geometries**, because one geometry is what caused this: at
      `--scale` 1.15, 1.6, 2.0, 2.4 and 3.0, for an act and an observe, the contract selector, the
      job strip, the name field and the save button are all on screen.

### Round 1 — the bench and the trial run (2026-08-26, done 2026-08-27)

- [x] **The page.** A workbench route on the canvas: contract selector, `--cwd` picker, argv
      field, trial run. Selecting a contract swaps the draft rather than clearing it.
- [x] **The result, in the renderer it will really use.** Route the existing subprocess execution
      at the bench and draw the envelope through `render.js` unchanged — table, verbatim, ring,
      file cursor — with the [[chrome]] band top and bottom for that shape. `MAX_ROWS` and
      `MAX_CHARS` apply here exactly as everywhere else.
- [x] **The reference rail**, from `/api/catalog`, carrying the contract's acts/observes badge.
- [x] **The empty state.** A fresh install has no tools and no draft. Decide what the bench opens
      on before the screen exists, not after.
- [x] Tests: the bench route refuses an unauthenticated request like every other; a trial run of
      an `acts` contract is refused server-side and not merely hidden in the UI.

### Round 2 — the view controls (2026-08-26, done 2026-08-27)

- [x] **The column checklist**, assembled from `view.columns + view.details + view.hidden`. No new
      envelope field; if one turns out to be needed, that is a [[table-views]] round, not this one.
- [x] Clicking a chip rebuilds the table, the hidden-column warning and the composed argv together.
- [x] `--from` and `--rows` beside it; `--due` and `--highlight` for `follow`, with the declared
      highlight rules applied to the drawn result so you can see which words claimed what.
- [x] Tests, in `cli/view.py` where pytest reaches them: the offered set is exactly what the
      envelope carried, and a chip for a column no row has is never offered.

### Round 3 — the act asymmetry and save (2026-08-26, done 2026-08-27)

- [x] **`run`'s refusal**, drawn: the checks that are possible without running, and one button
      that runs it for real.
- [x] **Save.** Compose the argv, show it, run it as a subprocess. The append-only and
      refuse-a-duplicate behaviour comes from `--save` unchanged.
- [x] **The name field is the last control, and it is checked before it is used.** `--save`
      writes *before* it runs (`cli/data.py`), so a mis-composed argv is on disk before its own
      output shows it was wrong — and the name cannot be reused, because a duplicate is refused
      and editing stays `$EDITOR`'s. The bench asks *the server* whether the name is taken and
      says so *before* offering the button, rather than surfacing a refusal after the write.
      **Not `/api/catalog`, as this line originally said** — `cli.tools.name_problem`, which reads
      the file. The catalog would have answered a slightly different question.
- [x] **Save is drawn as a second run, because it is one.** Trial run and save are two separate
      invocations of the same argv; the save does not confirm the trial run's output, it repeats
      the work. A UI that implies otherwise is claiming a guarantee `--save` does not make.
- [x] **The `[tool.name]` block** for `run`, rendered to copy.
- [x] Tests: no route writes `tools.toml`; the composed argv round-trips — saving it and reading
      the tool back yields the same invocation.

## Notes

**2026-08-26 — the console was two screens wearing one.**

The design pass began with a console tab holding a composer, a job rail, a queue strip and a live
output pane, plus a three-way layout switcher (console / wall / floating). Reviewing it against
the tower found that the rail and the tail were the tower's job already, and that *wall* was
simply the tower's `split`. What the console uniquely held was the composer — and the composer had
nowhere to put the things that make authoring hard, because a canvas of log panes has no place to
draw a table.

So the console was removed and the workbench replaces it, and the three screens now read as three
verbs: **build → schedule → watch**.

Two things died with the console and are deliberately *not* resurrected here, because they belong
to the tower if they belong anywhere: the **queue strip** (the only widget that showed one run's
shape at a glance) and the **floating canvas** (the draggable-window metaphor [[canvas]] was built
around). Both are recorded in `docs/open.md` rather than quietly dropped — the floating canvas in
particular is a reversal of [[canvas]]'s central claim and deserves an argument, not an omission.

**Why this is buildable now, when the plan and tower are not.** Nearly every part of the bench
maps onto shipped code: the four entry points exist, `--cwd` exists, the catalog walks the live
tree, [[chrome]] is one contract drawn twice, [[table-views]] already returns the full column set
in the envelope, [[highlight]] tints, [[follow]] and [[file-follow]] stream, and `--save` writes.
What the bench adds is a *place to look* — not new mechanism. The plan and the tower are the
opposite: they need job identity, a claim, a budget and a clock source, none of which exist, and
the last of those crosses the scheduler/daemon line [[fundamentals]] says is only ever crossed on
purpose.

**The trial run is expected to change the CLI, and that is the point.** Building a surface that
runs the real commands and draws the real envelope is the cheapest way to find the flags that
should exist and the facts that should ship. A mockup can only draw what someone imagined.

**2026-08-27 — `--save` from a surface, ratified.** `docs/open.md` held this open on the grounds
that *"no surface writes" is the kind of rule that erodes by reasonable-looking steps* and wanted
the round-3 proposal ratified rather than assumed. Ratified as proposed, and the argument is
stronger than the doc had it: this is not a new mechanism and it is not even a new *shape*.

The canvas already runs commands as subprocesses — [[canvas]]'s *reads in, execution out* — so the
bench adds no execution path. And `--save` was already built to compose with a cadence: `cli/data.py`
documents *"a `--refresh` in force becomes the saved command's own cadence"*, which is exactly what
the job strip reads left to right. The bench composes a one-liner the CLI already supports; it does
not teach the CLI anything.

So append-only, refuse-a-duplicate, and *you are saving an argv, not a result* all come free,
because it is the same code path rather than a second one that agrees for now. Held by a test
shaped like [[canvas]]'s no-CORS assertion: **no route writes `tools.toml`.**

What the ratification *did* surface is two consequences of `--save` writing **before** it runs,
both now round-3 items. The save is a fresh invocation rather than a confirmation of what the
trial run drew, and a wrong argv reaches disk ahead of the output that proves it wrong — under a
name that then cannot be reused. Neither changes the decision; both change the drawing.

**2026-08-27 — round 1, and the four things it decided by building.**

**The empty state opens on nothing selected**, which is a departure from the mockup and the one
round-1 decision worth arguing. The mockup pre-selects `data`. But the Why above says the selector
*is* the operator asserting the bit no parser can infer — and answering it for them on arrival is
that inference with a friendlier face. It also gives the empty pane something true to say instead
of a blank: the reference rail lists all four contracts with their badges, which is exactly the
choice being asked for. The cost is one click, which is the correct price for an assertion.

**A second route, not a flag.** `/api/trial` is `/api/run` with one rule added — an act is refused
— and that rule is why it is a route rather than `run` with `trial: true`. The palette must keep
being able to open a `sb run` window, so one route that sometimes refuses `run` and sometimes does
not would be a route with two contracts. The refusal is server-side because a surface that merely
declines to draw a button has not refused anything: the check has to be where the request arrives.
`follow` is refused there too, for a different reason — `runner.run` would sit on a held-open
stream until the timeout and then report a hang as a result.

**A follow trial is a pseudo-window on the session.** It goes down `/api/follow` with the window id
`bench`, so its frames arrive on the existing stream and it dies with the session exactly as a
window's would. Nothing new was built to hold it open. This is the same reasoning as the trial run
itself: the bench adds a place to look, not a mechanism.

**`--` is inserted, and inserting it chooses nothing.** The bench prefixes the operator's typed argv
with `--` unless they typed one. That is safe even for `follow`, whose file-versus-command dispatch
reads what comes *after* the separator — `sb follow -- build.log` is still the file form. What the
bench does *not* do is decide the form itself, which would be the second parser sky.boss refuses to
have. The composed line is drawn above the result before it runs, so the one real limitation — the
argv is split on whitespace, so a foreign argument containing a space cannot be typed yet — is
visible rather than silent. That is the first flag the trial run has already asked for.

**What building it changed elsewhere**, which is the Notes entry above predicting itself:

- `_summary` in the catalog took the first *line* of a docstring, and a docstring is hard-wrapped
  by whoever wrote it — `sb data`'s ended "An observe — a window may". The palette hid it behind an
  ellipsis and nobody noticed. The rail draws it in full. It now takes the first paragraph with its
  newlines collapsed, and drops a trailing clause ending in a colon, because that colon is
  introducing an example the summary does not carry.
- `entry_for` replaced `{e["name"]: e["acts"]}.get(argv[0])`, which called every saved tool a read
  — including one wrapping `run`, the exact mistake the read/write split exists to prevent. Longest
  path first, the same rule the palette's `suggest` follows.
- The reference rail's flag descriptions and the empty state's prose moved off `TEXT_3`. Reading
  text takes `TEXT_2`; `TEXT_3` is structure and is what `BORDER` is. That is the ruling from
  [[fundamentals]] § *the label tier* landing on its first real screen rather than being restated.

**Deferred to a later round, deliberately.** The saved-commands rail on the left, which the mockup
draws on the bench: clicking a tool there should load it *into the draft*, and the expansion of a
saved command is not something the page has — the server resolves it, as `resolve_follow` does.
That is a real dependency and not a layout question, so it waits rather than being drawn as a
sidebar that opens canvas windows from the wrong screen.

**2026-08-27 — round 2, and the trap the checklist walks into if you do not shape twice.**

**A chip click re-shapes; it does not re-run.** `/api/shape` takes the payload the trial run
already returned and hands back a fresh view — a pure function of the rows, running nothing, on the
same side of *reads in, execution out* as `/api/catalog`. Two reasons, and the second is the one
that decided it. A view *describes how to present data and never filters it*, so which columns are
drawn is a question about the drawing, and answering it by re-running the foreign tool would be
re-fetching to settle a layout. And re-running would make every chip compare against a slightly
different dataset, which is precisely the comparison the checklist exists to let you make.

**The trap: a `--cols` view cannot supply its own checklist.** With `--cols` in force `shape`
returns exactly what was named and `hidden` is empty — so a checklist built from the drawn view
loses every column the moment you untick it, with no way to tick it back. The route therefore
shapes **twice**: once with what was asked for, to draw; once with nothing asked for, for
`offered`. Held by a test, because it is invisible until someone unticks the last column.

**A chip is lit when its column is drawn, not when it was named.** With no `--cols` the shaping has
already decided — an empty column and an opaque sha are hidden by rule — so lighting every chip
would claim nine columns were showing when six are. Read off the view like everything else here.

**The chosen set is rebuilt in the checklist's order, not in click order.** `--cols` sets column
order, and letting that depend on the sequence of clicks would produce a table that quietly differs
from an identical-looking one. The checklist's own order is inline → prose → hidden-by-rule, which
answers *why is this chip here* rather than reproducing the tool's key order.

**Two flags re-shape and three do not.** `--cols` and `--rows` describe the drawing. `--from`
changes how the tool's bytes are parsed, and `--due` and `--highlight` belong to a stream being
opened — all three compose into the argv and take effect on the next trial run. The panel says so
rather than leaving it to be discovered by clicking.

**`warnings_for` moved into `cli/view.py`, and it should always have been there.** It was inline in
`cli/data.py` only because there had been one caller. *Which columns went quiet* is exactly the
kind of decision the module header already argues belongs in Python — and the bench asks the same
question of the same payload without re-running the tool, so two copies would have drifted the week
after they were written.

**The foot band counts this shaping's warnings, not the trial's.** Found by looking at a screenshot:
the band said `1 warning` above a body showing none, because the chrome still carried the count
from the run while the body had been re-shaped. A footer describing a shaping nobody is looking at
any more is the looks-right-and-isn't failure in miniature.

**Round 1's plain follow tail is reversed here.** It was drawn without marks on the reasoning that
tinting belongs to a window living with a stream. `--highlight` being a *control* on this screen
makes that untenable: you cannot choose a ruleset by name and then not see what it claimed.
`markedLine` moved from `app.js` into `render.js` so there is one slicer rather than a copy —
verified against the operator's own `[highlight.jam]`, which claimed `passed`/`clean` as ok,
`failed`/`errors` as fail, `escalating` as warn and `skipped`/`deferred` as muted, while sky.boss's
own timestamp rule had already claimed `20:41` ahead of them.

**One unexplained thing, recorded rather than claimed fixed.** During testing the page reached a
state where no `setDraft` re-rendered — the composed line froze while chip clicks still fired their
requests. It did not survive a reload and did not reproduce afterwards, including against the exact
sequence that produced it. The most plausible cause was `shaped: null` meaning two different things
(*no shaping asked for yet* and *this shaping found no rows*), which is now tracked as a separate
`hasShaped`. That is a real bug fixed on its own merits; whether it was **the** bug is unproven.

**2026-08-27 — round 3, and four defects the bench found in the CLI it was built on.**

The doc predicted this: *"Building a surface that runs the real commands and draws the real
envelope is the cheapest way to find the flags that should exist and the facts that should ship."*
Three rounds in, the surface has cost more bugs than it has caused. All four below are in `cli/`,
not in the bench.

**1. `--save` wrote before a usage error refused the run.** `sb --json data --save prs --refresh 30
-- …` appended the tool, cadence and all, and *then* exited 2 with `--refresh and --json refuse
each other`. A name taken, a file changed, and a failure reported — the worst available
combination, and the name could not be reused because a duplicate is refused. `--save` writes first
on purpose (so a resident invocation saves at all), which means any refusal below it fires too
late. The conflict check is now `refuse_resident_json` in `cli/output.py`, raised at the door in
both `data` and `read`, with the guard left in the resident path as belt and braces. Found by a
test hanging, which is its own small lesson: the test hung because running that line goes resident.

**2. A hidden option was in the reference rail.** `sb run --refresh` is `hidden=True` and exists
only to refuse an act a cadence with a readable message rather than a bare usage error. `--help`
does not list it; the rail did. That is exactly the drift *one help string, two surfaces* is
supposed to make impossible, and it was visible the moment the rail was drawn. `_options` now skips
`param.hidden`.

**3. A tool saved from the bench did not exist as far as its own surface was concerned.**
`register` runs once at CLI boot — right for a process that exits, wrong for a server that lives
for hours. The name check reads the file, so it refused the name; the tools rail read the
in-process tree, so it claimed the tool was not there. A surface disagreeing with itself.
`/api/catalog` now calls `tools.reload`, which drops the registered tools and reads the file again
— the catalog's own doctrine one level down: *derived on every request, never kept*. Dropping first
is what makes it a reload rather than an accumulation, so a tool deleted in `$EDITOR` also goes.

**4. Two preflight requests raced.** `setCwd` then `setArgv` in the same tick both read the ref
before the first `setDraft` landed, so the second request carried the old cwd and the checks
described a line nobody had typed — the pane said `--cwd /home/jeston` while the block beside it
said `/tmp`. One effect keyed on the fields that matter replaced per-setter firing; it sees the
merged state by construction.

**The cadence control is gone from the job strip, and its absence is the finding.** The mockup
draws one and § Shape describes it. It cannot exist: a cadence is saved by having `--refresh` in
force on the line being saved, `--refresh` goes *resident*, and a surface that runs a subprocess to
completion cannot be resident — under `--json` it is a usage error. So the bench would compose a
line that refuses itself. Absent rather than disabled, with the reason where the control would have
been and `refresh = 30` in `$EDITOR` named as the way to get one. Whether the CLI should grow a way
to record a cadence without going resident is a real question and not this round's.

**What the act gets instead of a trial run.** Three checks, and the third is the one that matters:
the argv goes through `make_context`, which parses and type-converts without invoking. So `--cwd`'s
existence, an unknown flag and a bad integer are all caught by *sky.boss's own parser* rather than
by a surface re-deriving its rules. A bad `--cwd` fails the directory check and the parse both — a
cause and its consequence, printed in that order, not a duplicate. `run it for real` is disabled
while any check fails, and the line beside it says there is no dry run to fall back to.

**`preflight` runs nothing, and a test proves it** by asking it to check `touch <path>` and
asserting the path does not exist. That is the whole distinction between a check and a dry run.


### Round 4 — executed, and every intermediate fix was wrong in an instructive way (2026-08-28)

Four attempts, and the value is in what each one broke, because they are all the same mistake in
different clothes: **fixing where a thing is drawn without bounding how big it can get.**

1. **`min-height: 0` on `.bench-main` alone.** Correct and insufficient. The strip stopped being
   clipped and started being *pushed*, because the fixed panels above it still wanted more than the
   column had.
2. **`max-height: 34%` on the strip.** This is the one worth remembering. A capped panel whose
   content still overflows **paints outside its own box** — so `getBoundingClientRect()` on
   `.bench-job` said 413→557 of a 669px viewport, perfectly on screen, while the name field inside
   it was drawn below the window. The measurement agreed with the fix and the screen did not.
   Bounded-and-lying is worse than tall.
3. **`flex: 1 1 70rem` on `.job-note`.** Set the trailing note's **height** to 70rem — 322px of
   empty paragraph — because `.job-body` is a *column* and `flex-basis` is whichever axis you are
   on. The same declaration was correct in `.job-row`, six lines away. It is now scoped to the row.
4. **Everything above, at `--scale 2.4`,** where the real driver turned out to be horizontal: the
   reference rail's width is in `rem`, so it grows with the scale while the window does not, and it
   took 1037px of 1416, leaving the bench 340px in which every note wrapped into a word-column. A
   rail that starves the thing it annotates is the horizontal half of the same defect. Bounded, and
   the Does-not-do amended.

**What holds is pinned + capped + scrolling inside, with both ends sticky.** The name is the step
and the save is the act, so those stay put; the block and the notes scroll between them. That is
the bench's own shape one panel down, which is the argument for it beyond "it works".

**One geometry is what caused this, so the verification is five.** Every earlier round was checked
at the default `--scale 1.15` in a window that happened to be tall enough, and the bug was
invisible in exactly that one configuration. The harness now sweeps 1.15/1.6/2.0/2.4/3.0 × act ×
observe and asserts four elements are on screen. **`--scale` is not a preference, it is a
geometry** — `CLAUDE.md` already says one number drives every size, and the corollary nobody had
written down is that a layout verified at one value of it has been verified once.

**The report was "we are missing a way to save the command", and nothing was missing.** Worth
recording because the diagnosis nearly went the other way: the obvious reading was that round 3's
act asymmetry had left `run` with no save path, which would have been a design argument. It was a
`min-height`. **A feature you cannot see and a feature that is not there produce the same bug
report**, and the difference is only visible by measuring.
