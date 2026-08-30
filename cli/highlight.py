"""Highlight — lexical tint for followed lines. See [[highlight]].

**Recognition for tinting only.** The text stays verbatim, nothing is
filtered, folded or reordered, and a missed match costs a color, not a fact.
That asymmetry is what let this through the boundary [[file-follow]] drew:
a tint that misfires is visibly cosmetic; a column that misfires is invisibly
wrong. Structure claims stay refused — marks tint characters, they never
become columns, fields or a `view`.

**Shape, not vocabulary.** A leading ISO timestamp, a job tag in brackets, a
URL — patterns a regex can name without an opinion. "This line is an error"
is a judgment, and judgments belong to the escalation ladder's Rule branch,
with the operator holding the pen, as a future round here.

**One rule set, applied everywhere a followed line renders.** The terminal
forms tint through `spans()`; the canvas receives each frame line's `marks`
beside its verbatim text and applies them dumbly — offsets into the text, so
the payload the window appends is provably the payload the file carried. The
frontend has no test runner, and two renderers holding their own opinions
would drift the week they were written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# (start, end, role) — offsets into the line, role names from cli/theme.py.
Mark = tuple[int, int, str]

# A leading ISO-8601 stamp, seconds required, fraction and zone optional. The
# least informative and most repeated thing on every line; dimming it is what
# makes everything else legible.
_TIMESTAMP = re.compile(
    r"\A\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)

# A [bracketed-tag]: short, no nesting, no inner whitespace-only. The job's
# name — the boundary the eye actually scans for in a multi-job log.
_TAG = re.compile(r"\[[^\[\]\s][^\[\]]{0,63}\]")

# A URL. Links are destinations; they should look like it.
_URL = re.compile(r"https?://[^\s<>\"]+")

# Punctuation a sentence hangs on a URL's end without meaning it.
_TRAILING = ".,;:!?'\")]}"

# ---------------------------------------------------------------- round 2
#
# The rest of the shapes an agent's log actually contains, each taking the
# role its *kind* already has in a table cell (`cli/output.py`'s `_cell`:
# numbers `sb.num`, path-like strings `sb.path`). One value vocabulary across
# both surfaces — a number that looked like a number in `sb data` and like
# prose in `sb follow` would be two palettes wearing one name. See [[highlight]].

# Inline code. Takes the *path* role rather than a hue of its own: a code span
# and a path are the same kind of thing — a literal, an identifier — and the
# design system has no third colour to spend on the distinction. A violet was
# prototyped, looked good, and is exactly how a second palette starts.
_CODE = re.compile(r"`[^`\n]{1,200}`")

# A path: absolute, or anything with an interior slash, or a dotted filename —
# each with an optional `:line`. The `:line` suffix is why this beats tinting
# the number separately: `report.py:75` is one location, not a file and a 75.
_PATH = re.compile(
    # A dotfile directory keeps its dot: `\b` cannot start a match at `.`, so
    # `.github/scripts/x.sh` used to tint from `github` and leave the dot bare.
    r"(?<![\w./-])(?:\.{1,2}/|\.?[\w@+-][\w.@+-]*/)[\w.@+-]+(?:/[\w.@+-]+)*(?::\d+)?"
    r"|(?:/[\w.@+-]+){2,}(?::\d+)?"
    r"|\b[\w@+-]+\.[a-z]{1,5}(?::\d+)\b"
)

# A date or a clock time *inside* the line. Deliberately the opposite job from
# the leading timestamp above: that one is the most repeated and least
# informative thing on every line, so it is dimmed; a date in the prose is a
# fact someone wrote down, so it reads as the value it is.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

# `#925` — an issue or PR reference, and the single most scanned token in a
# queue-working log.
#
# **Round 6 gives it a ground rather than a hue, because there was no hue to
# give.** It read as a number, which it is, and looked like every other number
# on the line, which the operator asked it not to. The design system has four
# hues and all four are spent, so the ask could not be answered in colour at
# all — see `cli/theme.py` § Ground, not hue. `sb.ref` is the brand on a wash
# of itself: the same colour, a different *object*. It is still the number's
# hue, which keeps round 2's rule intact — a value looks like its kind on both
# surfaces — and adds the one axis the system had left.
_REF = re.compile(r"#\d+")

# A number, with an attached `%` or short unit — `8%`, `90m`, `10.2`, `20000`.
#
# **Attached only, and this is the rule that was got wrong first.** A version
# allowing a space before the unit tinted `8 issue`, `104 archive` and
# `50 candidate` — the numeral plus whatever English word happened to follow
# it. That is invisible in a unit test and unmissable in a rendered log, which
# is why the rules were prototyped against a real one before being written.
# The lookarounds are not decoration. `\b\d` happily matches the `7` inside the
# git SHA `7d9d878` and tints one character of an identifier, which looks like
# a rendering fault rather than a highlight; requiring plain text on both sides
# means a number is tinted only when it is a number.
_NUMBER = re.compile(r"(?<![\w-])\d[\d,_]*(?:\.\d+)?(?:%|[a-zA-Z]{1,3})?(?![\w-])")

# ---------------------------------------------------------------- round 4
#
# **A glyph that means one thing everywhere, and a word that *is* its own
# colour.** Both are still shape rather than judgment, which is the line this
# module has held since round 1 — but the reasoning is worth stating because
# they look like the vocabulary rules that are refused.
#
# A check mark is not sky.boss deciding a line went well; it is sky.boss reading a symbol
# whose meaning is not in dispute, and `sb data` already renders a true
# boolean as a green `✓` and a false one as a red `✗` (`_cell` in
# cli/output.py). One value vocabulary, two surfaces — a check is green in a
# table cell, so it is green in a log line.
#
# `red` is the same claim in its strongest form: the word denotes the colour.
# There is no inference between "the text says red" and "show it red", which
# is exactly what separates this from "the text says ERROR, so it is bad".
#
# **Round 5 widens the set by sharpening the test, not by lengthening a list.**
# Round 4 asked whether a glyph's meaning was *in dispute*, which does not
# decide the cases the operator actually named. The test that does: **a glyph
# qualifies when carrying the verdict is its whole job.** Strip the verdict
# from ✓ 👍 ⚠ 🚨 ⛔ and there is no glyph left. 🎉 🚀 🔥 🤝 🌙 all *correlate*
# with a verdict in agent prose and denote something else — a party, a rocket,
# a fire, a handshake, night — so tinting them reads a convention, which is the
# judgment this module has refused since round 1.
#
# That line was drawn against a real log rather than from the armchair. The
# 251 KB `cron.log` this was raised over carries 🤝 fifteen times, 🌙 ten, 🙋
# three: every one of them means something to *that grid* and nothing anywhere
# else. They are the operator's vocabulary, and round 3 already ships the way to
# say so — **a declared pattern may be a glyph.** See [[highlight]] round 5.
_OK_GLYPH = re.compile(r"[\u2713\u2714\u2705\u2611]\uFE0F?|\U0001F44D")
_FAIL_GLYPH = re.compile(
    r"[\u2716\u2717\u2718\u274C\u274E\u2612]\uFE0F?|\U0001F534|\U0001F44E"
)
_WARN_GLYPH = re.compile(
    r"[\u26A0\u26D4\u2757\u2755\u203C]\uFE0F?|\U0001F7E1|\U0001F6A8|\U0001F6D1"
)
_OK_EMOJI = re.compile(r"\U0001F7E2|\U0001F7E9")
_INFO_GLYPH = re.compile(r"\U0001F535|\U0001F7E6|\u2139\uFE0F?")

# ---------------------------------------------------------------- round 5
#
# **Two shapes wearing one costume, and the corpus is what told them apart.**
# "ALL CAPS should be emphasised" reads as one rule and measured as two. Of the
# 150 all-caps runs of five characters or more in that same log, the clear
# majority are configuration identifiers — `JAM_KUMA_FORCE_PING` twenty-two
# times, `MAX_PER_RUN`, `ALLOWED_HOSTS`, `GEOIP_ASN_DB_PATH` — and the rest are
# genuine shouts: `ERROR`, `FAILED`, `REFUSED`, `SKIPPED`, `PREFLIGHT`.
#
# So an underscore decides it. A SCREAMING_SNAKE name is a **literal**, which
# round 2 already ruled takes the path role — the same role a code span and a
# filename take, for the same reason. A bare capitalised word is a **shout**,
# and a shout is a weight rather than a colour; it is handled in `_emphasise`
# below, not here.
_SCREAMING = re.compile(r"(?<![\w-])[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+(?![\w-])")

# **Five characters, and the number is measured rather than chosen.** Below it
# the corpus is acronyms in ordinary prose: `PR` 122 times, `CI` 52, plus `I`
# and `A` — 349 occurrences of pure noise at one to three characters, against
# roughly 40 real shouts at five and up. Four is the interesting boundary and
# it loses: it would buy `TODO` (12) at the price of `HEAD` (23) and `HTTP`
# (10). `TODO` going untinted is the known cost of this line.
_SHOUT = re.compile(r"(?<![\w-])[A-Z][A-Z0-9]{4,}(?![\w-])")

# ---------------------------------------------------------------- round 6
#
# **A bracket is structure, so the delimiters dim and the contents are left
# alone.** The operator asked for `()`, `{}` and `[]` to stand out in a colour
# of their own, and there is no colour of their own to give. The answer that
# needs none is the leading timestamp's, turned on punctuation: `--text-3` is
# defined by the design system as *"structure, not reading text"*, which is
# exactly what a delimiter is. Dimming the two characters makes what they wrap
# stand out by taking noise away rather than adding it.
#
# Three separate alternatives rather than one character class, so `(foo]` is
# not a pair. No nesting and no newline; bounded, like every rule here.
# **The brace matters most and is the reason this is worth having**: an agent
# log carries JSON, so `{…}` is where the eye loses the line.
# A pair of delimiters on one line, whose *marks* dim so the contents stand
# out. Quotes joined the brackets in round 7: the ask was that quoted text be
# differentiated, the palette has no hue left to differentiate it with, and
# round 6 had already answered this exact shape for `()`/`[]`/`{}`.
#
# **The single-quote form is guarded and the guard is the whole rule.** A naive
# `'…'` starts at the apostrophe in `don't` and runs to the next one: measured
# against the live 140-line log it produced 15 spans, two of them that failure,
# one running 100+ characters from `checkout's` to `didn't`. Requiring a
# non-word character before the opening quote and after the closing one leaves
# 13 and neither. Double quotes carry no such hazard and need no guard.
_WRAPPED = re.compile(
    r"\([^()\n]{1,200}\)"
    r"|\[[^\[\]\n]{1,200}\]"
    r"|\{[^{}\n]{1,200}\}"
    r"|\"[^\"\n]{1,200}\""
    r"|(?<![\w'])'[^'\n]{1,200}'(?!\w)"
)

# A word that names a colour, in that colour. Standalone only — `\b` on both
# sides, so `reported` is not `red`.
_COLOUR_WORDS = {
    "red": "sb.fail",
    "green": "sb.ok",
    "yellow": "sb.warn",
    "amber": "sb.warn",
    "orange": "sb.warn",
    "blue": "sb.accent",
    "grey": "sb.muted",
    "gray": "sb.muted",
}
_COLOUR_WORD = re.compile(
    r"\b(?:" + "|".join(sorted(_COLOUR_WORDS)) + r")\b", re.IGNORECASE
)

# Markdown emphasis, which the agent prose in these logs leans on for its
# findings. **Bold is a weight, not a colour**, so it composes with whatever
# colour a mark already carries instead of competing for the same slot — the
# role becomes `bold sb.path`, which Rich reads directly and the canvas splits
# into two classes. The `**` markers stay on screen: marks tint characters and
# never alter them, and a renderer that hid them would be editing the log.
_BOLD = re.compile(r"\*\*(?=\S)[^\n]{1,300}?\*\*")
_HEADING = re.compile(r"\A#{1,6} +\S")

# What one line may carry. Every mark rides to the canvas inside the frame, and
# round 2 turned three rules into ten — a dense numeric line can now produce
# dozens where it used to produce three. The tail is dropped rather than the
# line, the same rule every surface here has had since the first unbounded
# render froze one.
MAX_MARKS = 64

# In priority order after the timestamp and tag, which are positional. First
# match wins and nothing nests, so a number inside a code span or a `:75`
# inside a path is claimed once, by the outer shape.
#
# The fourth field is round 5's: **this match is also an emphasis range.** A
# glyph is one character wide, and hue at one character is the weakest signal
# this palette has — weight is the strongest, and it costs no role, because
# round 4 already established that bold composes rather than competing. So a
# glyph keeps the colour its kind already has *and* reads at a glance.
_RULES: tuple[tuple[re.Pattern, str, bool, bool], ...] = (
    (_CODE, "sb.path", False, False),
    (_URL, "sb.path", True, False),
    (_OK_GLYPH, "sb.ok", False, True),
    (_OK_EMOJI, "sb.ok", False, True),
    (_FAIL_GLYPH, "sb.fail", False, True),
    (_WARN_GLYPH, "sb.warn", False, True),
    (_INFO_GLYPH, "sb.accent", False, True),
    (_PATH, "sb.path", True, False),
    (_SCREAMING, "sb.path", False, False),
    (_DATE, "sb.num", False, False),
    (_TIME, "sb.num", False, False),
    (_REF, "sb.ref", False, False),
    (_NUMBER, "sb.num", True, False),
)


# ============================================================================
# The legend — what the built-in rules are, shown rather than described
# ============================================================================
#
# **The declared half is the small half, and it was the only half any surface
# showed.** A bench offering `--highlight` and nothing else says, by omission,
# that a ruleset is where tint comes from; thirteen rules here do most of it
# and none of them was visible anywhere. See [[highlight]] round 5.
#
# **These are examples, not descriptions, and that is the whole design.** Each
# one is rendered by running `marks()` over it — the same function the stream
# uses, no second opinion — so the legend cannot drift from the rules it
# documents. A rule that stops matching stops being tinted in its own legend
# entry, which is a louder failure than a stale sentence and needs no test to
# notice it. What a test *does* guard is coverage: every pattern in `_RULES`
# has an entry here.
BUILTINS: tuple[tuple[str, str], ...] = (
    ("a leading timestamp, dimmed", "2026-08-29 04:15:02 grid woke"),
    ("the job tag after it", "2026-08-29 04:15:02 [agent-fix] starting"),
    ("inline code and a path", "`jam report` wrote docs/plan.md:75"),
    ("a SCREAMING_SNAKE name", "MAX_PER_RUN was already set"),
    ("a URL", "opened https://example.com/pull/1050"),
    ("an issue or PR reference", "closed #1050 after review"),
    ("a number, with its unit attached", "8% of 20000 in 90m"),
    ("a date or a clock inside the line", "due 2026-09-01 at 04:15"),
    ("a verdict glyph, coloured and weighted", "✓ done ✗ failed ⚠ late 👍 ok"),
    ("a status light", "🟢 up  🔴 down  🟡 slow  ℹ️ note"),
    ("a word that names a colour", "the light was red, then green"),
    ("markdown emphasis, as weight", "**the reason it recurs** nightly"),
    ("a shout — five capitals or more", "ERROR the grid is unreachable"),
    ("delimiters dim, so contents stand out", "ran 'repo-report' on (node-01) at \"04:15\""),
)


def hang(text: str) -> int:
    """Where a wrapped continuation of this line should start. See [[wrap]].

    **The same matcher that dims the stamp, exposed rather than repeated.** A
    wrapped log line beginning at column zero looks like a new record, so the
    continuation is indented to the first character *after* the timestamp — and
    that offset is one this module already computes, as a side effect of
    deciding where the tag rule may start. Measuring the stamp again in the
    frontend, or here, would be the second timestamp matcher the one-rule-set
    design exists to prevent.

    Zero when the line has no leading stamp, and a flush wrap is what zero
    means — not a special case, the same rule with nothing to skip. Note that
    the leading-space skip runs *only* behind a stamp: a line indented for its
    own reasons is not silently given a hanging indent it never asked for.

    Characters, not UTF-16 code units, and no conversion is owed: the stamp is
    ASCII by construction, so the two counts cannot differ, and the consumer
    is a CSS `ch` — a column count — rather than `String.slice`.
    """
    stamp = _TIMESTAMP.match(text)
    if not stamp:
        return 0
    at = stamp.end()
    while at < len(text) and text[at] == " ":
        at += 1
    return at


def marks(text: str, ruleset: "Ruleset | None" = None) -> list[Mark]:
    """The line's lexical marks: sorted, non-overlapping, first match wins.

    Pure, and bounded: every rule is a linear scan and the result is capped at
    `MAX_MARKS`. The text is never altered — a caller holding the marks and
    the line holds everything.

    A `ruleset` is the operator's declared vocabulary ([[highlight]] round 3).
    **It runs last and claims only text no built-in rule claimed**, so a
    timestamp stays muted and a tag stays a tag whatever the operator writes.
    Letting a declaration win would make every built-in rule conditional on a
    file sky.boss does not ship, and the first surprising log would be
    unexplainable.
    """
    found: list[Mark] = []

    stamp = _TIMESTAMP.match(text)
    if stamp:
        found.append((0, stamp.end(), "sb.muted"))

    # The tag rule is positional: immediately after the timestamp (spaces
    # allowed) or at line start — a bracket mid-prose is prose.
    at = stamp.end() if stamp else 0
    while at < len(text) and text[at] == " ":
        at += 1
    tag = _TAG.match(text, at)
    if tag:
        found.append((tag.start(), tag.end(), "sb.accent"))

    # Ranges this line's matches ask to be *emphasised* as well as coloured.
    # Collected here rather than re-derived in `_emphasise`, so the weight
    # lands on exactly the span the colour did — one match, one decision.
    loud: list[tuple[int, int]] = []

    for pattern, role, trim, emphasise in _RULES:
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            if trim:
                # Punctuation a sentence hangs on the end without meaning it.
                while end > start and text[end - 1] in _TRAILING:
                    end -= 1
            if end <= start:
                continue
            if any(start < e and s < end for s, e, _ in found):
                continue  # first match wins, no nesting
            found.append((start, end, role))
            if emphasise:
                loud.append((start, end))

    # A colour word takes the colour it names. Its role comes from the word
    # itself rather than from the rule, which is why it cannot ride `_RULES`.
    for match in _COLOUR_WORD.finditer(text):
        start, end = match.start(), match.end()
        if any(start < e and s < end for s, e, _ in found):
            continue
        found.append((start, end, _COLOUR_WORDS[match.group(0).lower()]))

    if ruleset is not None:
        for pattern, role, emphasise in ruleset.rules:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                if end <= start:
                    continue  # a zero-width pattern marks nothing
                if any(start < e and s < end for s, e, _ in found):
                    continue
                found.append((start, end, role))
                # **A declared weight is the same object a built-in one is.**
                # It joins `loud` rather than becoming a `"bold sb.warn"` role
                # string, so `_merge` handles its overlap, `_emphasise` folds it
                # once, and nothing downstream learns a second shape. See
                # [[highlight]] round 7.
                if emphasise:
                    loud.append((start, end))
                if len(found) >= MAX_MARKS:
                    break

    # Delimiters last, after the operator's rules — a dimmed bracket is the
    # least important mark on any line, so it takes only what nothing else
    # wanted. That ordering is what keeps a leading `[tag]` whole: the
    # positional rule claimed it long before this ran.
    for match in _WRAPPED.finditer(text):
        for at in (match.start(), match.end() - 1):
            if any(at < e and s <= at for s, e, _ in found):
                continue
            found.append((at, at + 1, "sb.muted"))

    return _emphasise(text, sorted(found), loud)[:MAX_MARKS]


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Overlapping emphasis ranges, unioned into disjoint ones.

    Round 4 had exactly one source of range and could skip this. Round 5 has
    four — markdown, a heading, a shout, a glyph — and they overlap in the most
    ordinary line there is: `**ERROR**` is a shout inside an emphasis. The
    filler below walks a range assuming nothing else covers it, so overlapping
    input made it emit two marks for one stretch, which the frontend applies
    dumbly and by construction cannot notice.
    """
    out: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def _emphasise(
    text: str, coloured: list[Mark], loud: list[tuple[int, int]] = []
) -> list[Mark]:
    """Fold emphasis into the colour marks as a *weight*.

    Bold is the one attribute here that is not a colour, so it does not
    compete for the slot: a mark inside an emphasised range keeps its role and
    gains `bold`, and the stretches with no colour of their own become bold on
    their own. Rich reads `"bold sb.path"` directly; the canvas splits it into
    two classes. Nothing overlaps and the list stays flat, which is what lets
    the frontend keep applying marks dumbly.

    **Round 5 makes this the round's whole argument rather than a detail.** The
    operator asked for six things emphasised and the palette has no ninth
    colour to give any of them, so emphasis is spent instead of hue. That works
    only because this pass *composes*, and the case that proves it is the
    shout: a colour rule claiming `ERROR` would block the operator's own
    `error → fail` from ever reaching it, since a declared rule takes only
    unclaimed text. As a range it does the opposite — their colour lands first
    and the shout adds weight to it.

    `loud` is the ranges the colour rules themselves asked for (the glyphs).
    A shout and a heading are found here because neither carries a colour of
    its own; a glyph's range comes in because it does.
    """
    ranges = [(m.start(), m.end()) for m in _BOLD.finditer(text)]
    ranges += [(m.start(), m.end()) for m in _SHOUT.finditer(text)]
    ranges += loud
    if _HEADING.match(text):
        ranges.append((0, len(text)))
    if not ranges:
        return coloured

    ranges = _merge(ranges)
    out: list[Mark] = []
    for start, end, role in coloured:
        inside = any(s <= start and end <= e for s, e in ranges)
        out.append((start, end, f"bold {role}" if inside else role))

    # The stretches an emphasised range covers that no colour mark claimed.
    # Read off `coloured` rather than off `out`, which the loop is appending
    # to: the ranges are disjoint now, so no fill can be inside another one.
    base = sorted(out)
    for start, end in ranges:
        cursor = start
        for s, e, _ in base:
            if e <= cursor or s >= end:
                continue
            if s > cursor:
                out.append((cursor, s, "bold"))
            cursor = max(cursor, e)
        if cursor < end:
            out.append((cursor, end, "bold"))

    return sorted(out)


def utf16(text: str, found: list[Mark]) -> list[Mark]:
    """The same marks, with offsets a browser can slice by.

    **Python counts code points and JavaScript counts UTF-16 code units, and
    every mark shipped to the canvas crosses that boundary.** An astral
    character — 🔴, 🟢, 👍, every emoji above U+FFFF — is one Python character
    and *two* JS ones, so `text.slice(start, end)` cut a surrogate pair in half
    and shifted every offset after it on the line. The page rendered a lone
    high surrogate and then tinted the wrong words for the rest of the line.

    Shipped in round 4 and invisible for a week, because both sides were
    self-consistent: the terminal applies these offsets to the same Python
    string that produced them and is correct, the suite compares marks to
    marks and never slices, and the live log's most common glyph (`✅`, U+2705)
    is inside the BMP and behaves. It took drawing the legend in a real browser
    to see a status light come out as half of itself. See [[highlight]] round 5.

    Converted here, at the wire, rather than by teaching the page to index by
    code point: the offsets exist to be applied by `String.prototype.slice`, so
    they should be in that function's units by the time it sees them. The
    terminal path keeps using `marks()` and is untouched.
    """
    if not found:
        return found
    # Cumulative extra code units before each code point. Only computed when
    # the line actually holds an astral character, which is the rare case.
    wide = [i for i, ch in enumerate(text) if ord(ch) > 0xFFFF]
    if not wide:
        return found
    def shift(at: int) -> int:
        return at + sum(1 for i in wide if i < at)

    return [(shift(s), shift(e), role) for s, e, role in found]


def spans(text: str, ruleset: "Ruleset | None" = None) -> list[tuple[str, str | None]]:
    """The line as (chunk, role) spans — the same shape the chrome bands use,
    so both terminal forms tint through the same assembler and untinted text
    rides through with role None."""
    out: list[tuple[str, str | None]] = []
    cursor = 0
    for start, end, role in marks(text, ruleset):
        if start > cursor:
            out.append((text[cursor:start], None))
        out.append((text[start:end], role))
        cursor = end
    if cursor < len(text) or not out:
        out.append((text[cursor:], None))
    return out


# ============================================================================
# Declared rules — the operator's own words. See [[highlight]] round 3.
# ============================================================================
#
# **Shape is sky.boss's; vocabulary is the operator's.** `ESCALATE`, `Done.`,
# `handing to 'claude'` — the words that matter in one operator's log and mean
# nothing in anyone else's. sky.boss cannot know them and must not guess, for exactly
# the reason it does not guess columns ([[capture]]): a word list is a judgment
# wearing a regex's clothes. So it is declared, in the file that already holds
# declarations about output, and named on the command that follows the stream.

# Longer than this is not a pattern, it is a program. The cap is a guard
# against a pasted mistake, not against an adversary — this is the operator's
# own file on their own machine, at `tools.toml`'s trust level.
MAX_PATTERN = 200

# What a declared rule may ask for: the palette's role names, minus the `sb.`
# prefix the operator should not have to type. A role the theme does not
# define is refused by name — nothing operator-authored gets near a colour.
def _roles() -> dict[str, str]:
    from cli.theme import STYLES

    return {name.removeprefix("sb."): name for name in STYLES}


@dataclass(frozen=True)
class Ruleset:
    """One named set of operator patterns, already compiled and validated."""

    name: str
    description: str = ""
    rules: tuple[tuple[re.Pattern, str], ...] = ()


def parse_rulesets(raw: dict) -> tuple[list[Ruleset], list[str]]:
    """Validate `[highlight.<name>]` declarations. Pure — reads no file.

    One bad ruleset must not cost the operator the other nine, and one bad
    *rule* must not cost the ruleset: both are skipped and named, the way a
    malformed format and a malformed tool already are.
    """
    if "__error__" in raw:
        return [], [raw["__error__"]]

    roles = _roles()
    found: list[Ruleset] = []
    problems: list[str] = []

    for name, body in (raw.get("highlight") or {}).items():
        if not isinstance(body, dict):
            problems.append(f"highlight {name!r}: not a table")
            continue
        declared = body.get("rules")
        if not isinstance(declared, list) or not declared:
            problems.append(f"highlight {name!r}: rules must be a non-empty list")
            continue

        compiled: list[tuple[re.Pattern, str]] = []
        for index, rule in enumerate(declared):
            problem = _check_rule(rule, roles)
            if problem:
                problems.append(f"highlight {name!r} rule {index + 1}: {problem}")
                continue
            compiled.append(
                (
                    re.compile(rule["pattern"]),
                    roles[rule["role"]],
                    rule.get("weight", "") == "bold",
                )
            )

        if compiled:
            found.append(
                Ruleset(
                    name=name,
                    description=str(body.get("description", "")),
                    rules=tuple(compiled),
                )
            )

    return found, problems


def _check_rule(rule, roles: dict[str, str]) -> str | None:
    """The reason this rule is unusable, or None."""
    if not isinstance(rule, dict):
        return "not a table"
    pattern = rule.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return "pattern must be a non-empty string"
    if len(pattern) > MAX_PATTERN:
        return f"pattern is longer than {MAX_PATTERN} characters"
    role = rule.get("role")
    if role not in roles:
        # Names the alternatives rather than just refusing: the mistake this
        # catches is someone writing a colour, and the fix is to say which
        # words the palette answers to.
        return f"role must be one of {', '.join(sorted(roles))} — not {role!r}"
    weight = rule.get("weight", "")
    if weight not in ("", "bold"):
        # One value, because `bold` is the only weight the palette has. A
        # second is a design-system decision exactly as a ninth hue is, and
        # this is not the place it gets made. See [[highlight]] round 7.
        return f"weight must be 'bold' if given — not {weight!r}"
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"pattern does not compile: {exc}"
    return None


def load_rulesets(home: Path | None = None) -> tuple[list[Ruleset], list[str]]:
    """Every declared ruleset, and every reason one was skipped.

    Read at use rather than cached, like the formats beside them: editing the
    file under a pinned window is the REPL.
    """
    from cli import capture as capture_

    return parse_rulesets(capture_.read(home))


def resolve(name: str, home: Path | None = None) -> tuple[Ruleset | None, str | None]:
    """`--highlight <name>` down to a ruleset, or the reason it is not one."""
    found, problems = load_rulesets(home)
    for ruleset in found:
        if ruleset.name == name:
            return ruleset, None
    mine = [p for p in problems if p.startswith(f"highlight {name!r}")]
    if mine:
        return None, mine[0]
    known = ", ".join(sorted(r.name for r in found)) or "none declared"
    return None, f"no highlight named {name!r} — declared: {known}"
