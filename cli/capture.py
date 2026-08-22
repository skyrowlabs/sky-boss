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

import json
import re
import subprocess
from dataclasses import dataclass

from cli.helpers import child_env

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


# ============================================================================
# The transform stage
# ============================================================================


def transform(data, program: str, name: str, timeout: int | None = None):
    """Parsed data through the operator's own `jq` binary. Returns
    `(data, None)` or `(None, reason)`.

    The binary rather than a Python binding: tb does not reimplement a JSON
    language, and a wheel is a gamble on 3.14 that buys nothing over the jq
    already on the machine. It runs through `child_env()` like everything tb
    spawns — the operator's environment, not tb's. See [[subprocess-env]].

    Absent jq degrades loudly *at use*, naming the format that wanted it;
    formats without a `jq` field never reach this function. A failing program
    is a failed contract carrying jq's own stderr — the same honesty rule as
    everything else here.
    """
    try:
        proc = subprocess.run(
            ["jq", program],
            input=json.dumps(data),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=child_env(),
        )
    except FileNotFoundError:
        return None, f"jq is not on PATH — format {name!r} declares a jq transform"
    except subprocess.TimeoutExpired:
        return None, f"jq timed out after {timeout}s running format {name!r}"

    if proc.returncode != 0:
        reason = _first_line(proc.stderr) or f"jq exited {proc.returncode}"
        return None, f"format {name!r}: {reason}"

    return _values(proc.stdout, name)


def _values(stdout: str, name: str):
    """jq's output as data. One value is the data; a stream of values — the
    `.[]` idiom — becomes a list, because that is what the operator's program
    plainly meant. No output at all (`empty`) is null, honestly."""
    decoder = json.JSONDecoder()
    text = stdout.strip()
    values = []
    index = 0
    while index < len(text):
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            # jq emits JSON on success; anything else here is a contract
            # violation worth naming rather than carrying.
            return None, f"format {name!r}: jq printed something that is not JSON"
        values.append(value)
        index = end
        while index < len(text) and text[index] in " \t\r\n":
            index += 1

    if not values:
        return None, None
    if len(values) == 1:
        return values[0], None
    return values, None


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def unmatched_warning(captured: Captured, name: str) -> str | None:
    """The visible account of a capture that missed — which is the whole
    difference between a declared parser and a guessed one."""
    if not captured.unmatched or captured.matched_nothing:
        return None
    return (
        f"{captured.unmatched} of {captured.total} lines did not match "
        f"{name} — first: {captured.sample!r}"
    )
