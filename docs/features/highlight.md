---
status: active
created: 2026-08-22
updated: 2026-08-22
agent_value: 2
key_files:
  - cli/highlight.py
  - tests/test_highlight.py
---

# Highlight — lexical tint for followed lines

## Why

A follow window's body is a wall. Rendered against the live cron.log, every line — timestamps,
job tags, agent prose, URLs, warnings — arrives in one undifferentiated foreground, and the eye
has to *read* to find the boundary between one job's block and the next. The [[chrome]] round-2
polish fixed the bands; the body is still round-zero.

**This spec amends a recorded boundary, and says so plainly.** [[file-follow]] ruled: *"does
not parse, filter, or judge lines — highlighting and the delta view are Rule branches that bind
onto this loop later; they are not this loop."* This doc is that later rung arriving, and the
amendment is deliberately narrow. The original fear was the "silently wrong" failure —
structure inferred from whitespace that reads as complete and is not, columns that lie. That
argument still holds for *structure* and this doc does not touch it. What it permits is
**recognition for tinting only**: the text stays verbatim, nothing is filtered, folded or
reordered, and a missed match costs a color, not a fact. A tint that misfires is visibly
cosmetic; a column that misfires is invisibly wrong. That asymmetry is what makes this safe
where parsing was not.

**Why lexical and not semantic.** Dimmed timestamps and tinted `[tags]` are *shape* — patterns
a regex can name without an opinion. "This line is an error" is a *judgment* — exactly what the
chrome's attention slot refuses to hold and what the escalation ladder's Rule branch exists to
decide, later, with the operator declaring the patterns. Round 1 draws the line at shape;
operator-declared highlight patterns are this doc's future round, not its first.

## Shape

**One rule set, in Python, applied everywhere a followed line renders.** `cli/highlight.py`
holds a pure function — a line in, `(start, end, role)` marks out — for the same reason the
view heuristic and the chrome facts live where they do: the frontend has no test runner, and
two renderers holding their own opinions would drift the week they were written. The terminal
forms tint through it directly; the canvas receives each frame line's marks *beside* its
verbatim text and applies them dumbly in `render.js`.

The round-1 rules, all shape, no vocabulary:

- **A leading ISO-8601 timestamp** → muted. It is the least informative and most repeated
  thing on every line; dimming it is what makes everything else legible.
- **A `[bracketed-tag]` immediately after it (or at line start)** → brand. The tag is the
  job's name — the boundary the eye actually scans for in a multi-job log.
- **A URL** → the path role. Links are destinations; they should look like it.
- **The cursor's and stream's own voice** (rotation, truncation, stderr lines) — already
  tinted warn by [[follow]]/[[file-follow]]; unchanged, and this module never re-tags them.

**Marks ride beside the text, never instead of it.** A stream frame's line stays
`{text, stderr}` verbatim and gains `marks: [[start, end, role], …]` — offsets into the text,
so the payload the canvas appends is provably the payload the file carried. Roles are theme
role names; the canvas already has every token as a CSS custom property, and no color is named
outside `cli/theme.py` in any language.

**Does not do:**

- **No filtering, folding, or reordering.** Every line renders, whole, in arrival order. This
  boundary is inherited from [[file-follow]] and is not amended.
- **No severity inference.** No ERROR/WARN/INFO vocabulary, no "this looks bad" — a word list
  is a judgment wearing a regex's clothes, and judgments are the Rule branch's, with the
  operator holding the pen. When operator patterns arrive (`highlight = […]` in a tool's
  declaration), they arrive as *their* declared opinion, as a new round here.
- **No structure claims.** Marks tint characters; they never become columns, fields, or a
  `view`. A tool with real structure has `--json` and [[table-views]].
- **No touch on `data`, envelopes, or `--json`.** Tint is rendering. The accrual path's piped
  stdout stays byte-pure; marks appear only in canvas frames and terminal styling.
- **No marks on `run`/`read` accrual output.** Those lines go to a possibly-piped stdout as
  the tool printed them; tinting belongs to the resident surfaces, where the ring is the
  display. If a real want appears for tinted accrual, argue it as its own round.

## Phases

### Round 1 — shape, not vocabulary (2026-08-22)

- [x] **The rules, pure.** `cli/highlight.py`: `marks(text) -> list[(start, end, role)]` for
      timestamp, tag and URL; overlaps resolved (first match wins, no nesting). Tests per
      rule, plus the properties: text never altered, a non-matching line yields no marks, a
      pathological line (200 KB, no spaces) returns in bounded time.
- [x] **The terminal forms tint.** Both follow bodies apply marks via the span assembler the
      chrome bands already use; stderr/announcement lines keep their warn tint untouched.
- [ ] **The canvas applies marks.** Frame lines gain `marks`; `render.js` wraps the offsets in
      role-classed spans and changes nothing else. Verified by rendering headless Chromium
      against the live server, per house practice.
- [ ] **The boundary, amended on the record.** [[file-follow]] gains a dated Notes entry:
      recognition-for-tinting permitted by [[highlight]], parsing/filtering/judging still
      refused, original argument left standing. The constitution's escalation-ladder entry
      gains the pointer that its first rung landed.

## Notes

### Round 1 — drafted, awaiting the word (2026-08-22)

Drafted at the operator's instruction after the chrome round-2 review — their call, made
explicitly *because* it changes a recorded boundary, which is exactly what a spec is for. The
scope question was asked once already during that review: band polish was chosen first and
line tinting deferred; this doc is the deferred half arriving through the front door. Operator
highlight patterns and any severity vocabulary were considered for round 1 and parked: they
are declarations of judgment, and the Rule branch that owns judgment has not been designed yet
— landing its first opinionated tenant early would shape that design by accident.
