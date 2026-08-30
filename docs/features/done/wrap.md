---
status: complete
created: 2026-08-29
updated: 2026-08-29
agent_value: 2
key_files: [cli/canvas/static/app.js, cli/canvas/static/render.js, cli/canvas/static/sb.css]
---

# Wrap — a followed line that fits the window

## Why

A window's body scrolls sideways. That was decided on purpose and the reasoning holds for a table:
[[chrome]] rules that a wide result *"scrolls sideways instead, the way the table does"*, because
reflowing a table destroys the columns that are the whole point of it.

**A prose log is not a table and inherits the wrong answer.** An agent writes paragraphs — findings,
reasons, a plan — and a long one runs off the right edge of a window that has room underneath it.
The operator's choice today is to scroll sideways for every line, losing the left edge of the log
while reading the right, or to widen a window that is competing with the others for canvas.

**The timestamp is what makes this more than a CSS property.** A naive wrap breaks the log's one
piece of visual structure: every line starts with a stamp, and a continuation that begins at column
zero looks like a new record. The stamp column stops being a column. So the ask has a specific
shape — **wrap indented to the first character after the stamp**, so a continuation sits under the
text it belongs to and the timestamp column survives, without the stamp being repeated.

## Shape

**A toggle in the window header, next to the controls a window already carries.** Per window, not
per surface: two windows on one canvas can want different answers — a `sb data` table wants the
scroll it was given, a `sb follow` on an agent log wants the wrap — and the header is where a
window's own state lives, the way `pinned` does.

**The indent is derived from a mark sky.boss already produces, never guessed.**
`cli/highlight.py`'s `_TIMESTAMP` matches a leading ISO stamp and its mark already carries the end
offset. That number *is* the hanging indent. Two consequences worth stating because they are what
makes this small:

- **No new parse.** The offset rides in the frame beside the text, as every mark does.
- **A line with no stamp wraps flush**, by the same rule and with no special case. The indent is
  the stamp's width or zero, and zero is not an exception.

**Wrapping is a decision about the `<pre>`, never about the text.** Marks are offsets into the
verbatim line, so anything that reflowed the *string* — inserting a newline, padding a continuation
— would invalidate every offset after it and put the rendered line out of step with the bytes it
came from. `white-space: pre-wrap` plus a hanging indent does the whole job in CSS and
`markedLine` needs no opinion at all.

**The indent is a character count, so it is a `ch`.** `--scale` is a geometry and a character is a
different width at 1.15 than at 2.4; a `rem` indent computed from a column count would drift apart
from the text it is meant to line up under. `text-indent: -Nch; padding-inline-start: Nch` is the
hanging-indent idiom and both halves are in the same unit as the glyphs.

**Does not do:**

- **Not the terminal.** `sb follow`'s ring is a fixed-height frame and it counts *rows*; a wrapped
  line occupies a number of rows that depends on the window width, so the ring's arithmetic stops
  being about records. That is a real feature and a different one — do not assume it crosses over.
- **No reflow of the payload.** See above. The bytes the window appends stay the bytes the file
  carried.
- **Not per-line.** One setting for the window, not a heuristic that wraps prose and scrolls tables
  by guessing which a line is. Guessing what a line *is* is the inference this repo refuses.
- **No re-stamping.** The continuation rows carry no timestamp. Repeating it would make the stamp
  column lie about how many records there are.

## Phases

### Round 1 — the toggle and the hanging indent (2026-08-29)

- [x] The stamp's end offset reaches the frame line. *It did not, and reading it off `marks` was
      the wrong answer — see Notes. `highlight.hang` exposes it and the frame carries `indent`.*
- [x] `wrap` as per-window state, with a header control beside the existing ones.
- [x] CSS: `pre-wrap` plus a `ch`-based hanging indent, applied only when wrap is on.
- [x] Verified by rendering, at **more than one `--scale`** — the indent is the thing most likely to
      drift, and CLAUDE.md is explicit that a layout verified at one scale has been verified once.
- [x] A line with no leading stamp wraps flush, and a line whose stamp is longer than the window is
      not an infinite indent.

### Round 2 — whether it is remembered (not scheduled)

`rail` went into `$SB_STATE` through `/api/prefs` ([[tools]] round 7) because the surface has no
stable origin. Whether a *default* for wrap belongs there is the same question and does not block
round 1, which can open every window unwrapped.

## Notes

### Round 1 — drafted, awaiting the word (2026-08-29)

Asked for by the operator 2026-08-29 while reading the live agent-fix drain, and recorded as
`docs/open.md` item 21 the same day.

The thing worth not losing: **the indent was the hard part and it is already solved.** The obvious
implementation is to measure the timestamp, which means writing a second timestamp matcher beside
`cli/highlight.py`'s — a rule this repo has broken before and named for it (*one rule set, applied
everywhere a followed line renders*). `_TIMESTAMP` produces the offset as a side effect of tinting,
and the indent is that number. Anything that re-derives it has built the second implementation.

### Round 1 — executed (2026-08-29)

**The doc's first phase said "read it off `marks` rather than adding a field, if so", and the
answer was no.** The timestamp's mark is a `sb.muted` span starting at zero, and so is a dimmed
opening bracket on a line that begins with one ([[highlight]] round 6, the same week). Reading
*which mark is the stamp* out of a list of marks is inference — a 1ch indent on `(foo) bar` is
harmless and it is still the surface guessing at structure. So `hang` exposes the offset from the
matcher that already computes it, and the frame carries it as a field. That is not the second
timestamp matcher the note warned about: it is the same `_TIMESTAMP`, and `marks` derives the same
number one line away.

**A line had to stop being a span-plus-newline and become a block.** `text-indent` applies to a
block container and an inline span inside a `<pre>` is not one, so the hanging indent was
impossible in the markup as it stood. Making the line a block means the trailing `"\n"` has to go —
a block *and* a newline is two line boxes, so every line in every window would have drawn
double-spaced. Consequences, all verified rather than assumed:

- **A blank line needs `min-height`.** With the newline gone an empty block has no line box, and
  the run of blank lines an agent writes between findings would have closed up. `1lh` holds it.
- **The legend got shorter by accident and correctly.** Its rows were 40px — one line of content
  and one of trailing newline — and are 20px now. Nobody had noticed.
- **All three consumers of `markedLine` were checked**: the canvas stream, the bench's trial tail,
  and the legend. It is one function drawing three things and the change was structural.

**`min-width` was the half most likely to be forgotten.** `pre.raw` sets `min-content`, which is
what makes a wide result scroll sideways. Setting `pre-wrap` without clearing it wraps the text
inside a box that is still too wide to see it in — the wrap would have looked broken while being
correct.

**The cap is measured, not defensive.** The last phase asked whether a stamp wider than the window
produces an infinite indent, and it does: at scale 2.4 in a 900px viewport, one record laid out as
**101 visual lines and 4217px tall**, one character per row, and the body started scrolling
sideways again — which is the thing wrapping was turned on to stop. `min(…, 40%)` fixes it (23
lines). Below that the canvas window itself measures 16px and then 4px, which is the
scale-is-a-geometry limit and predates this round; nothing there is wrap's to fix.

**Verified at both scales, and the `ch` unit did exactly its job.** At 1.15 one column is 8.27px and
the indent measured 19.95ch; at 2.4 it is 17.28px and the indent measured 20.02ch. The pixel indent
doubled, the column count did not, and the strong property held at both: the continuation's left
edge equals the left edge of the character at index `hang` on the first line — *directly under the
first text after the timestamp*, which is what was asked for rather than an approximation of it.
