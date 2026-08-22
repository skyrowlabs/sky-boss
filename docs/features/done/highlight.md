---
status: complete
created: 2026-08-22
updated: 2026-08-22
agent_value: 3
key_files:
  - cli/highlight.py
  - cli/resident.py
  - cli/tools.py
  - cli/follow.py
  - cli/filefollow.py
  - cli/canvas/server.py
  - cli/canvas/static/app.js
  - cli/canvas/static/tb.css
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

Round 2 adds the rest of the shapes an agent's log actually contains — see Phases. The rule
that governs *which role* each gets is new and is the point of that round: **the value
vocabulary is shared with `tb data`.** A number is `tb.num` whether it sits in a table cell or
a log line; a path is `tb.path` in both. `cli/output.py` already decides that for table cells
(`_cell`: numbers `tb.num`, `/`-leading strings `tb.path`), and a stream that invented its own
palette would mean the same value looked like two different things depending on which surface
you were reading. One vocabulary, two surfaces — the same argument the theme itself makes.

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
- [x] **The canvas applies marks.** Frame lines gain `marks`; the stream body wraps the
      offsets in role-classed spans and changes nothing else (in `app.js`, where the stream
      body actually lives — the spec said `render.js` and was wrong by one file). Verified by
      driving the live server's page and reading the DOM back, per house practice.
- [x] **The boundary, amended on the record.** [[file-follow]] gains a dated Notes entry:
      recognition-for-tinting permitted by [[highlight]], parsing/filtering/judging still
      refused, original argument left standing. The constitution's escalation-ladder entry
      gains the pointer that its first rung landed.

### Round 2 — the shapes an agent's log actually contains (2026-08-22)

Round 1 shipped three rules against a wall of text and the operator read the result on a real
stream: *"I would like common formats to stand out — dates, numbers and text should have
distinctions; keywords, icons and graphics should be emphasized."* The reference point given
was `tb data`: **make a followed line look the way a table cell already looks.**

That reference is the round's governing rule, not a mood. `tb data` already assigns roles to
value *kinds* — `tb.num` for numbers, `tb.path` for path-like strings. A stream inventing its
own palette would make the same value look like two different things on two surfaces. So round
2 adds shapes, and every shape takes **the role its kind already has in a table**.

Measured against the live cron.log rather than imagined. What is on those lines, in the order
the eye needs them:

- **`#925`** — the issue under work, and the single most scanned token in the file → `tb.num`.
  It is a number; it gets the number's role.
- **Numbers, with an attached `%` or short unit** (`8%`, `90m`, `10.2`, `20000`) → `tb.num`.
- **Dates and clock times mid-line** (`2026-08-26`, `19:00`) → `tb.num`. Note the asymmetry
  with the *leading* timestamp, which stays muted: the leading stamp is the most repeated and
  least informative thing on the line, while a date inside the prose is a fact someone wrote
  down. Same shape, opposite jobs.
- **Inline code spans** (`` `MAX_COMMITS = 50` ``, `` `agent_commit_review.py:75` ``) → `tb.path`.
- **Path-like tokens with an optional `:line`** (`docs/AGENTIC_AUTOMATION.md:3251`) → `tb.path`.
- **Markdown bold** (`**Zero scope violations**`) → **bold, no colour**. The agent prose in
  these logs is written in markdown and leans on bold for its findings; honouring it costs no
  hue at all, which is the cheapest legibility win available.
- **A markdown heading** at line start → bold, same argument.

**Code spans take `tb.path` rather than a hue of their own, and that is a deliberate refusal.**
A violet for code was prototyped and looked good, and the design system has no violet. Inventing
one would put a colour outside `colors_and_type.css` into the CLI, which is the exact drift
`cli/theme.py` exists to prevent. A code span and a path are the same *kind* of thing — a
literal, an identifier — and one role for both is honest.

**The text stays verbatim, so the `**` markers stay on screen.** That is inherited from round 1
and is not up for negotiation here: marks tint characters and never alter them. A renderer that
stripped the asterisks would be editing the log, and the canvas's guarantee — the payload the
window appends is provably the payload the file carried — dies with it.

**Marks get a ceiling.** Every mark rides to the canvas in the frame; a dense numeric line can
now produce dozens where round 1's three rules produced at most three. `MAX_MARKS` bounds them
per line, dropping the tail rather than the line — the same rule every surface here has had
since the first unbounded render froze one.

**Does not do, this round:**

- **Still no severity vocabulary.** No ERROR/WARN/INFO word list, no "this line looks bad".
  That is judgment, it belongs to the operator, and it is round 3 — arriving as *their*
  declaration rather than tb's opinion. The boundary round 1 drew is unmoved.
- **No emoji or box-drawing handling.** Terminals already colour emoji and the canvas already
  shows them; "emphasize the icons" is answered by not dimming them, which nothing does. A rule
  that restyled them would be tb overriding the font.
- **No change to `data`, envelopes, `--json`, or accrual output.** Tint is rendering.

- [x] **The rules.** `cli/highlight.py` gains ref, number, date, time, code, path, bold and
      heading, with an explicit priority so a number inside a code span does not tint twice —
      timestamp, tag, code, url, path, date, time, ref, number. `MAX_MARKS` caps the line.
- [x] **The number rule does not eat the following word.** Found in the prototype: a rule that
      allowed a spaced unit tinted `8 issue`, `104 archive`, `50 candidate` — the numeral plus
      whatever English word came next. Only a directly attached `%` or short unit joins.
- [x] **Both surfaces, unchanged in shape.** Terminal forms tint through `spans()`; the canvas
      already applies marks dumbly and needs the roles to exist as CSS classes — `mk-num` joins
      `mk-muted`/`mk-accent`/`mk-path`, and bold is a weight, not a colour.
- [x] **Tests per rule, plus the properties that make tinting safe**: `spans` still joins back
      to exactly the text, marks never overlap, the cap holds on a pathological line, and a
      line with nothing to tint still carries no marks at all.

### Round 3 — the operator's own patterns (2026-08-22)

The half round 2 cannot do, named in round 1's *"Does not do"* as this doc's future round, and
asked for in the same breath as round 2: *"if we can only do so much by default we might
consider a formatting tool or layer to user-defined tools."*

**Shape is tb's; vocabulary is the operator's.** `ESCALATE`, `Done.`, `handing to 'claude'`,
`skip` — these are the words that matter in one operator's log and mean nothing in anyone
else's. tb cannot know them and must not guess, for exactly the reason it does not guess
columns ([[capture]]): a word list is a judgment wearing a regex's clothes.

**So it is declared, in the file that already holds declarations about output.**
`$TB_HOME/formats.toml` gains `[highlight.<name>]` beside `[format.<name>]` — one operator file
for "things I have asserted about what my tools print", and one listing (`tb tools`) that
already shows what loaded and what was refused.

```toml
[highlight.jam]
description = "the words that matter in jam's cron log"
rules = [
  { pattern = "\\bESCALAT(E|ED|ION)\\b", role = "warn" },
  { pattern = "\\bhanding to '[^']+'", role = "accent" },
  { pattern = "\\bskip\\b", role = "muted" },
]
```

Named on the command, or inherited from a saved command:

    tb follow --highlight jam -- jam report watch --follow

**Roles are names from the palette, never colours.** `role = "warn"` resolves to `tb.warn`; a
role the theme does not define is refused at load, by name. Nothing operator-authored may put a
hex anywhere near this — the rule the whole theme rests on does not get an exception for a
config file.

**Operator rules run after tb's and never displace them.** A declared pattern claims only text
no built-in rule already claimed, so a timestamp stays muted and a tag stays a tag whatever the
operator writes. The alternative — letting a declaration win — makes every built-in rule
conditional on a file tb does not ship, and the first surprising log would be unexplainable.

**A regex from a file is the one real hazard, and it is bounded rather than trusted.** Patterns
are compiled at load and a bad one is refused by name; a pattern is length-capped; matching is
capped per line by `MAX_MARKS` like everything else. Catastrophic backtracking is still
reachable — Python's `re` has no timeout — so the honest mitigation is that this is the
operator's own file on the operator's own machine, the same trust level as `tools.toml`, and
**the canvas never accepts one over the wire.**

**Does not do:**

- **No replacement, no rewriting, no folding.** A rule tints a match. It cannot rewrite the
  line, hide it, collapse it or reorder it — the [[file-follow]] boundary stands.
- **No per-rule colours, no styles beyond the palette's roles.** Not "bold red at 60% opacity".
- **No rules over the wire.** The canvas reads the operator's file the same way the CLI does;
  no API route accepts a pattern, for the reason [[tools]] gives about writes.
- **No `--highlight` on `data`.** It shapes tables, and a table cell's role comes from its
  value's kind. Streams are where lexical rules belong.

- [x] **Declared rules load and validate.** `[highlight.<name>]` in `formats.toml`: patterns
      compile, roles resolve against the palette, a bad one is skipped and named in `tb tools`
      alongside the format problems it already lists.
- [x] **`--highlight NAME` on `follow`**, both forms, plus `highlight = "<name>"` on a saved
      command, inherited the way `refresh` is.
- [x] **Applied after the built-ins, claiming only unclaimed text**, with a test that proves a
      declared rule cannot repaint a timestamp or a tag.
- [x] **The canvas gets them too**, read from the same file server-side — marks arrive as marks
      and the frontend stays dumb, which is round 1's rule and the reason it is still true.

### Round 4 — the yellow, the glyphs, and the colour words (2026-08-22)

Reported against the live stream: *"the default colour for tb follow is yellow, can you make it
a grayish colour. There are checks that should naturally be green, Xs red, escalated yellow, red
is red — when words say a colour we should display that colour."*

**The yellow was a defect, not a default**, and it was introduced by [[follow]] round 2. The
tail-clip built its frame as `Text(marker, style="tb.warn")`, which sets the *base* style of the
whole Text object rather than styling the marker — so every line appended after it inherited
warn. And because a follow's ring always outruns the terminal, **every inline frame is clipped**,
so every line came out yellow. The round-2 test asserted the clip's text and never its styles,
which is exactly the gap a rendered check would have closed and a unit test did not. Fixed, with
a test on the styles.

**Three rules, and all three are still shape rather than judgment** — worth arguing, because
they look like the vocabulary rules this doc refuses:

- **A check is green, a cross is red, a warning sign is warn.** Not tb deciding a line went
  well: `tb data` already renders a true boolean as a green `✓` and a false one as a red `✗`
  (`_cell` in `cli/output.py`). One value vocabulary, two surfaces — the same rule round 2 ran
  on. `⚠️` is two codepoints (the sign plus U+FE0F) and both are claimed, or the glyph tints
  half.
- **A coloured circle shows its colour** — `🔴` red, `🟢` green.
- **A word that names a colour is shown in it.** The strongest form of the claim: the word
  *denotes* the colour. There is no inference between "the text says red" and "show it red",
  which is precisely what separates it from "the text says ERROR, so it is bad". Standalone
  words only, so `greenery` and `Greenland` are neither.

**An ordinary stderr line is now grey, and tb's own voice keeps the warning tint.** Painting all
of stderr yellow was the same judgment-in-a-regex's-clothes this module refuses everywhere else:
a tool talking on its second channel is reporting progress or printing a banner as often as it
is failing. The cursor's rotation and truncation announcements *are* tb speaking and must stay
loud, so they gain `voice` on the `Line` rather than borrowing a tag whose meaning changed
underneath them.

**"escalated yellow" is the operator's, and round 3 is where it goes.** It is vocabulary — it
means something in one grid and nothing anywhere else — so it is declared, not shipped.

**Does not do:**

- **No status colour on the whole line.** A green `✔` does not make its line green: the line
  still carries a timestamp, a job name and durations that have their own roles, and a line-wide
  wash would erase all of them to say one thing.
- **No process-state glyphs.** `▶ ▣ ⤼ ⤴` are jam's own vocabulary for started, held, skipped and
  escalated — a shape rule for them would be tb guessing another tool's semantics from a
  codepoint. They belong in a declared ruleset, which is where they went.

- [x] **The clip regression.** The marker is a span, not a base style; a test asserts the body's
      roles survive the cut.
- [x] **Glyph and colour-word rules**, positioned so a glyph inside a code span stays code.
- [x] **stderr grey, `voice` warn**, on both surfaces — `Line.voice`, the terminal body, the
      frame line, and a `.voice` class beside `.err`.
- [x] **The operator's own vocabulary declared**, proving round 3 carries the half tb refuses to
      guess.

## Notes

### Round 1 — drafted, awaiting the word (2026-08-22)

Drafted at the operator's instruction after the chrome round-2 review — their call, made
explicitly *because* it changes a recorded boundary, which is exactly what a spec is for. The
scope question was asked once already during that review: band polish was chosen first and
line tinting deferred; this doc is the deferred half arriving through the front door. Operator
highlight patterns and any severity vocabulary were considered for round 1 and parked: they
are declarations of judgment, and the Rule branch that owns judgment has not been designed yet
— landing its first opinionated tenant early would shape that design by accident.

### Round 1 — shipped (2026-08-22)

Four commits, no reversals. What the build added:

- **`spans()` earned its place beside `marks()`.** The terminal forms want (chunk, role)
  pairs — the chrome bands' shape — so the module offers both readings of the same rules,
  and the test that `spans` joins back to exactly the text is the one property that makes
  tinting safe to apply anywhere.
- **The spec was wrong by one file.** The canvas stream body lives in `app.js`, not
  `render.js`; marks are applied there. The deciding half stayed in Python either way,
  which was the point.
- **The path role costs the canvas no new hue.** `mk-path` is text-2 underlined — links
  look like destinations without `tb.css` growing a colour the palette does not have. The
  terminal keeps its existing `tb.path` steel blue.
- **A frame line with nothing to tint carries no `marks` key at all** — quiet frames stay
  byte-identical to before this round, the same omitted-not-null rule the envelope's `view`
  follows.
- Verified live: a stamped log followed on the canvas rendered muted timestamps, accent
  tags, an underlined URL, and untinted prose, with `textContent` equal to the file's bytes.

### Rounds 2 and 3 — drafted, awaiting the word (2026-08-22)

Asked for against a real stream — `tb follow -- jam report watch --follow` — with `tb data`
named as the reference. That reference did more work than a mood would have: it turned "make it
prettier" into a rule with a test behind it, **the value vocabulary is shared**, and it settled
every role question by asking what a table cell already does with that kind of value.

**The rules were prototyped against the live cron.log before any of this was written, and the
prototype earned its keep twice.** A number rule that allowed a spaced unit tinted `8 issue`,
`104 archive` and `50 candidate` — the numeral plus whatever English word followed it — which
reads as a highlighter having a stroke and would have shipped, because it is invisible in a
unit test and obvious the moment you look at a rendered log. And a violet for code spans looked
genuinely better than the alternative, which is exactly why it is refused: the design system has
no violet, and "looked better in a prototype" is how a second palette starts.

**The split between the two rounds is the split the doc has always had.** Round 1 wrote it as
*shape, not vocabulary*; round 2 is the rest of the shapes and round 3 is the vocabulary,
arriving as the operator's declaration rather than tb's opinion. What is new is only *where*
the declaration lives: `formats.toml`, beside the capture formats, because that file is already
"what I have asserted about what my tools print" and `tb tools` already lists what it refused.

### Rounds 2 and 3 — executed (2026-08-22)

What the execution argued back:

- **Writing the rules against a real log, rather than from the patterns, was the whole
  difference.** Three false positives showed up in the first pass over the live cron.log and
  none of them would have failed a unit test written from the regex: a spaced unit tinted the
  numeral *plus the next English word* (`8 issue`, `104 archive`, `50 candidate`); `\b\d` tinted
  the leading `7` of the git SHA `7d9d878`, which reads as a rendering fault rather than a
  highlight; and `\b` cannot begin a match at a dot, so `.github/…` and `./scripts/…` rendered
  with their leading dot bare. The fix for the second is the interesting one — lookarounds on
  *both* sides, so a number is tinted only when it is a number and not when it is a character of
  an identifier.
- **Bold could not be a role, so it became a modifier.** The flat, non-overlapping mark list is
  what lets the canvas apply marks dumbly, and emphasis nests over everything by nature. Making
  it compete for the slot would have meant a bold finding losing its code tint or the reverse.
  A composite role — `"bold tb.path"` — keeps the list flat, is what Rich already reads, and
  cost the canvas one `split(" ")`. The model bent rather than the feature.
- **Round 3's ordering rule earned a test the moment it was written.** Operator rules run last
  and claim only unclaimed text, so a declared `2026` cannot repaint a timestamp and a declared
  `agent` cannot repaint a tag. The alternative — a declaration winning — makes every built-in
  conditional on a file tb does not ship, and the first surprising log is unexplainable.
- **`highlight` on a saved command needed the same refusal `refresh` has.** Declared on a tool
  that wraps `data`, the field would load cleanly and mean nothing, because tint belongs to a
  stream. Refused at load by name — the "wrong but looks right" failure this loader exists to
  catch, arriving through a second door.
- **The listing absorbed rulesets without a new command**, the way formats did before them: one
  door for "what did I declare, and what was refused". `tb tools` grew a `highlights` section
  and their load problems join the same degrade list.
- Verified end to end against the live cron.log with a real `[highlight.jam]` declared — four
  rules, all firing, with the built-ins unmoved underneath them.

### Round 4 — executed (2026-08-22)

**The bug is the lesson.** `Text(marker, style=...)` styling the *whole object* rather than the
initial string is an ordinary Rich footgun, and it survived round 2's tests, its prototype and a
rasterised preview — because the preview rendered `spans()` directly and never went through
`clip()`, and the test asserted which lines survived the cut rather than what colour they were.
The operator found it in one look at a real stream. Two habits come out of it: a rendering check
has to run the *whole* path, and a test that asserts text should assert style when style is the
feature.

**Everything else the round asked for turned out to already have an argument in the doc.** The
check-is-green rule is round 2's shared-value-vocabulary rule applied to a glyph instead of a
number; the colour-word rule is the shape-not-judgment line at its clearest; and "escalated
yellow" is round 3 doing exactly the job it was built for, which is the first evidence that the
shape/vocabulary split holds up under a real request rather than only in the spec. The one thing
that needed a genuinely new decision was stderr, and it went the same way for the same reason: a
second channel is not a severity.

