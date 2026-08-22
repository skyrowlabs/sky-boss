"""Capture — named formats: parse, transform, present. See [[capture]].

**tb never guesses; the operator asserts.** A format is a named, operator-
authored declaration in `$TB_HOME/formats.toml`, and the command line only
says the name: `tb data --from jam-status -- sometool status`. The inference
version of this feature — columns guessed from whitespace — is the "silently
wrong" failure CLAUDE.md rejects by name, and it is not here.

**Two levels: kinds are code, formats are declarations.** A kind is a parsing
contract tb ships and tests (`json`, `lines`); a format parameterizes one and
may add a `jq` program as the pipeline's middle stage:

    bytes ──(kind: parse)──▶ data ──(jq: transform)──▶ data′ ──(view)──▶ display

Presentation is already shape-driven, so the transform needs no formatting
vocabulary: jq's job is to produce the shape, tb's job is to render the shape.

**The deciding half is pure.** `capture()` is a function over text — no
subprocess, no file I/O — which is what makes the interesting rules testable:
a matched line is a row, a number-shaped value becomes a number, an unmatched
line is counted and sampled but never silently dropped, and nothing matching
at all is a verdict the caller must wear, not an empty table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FORMATS_FILE = "formats.toml"

# The kinds tb ships. A later kind — csv, an aligned table, multi-line
# records — arrives here one at a time when something real needs it.
KINDS = ("json", "lines")


@dataclass(frozen=True)
class Format:
    """One parsing contract, named. Builtin kinds are the parameterless case."""

    name: str
    kind: str
    pattern: str = ""
    description: str = ""
    jq: str = ""


@dataclass(frozen=True)
class Captured:
    """What the lines kind saw: rows, and an honest account of the rest."""

    rows: list
    total: int  # non-blank lines seen
    unmatched: int
    sample: str | None  # the first unmatched line, for the warning

    @property
    def matched_nothing(self) -> bool:
        """Lines arrived and none matched — a failed contract, not an empty
        table. An empty table would read as "the tool reports nothing", the
        exact lie this command exists to never tell. Zero lines in is the
        other case: the tool genuinely printed nothing, and that is not a
        capture miss."""
        return self.total > 0 and not self.rows


def capture(text: str, fmt: Format) -> Captured:
    """Text through a lines format. Pure — the whole deciding half.

    `re.search` semantics, so a pattern need not anchor the whole line to be
    useful. A matched line is a row; its named groups are the fields, in group
    order. Blank lines are ignored; every other unmatched line is counted.
    """
    regex = re.compile(fmt.pattern)
    rows: list[dict] = []
    total = unmatched = 0
    sample: str | None = None

    for line in text.splitlines():
        if not line.strip():
            continue
        total += 1
        match = regex.search(line)
        if match is None:
            unmatched += 1
            if sample is None:
                sample = line
            continue
        rows.append({key: _shape(value) for key, value in match.groupdict().items()})

    return Captured(rows, total, unmatched, sample)


# Shape, not judgment: digits with an optional sign and an optional decimal
# point. It is what makes a numeric column right-align and a `*_bytes` group
# humanize through the existing conventions for free. Dates, durations and
# enums stay the strings the tool printed.
_INT = re.compile(r"\A[+-]?\d+\Z")
_FLOAT = re.compile(r"\A[+-]?\d+\.\d+\Z")


def _shape(value: str | None):
    """A value shaped like a number becomes one; everything else is returned
    exactly as the tool printed it. An optional group that did not participate
    stays None, which renders as the empty cell it is."""
    if value is None:
        return None
    if _INT.match(value):
        return int(value)
    if _FLOAT.match(value):
        return float(value)
    return value


def unmatched_warning(captured: Captured, name: str) -> str | None:
    """The visible account of a capture that missed — which is the whole
    difference between a declared parser and a guessed one."""
    if not captured.unmatched or captured.matched_nothing:
        return None
    return (
        f"{captured.unmatched} of {captured.total} lines did not match "
        f"{name} — first: {captured.sample!r}"
    )
