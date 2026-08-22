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
# numbers `tb.num`, path-like strings `tb.path`). One value vocabulary across
# both surfaces — a number that looked like a number in `tb data` and like
# prose in `tb follow` would be two palettes wearing one name. See [[highlight]].

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
# queue-working log. It is a number; it gets the number's role.
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

# Markdown emphasis, which the agent prose in these logs leans on for its
# findings. **Bold is a weight, not a colour**, so it composes with whatever
# colour a mark already carries instead of competing for the same slot — the
# role becomes `bold tb.path`, which Rich reads directly and the canvas splits
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
_RULES: tuple[tuple[re.Pattern, str, bool], ...] = (
    (_CODE, "tb.path", False),
    (_URL, "tb.path", True),
    (_PATH, "tb.path", True),
    (_DATE, "tb.num", False),
    (_TIME, "tb.num", False),
    (_REF, "tb.num", False),
    (_NUMBER, "tb.num", True),
)


def marks(text: str) -> list[Mark]:
    """The line's lexical marks: sorted, non-overlapping, first match wins.

    Pure, and bounded: every rule is a linear scan and the result is capped at
    `MAX_MARKS`. The text is never altered — a caller holding the marks and
    the line holds everything.
    """
    found: list[Mark] = []

    stamp = _TIMESTAMP.match(text)
    if stamp:
        found.append((0, stamp.end(), "tb.muted"))

    # The tag rule is positional: immediately after the timestamp (spaces
    # allowed) or at line start — a bracket mid-prose is prose.
    at = stamp.end() if stamp else 0
    while at < len(text) and text[at] == " ":
        at += 1
    tag = _TAG.match(text, at)
    if tag:
        found.append((tag.start(), tag.end(), "tb.accent"))

    for pattern, role, trim in _RULES:
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

    return _emphasise(text, sorted(found))[:MAX_MARKS]


def _emphasise(text: str, coloured: list[Mark]) -> list[Mark]:
    """Fold markdown emphasis into the colour marks as a *weight*.

    Bold is the one attribute here that is not a colour, so it does not
    compete for the slot: a mark inside an emphasised range keeps its role and
    gains `bold`, and the stretches with no colour of their own become bold on
    their own. Rich reads `"bold tb.path"` directly; the canvas splits it into
    two classes. Nothing overlaps and the list stays flat, which is what lets
    the frontend keep applying marks dumbly.
    """
    ranges = [(m.start(), m.end()) for m in _BOLD.finditer(text)]
    if _HEADING.match(text):
        ranges.append((0, len(text)))
    if not ranges:
        return coloured

    out: list[Mark] = []
    for start, end, role in coloured:
        inside = any(s <= start and end <= e for s, e in ranges)
        out.append((start, end, f"bold {role}" if inside else role))

    # The stretches an emphasised range covers that no colour mark claimed.
    for start, end in ranges:
        cursor = start
        for s, e, _ in sorted(out):
            if e <= cursor or s >= end:
                continue
            if s > cursor:
                out.append((cursor, s, "bold"))
            cursor = max(cursor, e)
        if cursor < end:
            out.append((cursor, end, "bold"))

    return sorted(out)


def spans(text: str) -> list[tuple[str, str | None]]:
    """The line as (chunk, role) spans — the same shape the chrome bands use,
    so both terminal forms tint through the same assembler and untinted text
    rides through with role None."""
    out: list[tuple[str, str | None]] = []
    cursor = 0
    for start, end, role in marks(text):
        if start > cursor:
            out.append((text[cursor:start], None))
        out.append((text[start:end], role))
        cursor = end
    if cursor < len(text) or not out:
        out.append((text[cursor:], None))
    return out
