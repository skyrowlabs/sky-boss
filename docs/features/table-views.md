---
status: active
created: 2026-08-20
updated: 2026-08-23
agent_value: 3
key_files:
  - cli/view.py
  - cli/data.py
  - cli/output.py
  - cli/canvas/static/render.js
  - cli/canvas/static/tb.css
  - tests/test_view.py
  - tests/test_data.py
  - tests/test_output.py
---

# Table views — shaping a foreign CLI's JSON into a table worth reading

## Why

`tb wrap` already works. The whole path the operator asked for — hold another CLI's output open on
the canvas and re-run it on a cadence — exists today and needs no new plumbing:

```
tb wrap --cwd ~/src/jam.sense -- jam pr list --json
```

parses, lands in the envelope as a list of rows, gets `acts: false` from the catalog so the window
may be pinned, and renders through `_render_columns` in the CLI and `Table` in `render.js`.

What comes back is unreadable. Measured, not imagined — that exact command at a 100-column
terminal today:

```
NU…   TI…   IS…   ME…   HE…   HE…   B…   BE…   L…   MA…   M…   CH…   E…   NEXT
945   fi…   ✓     UN…   cb…   fi…   d…    4   a…   ab…   -    {'…   n…   run
```

Fourteen columns crushed to three characters each, headers truncated past recognition, and a
nested dict rendered as a Python repr. Every renderer we have takes **every key of every row, in
first-seen order, at equal weight.** That rule is correct for tb's own commands, whose fields were
chosen by the person who wrote the command. It is wrong the moment the data is *foreign*, because
nobody chose those fields for a table — they are a tool's complete internal record of a pull
request, and shaping them was always going to be somebody's job.

Here is what that one row actually carries:

| field | type | why a table wants it or not |
|---|---|---|
| `number` | int | the identifier — must lead |
| `title` | str | prose, 78 chars, wraps and blows up the row |
| `is_draft` | bool | fits, matters |
| `merge_state` | str | a verdict — `roleFor` already colours it |
| `head` | str | a 40-char sha. Opaque. Costs a column, tells you nothing |
| `head_ref` `base_ref` | str | branch names — wanted |
| `behind` | int | wanted |
| `labels` | list | short list, joins fine |
| `marker` | str | wanted |
| `marker_payload` | null | **null in every row.** Pure cost |
| `checks` | dict | six counters nested one level, currently `{'…` |
| `execution` | str | wanted |
| `next` | str | prose, the longest field of all |

Two of fourteen columns are worth nothing at all, two are prose that destroys the layout, and one
is nested. That is not specific to `jam` — it is what a rich tool's JSON looks like. `gh pr list
--json` has the same shape, so does `docker ps --format json`. The generalisation is the feature.

## Shape

**A view is not the data.** The heuristic never edits `data`. `tb wrap --json | jq` keeps every
field including `head` and `marker_payload`, and so does any future MCP consumer — dropping a
column from `data` to make a table prettier would be trading a machine contract for a human one.

Instead the envelope gains an optional `view`: a *hint about presentation*, computed once, that
both renderers apply.

```json
{
  "command": "wrap",
  "ok": true,
  "data": [ { "number": 945, "head": "cbb6c29…", "marker_payload": null, … } ],
  "view": {
    "columns": [
      {"key": "number",      "label": "NUMBER",      "align": "right", "flex": 1, "min": 6, "max": 6},
      {"key": "merge_state", "label": "MERGE_STATE",  "flex": 1, "min": 11, "max": 11},
      {"key": "behind",      "label": "BEHIND",       "align": "right", "flex": 1, "min": 6, "max": 6},
      {"key": "checks",      "label": "CHECKS",       "summarise": true, "flex": 2, "min": 6, "max": 18}
    ],
    "details": [
      {"key": "title", "label": "TITLE", "flex": 5, "min": 5, "max": 40},
      {"key": "next",  "label": "NEXT",  "flex": 3, "min": 4, "max": 40}
    ],
    "hidden": ["head", "marker_payload", "execution"]
  },
  "warnings": ["5 columns hidden — use --cols to choose"]
}
```

`view` is **omitted entirely when nothing set it**, so every existing envelope stays byte-identical
and the stdout-purity test keeps meaning what it meant.

### The heuristic lives in Python

`cli/view.py`, as pure functions over `list[dict]`. Not in `render.js`, and the reason is not
taste: **the frontend has no test runner and adding one means npm.** Putting the decisions in
Python makes the interesting half the tested half, and leaves `render.js` doing something dumb
enough to be obviously correct — *render these columns in this order*. It stops being a place
where a second, drifting opinion about column selection can grow.

### The rules, and what each one earned its place on

Ordered, each applied to the whole row set rather than to one row:

1. **Drop a column that is empty in every row.** `marker_payload` is null in all of them. A column
   that has never once carried a value is pure width.
2. **Drop an opaque identifier.** Every value is hex, ≥32 chars, same length. That is `head` and
   it is a sha. Matched on the *values*, never on the name — `head_ref` is a branch name and must
   survive, and the next tool will call its sha something else.
3. **Summarise a nested dict into one cell**, omitting zero and null members:
   `checks` → `passed=2 skipped=7`. One column, not six. The alternative — flattening to
   `checks.passed`, `checks.failed`, … — turns one column into six and makes the crowding worse,
   which is the problem we started with.
4. **Prose leaves the row.** A column you *read* rather than *scan* — a string whose longest value
   runs past `PROSE_WIDTH` — is not given a share of the width at all. It gets the full width on its
   own line beneath the record, indented under the second column so the identifier stays the
   leftmost thing:

   ```
   NUMBER  MERGE_STATE  BEHIND  CHECKS
   ──────────────────────────────────────────────
      946  CLEAN            19  passed=2 skipped=7
           docs: use an absolute .venv/bin PATH prefix in the commit snippets
   ```

   Matched on values, like every other rule, and deliberately **not** on a list of blessed names
   like `title` or `description`: the next tool calls it `subject`, or `Command`, or `message`, and
   a name list goes stale the first time one does. A column of one-word statuses that happens to be
   called `title` stays inline, which is right.

   Details are **exempt from the column budget** — they cost a line each rather than a share of the
   width, so they are not competing for what the budget rations.

5. **Clip what is left, and weight the columns.** Each column carries a `flex` — a
   proportional width, not a character count — and long values are clipped with an ellipsis.
   Rich folds by default, and a folded 78-char title makes a one-row table twelve rows tall.

   `flex` rather than `clip` because **a character count is not portable across the two
   renderers.** `Toolbox Surface.dc.html` settles this: every cell there is
   `nowrap; overflow:hidden; text-overflow:ellipsis` inside a `flex:{{ c.flex }}` span, so the
   canvas gets clipping free from CSS at whatever width the window happens to be — and a window is
   draggable, so it has no fixed width to compute a character count against. Rich maps the same
   number onto a column `ratio`. One primitive, two correct renderings, and the mockup is the
   authority for the shape.

   The canvas keeps the full text in a `title` attribute so hovering still shows it.
6. **Size a scan column to its content.** Every column carries a `max` — the width it would take if
   nothing competed — and when everything fits, the table stops there and leaves the rest of the
   terminal empty. Since prose left the row, nothing still in it wants to be wider than its own
   values, and padding a table out to the full width to avoid looking unfinished is how `NUMBER`
   ends up eighteen characters wide with a three-digit number in it.
7. **Budget the remainder.** If columns still exceed the budget, keep the leading ones and
   **name the ones dropped in a warning.** A silently hidden column is the "looks right and isn't"
   failure — the table reads as complete when it is not.

   *Reversed in Round 3 (2026-08-22): the budget was a fixed **count** (eight), decided in Python
   where no width is known, and it hid the same two columns at every window size. The half that
   survives is the second sentence — nothing is dropped silently, ever. What moves is **who
   counts**: fitting is arithmetic against a width, and only a renderer knows its width. See
   Round 3.*

### The overrides

On `wrap`, so the operator has recourse the moment a guess is wrong:

| flag | does |
|---|---|
| `--cols number,title,checks.failed` | exactly these, in this order. Dotted paths reach into a nested dict. Defeats every *selection* rule above — but not the detail layout, since a ninety-character title asked for by name is still a ninety-character title |
| `--drop head,next` | subtractive — keep the heuristic, lose these |
| `--no-shape` | every column, first-seen, as today. The escape hatch, and what the tests compare against |

These are ordinary Click options, so the catalog already exposes them to the palette as chips, and
typing `wrap --cols number,title -- jam pr list --json` into the palette works with **no frontend
change at all** — `app.js` already treats everything past the command name as argv.

**Does not do:**

- **Does not reshape tb's own commands.** Only `wrap` sets a view, because only `wrap` carries
  data nobody on this side chose. tb's own commands picked their fields deliberately and auto-dropping
  one would be a bug wearing a feature's clothes. *(Corrected 2026-08-23: this line cited `tb info`,
  a command removed 2026-08-20. Unlike the `wrap`→`data` rename below, a removed command leaves the
  argument uncheckable rather than merely renamed — see Notes.)*
- **Does not persist — and does not need to.** No named views, no saved column sets, no state file
  *in this feature*. `wrap --cols …` is typed per window and dies with it, which keeps the canvas's
  "nothing survives the last window" intact.

  Persistence arrives from the other direction instead. [[tools]] gives the operator a
  `tools.toml`, and because a tool is simply a **tb argv**, a saved column set is already
  expressible without this feature growing a store of its own:

  ```toml
  argv = ["wrap", "--cols", "number,title,merge_state,behind,checks.failed", …]
  ```

  That is the better split. Shaping stays a pure function of the rows plus some flags, and the
  question of where operator content lives is answered once, in the doc that exists to answer it.
- **Does not sort or filter.** `wrap.py`'s docstring anticipates both and they are a separate
  round; sorting is a canvas interaction (click a header) and belongs to the surface, not to the
  shaping contract.
- **Does not touch `data`.** Stated twice on purpose.
- **Does not guess a tool's JSON flag**, and does not learn `--cwd` for a tool that needs one.
  `jam` requires `--cwd ~/src/jam.sense` because its wrapper resolves `.venv` against the
  working directory; that is jam.sense's bug to fix and tb should not grow a workaround for it.
- **Does not do ANSI.** Unchanged from [[canvas]]: a tool without JSON is out of scope rather than
  half-supported.

## Phases

### Round 4 — a payload is not always a list (2026-08-23)

Found by pointing the tool at a real project rather than a fixture. [[roll-call]] needs this
command to be readable and today it is not:

```
tb data --cwd ~/src/jam.sense --cols job,result,last_age,overdue -- jam report status --json
```

`--cols` is **silently ignored.** Fifteen columns render at two characters each, and nothing says
why. That is the "looks right and isn't" failure this doc has refused three times, arriving
through a door nobody was watching.

**Two independent breaks, both from the same wrong assumption.**

1. `shape()` opens with `if not is_rows(data): return None`, and `is_rows` requires a *bare list of
   dicts*. jam returns `{"generated": "…", "jobs": [ … ]}` — the rows are one level down. So no
   view is computed, `--cols` is discarded without a word, and `view` never enters the envelope.
2. Even with a view, it could not arrive. `_render_mapping` in `cli/output.py` dispatches a nested
   list of dicts to `_render_columns(list(value), title=None, indent=indent)` — **and passes no
   `view`**. The nested render path predates views and never learned about them.

The assumption was that a foreign tool returns rows. Real tools return rows *plus metadata* —
a generated-at stamp, a count, a version — because a bare array has nowhere to put them. jam's
envelope is the normal case, not an exotic one, and the fixture was synthetic in exactly the way
that hid it.

**Finding the rows without guessing.** `--rows jobs` names the path explicitly, and is the same
idea as `--cols checks.failed` one level up — dotted paths already reach into nested structures
here. Unnamed, tb may infer only when the answer is unambiguous: **exactly one value in the
mapping is a non-empty list of dicts.** Two candidates is not a near-miss to be broken by
preferring the longer one or the better-named one; it is a question tb cannot answer, and it says
so and renders as it does today. Matching on the *value* rather than on a blessed key name
(`items`, `results`, `rows`) is rule 2 and rule 4's idiom unchanged — a name list goes stale the
first time a tool disagrees with it, and the next tool always disagrees with it.

The unshaped remainder keeps rendering as a mapping above the table, which is already what the
operator wants: `generated 2026-08-23T20:02:53+00:00` is a useful line, just not a column.

**And the payload says what it is.** One fact, computed from what shaping already knows and drawn
in the header line that today reads `● data  53 rows`:

```
● data  table · 15 × 27
```

The row count is already there; the **column count is invisible**, and the column count is
precisely what tells the operator whether `--from` and `--rows` did what they meant. It is a fact
the data itself states, so it belongs in-band here rather than in [[chrome]] — which draws what
the output does *not* say, and takes the terminator half of this in its own round 3.

**Does not do** gains:

- **Does not guess between two candidate row lists.** Ambiguity is reported, never broken by a
  tiebreak. A wrong table read as the right one is worse than no table.
- **Does not flatten the wrapper into the rows.** `generated` does not become a column repeated
  27 times.

- [x] **`is_rows` grows a sibling, not an exception.** `find_rows(data, path=None)` in
      `cli/view.py`: returns the row list and the key it came from, or a reason it could not.
      Pure, tested first — the ambiguous case and the zero-candidate case before the happy one.
- [x] **`--rows KEY` on `tb data`**, dotted paths allowed, alongside `--cols` / `--drop` /
      `--no-shape`. A named path that does not resolve is an error, not a silent fallback.
- [x] **The nested render path learns views.** `_render_mapping` threads `view` through to
      `_render_columns`; the canvas's equivalent path in `render.js` checked for the same gap,
      since it was written against the same assumption.
- [ ] **A discarded flag is never silent.** If `--cols` cannot be applied because nothing shapeable
      was found, say so on stderr and name why. This is the defect's real lesson and it outlives
      the specific fix.
- [ ] **The header states type and dimensions.** `● data  table · 15 × 27`, from the view; scalar
      and mapping payloads say what they are too. Both renderers.
- [ ] **A fixture with a wrapper.** `tests/test_view.py` gains the shape of `jam report status
      --json` — a metadata key beside a row list — for the same reason round 1's fixture was
      synthetic, and covering the case round 1's fixture structurally could not.

### Round 3 — the budget is a fit, not a count (2026-08-22)

Reported by the operator against the live canvas: *"it's hiding columns even though there is
room."* Measured on the real fourteen-field `jam pr list --json`, six rows:

| | |
|---|---|
| columns worth showing after every rule | **10** |
| sum of their floors (`min`) + gutters | **98 ch** |
| sum of their natural widths (`max`) | **126 ch** |
| the operator's terminal | 100 columns |
| the canvas window in the screenshot | comfortably wider |
| columns actually drawn | **8** — the budget |

So all ten fit at their floors in a 100-column terminal, and fit with room to spare on the
canvas, and two were dropped anyway. `head` is *correctly* gone (uniform-length hex — a sha);
`checks` and `execution` were taken by the count alone. This doc's Notes have said so twice,
in Round 1 and again in Round 2 — *"the budget hides `checks` and `execution` on the real
fourteen-field row, `--cols` is the recourse"* — which is the tell that the recourse was
covering for a rule that was wrong rather than merely imperfect.

**The diagnosis: two different decisions were wearing one number.**

- *Which columns are worth showing at all, in what order, at what floor and weight* — a
  judgment about the data. Belongs in Python, where pytest reaches it. Unchanged.
- *How many of them fit right now* — arithmetic against a width **nobody in Python knows**.
  The canvas is a draggable window; the terminal is whatever `COLUMNS` says this second.

The second was being answered in Python with a constant, which is why the answer could not
depend on the thing it was supposedly about.

**And the canvas never needed a count.** It already fits to available space — `.grid.shaped
.row` is a flexbox and every cell carries `flex:N 1 0; min-width:Xch; max-width:Ych` straight
from the view. CSS has been doing exactly what the operator is asking for since Round 1; the
budget was the only thing standing in front of it. The terminal likewise already resolves
widths against `_out().width` in `_resolve_widths`, and already has the tail-drop arithmetic
in all but name.

**So `shape()` stops truncating.** The view carries every column worth showing, ordered, with
floors and weights; each renderer takes columns while their floors still fit its own width and
**names what it could not draw**, in the same place it already says "N more rows not shown".
This is the pattern the doc already set for `min`: *"the floor lives in the view rather than in
either renderer, because both need it for the same reason and two copies would drift"* — one
contract, two correct renderings.

**`hidden` narrows to mean one thing.** Hidden *by rule* — empty in every row, an opaque
identifier, explicitly `--drop`ped — is a property of the **run**: true at any width, correct
in the envelope, worth a warning. Overflowing the width is a property of the **drawing**: it
differs per renderer, changes when you drag a window, and has no business in an envelope a
machine consumer reads. Splitting them is what lets the warning finally mean something —
today it fires on a window with room to spare, which is the fastest way to teach someone to
ignore a warning.

- [x] **`shape()` stops truncating.** `DEFAULT_BUDGET` and the `budget` parameter retire;
      `hidden` means hidden-by-rule only. `tests/test_view.py` updated — the budget tests
      become fit tests against a declared width.
- [x] **The terminal fits to its console.** `_resolve_widths` in `cli/output.py` takes columns
      while floors fit, and `_render_view` prints `N columns not shown: …` in the dim style
      the row-truncation line already uses. Today floors that do not fit are used anyway and
      the table overflows sideways — that stays the *last* resort, for a single column too
      wide for the terminal, and is no longer the common case.
- [x] **The canvas fits to its window.** The same tail arithmetic in `render.js` against the
      measured body width — arithmetic, not judgment, which is the standard that file is held
      to. Plus a fix for the truncated headers visible in the operator's screenshot
      (`NUMBE…`, `IS_DRAF…`, `MERGE_STAT…` inside columns floored to fit them exactly): the
      terminal renders the same labels in full, so this is a canvas-side `ch`-rounding
      question, cause to confirm before fixing.
- [x] **The warning narrows.** `cli/data.py` warns only about rule-hidden columns. A window
      with room stops being told it is missing something.
- [x] **Docs.** Rule 7's reversal is already recorded above; Round 1's and Round 2's
      "still imperfect" notes get their dated resolution.

### Round 2 — a title is not a column (2026-08-20)

- [x] Prose becomes a `details` list in the view rather than an inline column, exempt from the
      budget. `_is_prose` matches on values; `_reorder` and Round 1's rule 5 are deleted.
- [x] Columns carry `max`, their natural width, and a table that fits stops there.
- [x] The terminal renderer lays a shaped table out by hand — Rich has no colspan and a detail line
      spans every column.
- [x] Header rule, a blank line between records when details are present, two-space gutters, dim
      detail lines. Both renderers.
- [x] `render.js` renders detail rows, aligned under the second column by a spacer carrying the
      first column's sizing.

### Round 1 — shape a wrapped table (2026-08-20)

- [x] `cli/view.py`: the rules as pure functions over `list[dict]`, plus `tests/test_view.py`
      covering each rule and a fixture with the *shape* of `jam pr list` rather than its content.
      Nothing wired yet.
- [x] `Result` gains an optional `view`; `to_dict` omits the key when unset, so existing envelopes
      and the stdout-purity test are untouched.
- [x] `wrap` computes the view and attaches it. `data` unchanged — asserted by a test.
- [x] `_render_columns` in `cli/output.py` honours a view when present, first-seen order when not.
- [x] `Table` in `render.js` honours a view when present. Full text of a clipped cell in `title`.
- [x] `--cols` / `--drop` / `--no-shape` on `wrap`.
- [x] Hidden columns reported as a warning naming them.
- [x] Verify against the live canvas headless, per [[canvas]] — the frontend still has no runner.

## Notes

### Round 4 — what a doc audit is allowed to touch (2026-08-23)

Asked before executing: should the docs be corrected first. Audited, and the answer split in a way
worth writing down, because it will come up every time.

Measured across all sixteen docs: every `key_files` path resolves except `mcp.md`'s two, which name
files that spec has not built yet — correct for an unbuilt spec, not drift. `CLAUDE.md` was wrong in
three ways about this directory (claimed it was empty, omitted three completed docs, listed two that
had moved out) and is fixed. One stale reference: this doc's *Does not do* cited `tb info`, removed
2026-08-20.

**The rule the audit produced: correct the living sections, never the dated ones.** Why, Shape and
Does-not-do describe the system *now*, so they can be wrong and should be fixed. Rounds and Notes
describe a moment, so they cannot be wrong — only accurate about something that has since changed.
Rewriting those to match today would destroy the one thing this format is for.

Which is why the seventeen `wrap` references above were **left exactly as they are**. They look like
the biggest drift in the repo and are not drift at all; the 2026-08-21 supersession note already
says so. `tb info` was different in kind: a rename leaves an argument followable, a removal leaves it
citing nothing, and a reader cannot tell which they are looking at without checking. Fixed in place
with the correction marked, rather than silently — the same standard the code is held to.

### Round 4 — the fixture was the bug (2026-08-23)

Round 1's Notes defend the synthetic fixture at length, and the defence is still right: real rows
carry branch names belonging to this operator and nothing operator-specific goes in a tracked
file. What the defence got wrong is the claim underneath it — *"the fixture reproduces the shape
— fourteen fields, a digest, an always-null column, a nested dict, two columns of prose — which is
the whole of what is under test."*

It reproduced the shape of a **row**. It did not reproduce the shape of a **payload**, because it
was a bare list, and so was every fixture after it. Three rounds of column rules were tested
against a structure that a real tool had already stopped returning. `jam pr list --json` happens
to be a bare array; `jam report status --json` is not, and neither is most JSON that carries a
timestamp or a count beside its rows.

The correction is narrow and worth stating precisely, because the general version would be wrong:
**a fixture may be synthetic in its values and must not be synthetic in its envelope.** Values are
what the operator owns; structure is what the contract is about.

Worth noting how it was found. Not by a test, not by review — by running the command against a
real project while scoping [[roll-call]], and reading the output. The two breaks are three lines
apart in files with good coverage, and both are invisible to any test that constructs its own
input.

### Round 1 — deferring persistence, and where it landed (2026-08-20)

Written assuming saved column sets were a later round of *this* doc, gated on there being an
operator content directory again — the original line read "worth reopening once there is an
operator content directory again — there is not one now, and re-introducing one for this would be
the tail wagging the dog."

That reasoning held and the conclusion still did not survive the afternoon, because [[tools]]
turned up needing the same directory for its own reasons and got there first. The useful part is
*why the reversal cost nothing*: a tool is a tb argv, and `--cols` is a flag on a tb command, so
the moment tools existed, saved column sets existed too — with no view store, no second config
format, and no edit to this feature at all. **A flag composes with a mechanism that saves argvs; a
bespoke persistence layer would not have.** Worth remembering the next time something here is
tempted to grow its own file.

### Round 1 — what shipped, and what the implementation argued back (2026-08-20)

Four of the six rules survived contact unchanged. The other two were wrong in
ways only visible once there was output to look at.

**"Push prose columns last" was wrong, and the budget made it worse.** The rule
reads sensibly — prose eats width, so move it out of the way — and on a real
pull-request table it moves `title` to the far right, where the column budget
then hides it. The table you are left with identifies its rows by number alone.
The fix is that the *first* prose column is the row's label and keeps its place;
only the second and later ones move. `_label_of` in `cli/output.py` has treated
the first string field as the label since long before this, so the corrected
rule is one tb already believed.

**Rich's `ratio` and `min_width` are mutually exclusive, undocumentedly so.**
The first implementation handed `flex` straight to Rich as a column `ratio` and
set `min_width` to the header length. Headers still truncated. Rich's ratio
distribution builds its floor from `column.width or 1` and never consults
`min_width`, so a weight-1 column is free to render at four characters —
`MERGE_STATE` as `ME…`. Widths are resolved against the console in
`_render_columns` instead, six lines of arithmetic.

That bug produced the more useful rule underneath it: **a truncated value is a
readable table with a detail elided; a truncated header is a column you cannot
identify at all.** So every column now carries a `min` — its own label, capped
— and the floor lives in the view rather than in either renderer, because both
need it for the same reason and two copies would drift.

**The fixture is synthetic and that was not laziness.** The obvious move was to
paste a real `jam pr list --json` row in as a fixture. Real rows carry branch
names and repository paths belonging to this operator, and nothing
operator-specific goes in a tracked file. The fixture reproduces the *shape* —
fourteen fields, a digest, an always-null column, a nested dict, two columns of
prose — which is the whole of what is under test. Real rows were used to check
the result, at a terminal, and not committed.

**`summariseMapping` is duplicated in JavaScript, knowingly.** It is the only
piece of `cli/view.py` with a second implementation. The alternative is putting
the rendered string in the envelope, and that would make a view a
*transformation* of `data` rather than a description of it — the one property
the whole feature rests on. Four lines that have to agree is the cheaper price,
and the comment in `render.js` says so at the site.

**Still imperfect, deliberately.** On the real fourteen-field jam row the
budget of eight still hides `checks`, which is one of the columns worth seeing.
No heuristic that ranks columns by usefulness would be honest — it would be
guessing at intent — so the answer is `--cols`, and the warning names exactly
what went missing so you know to reach for it. Predictable beats clever here;
a table that hides a different column each run would be worse than one that
hides a known column every run.

**Verification.** The frontend still has no test runner, so `render.js` was
checked by rendering it headless against a fabricated envelope and reading the
DOM back — the harness was built outside the repo, because
`cli/canvas/static/` is *served*, and two scratch pages once lived there with a
live token baked in. Then end to end against a live server: the catalog offers
the three flags as chips, `wrap` stays `acts: false` so a window may still be
pinned, and `/api/run` returns a view with `data` intact.

### Round 2 — a title is not a column (2026-08-20)

Round 1 asked the wrong question about prose. It took "a ninety-character title does not fit in a
share of the width" and looked for a better *place in the row* to put it — first "push prose last",
then, when that hid the one column you identify a record by, "the first prose column keeps its
place". Both are answers to "where in the row", and the honest answer is that it does not go in the
row. **A column you read and a column you scan are different kinds of thing and a single row cannot
serve both.**

Which makes the fix subtractive, and it pays twice. Prose stops competing for width, so the scan
columns can be sized to their own content instead of splitting the terminal between them. And
details stop counting against the column budget, so `next` — hidden by the budget for the whole of
Round 1 — is simply readable now. Round 1's Notes end by saying the budget still hid a column worth
seeing and `--cols` was the recourse. Half of that turned out to be self-inflicted.

**Detection stayed on values, against the request.** The ask named `title` specifically. A name
list is the version that goes stale: the next tool calls it `subject`, or `Command`, or `message`,
and a column of one-word statuses that happens to be called `title` would be promoted to its own
line for no reason. `PROSE_WIDTH` already identified exactly the right columns in Round 1 and needed
no help. This is the same argument that keeps `head` dropped for being uniform-length hex rather
than for being called "head", and it is the third time it has come up.

**The duplication warned about in Round 1 drifted within a day.** `summariseMapping` in
`render.js` is the one piece of `cli/view.py` with a second implementation, and Round 1's Notes
called it "four lines that must agree" and accepted the risk. They did not agree: the JavaScript
checked `null`/`undefined`/`""`/`0`/`false` and forgot empty arrays, so a `checks` dict carrying
`failing_names: []` rendered `failing_names=` in the canvas while the terminal correctly dropped it.
Not caught by a test — there is no JS test runner, which is the whole reason the logic is supposed
to live in Python. Caught by rendering both and reading them side by side. The accepted risk was
real and the mitigation is that this is the *only* such function; if a second one appears, the
trade should be re-argued rather than repeated.

**Two rendering bugs that only a screenshot shows.** Neither is visible in a DOM dump, because in
both cases every element was present and every style was applied:

- The canvas ignored `align` and `max`, so four scan columns spread across the whole window and a
  right-aligned `946` sat nowhere near the `NUMBER` above it.
- `.row.head` carries `letter-spacing: .1em`. The column widths are a contract measured in `ch`,
  and tracking silently makes a six-character label need more than six of them — so `NUMBER`
  rendered as `NUMB…` inside a column sized to fit it exactly. Removed for shaped headers only;
  the unshaped grid keeps its tracking, since nothing there is measured.

**Rich was left behind for the view path.** `Table` has no colspan and a detail line spans every
column. The widths were already being resolved by hand — Round 1 found that `ratio` ignores
`min_width` — so owning the layout outright cost little and bought the header rule, the record
spacing and the exact gutter with it.

**Still true, and now for a smaller set:** the budget hides `checks` and `execution` on the real
fourteen-field row. `--cols` is still the recourse and the warning still names what went missing.

### 2026-08-21 — the words moved; the history stays (supersession)

`wrap` was renamed `data` and the `every` field renamed `refresh` — hard renames, no aliases;
see [[refresh]]. This doc predates the rename and its prose says `wrap` because it *was*
`wrap`; that is history being accurate, and nothing above has been scrubbed.

### Round 3 — drafted, awaiting the word (2026-08-22)

Raised by the operator from the canvas, in the form the doc had been half-admitting for two
rounds: *"it's hiding columns even though there is room."* The measurement is in the round
above and it settles it — ten columns, ninety-eight characters of floor, a hundred-column
terminal, eight drawn.

**What makes this a reversal rather than a tuning.** Raising the count to ten would fix this
table and nothing else; the defect is not the number, it is that a *count* cannot answer a
question about *width*. Both renderers already know their width and already do width
arithmetic — the terminal in `_resolve_widths`, the canvas in flexbox — so the budget was a
third, blinder opinion sitting upstream of two informed ones.

**The line that does not move.** Round 1 put the heuristic in Python because the frontend has
no test runner, and that argument is untouched: *selection* stays in `cli/view.py`, tested.
What moves is *fitting*, which was never a judgment — "take columns while the running total
still fits" is arithmetic of the kind `render.js` is already trusted with, and is the same
reason both renderers already apply `min` themselves.

**A cost, accepted:** `view.hidden` stops being the whole story of what you cannot see. That
is the honest shape — a warning in an envelope cannot describe a window the operator is still
dragging — but it does mean the answer to "what am I not seeing" now lives in two places: the
envelope for rule-hidden, the rendering for width-hidden. Both name names, which is the
property Round 1 actually cared about.

### Round 3 — shipped (2026-08-22)

The reversal cost less than the round that introduced the thing it reversed. Deleting
`DEFAULT_BUDGET` and the `budget` parameter was the whole of the Python change; everything else
was consequence.

**Two phases collapsed into one commit on purpose.** Shipping "shape stops truncating" alone
leaves a 100-column terminal drawing ten columns whose floors need 116, so the terminal fit
landed in the same commit. A phase boundary that leaves the repo visibly broken is not a
boundary worth keeping.

**The warning narrowed for free, which is the tell that the split was already latent.**
`cli/data.py` has always warned about `hidden` *minus* the keys the operator explicitly
dropped — so the moment `hidden` stopped carrying budget casualties, the warning started
naming exactly the rule-hidden ones. No edit to `data.py` at all. The code had the right shape
and the wrong input.

**The canvas needed no fitting code, and that is the round's best result.** The draft proposed
mirroring the tail arithmetic in `render.js`; it turned out to be unnecessary, because the two
substrates genuinely differ — **a browser can scroll sideways and a terminal cannot.** So the
terminal drops from the tail and names what it dropped, the canvas overflows into the scroll
`.body` already had, and neither is a compromise. `fit_columns` therefore lives in
`cli/output.py` as the *terminal's* arithmetic rather than as shared code, and the JS
duplication Round 2's Notes warned about was not repeated.

**The header truncation was a different bug wearing the same screenshot.** Not the budget: a
column whose `max` equals its label length asks for exactly as many `ch` as the label renders
in, and the engine has to land on the nose. Blink does — swept 70 window widths and never
clipped — and WebKitGTK, which is what the native shell actually runs, does not. Fixed with a
quarter-character of slack on the `ch` bounds, in `ch` rather than a pixel so it keeps covering
the gap when `--tb-scale` moves. **Verified only in Chromium**, since this session has no
handle on the native webview; the operator's own window is the confirming test.

Measured after, at the operator's terminal width of 100: ten columns, `checks` and `execution`
among them, and the envelope warning down to `head` — the sha, which was always correctly
gone.
