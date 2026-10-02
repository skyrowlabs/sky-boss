# Output Rules

Applies to everything that prints — `cli/`, `scripts/`, and anything a job runs.

## Two Channels, One Question

**stdout is what a caller consumes. stderr is what only a human reads.**

| Goes to stdout                                     | Goes to stderr                                |
| -------------------------------------------------- | --------------------------------------------- |
| a `--json` payload                                  | `✅` / `❌` / `⚠️` / `⏸️` status lines           |
| a generated block (`report cron --print`)          | progress (`→ running x`), echoed commands     |
| a listing somebody may pipe (`docs status`)        | the gate table from `check pre-push`          |
| a resolved value a script exists to produce        | "here is what to do next" under an error      |

Both land on the terminal, so nothing looks different when you run a command by
hand. The difference shows up the moment somebody pipes one.

That is not a style preference — it is what makes `--json` cheap. Because the
narration is on the other stream, `--json` is **purely additive**: build the
result object, emit it, and render the human half exactly as before. No early
return, no second code path, nothing to drift.

Before the split, `python scripts/check_doc_tables.py --json | jq` failed: the
same stdout carried the JSON *and* the `❌` lines explaining it. Four scripts had
grown a `--json` flag, three of them emitted output no parser could read, and
the two ratchets whose numbers a dashboard actually wants had no flag at all.

## Never Spell a Symbol

Every status line comes from `scripts/output.py`:

```python
from scripts.output import detail, emit, fail, item, line, ok, skip, step, warn
```

| Call                   | Stream | For                                                   |
| ---------------------- | ------ | ----------------------------------------------------- |
| `ok(msg)`              | stderr | a gate passed, a mutation succeeded                   |
| `fail(msg)`            | stderr | a gate failed                                         |
| `warn(msg)`            | stderr | something is off, nothing is blocked                  |
| `skip(msg)`            | stderr | executed and **deliberately did not act** — with why  |
| `step(msg)`            | stderr | narration: what is running now                        |
| `shell(cmd)`           | stderr | echo a command about to be spawned                    |
| `detail(msg)`          | stderr | a continuation line under the status line above it    |
| `item(msg)`            | stderr | one entry in a list of findings                       |
| `die(msg)`             | stderr | `fail`, then stop                                     |
| `line(text)`           | stdout | a line of the command's own output                    |
| `emit(payload)`        | stdout | the `--json` payload, and nothing else                |
| `summarize(results)`   | stderr | the pass/fail gate table; returns the exit code       |

`cli/helpers.py` re-exports all of it, so a command module has one import.

**`skip` is not a warning.** A job that executed and correctly chose not to act
is working. Reporting it as a warning means every legitimate decline reads as a
problem, and a channel that cries wolf stops being read. This is the same
distinction the run ledger draws — in the tiers that ship one — between
`declined` and a cron that never fired.

## Why a Module and Not a Convention

`cli/helpers.py` already shipped `ok()` / `fail()` / `warn()`. Roughly twenty
call sites retyped `print(f"✅ ...")` anyway, because `scripts/` could not reach
them — and a vocabulary only half the tree can import is one the other half
reinvents. `⏸️` meant "executed and declined" in three files and was defined in
none of them; the two spellings had already drifted by a trailing space. The
gate table had a second implementation inside the commit command.

None of that is visible to a linter or to review, because each file is
internally consistent. So it is checked:

```bash
dev check output      # python scripts/check_output_discipline.py
```

**Enrolment is not a registry.** Every `.py` under `cli/` and `scripts/` is
checked — a new file is enrolled by existing. It flags three things: a state
symbol typed into a `print`, a stream picked by hand (`file=sys.stderr`), and a
`scripts/check_*.py` with no `--json`. Exemptions go in
`scripts/output_allowlist.yaml` **with a reason**, because an intended
divergence is a decision record and one nobody decided is the bug.

Prose is not output: the checker skips docstrings and comments, so a file may
document the rule it follows.

## Every Check Script Answers in JSON

A `scripts/check_*.py` supports `--json`, and emits its payload on **every**
path — including the ones that pass. A ratchet a dashboard can only read when it
is red says nothing about the direction it has been moving, which is the only
thing a ratchet is for.

One result object, two renderings. Never two code paths:

```python
def done(payload: dict, status: int) -> int:
    if args.json:
        emit({"suite": args.suite, **payload})
    return status
```

`tests/test_output_contract.py` runs each of them and parses the result, so a
payload that stops being parseable fails the unit suite rather than a dashboard.
