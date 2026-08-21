---
status: active
created: 2026-08-20
updated: 2026-08-20
agent_value: 2
key_files:
  - cli/view.py
  - cli/wrap.py
  - cli/output.py
  - cli/canvas/static/render.js
  - tests/test_view.py
---

# Table views — shaping a foreign CLI's JSON into a table worth reading

## Why

`tb wrap` already works. The whole path the operator asked for — hold another CLI's output open on
the canvas and re-run it on a cadence — exists today and needs no new plumbing:

```
tb wrap --cwd ~/skyrow.labs/jam.sense -- jam pr list --json
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
      {"key": "number",      "label": "NUM",    "align": "right", "flex": 1},
      {"key": "title",       "label": "TITLE",  "flex": 5},
      {"key": "merge_state", "label": "MERGE",  "flex": 1},
      {"key": "behind",      "label": "BEHIND", "align": "right", "flex": 1},
      {"key": "checks",      "label": "CHECKS", "summarise": true, "flex": 2},
      {"key": "next",        "label": "NEXT",   "flex": 3}
    ],
    "hidden": ["head", "marker_payload", "is_draft", "labels", "execution"]
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
4. **Clip prose rather than wrap it, and weight the columns.** Each column carries a `flex` — a
   proportional width, not a character count — and long values are clipped with an ellipsis.
   Rich folds by default, and a folded 78-char title makes a one-row table twelve rows tall.

   `flex` rather than `clip` because **a character count is not portable across the two
   renderers.** `Tackle Box Surface.dc.html` settles this: every cell there is
   `nowrap; overflow:hidden; text-overflow:ellipsis` inside a `flex:{{ c.flex }}` span, so the
   canvas gets clipping free from CSS at whatever width the window happens to be — and a window is
   draggable, so it has no fixed width to compute a character count against. Rich maps the same
   number onto a column `ratio`. One primitive, two correct renderings, and the mockup is the
   authority for the shape.

   The canvas keeps the full text in a `title` attribute so hovering still shows it.
5. **Push prose columns last.** Identifiers and verdicts are what you scan; prose is what you read
   once you have found the row. First-seen order is otherwise preserved.
6. **Budget the remainder.** If columns still exceed the budget, keep the leading ones and
   **name the ones dropped in a warning.** A silently hidden column is the "looks right and isn't"
   failure — the table reads as complete when it is not.

### The overrides

On `wrap`, so the operator has recourse the moment a guess is wrong:

| flag | does |
|---|---|
| `--cols number,title,checks.failed` | exactly these, in this order. Dotted paths reach into a nested dict. Defeats every rule above |
| `--drop head,next` | subtractive — keep the heuristic, lose these |
| `--no-shape` | every column, first-seen, as today. The escape hatch, and what the tests compare against |

These are ordinary Click options, so the catalog already exposes them to the palette as chips, and
typing `wrap --cols number,title -- jam pr list --json` into the palette works with **no frontend
change at all** — `app.js` already treats everything past the command name as argv.

**Does not do:**

- **Does not reshape tb's own commands.** Only `wrap` sets a view, because only `wrap` carries
  data nobody on this side chose. `tb info`'s fields were picked deliberately and auto-dropping one
  would be a bug wearing a feature's clothes.
- **Does not persist — and does not need to.** No named views, no saved column sets, no state file
  *in this feature*. `wrap --cols …` is typed per window and dies with it, which keeps the canvas's
  "nothing survives the last window" intact.

  Persistence arrives from the other direction instead. [[toolbox]] gives the operator a
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
  `jam` requires `--cwd ~/skyrow.labs/jam.sense` because its wrapper resolves `.venv` against the
  working directory; that is jam.sense's bug to fix and tb should not grow a workaround for it.
- **Does not do ANSI.** Unchanged from [[canvas]]: a tool without JSON is out of scope rather than
  half-supported.

## Phases

### Round 1 — shape a wrapped table (2026-08-20)

- [x] `cli/view.py`: the rules as pure functions over `list[dict]`, plus `tests/test_view.py`
      covering each rule and a fixture with the *shape* of `jam pr list` rather than its content.
      Nothing wired yet.
- [ ] `Result` gains an optional `view`; `to_dict` omits the key when unset, so existing envelopes
      and the stdout-purity test are untouched.
- [ ] `wrap` computes the view and attaches it. `data` unchanged — asserted by a test.
- [ ] `_render_columns` in `cli/output.py` honours a view when present, first-seen order when not.
- [ ] `Table` in `render.js` honours a view when present. Full text of a clipped cell in `title`.
- [ ] `--cols` / `--drop` / `--no-shape` on `wrap`.
- [ ] Hidden columns reported as a warning naming them.
- [ ] Verify against the live canvas headless, per [[canvas]] — the frontend still has no runner.

## Notes

### Round 1 — deferring persistence, and where it landed (2026-08-20)

Written assuming saved column sets were a later round of *this* doc, gated on there being an
operator content directory again — the original line read "worth reopening once there is an
operator content directory again — there is not one now, and re-introducing one for this would be
the tail wagging the dog."

That reasoning held and the conclusion still did not survive the afternoon, because [[toolbox]]
turned up needing the same directory for its own reasons and got there first. The useful part is
*why the reversal cost nothing*: a tool is a tb argv, and `--cols` is a flag on a tb command, so
the moment tools existed, saved column sets existed too — with no view store, no second config
format, and no edit to this feature at all. **A flag composes with a mechanism that saves argvs; a
bespoke persistence layer would not have.** Worth remembering the next time something here is
tempted to grow its own file.
