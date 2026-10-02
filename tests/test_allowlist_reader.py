"""A reason is not optional, and a blank one is the spelling that got past it.

`scripts/allowlist.py` states the rule in its own module docstring — *"An entry
with no reason is dropped rather than honoured"* — and for a while the parser
implemented three quarters of it. `_ENTRY` requires a colon *followed by
whitespace*, so `key:` alone never matched and the bare-key case really was
dropped. `key: ""` matched, survived `.strip("\"'")` as the empty string, and
was stored: an exemption honoured on the strength of a reason nobody wrote.

**The rule was stated, tested by nothing, and the case that broke it was the
one a person actually types.** Somebody silencing a check reaches for the
quotes precisely because a bare key looks unfinished — so the spelling that
looks most like a filled-in field is the one that was empty.

## Why this is a unit test and not a gate in the verifier

`bin/skeletor-verify`'s `allowlist_gate` already plants a *meaningless* entry
in every discovered `*_allowlist.yaml` and requires the tree's own gates to go
red. That is the staleness question — does an entry still exempt something real
— and it is a different question from whether the reader honours an entry with
nothing behind it. The gate plants a key that matches nothing; this plants a
key that matches everything and says nothing.

## The both-directions rule, applied to the reader itself

A test that only asserts *blank reasons are dropped* is green under a reader
that drops everything, which is the failure mode with the worse blast radius:
every allowlist in the tree silently stops exempting, and the checks they feed
go red on entries somebody did write. So the real reason has to survive, and it
has to survive **unchanged** — a reader that quietly trimmed content out of a
decision record would be its own defect.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import allowlist  # noqa: E402

pytestmark = [pytest.mark.unit]

#: Every spelling of "no reason given". The quoted forms are the ones that were
#: honoured; the bare forms already worked, and are kept so a future rewrite of
#: `_ENTRY` cannot regress them in silence while the interesting cases pass.
BLANK = [
    "somekey",
    "somekey:",
    'somekey: ""',
    "somekey: ''",
    "somekey: '   '",
    'somekey: "  "',
]

#: A reason with quoting and punctuation *inside* it, because the fix strips
#: quotes before testing for emptiness and a careless strip eats real content.
#: Composed rather than written twice — the line and the reason it should parse
#: to are the same string, and spelling it in both places is a second home for
#: the value under test that can drift into agreeing with a broken reader.
REAL_KEY = "somekey"
REAL_REASON = 'pyright\'s "standard" mode disagrees with CI — see #412'
REAL = f"{REAL_KEY}: {REAL_REASON}"


def _read(tmp_path: Path, line: str) -> dict:
    path = tmp_path / "some_allowlist.yaml"
    path.write_text(line + "\n", encoding="utf-8")
    return allowlist.read(path)


def test_an_entry_with_no_reason_is_dropped(tmp_path):
    """Every spelling of a blank reason, including the quoted ones."""
    for line in BLANK:
        assert _read(tmp_path, line) == {}, (
            f"{line!r} was honoured as an exemption. A blank reason is not a shorter reason — "
            "it is an entry nobody can re-evaluate, which is what scripts/allowlist.py exists to refuse."
        )


def test_a_real_reason_survives_intact(tmp_path):
    """The other direction: a reader that drops everything passes the test above.

    Asserted on the *text*, not on the key alone. Stripping quotes off the ends
    is what makes the blank case detectable, and the same strip applied without
    care would truncate a reason that legitimately opens or closes with one.
    """
    entries = _read(tmp_path, REAL)
    assert entries == {REAL_KEY: REAL_REASON}, f"a real reason did not survive the read: {entries!r}"


def test_a_blank_entry_does_not_take_a_real_one_with_it(tmp_path):
    """One bad line drops itself and nothing else.

    A reader that bailed on the file, or that let the blank key overwrite a
    populated one, would turn a typo in an unrelated entry into a silent
    un-exempting of everything below it.
    """
    path = tmp_path / "some_allowlist.yaml"
    path.write_text('blank: ""\nreal: because the upstream tool is broken\n', encoding="utf-8")
    assert allowlist.read(path) == {"real": "because the upstream tool is broken"}
