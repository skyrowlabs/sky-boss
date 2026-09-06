#!/usr/bin/env python3
"""One vocabulary for status lines, and one rule about which stream carries them.

There are two channels here, and conflating them is the bug this module exists
to prevent:

* **stdout is what a caller consumes** — a `--json` payload, a generated crontab
  block, a listing somebody pipes into `grep`.
* **stderr is what only a human reads** — progress, gate results, warnings,
  errors, and the "here is what to do next" lines underneath them.

Both land on the terminal, so nothing looks different when you run a command by
hand. The difference appears the moment somebody pipes one. Before this split,
`python scripts/check_doc_tables.py --json | jq` failed: the same stdout carried
the JSON *and* the ❌ lines explaining it. Four scripts had grown a `--json`
flag, three of them emitted output no parser could read, and the two ratchets
whose numbers a dashboard would actually want had no flag at all.

Routing the human half to stderr fixes that **structurally** rather than by
remembering to return early. `--json` becomes purely additive: one result
object, one payload, one narration, and no second code path to drift from the
first — which is the same rule the docs indexes and the job registry follow.

The symbols live here for the same reason. `⏸️` meant "executed and declined" in
three files and was defined in none of them; `helpers.ok()` existed and roughly
twenty call sites retyped `print(f"✅ ...")` instead. A vocabulary that lives in
one dict can be read and changed. One that is retyped per call site cannot.

Stdlib only, and importable from both `cli/` and `scripts/` — a status line that
needs a dependency is a status line somebody will reinvent with `print`.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Iterable, NoReturn, Sequence, Tuple

#: The whole vocabulary. Add a state here, never at a call site.
#:
#: Split in two because the checker needs the halves apart, and one dict that
#: both the renderers and the checker read beats two that agree by hand.
#:
#: `skip` is not a failure and not a success: a gate that correctly chose not to
#: act executed properly, and it has to stay distinguishable from one that never
#: ran. That distinction is load-bearing in the run ledger, where a tier ships one.
STATE_SYMBOLS = {
    "ok": "✅",
    "fail": "❌",
    "warn": "⚠️ ",
    "skip": "⏸️ ",
    "bypass": "⏭️ ",
}

#: Formatting marks, which are not states. The distinction is load-bearing:
#: `scripts/check_output_discipline.py` flags a state symbol typed into a
#: `print`, and a `→` inside generated prose is punctuation, not a status line.
MARK_SYMBOLS = {
    "step": "→",
    "item": "·",
}

SYMBOLS = {**STATE_SYMBOLS, **MARK_SYMBOLS}

#: Recorded outcome -> symbol name. The outcome *names* belong to the run
#: ledger; the symbols belong here, so a status viewer never spells its own. It used to, and the viewer's `declined` glyph and the
#: runner's had already drifted apart by a trailing space.
OUTCOME_SYMBOLS = {
    "ok": "ok",
    "failed": "fail",
    "declined": "skip",
    "skipped": "bypass",
}

#: How wide `summarize` draws its rules.
_RULE_WIDTH = 60


def _say(symbol: str, message: str) -> None:
    print(f"{symbol} {message}" if message else symbol, file=sys.stderr)


# ── The human channel (stderr) ───────────────────────────────────────────────


def ok(message: str) -> None:
    """A gate passed, or a mutation succeeded."""
    _say(SYMBOLS["ok"], message)


def fail(message: str) -> None:
    """A gate failed. Say what is wrong; follow with `detail` for what to do."""
    _say(SYMBOLS["fail"], message)


def warn(message: str) -> None:
    """Something is off but nothing is blocked."""
    _say(SYMBOLS["warn"], message)


def skip(message: str) -> None:
    """Executed, and deliberately did not act — with the reason.

    Distinct from `warn` on purpose: a job that declined is working. Reporting
    it as a warning means every legitimate decline reads as a problem, and a
    channel that cries wolf stops being read.
    """
    _say(SYMBOLS["skip"], message)


def step(message: str) -> None:
    """Narration: what is about to happen, or what is running now."""
    _say(SYMBOLS["step"], message)


def shell(cmd: str) -> None:
    """Echo a command about to be spawned, in a form you can paste back.

    Narration, not output: the child's own stdout is the caller's, and mixing
    "here is what I ran" into it is how a captured log stops being replayable.
    """
    print(f"$ {cmd}", file=sys.stderr)


def detail(message: str = "") -> None:
    """A continuation line under the status line above it."""
    print(f"   {message}" if message else "", file=sys.stderr)


def item(message: str) -> None:
    """One entry in a list of findings under a `fail` or `warn`."""
    print(f"   {SYMBOLS['item']} {message}", file=sys.stderr)


def die(message: str, code: int = 1) -> NoReturn:
    """`fail`, then stop. For the errors that have no useful continuation."""
    fail(message)
    raise SystemExit(code)


# ── The machine channel (stdout) ─────────────────────────────────────────────


def line(text: str = "") -> None:
    """A line of the command's own output — the half a caller might pipe.

    A crontab block, a table row, a resolved value. If a script is asked for a
    thing, the thing goes here; everything the script says *about producing* it
    goes to stderr.
    """
    print(text)


def emit(payload: Any) -> None:
    """The `--json` payload, and nothing else on this stream.

    `default=str` so a Path or a datetime in a result object serialises instead
    of raising at the very end of a check that already did its work.
    """
    print(json.dumps(payload, indent=2, default=str, sort_keys=True))


def badge(outcome: str) -> str:
    """The symbol for a recorded outcome, for rows in a listing.

    Returns the `?` symbol for an outcome the vocabulary does not know, rather
    than raising: a viewer that crashes on one malformed ledger row shows you
    nothing about the other forty-nine.
    """
    return SYMBOLS.get(OUTCOME_SYMBOLS.get(outcome, outcome), "?")


# ── The gate table ───────────────────────────────────────────────────────────


def summarize(results: Iterable[Tuple[str, int]]) -> int:
    """Print a pass/fail table for a set of gates and return the exit code.

    Every gate runs even when an earlier one failed. A pre-push check that stops
    at the first red gives you one fix per round trip; the whole point is to
    learn everything that is wrong in a single run.
    """
    rows: Sequence[Tuple[str, int]] = list(results)
    print("\n" + "─" * _RULE_WIDTH, file=sys.stderr)
    for name, code in rows:
        _say(SYMBOLS["ok"] if code == 0 else SYMBOLS["fail"], f" {name}")
    print("─" * _RULE_WIDTH, file=sys.stderr)
    failed = [name for name, code in rows if code != 0]
    if failed:
        fail(f"{len(failed)} gate(s) failed: {', '.join(failed)}")
        return 1
    ok(f"all {len(rows)} gates passed")
    return 0
