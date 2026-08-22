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


def marks(text: str) -> list[Mark]:
    """The line's lexical marks: sorted, non-overlapping, first match wins.

    Pure, and bounded: every rule is a linear scan. The text is never
    altered — a caller holding the marks and the line holds everything.
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

    for url in _URL.finditer(text):
        start, end = url.start(), url.end()
        while end > start and text[end - 1] in _TRAILING:
            end -= 1
        if any(start < e and s < end for s, e, _ in found):
            continue  # first match wins, no nesting
        found.append((start, end, "tb.path"))

    return sorted(found)


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
