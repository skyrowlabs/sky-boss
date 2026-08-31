---
status: complete
created: 2026-08-22
updated: 2026-08-30
agent_value: 3
key_files:
  - cli/highlight.py
  - cli/resident.py
  - cli/tools.py
  - cli/follow.py
  - cli/filefollow.py
  - cli/canvas/server.py
  - cli/canvas/catalog.py
  - cli/canvas/static/api.js
  - cli/canvas/static/app.js
  - cli/canvas/static/bench.js
  - cli/canvas/static/sb.css
  - tests/test_canvas_catalog.py
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
vocabulary is shared with `sb data`.** A number is `sb.num` whether it sits in a table cell or
a log line; a path is `sb.path` in both. `cli/output.py` already decides that for table cells
(`_cell`: numbers `sb.num`, `/`-leading strings `sb.path`), and a stream that invented its own
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
- **No ninth colour, and no per-rule colour override** (round 5). Every ask this round could not
  answer wanted a hue the design system does not have, and adding one is an edit to the vendored
  `colors_and_type.css` — not a sky.boss decision. This module records the last attempt: a violet
  for code spans, prototyped, good-looking, rejected as *exactly how a second palette starts*.
  Held open as `docs/open.md` item 20 rather than settled here.
- **No conventional glyphs** (round 5). 🤝 🌙 🙋 👉 🔎 all appear in the live log and every one
  means something to *that grid* and nothing anywhere else. They are the operator's vocabulary, and
  round 3 already ships the way to say so — **a declared pattern may be a glyph**, which nobody had
  noticed because nothing in the surface shows it.
- **No ninth hue, and the question is closed rather than deferred** (round 6). The design system
  has four and sky.boss spends four; adding one is an edit to the vendored `colors_and_type.css`
  and a decision for the brand, not for this tool. What replaced it is the **ground** axis, which
  costs nothing. Quoted text is the one ask still unanswered — it wants to be distinct from
  `` `code` `` and a path, and those already share the literal role.
- **No editing of `formats.toml` from the bench** (round 5). `tools.toml` writes are safe because
  they splice one block's line range and back the file up first; `formats.toml` has neither, and
  building both is a larger round than this one.

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
was `sb data`: **make a followed line look the way a table cell already looks.**

That reference is the round's governing rule, not a mood. `sb data` already assigns roles to
value *kinds* — `sb.num` for numbers, `sb.path` for path-like strings. A stream inventing its
own palette would make the same value look like two different things on two surfaces. So round
2 adds shapes, and every shape takes **the role its kind already has in a table**.

Measured against the live cron.log rather than imagined. What is on those lines, in the order
the eye needs them:

- **`#925`** — the issue under work, and the single most scanned token in the file → `sb.num`.
  It is a number; it gets the number's role.
- **Numbers, with an attached `%` or short unit** (`8%`, `90m`, `10.2`, `20000`) → `sb.num`.
- **Dates and clock times mid-line** (`2026-08-26`, `19:00`) → `sb.num`. Note the asymmetry
  with the *leading* timestamp, which stays muted: the leading stamp is the most repeated and
  least informative thing on the line, while a date inside the prose is a fact someone wrote
  down. Same shape, opposite jobs.
- **Inline code spans** (`` `MAX_COMMITS = 50` ``, `` `agent_commit_review.py:75` ``) → `sb.path`.
- **Path-like tokens with an optional `:line`** (`docs/AGENTIC_AUTOMATION.md:3251`) → `sb.path`.
- **Markdown bold** (`**Zero scope violations**`) → **bold, no colour**. The agent prose in
  these logs is written in markdown and leans on bold for its findings; honouring it costs no
  hue at all, which is the cheapest legibility win available.
- **A markdown heading** at line start → bold, same argument.

**Code spans take `sb.path` rather than a hue of their own, and that is a deliberate refusal.**
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
  declaration rather than sky.boss's opinion. The boundary round 1 drew is unmoved.
- **No emoji or box-drawing handling.** Terminals already colour emoji and the canvas already
  shows them; "emphasize the icons" is answered by not dimming them, which nothing does. A rule
  that restyled them would be sky.boss overriding the font.
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

**Shape is sky.boss's; vocabulary is the operator's.** `ESCALATE`, `Done.`, `handing to 'claude'`,
`skip` — these are the words that matter in one operator's log and mean nothing in anyone
else's. sky.boss cannot know them and must not guess, for exactly the reason it does not guess
columns ([[capture]]): a word list is a judgment wearing a regex's clothes.

**So it is declared, in the file that already holds declarations about output.**
`$SB_HOME/formats.toml` gains `[highlight.<name>]` beside `[format.<name>]` — one operator file
for "things I have asserted about what my tools print", and one listing (`sb tools`) that
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

    sb follow --highlight jam -- jam report watch --follow

**Roles are names from the palette, never colours.** `role = "warn"` resolves to `sb.warn`; a
role the theme does not define is refused at load, by name. Nothing operator-authored may put a
hex anywhere near this — the rule the whole theme rests on does not get an exception for a
config file.

**Operator rules run after sky.boss's and never displace them.** A declared pattern claims only text
no built-in rule already claimed, so a timestamp stays muted and a tag stays a tag whatever the
operator writes. The alternative — letting a declaration win — makes every built-in rule
conditional on a file sky.boss does not ship, and the first surprising log would be unexplainable.

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
      compile, roles resolve against the palette, a bad one is skipped and named in `sb tools`
      alongside the format problems it already lists.
- [x] **`--highlight NAME` on `follow`**, both forms, plus `highlight = "<name>"` on a saved
      command, inherited the way `refresh` is.
- [x] **Applied after the built-ins, claiming only unclaimed text**, with a test that proves a
      declared rule cannot repaint a timestamp or a tag.
- [x] **The canvas gets them too**, read from the same file server-side — marks arrive as marks
      and the frontend stays dumb, which is round 1's rule and the reason it is still true.

### Round 4 — the yellow, the glyphs, and the colour words (2026-08-22)

Reported against the live stream: *"the default colour for `sb follow` is yellow, can you make it
a grayish colour. There are checks that should naturally be green, Xs red, escalated yellow, red
is red — when words say a colour we should display that colour."*

**The yellow was a defect, not a default**, and it was introduced by [[follow]] round 2. The
tail-clip built its frame as `Text(marker, style="sb.warn")`, which sets the *base* style of the
whole Text object rather than styling the marker — so every line appended after it inherited
warn. And because a follow's ring always outruns the terminal, **every inline frame is clipped**,
so every line came out yellow. The round-2 test asserted the clip's text and never its styles,
which is exactly the gap a rendered check would have closed and a unit test did not. Fixed, with
a test on the styles.

**Three rules, and all three are still shape rather than judgment** — worth arguing, because
they look like the vocabulary rules this doc refuses:

- **A check is green, a cross is red, a warning sign is warn.** Not sky.boss deciding a line went
  well: `sb data` already renders a true boolean as a green `✓` and a false one as a red `✗`
  (`_cell` in `cli/output.py`). One value vocabulary, two surfaces — the same rule round 2 ran
  on. `⚠️` is two codepoints (the sign plus U+FE0F) and both are claimed, or the glyph tints
  half.
- **A coloured circle shows its colour** — `🔴` red, `🟢` green.
- **A word that names a colour is shown in it.** The strongest form of the claim: the word
  *denotes* the colour. There is no inference between "the text says red" and "show it red",
  which is precisely what separates it from "the text says ERROR, so it is bad". Standalone
  words only, so `greenery` and `Greenland` are neither.

**An ordinary stderr line is now grey, and sky.boss's own voice keeps the warning tint.** Painting
all of stderr yellow was the same judgment-in-a-regex's-clothes this module refuses everywhere else:
a tool talking on its second channel is reporting progress or printing a banner as often as it is
failing. The cursor's rotation and truncation announcements *are* sky.boss speaking and must stay
loud, so they gain `voice` on the `Line` rather than borrowing a tag whose meaning changed
underneath them.

**"escalated yellow" is the operator's, and round 3 is where it goes.** It is vocabulary — it
means something in one grid and nothing anywhere else — so it is declared, not shipped.

**Does not do:**

- **No status colour on the whole line.** A green `✔` does not make its line green: the line
  still carries a timestamp, a job name and durations that have their own roles, and a line-wide
  wash would erase all of them to say one thing.
- **No process-state glyphs.** `▶ ▣ ⤼ ⤴` are jam's own vocabulary for started, held, skipped and
  escalated — a shape rule for them would be sky.boss guessing another tool's semantics from a
  codepoint. They belong in a declared ruleset, which is where they went.

- [x] **The clip regression.** The marker is a span, not a base style; a test asserts the body's
      roles survive the cut.
- [x] **Glyph and colour-word rules**, positioned so a glyph inside a code span stays code.
- [x] **stderr grey, `voice` warn**, on both surfaces — `Line.voice`, the terminal body, the frame
      line, and a `.voice` class beside `.err`.
- [x] **The operator's own vocabulary declared**, proving round 3 carries the half sky.boss refuses
      to guess.

### Round 5 — weight instead of hue (2026-08-29)

**The operator asked for emphasis six times in one sitting and the palette has no room for another
colour.** Raised while reading the live agent-fix drain: symbols should stand out, quoted text
should differ, `#123` should be unique, brackets should differ, *escalate* should be emphasised,
and — added mid-round — so should ALL CAPS. Four of those want a hue, and `STYLES` has eight roles
with every one already spoken for. `docs/open.md` item 20 holds that question open.

**The answer was already in the module.** Round 4 established that **bold is a weight, not a
colour**, so it composes with whatever colour a mark already carries instead of competing for the
slot — and `_emphasise` is the machinery, already written, already tested, already understood by
both renderers. Emphasis is what was asked for. Emphasis is free. This round spends weight.

- [x] **The verdict glyphs, widened by a rule rather than a list.** The test round 4 used — *is the
  meaning in dispute* — does not decide the operator's examples on its own. The one that does:
  **a glyph qualifies when carrying the verdict is its whole job.** Strip the verdict from
  ✓ ✗ 👍 👎 ⚠ 🚨 ⛔ and there is no glyph left. 🎉 🚀 🔥 🤝 🌙 all *correlate* with a verdict in
  agent prose and denote something else — a party, a rocket, a fire, a handshake, night. Tinting
  those reads a convention, which is the judgment this module has refused since round 1.

  Adds thumbs (👍👎), alerts (🚨 ❗ ❕ ‼), refusals (❎ 🛑) and info (ℹ️) to the round-4 set.
- [x] **Every glyph becomes an emphasis range, not a louder colour.** A glyph is one character
  wide, and hue at one character is the weakest signal this palette has. Weight is the strongest
  and it costs no role.
- [x] **ALL CAPS is a shape, and the corpus says it is two shapes.** `FOO_BAR` with an underscore
  is an **identifier** and takes `sb.path`, the role round 2 already gave a literal. A bare
  capitalised word of five characters or more is a **shout** and takes weight alone. The threshold
  is measured, not chosen — see Notes.
- [x] **The caps rule runs as emphasis, which is what makes it composable.** A colour rule claiming
  `ERROR` would *block* the operator's own `error → fail` from ever reaching it, because a declared
  rule takes only unclaimed text. As an emphasis range it does the opposite: their colour lands
  first and the shout adds weight to it. This is the argument for the whole round in one case.
- [x] **Overlapping emphasis ranges merge before they fill.** Four sources of range where there was
  one, so `**ERROR**` is a shout inside a markdown emphasis. Union them first; the existing filler
  walks a range assuming nothing else covers it.
- [x] **The bench stops asking you to remember.** `--highlight` is a text box whose placeholder
  says *"a ruleset in `formats.toml`"*, and **the surface has never read that file** — nor has
  `--from` beside it. So the one control this round is about is the one that cannot show its own
  options, and a mistyped name yields an untinted stream with no reason given: the silent path and
  the healthy path are the same bytes.

  `/api/vocabulary` — introspection beside `/api/catalog` and `/api/shape`, in-process, running
  nothing — returns the declared rulesets and formats **with their problems**, because one that
  failed to compile must appear refused rather than absent. `sb tools` already groups both this way.
- [x] **A legend, because the declared half is the small half.** Thirteen built-in rules do most of
  the tinting and none is visible anywhere in the surface. Drawn in their real roles, the legend
  makes *"runs after sky.boss's own and claims only unclaimed text"* something you can see rather
  than a sentence you have to trust — and it is how an operator discovers that **a declared pattern
  may be a glyph**, which is the finding in Notes they most need.

### Round 7 — the two asks nothing answered (2026-08-30)

Both were named inside [[open]] item 20 as *unanswered* while the item itself was closed: a declared
rule can name a colour and never a weight, and quoted text is *"the one ask nothing answered"*. They
are one round because they turn out to be the same shape — **neither needs a hue, and both reuse a
mechanism this doc already has.**

**A declared rule may ask for weight, and it rides `loud` rather than a composite role.** Round 5
established that bold is a *weight, not a colour*, so it composes instead of competing for the role
slot — and the machinery for that is already end to end: `marks()` collects a `loud` range per
built-in rule that asks for one, `_emphasise` folds it in, `role_style` resolves `"bold sb.warn"`
for Rich, and the canvas splits it into two classes. What was missing was a spelling for the
operator:

```toml
[[highlight.jam.rules]]
pattern = "escalat(e|ed|es|ing|ion|ions)"
role = "warn"
weight = "bold"
```

**Adding the span to `loud` rather than writing `"bold sb.warn"` into the role.** A composite role
string would have to survive `mk-${role}` on the canvas, where it becomes two class names in one
attribute, and it would double up when `_emphasise` ran over it — `bold bold sb.warn`. Going through
the existing range list means a declared weight and a built-in one are the same thing by
construction, `_merge` already handles their overlap, and nothing downstream learns a new shape.
`weight` takes one value, `"bold"`, because that is the only weight the palette has; a second is a
design-system decision, exactly as a ninth hue is.

**Quoted text is answered as a delimiter, not as a colour.** The ask was that it be *"differentiated"*,
and item 20's own analysis is why that cannot be a hue: the design system holds four and sky.boss
spends all four. Round 6 already answered this shape once — `()`, `[]` and `{}` dim their
**delimiters** so the contents stand out — and a quote is a delimiter. So `"…"` and `'…'` join
`_WRAPPED`, dimming the marks and leaving whatever is inside them alone.

**That also disposes of the collision the item warned about**, rather than losing to it. The
operator's `handing to '…'` rule claims a quoted string, and built-ins run first, so a built-in rule
over the *contents* would have stolen it. The delimiter pass claims **single characters** and runs
**last**, after the operator's rules — so their colour lands on the words and the quotes dim around
it. Both asks are answered on the same line.

**The apostrophe hazard is real and is measured, not reasoned about.** Item 20 names it precisely: a
naive `'…'` matches from the apostrophe in `don't` and runs to the next one. Against the live 140-line
log, `'[^'\n]{1,200}'` produces **15** spans and two are exactly that failure — one running 100+
characters from `checkout's` to `didn't`. The guarded form
`(?<![\w'])'[^'\n]{1,200}'(?!\w)` produces **13** and neither. Double quotes need no guard and
produce 8.

**Does not do:**

- **No `weight` values but `bold`**, and no `dim` — dimming is what the delimiter pass does, and a
  rule that could dim its own match would be a second way to say one thing.
- **No colour for quoted contents.** The ask is answered by the surround; a role for the inside
  would be the ninth hue this doc has now refused three times.
- **No multi-line quotes.** Every rule here is per line, and a quote that opens and never closes on
  the same line is prose about a quote far more often than it is a quote.

### Round 7 phases

- [x] `weight = "bold"` on a declared rule, validated with the roles and refused otherwise.
- [x] A declared weight rides `loud`, so it is the same object a built-in emphasis is.
- [x] `"…"` and `'…'` dim their delimiters, the single-quote form guarded against the apostrophe.
- [x] Measured against the live log rather than a fixture: the guard's two false matches are gone.
- [x] The bench's legend shows a quoted example, since it renders through the real `marks()`.

### Round 6 — ground, not hue (2026-08-29)

**Round 5 answered everything weight could answer and left three asks needing a colour.** The
operator then asked the obvious next question — *can you pick colours from the skyrow theme* — and
the answer is **no, and the reason is worth writing down once**: the vendored system holds exactly
four hues and sky.boss spends all four. `--brand`/`--js` is one colour, `--bb` **is** `--ok`, `--mh`
**is** `--warn`, `--danger` is the fourth. The per-project tokens look like extra palette and are
aliases.

**What the system does still hold is a token that is not a hue.** `--text-on-accent` is its own
answer to *louder than a colour can be*: put the hue in the **background**. So the axis after
weight is **ground**, and it costs nothing. A painted ground is also outside the CLI's two-sided
contrast floor, by the mark's own argument — every other role is darkened because the terminal's
background is unknown, and a role that supplies its own removes the unknown.

- [x] **`#123` gets a ground rather than a hue.** `sb.ref` is the brand on a wash of itself: the
  same colour, a different *object*, so round 2's rule holds (a value looks like its kind on both
  surfaces) and it stops being indistinguishable from every other number. The CLI fills at
  `--brand-ring`'s 22% and the canvas at `--brand-dim`'s 12% inside a 22% ring — a mapping rather
  than a taste, since the system draws a chip as a fill inside a ring and a terminal cell has no
  edge to draw, so it spends the ring's weight on the fill.
- [x] **A painted role is checked against the ground it paints**, not exempted. The text floor
  applies to its text on its own ground; the *ground* is judged by perceptual distance from either
  terminal, with the threshold taken from the system — `--bg` to `--surface` is the smallest step
  it treats as a visible change of surface. Skipping them would have let a role into `STYLES` that
  nothing checked at all.
- [x] **A delimiter dims and what it wraps does not.** The ask was for `()`, `{}` and `[]` in a
  colour of their own; there is none to give. The answer that needs none is the leading timestamp's,
  turned on punctuation — `--text-3` is defined by the system as *"structure, not reading text"*,
  which is what a delimiter is. Dimming the two characters makes the contents stand out by taking
  noise away. The brace is the one that earns it: an agent log carries JSON.
- [x] **A composite role resolves in the terminal.** Not this round's subject; found by rendering
  one line and reading the escape codes. See Notes.
- [x] **A mark role paints on the canvas**, and the stylesheet is enumerated off the Python rules
  so the next one cannot ship unpainted. Also not this round's subject, and worse. See Notes.

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
  look like destinations without `sb.css` growing a colour the palette does not have. The
  terminal keeps its existing `sb.path` steel blue.
- **A frame line with nothing to tint carries no `marks` key at all** — quiet frames stay
  byte-identical to before this round, the same omitted-not-null rule the envelope's `view`
  follows.
- Verified live: a stamped log followed on the canvas rendered muted timestamps, accent
  tags, an underlined URL, and untinted prose, with `textContent` equal to the file's bytes.

### Rounds 2 and 3 — drafted, awaiting the word (2026-08-22)

Asked for against a real stream — `sb follow -- jam report watch --follow` — with `sb data`
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
arriving as the operator's declaration rather than sky.boss's opinion. What is new is only *where*
the declaration lives: `formats.toml`, beside the capture formats, because that file is already
"what I have asserted about what my tools print" and `sb tools` already lists what it refused.

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
  A composite role — `"bold sb.path"` — keeps the list flat, is what Rich already reads, and
  cost the canvas one `split(" ")`. The model bent rather than the feature.
- **Round 3's ordering rule earned a test the moment it was written.** Operator rules run last
  and claim only unclaimed text, so a declared `2026` cannot repaint a timestamp and a declared
  `agent` cannot repaint a tag. The alternative — a declaration winning — makes every built-in
  conditional on a file sky.boss does not ship, and the first surprising log is unexplainable.
- **`highlight` on a saved command needed the same refusal `refresh` has.** Declared on a tool
  that wraps `data`, the field would load cleanly and mean nothing, because tint belongs to a
  stream. Refused at load by name — the "wrong but looks right" failure this loader exists to
  catch, arriving through a second door.
- **The listing absorbed rulesets without a new command**, the way formats did before them: one
  door for "what did I declare, and what was refused". `sb tools` grew a `highlights` section
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

### Round 5 — the rules half, executed (2026-08-29)

**Both reversals in this round came from the corpus, not from the argument.** The 251 KB `cron.log`
being read when it was raised was measured before a rule was written, and it said no twice.

**"ALL CAPS should be emphasised" is two rules.** Of 150 all-caps runs at five characters or more,
the clear majority are configuration identifiers — `JAM_KUMA_FORCE_PING` ×22, `MAX_PER_RUN` ×10,
`ALLOWED_HOSTS` ×7, `GEOIP_ASN_DB_PATH` — and the rest are genuine shouts: `ERROR` ×12,
`PREFLIGHT` ×8, `FAILED`, `REFUSED`, `DRIFT`. Emphasising both identically would have shouted an
env-var name twenty-two times. An underscore separates them, and the identifier takes the role
round 2 already gave a literal.

**Five characters, measured rather than chosen.** Below it the corpus is acronyms in ordinary
prose: `PR` ×122, `CI` ×52, plus a bare `I` ×46 and `A` ×10 — **349 occurrences of pure noise at
one to three characters against roughly 30 real shouts at five and up.** Four is the interesting
boundary and it loses: it buys `TODO` (12) at the price of `HEAD` (23) and `HTTP` (10). `TODO`
going untinted is the known cost of the line, and it is the right trade at this ratio.

**The diff against the live log, old rules versus new, 1,897 lines:** 98 marks gained, 121 roles
changed, **nothing lost**. Every gain is a config identifier or a shout; every change is a glyph
picking up weight. No false positive in the whole file — which is the bar round 2 set when a rule
that looked fine in a unit test turned out to be tinting `8 issue` and `104 archive`.

**What the census also found, and it belongs to the operator rather than to this round.** The log
carries 🤝 ×15, 🌙 ×10, 🙋 ×3, 👉, 🔎 — jam's own vocabulary, correctly excluded by the round's
rule. They are already declarable today, because **a declared pattern is a regex and a regex may be
a glyph**. Nobody had noticed. That is not a gap in round 3; it is a gap in the surface, and it is
why the bench half of this round exists.

**One test had to be narrowed to be kept honest.** `test_no_severity_vocabulary_anywhere` asserted
`marks("ERROR …") == []`, which the shout rule breaks. Read as a boundary that would have blocked
a rule that judges nothing — the shout knows only that someone capitalised a word, and bolds
`VACUUM` with exactly the same enthusiasm as `ERROR`. The property that actually matters is
narrower and stronger, and is what it asserts now: **no word earns a verdict colour.** `sb.fail`
and `sb.warn` are what a severity vocabulary would reach for, and no built-in rule hands either to
a word. Weight carries no verdict — which is the whole argument for spending it here.

**And one test passed for the wrong reason before it was fixed.** The acronym case asserted
`marks("the PR is green and CI agrees") == []` and failed on `green`, which round 4's colour-word
rule had claimed a year of commits ago. The assertion wanted *no shout*, not *no marks*; an empty
list would have been testing something else and happening to be right.

**Thumbs are the one addition with no corpus evidence at all** — zero occurrences of 👍 or 👎 in
the file. They went in on the rule rather than the measurement, which is the correct order, and is
recorded here so the next reader knows which parts of this round were verified against real bytes
and which were reasoned.

### Round 5 — the bench half, executed (2026-08-29)

**Rendering it found three things the suite could not, which is the third time that has happened
this week and the reason CLAUDE.md calls that pass an obligation.**

**A shipped bug, a week old, in the thing this round is about.** Marks are computed in Python,
which counts **code points**, and applied by JavaScript's `slice`, which counts **UTF-16 code
units**. Every astral character — 🔴 🟢 🟡 👍, every emoji above U+FFFF — is one on one side and
two on the other, so the page cut a surrogate pair in half and every offset after it on the line
was wrong. The operator's live log carries 🔴 ×7, 🟢 ×5, 🟡 ×3.

It survived round 4 because **both sides were self-consistent**: the terminal applies these offsets
to the same Python string that produced them and is right; the suite compares marks to marks and
never slices; and the log's most common glyph, `✅` (U+2705), is inside the BMP and behaves. It took
drawing a row of status lights in a real browser to see one come out as half of itself. Converted at
the wire in `highlight.utf16`, because the offsets exist to be handed to `String.prototype.slice`
and should be in that function's units by the time it sees them. The new test slices UTF-16 rather
than comparing offsets — comparing offsets is exactly the check that missed it.

**A silent TypeError froze the whole panel.** The legend shipped its example as `example` while
`markedLine` reads `text`, so `l.text.slice(...)` threw inside preact's render. The component
mounted, re-rendered, logged the new state — and the DOM never changed, with **no console error and
no failing test**. Diagnosing it took a mount/render probe, because every ordinary signal said the
component was healthy. The field is `text` now and the name is load-bearing: a legend row is shaped
exactly like a followed line, which is what lets one applier draw both. A test asserts the whole
shape, not just the marks.

**The 62rem label overflowed at 2.4.** `flex: none; width: 62rem` is 285px at scale 1.15 and 595px
at 2.4, inside a pane that does not grow with it — the row overflowed the body by 500px, which is
the failure CLAUDE.md says the workbench lost a step to for three rounds. Now the row wraps: the
label keeps its width so the column still aligns, and the example takes its own line when there is
no room beside it. Checked at both. *(The bench still overflows at 2.4 in a 1440px viewport for
reasons that predate this round — the canvas screen does it before the bench is opened, and the
widest element is the top bar's quit button. Not touched here.)*

**And the panel was disagreeing with the line beside it.** `--save` writes `--highlight` into a
tool's *argv*, and the bench's decomposer lifted only `--cwd` and `--env` out — so opening the
operator's own `jam-agent-fix-log` showed the picker at `none` while the composed line carried
`--highlight jam`. `--from` and `--due` had the identical defect and were fixed with it; they are
three lines and one table. The argv wins over the declared field when both exist, because the argv
is what will run.

**The finding worth passing to the operator** came out of the glyph census rather than the code:
their log carries 🤝 ×15, 🌙 ×10, 🙋 ×3 — jam's own vocabulary, correctly outside sky.boss's
built-in set — and **a declared pattern is a regex, so it may be a glyph.** Nobody had noticed,
because until this round nothing in the surface showed what a declared rule even was.

### Round 6 — executed, and two older bugs fell out of it (2026-08-29)

**Neither of the two worst things found in this round was in this round's subject, and both were
the same shape: a mark that landed and was never painted.**

**Composite roles have rendered unstyled in the terminal since round 4.** Rich cannot resolve a
theme name inside a compound style string: `get_style("sb.ok")` finds the theme entry, and
`get_style("bold sb.ok")` falls through to `Style.parse`, which tries to read `sb.ok` as a *colour*,
fails, and raises `MissingStyle` — which the render path swallows. CLAUDE.md recorded that *"Rich
reads `bold sb.path` directly"*, which was never true. Round 4 made it a handful of bold phrases;
**round 5 made every glyph composite**, so every ✓, ✗ and ⚠ in the log rendered plain. `role_style`
in `cli/output.py` resolves each word against the theme and parses only what the theme has no entry
for. Found by rendering one line and looking at the escape codes.

**And the canvas never had a rule for `.mk-ok`, `.mk-fail` or `.mk-warn` at all.** Round 4's verdict
roles and its colour words shipped their classes with nothing to paint them, so the same glyphs
rendered in plain body text there too — for a week, in the opposite surface from the bug above.
Both were wrong, differently, about the same characters.

**Three separate checks had passed over this and could not see it**, which is the part worth
keeping. The suite compares marks to marks. The round-5 headless pass read `element.className`,
which is *present* whether or not a rule matches it. And the natural question — *did the mark land*
— is answerable without ever asking what colour came out. The failure is visible only in a computed
style. `test_every_mark_role_the_highlighter_can_emit_has_a_rule_in_the_stylesheet` now enumerates
the roles off `_RULES` rather than spot-checking, the way the API route list is.

**A third, smaller one from the same family:** the mark classes were scoped `pre.stream .mk-*`,
which covered every marked line until round 5's legend drew one inside `pre.raw.legend-eg`. The
classes landed, the paint did not, and my own verification of that legend had read class names.
Unscoped now — a mark is a mark wherever it is drawn, and `pre.stream` was only buying them a
margin.

**On the delimiters, measured before believing it.** Over the same 1,897 lines: 832 paren pairs, 9
bracket pairs, and the braces. That is a lot of new marks — roughly one pair every other line — so
the safety properties were re-checked over the whole file rather than over a fixture: spans still
join back to the text on every line, no line has overlapping or unsorted marks, and no line comes
near the 64-mark cap. 579 refs took the new ground.

**The `== []` assertion caught a third test out.** `test_a_digit_inside_an_identifier_is_not_a_number`
asserted `marks("new commits: 7d9d878 (first run)") == []`, which now fails on the dimmed parens —
the same failure as round 5's `green` case and round 3's before it. An empty list passes for reasons
the test's name never mentions, and the fix is always to assert the property the name claims. Three
times in this file now; worth reading as a rule rather than three accidents.

**One thing was found and deliberately not fixed.** `CLI_PATH = "#698bab"` is the only CLI role that
derives from no token — every other line says *from BRAND*, *from OK* — and the canvas draws that
same role as `--text-2` plus an underline, a different colour entirely. So the module's *one value
vocabulary, two surfaces* has an exception nobody wrote down, and
`test_the_two_renderings_cover_the_same_hues` cannot see it: it checks that the tokens ship
undarkened, not that every role has a token behind it. Left alone because it is a palette decision
and this round was already carrying two unrelated repairs.

### 2026-08-30 — round 7, and two asks that both turned out to be delimiters

**Neither ask needed anything new, and that is the round.** The weight machinery has been end to end
since round 5 — `loud` to `_emphasise` to `role_style` for Rich, split classes for the canvas — and
the only missing piece was a word an operator could write. The quoted-text ask had been answered in
round 6 without anyone noticing: dimming the delimiters of `()`/`[]`/`{}` so their contents stand out
is exactly what quoted text wanted, and a quote is a delimiter.

**A declared weight joins `loud` rather than becoming a composite role**, for a concrete reason
rather than a tidy one. Writing `"bold sb.warn"` into `ruleset.rules` would hit two things:
`mk-${role}` on the canvas turns it into two class names inside one attribute by accident rather
than by design, and `_emphasise` running afterwards would produce `bold bold sb.warn`. Through
`loud` a declared weight *is* the object a built-in emphasis is — `_merge` already unions it, and a
test asserts the doubling cannot come back.

**The collision item 20 warned about disposes of itself once quotes are delimiters.** The worry was
that a built-in quote rule would steal `handing to '...'` from the operator's ruleset, since
built-ins run first. The delimiter pass claims **single characters** and runs **last** — so their
colour lands on the words and the quotes dim around it. Both asks are answered on one line, and the
test asserts exactly that: with the operator's rule in force there is nothing left for the pass to
dim.

**The guard is measured, not argued.** Against the live 140-line log a naive single-quote rule
produces 15 spans and two are the documented failure — one running from `checkout's` a hundred
characters to `didn't`. The guarded form produces 13 and neither. Double quotes need no guard and
produce 8. The suite carries one line of each; the number that decided the design came from the real
file.

**The rendered proof was better than the assertion.** The legend row draws through the real
`marks()`, and in the DOM the quoted example comes out with `04:15` keeping its own `mk-num`
*inside* the dimmed quotes — the whole design visible in one line. A declared weight renders
`mk-bold mk-warn` on one span, two classes from one rule.

**One thing about the harness.** The legend is collapsed by default and exists only once the
`follow` contract is picked, so two headless passes found nothing before either was a bug. Worth
knowing before the next person concludes the legend is broken.

### 2026-08-31 — round 8, in which an ask turned out to be a defect

**The ask was that `#/#` stand out. It already stood out, as the wrong thing.** `308/693 fixes`,
`12/15 green` and `1/3 of the batch` were all coming out `sb.path` — the literal role a filename and
a code span take — because `_PATH`'s interior-slash alternative matches two digits either side of a
slash and runs before `_NUMBER`. Round 2's rule is that a value looks like its *kind* on both
surfaces, and a count's kind is a number. So this round adds no capability: it moves fourteen tokens
off the wrong colour.

**Which is the round's actual content.** Four of the five things the operator listed were already
answered — paths of the form `xxx/xxx/xxx.xx` since round 2, five-character shouts since round 5,
and *merge* and *PR* are vocabulary, which has been declarable since round 3 and is not this
module's to hold. Only one of the five was a change here, and it was not the one that looked like a
gap. **Reading a rendered log is what tells an absence from a miscolouring**; a list of asks read
from the armchair would have produced a rule for each.

**The lookarounds are the whole rule and they were free.** A `/`, a `.` or a word character on
either side means the digits are a path segment rather than a fraction, so `1/2/3`, `v1/2`,
`docs/12/13` and `2026/08/29/report.md` all stay with `_PATH`. The corpus settles the trade rather
than an argument about it: the 591-line grid log carries fourteen counts and no numeric path at all,
so nothing is given up. A date written `12/13` is claimed as a number, and the ambiguity has only
one answer either way — `_DATE` and `_TIME` already take `sb.num`.

**The floor on short shouts stays at five, and the operator overruled it in their own file rather
than here.** `PR` is 60 of the 134 sub-five capital runs in this log; the other side of that count is
`XP`, `RMS`, `WAV`, `SHA`, `F401`, `E402` — domain nouns and lint codes, roughly 45 of them, which is
the noise round 5 measured and declined. Lowering the floor buys the 60 at the price of the 45 for
*everyone*; a declared rule buys it for the one operator who wants it. That is the round 5 split
doing its job, and it is worth recording that the answer to "sky.boss will not tint my word" is
usually a line in `formats.toml` and not a line here.

**Two things about writing that line that only showed up against the real file.** `\b` is the wrong
boundary for a word people hyphenate: `\bmerg` fires after the hyphen in `non-merge` — which means
the opposite of what it would be painted as — and inside the `--merge` flag, where it paints half a
token and reads as a rendering fault, the same complaint `_NUMBER`'s lookarounds already exist for.
And `auto-merge` is 15 of the 41 real merge events, so the compound is named explicitly and claimed
whole rather than swept out with the other two. **A declared rule can also only take what is left**:
`PR #1200` renders as two `sb.ref` chips because `_REF` claims the number first, and one span across
both is not available at any price. That is the ordering working as designed, but it is a shape the
operator has to see before choosing the role.
