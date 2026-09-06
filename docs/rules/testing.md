# Testing Rules

Applies to everything under `tests/`.

## Registration Is Marker-Based — No Registries

A test file registers itself **by existing**. Declare which environment runs it with a
module-wide `pytestmark`:

```python
import pytest

pytestmark = [pytest.mark.unit]   # see tests/pytest.ini for the full marker list
```

| Marker        | Environment                                  | Run with                 |
| ------------- | -------------------------------------------- | ------------------------ |
| `unit`        | Host, no services required                   | `dev test unit`        |
| `integration` | Services up, seeded data                     | `dev test integration` |
| `manual`      | Never in scheduled CI (E2E, live third-party, paid APIs) | `dev test manual` |
| `ui`          | Drives an interface — see § Interaction below | `dev test ui`        |

`ui` **is** run by CI: `.github/workflows/ci.yml` has a job for it, because a
marker no workflow selects silently removes a test from every run. A headless
pilot needs nothing added; a browser or an Electron window needs a driver or a
virtual display, and that setup belongs in that job.
`tests/test_ci_runs_every_suite.py` fails if a suite the CLI offers is run by
nothing.

**If nothing here is marked `ui`, delete the job** — set `scheduled=False,
unscheduled="empty"` on the row in `cli/test_cmds.py` and remove the job from
`ci.yml`. Nothing else references it, and `tests/test_workflow_job_graph.py`
holds that: a `needs:` naming a deleted job is a `startup_failure`, which is
zero jobs and no logs rather than a red check.

An exemption has to say **which kind** it is, because the two expire
differently. `unattended` is a fact about the suite and keeps. `empty` is a fact
about this tree's contents, and the moment somebody marks a test the row is
false with nothing red — so the registry implies an emptiness assertion and the
suite writes it for you.

`tests/test_marker_coverage.py` fails the unit suite if a test file declares no marker.

**Never** add a per-feature CI step, a `run_tests.sh` case, or a CLI entry for a new test
file. Those are registries, and *forgetting to update a registry is the same bug* the marker
exists to remove. Dual-environment files list multiple markers.

## Behavioral Assertions Only

- ❌ No source-grep asserts (`assert "csrf" in open(...).read()`) — test the behaviour.
- ❌ No assert-only-`isinstance` / `is not None` — assert values, shapes, side effects,
  status codes.
- ❌ Never mock the method under test. Mock only true externals at the boundary.
- ✅ Cover the happy path, the edge cases, **and** the error cases.
- ✅ Prefer real local infrastructure (a test database, a fake in-process cache) over mocking
  storage — a mocked store cannot fail the way a real one does.

A test that `return`s instead of asserting cannot fail: pytest discards the value.
`filterwarnings = error::pytest.PytestReturnNotNoneWarning` in `tests/pytest.ini` makes that
an error on our schedule rather than during a future version bump.

## Env-Gate Skips: `require_or_skip`, Not `pytest.skip`

```python
from conftest import require_or_skip

require_or_skip(services_up, "the app is not reachable", requires="services")
```

Locally it **skips**; under `SB_CI=1` it **fails**. CI guarantees the services, so a skip
there means the harness broke, and a harness that silently skips its whole suite reports
green. Raw `pytest.skip` is only for genuine cross-environment conditions CI does not
guarantee.

## Interaction: Assert at the Act, Not at the Consequence

For the `ui` suite — a Textual pilot, a browser, an Electron window. The rule is
framework-independent because the failure is:

> **A UI harness can deliver an action to nothing, and every assertion after it
> is then vacuous.** The test fails later, somewhere unrelated, or does not fail
> at all.

This is the `scanned()` rule one domain over. An enumeration that found nothing
makes every assertion *over* it a tautology; an interaction that landed on
nothing makes every assertion *after* it a tautology. Same remedy: put the guard
in the act, not beside it.

Three ways the action goes missing, one per stack, all the same bug:

| | how it disappears |
| --- | --- |
| TUI | a widget is mounted **before the first layout pass**, so for a few frames it exists with a zero-width region and a click resolves to coordinates that hit nothing |
| Browser | the element is in the DOM before hydration, or is zero-size, or is covered, or an animation is still moving it |
| Electron | the window exists before it is focusable, and input goes to the previous window |

And one that is not about timing at all: **a harness may coalesce or drop the
action itself.** Textual's `pilot.click` merges repeat clicks at the same
position — measured at three clicks delivering two presses — so a test asserting
*a second run is refused* passes whether the refusal works or not.

So:

1. **Wait on the property that makes the action deliverable**, never on the
   element existing. Existence is the wrong predicate; size, focus, and
   stability are the right ones.
2. **Assert the interaction landed, in the helper that performs it** — the
   screen changed, the handler ran, the count moved. A missed click must fail
   *at the click*, not ten seconds later in an assertion about state.
3. **Never repeat an identical action to mean two things.** If a second press
   must be distinguishable from the first, use a different route — a keybinding,
   a distinct target — because a harness that merges them makes the distinction
   unobservable.
4. **A negative assertion after an interaction needs (2) before it is worth
   anything.** *Nothing happened* and *the action never arrived* look identical.

The adapter is yours: only this repository knows its framework. What is not
negotiable is that the helper asserts delivery, because a harness that silently
swallows input turns the whole suite into a coin flip that always lands green.

## Never Create State Without a Teardown

Every fixture that creates a record owns its deletion. A cleanup that runs at *startup* is
not a teardown — it hides the leak for exactly as long as it takes to become someone else's
problem. Put shared setup in a `yield` fixture in `tests/conftest.py`, where the teardown
sits in the same function as the creation; never construct records against a live session
by hand.

## Budgets Are Ratchets — Update Them in the Same Commit

Two counts are pinned so they can only move deliberately:

- **Skips**: `scripts/check_skip_budget.py` against `tests/skip_budget.json`.
- **Coverage**: `scripts/check_coverage_budget.py` against `tests/coverage_budget.json`.

Adding a legitimate skip → raise the budget **in the same commit** and justify it in the
body. Removing skips, or raising coverage meaningfully → lower/raise the baseline in the same
commit to lock the gain in. A ratchet is not a target: never chase the number.

Both read a report pytest writes, so **both fail when that report is missing** rather than
warning and passing. A ratchet with nothing to read has not passed, it has not run, and the
two are indistinguishable from a green step. Run them the way CI does:

```bash
python -m pytest tests/ -m unit -q --junitxml=tmp/junit.xml
python scripts/check_skip_budget.py --suite unit
```

Each suite is checked against **its own** report. A skip count belongs to the run that
produced it, and `count_skips` sums a whole file — so one report covering two markers
charges the second suite's skips to the first and names the wrong one while doing it.
Coverage is the opposite and stays combined: a line rate is a whole-tree measure.

`tests/test_ci_ratchet_inputs.py` holds the workflows to the same rule, because the version
of this that shipped was a job running the ratchet and never writing the file.

## Before You Commit

```bash
dev test unit            # the fast suite — must be green
dev check pre-push       # every CI gate that runs without the stack
```

All tests must pass. Never commit half-working code.
