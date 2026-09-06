"""The output contract, tested by running the programs — not by reading them.

`scripts/check_output_discipline.py` checks the *shape* of the source. This
checks the *behaviour*, which is the half that actually matters to a caller:

* every `scripts/check_*.py` answers `--json` with something a parser can read
* nothing else lands on that stdout — the explanation goes to stderr

Those are two separate failures. A script can grow a correct payload and still
be unusable because a `⚠️` line shares the stream with it, which is exactly what
had happened to three of them before `scripts/output.py` existed.

Enrolment is by pattern: any `scripts/check_*.py` is covered by existing. A new
checker that forgets `--json` fails here without anybody adding it to a list.

## The one exemption, and why it is not in a YAML file

Every checker here runs as a **host subprocess**. That is correct for a fresh
scaffold and false for a tree that grows a checker needing the repository
mounted in a container, a service up, or a credential — jam.sense hit this on
their first adoption with a checker that imports from a container-only path, and
the lifted test went red on a bare runner while passing locally.

`scripts/output_allowlist.yaml` cannot express it, and the reason is worth
stating because it is a collision rather than a gap. That file answers the
*source-shape* question `check_output_discipline.py` asks — does this script
declare `--json`? — and its staleness check reports an entry as stale the moment
the source check passes. A container-only checker that correctly declares
`--json` would therefore have its exemption deleted as stale, and deleting it
re-breaks this test. **One allowlist, two consumers, two different questions
wearing one filename.**

So the exemption is a constant in the script itself, holding its own reason:

```python
CANNOT_RUN_ON_HOST = "imports from the container mount; needs the repo at /app"
```

It travels with the script rather than with a path string somebody must
maintain, and it is **validated on every run in the direction that matters**: a
script claiming it cannot answer `--json` here, which then does, is reported as
a stale claim. An exemption nothing re-checks is the failure this whole suite is
built around.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import STATE_SYMBOLS  # noqa: E402
from scripts.paths import PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402

#: The exemption, read from the source rather than imported — importing is the
#: act being exempted, so a module that cannot be imported here cannot be asked.
#: A non-empty string literal is required: the value IS the reason, so there is
#: no way to claim the exemption without stating why.
_CANNOT_RUN = re.compile(r"""^CANNOT_RUN_ON_HOST\s*=\s*["'](?P<reason>[^"']+)["']""", re.MULTILINE)


def _checkers():
    return sorted(SCRIPTS_DIR.glob("check_*.py"))


def _declared_reason(script: Path) -> str:
    match = _CANNOT_RUN.search(script.read_text(encoding="utf-8"))
    return match.group("reason") if match else ""


def _host_runnable():
    return [script for script in _checkers() if not _declared_reason(script)]


def _host_exempt():
    return [script for script in _checkers() if _declared_reason(script)]


def _parses(result: subprocess.CompletedProcess) -> bool:
    try:
        return isinstance(json.loads(result.stdout), dict)
    except (json.JSONDecodeError, ValueError):
        return False


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=90,
    )


def test_there_are_checkers_to_check():
    """A glob that silently matches nothing is a test that always passes.

    Both sets, because the second is the one that can be emptied *without* the
    glob breaking: declare every checker `CANNOT_RUN_ON_HOST` and the two
    behavioural tests below parametrize over nothing and pass having run
    nothing, which looks identical to passing.
    """
    assert _checkers(), "no scripts/check_*.py found — the enrolment pattern is wrong"
    assert _host_runnable(), (
        "every scripts/check_*.py declares CANNOT_RUN_ON_HOST, so the output contract is "
        f"asserted against nothing. Exempt: {[s.name for s in _host_exempt()]}"
    )


@pytest.mark.parametrize("script", _host_runnable(), ids=lambda p: p.name)
def test_json_payload_parses(script: Path):
    """`--json` puts a parseable object on stdout, whatever the verdict."""
    result = _run(script, "--json")
    assert result.stdout.strip(), f"{script.name} --json wrote nothing to stdout (stderr: {result.stderr[-400:]})"
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict), f"{script.name} --json emitted {type(payload).__name__}, not an object"


@pytest.mark.parametrize("script", _host_runnable(), ids=lambda p: p.name)
def test_status_lines_stay_off_stdout(script: Path):
    """A status symbol on stdout is what makes `--json | jq` fail."""
    result = _run(script, "--json")
    for symbol in STATE_SYMBOLS.values():
        assert symbol.strip() not in result.stdout, (
            f"{script.name} wrote '{symbol.strip()}' to stdout — status lines belong on stderr. "
            "See docs/rules/output.md."
        )


def test_the_human_half_still_happens():
    """The split must not have made a check silent.

    A check whose narration went to a stream nobody reads is worse than one that
    is noisy: it reports nothing and passes.
    """
    result = _run(SCRIPTS_DIR / "check_doc_tables.py")
    assert result.stderr.strip(), "check_doc_tables.py said nothing to a human"
    assert any(symbol.strip() in result.stderr for symbol in STATE_SYMBOLS.values())


def test_a_host_exemption_is_still_true():
    """A script claiming it cannot answer `--json` here, which then does.

    This is the exemption's staleness check, and it is keyed to the exact
    capability being excused rather than to some neighbouring one. A checker
    that grew a host-runnable path, or whose container dependency was removed,
    is silently carrying a claim that is no longer true — and the next reader
    takes it as a live reason not to test the thing.

    ## Why this one loops where its neighbours parametrize

    Zero exemptions is the *expected* state of a fresh scaffold, and pytest
    reports an empty parameter set by **skipping** — which is a legitimate
    assertion over an empty set arriving as an illegitimate one. `skip_budget`
    ships at 0, so the intended case was the breaching case: every v0.5.1 tree
    was born one skip over its own ratchet. stash.flow found it, and declined to
    raise the budget on the grounds that the number would then record a claim
    about their tree that was false and outlive the fix — which is right, and is
    why the fix is here rather than there.

    An assertion that is correct when empty and a skip that is emitted when
    empty are different things, and only the second is visible to a ratchet.

    What keeps the empty case from being vacuous is not a guard beside it but
    the shape of the enumeration: `_host_exempt()` and `_host_runnable()`
    partition `_checkers()`, so a declaration this scanner fails to see does not
    vanish — it lands in the other set, where the contract is asserted against a
    script that cannot answer and fails loudly. That is why
    `test_there_are_checkers_to_check` can guard the other two sets and not this
    one, and why it does not need to.

    **Do not generalise that into "enumerations do not need guards."** It is the
    narrow case, and `tests/scanning.py` is the wide one: most scans here have no
    complement to fall into, so an empty result is indistinguishable from a
    broken pattern and `scanned()` is what says so. The question to ask of an
    empty enumeration is what makes emptiness *carry no information* — a
    partition, as here, or nothing, in which case the guard is doing real work
    and deleting it re-opens the hole. stash.flow asked it of a read-only surface
    pin and got the opposite answer: there the set not growing IS the invariant.
    """
    for script in _host_exempt():
        result = _run(script, "--json")
        assert not _parses(result), (
            f"{script.name} declares CANNOT_RUN_ON_HOST ({_declared_reason(script)!r}) and answered "
            "`--json` with a parseable object anyway. The exemption has outlived its reason: delete "
            "the constant so the contract is asserted against this script again."
        )
