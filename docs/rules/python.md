# Python Code Quality Rules

Applies to all `**/*.py` in this project. **CI blocks on every check below.**

## The Blocking Set — Run After Any Python Change

```bash
flake8 . --select=E9,F63,F7,F82,F401 --show-source --statistics   # errors that must be zero
isort --check-only --diff <file>                                  # import order
black --check --line-length=120 <file>                        # formatting
pyright --project pyrightconfig.json                              # types, whole-project
```

| Code | Meaning                 |
| ---- | ----------------------- |
| E9   | Syntax errors           |
| F82  | Undefined names         |
| F401 | Unused imports          |
| F63  | Invalid assertions      |
| F7   | Syntax in type comments |

Config lives in `.flake8`. Max line length **120**, max complexity **15** — a
function over 15 is flagged for refactoring, not blocked.

## Pyright Is Whole-Project, and That Is the Point

`pyrightconfig.json` sets `typeCheckingMode: "standard"`. The tree must stay at **0 errors**:
pyright runs whole-project in both the pre-commit hook (`pass_filenames: false`) and CI, so
**one stale error anywhere blocks every Python commit repo-wide** — including commits that
touch nothing near it. Fix errors when you see them rather than working around the hook.

Common fixes:

- `X is not a known attribute of None` → `assert X is not None`
- `X is possibly unbound` → initialize before the conditional
- A library whose stubs cannot express the runtime type → `cast(...)` at the call site, with
  a comment saying which stub is wrong

**Errors that appear only for some people.** `reportMissingImports` is `none`, so a package
pyright cannot import becomes `Unknown` and stops constraining anything. This cuts both ways:
a leaner environment is not a more permissive check, just a *different* one — and because the
root cause is the suppressed one, what you see is a pile of consequences in files your commit
never touched.

Pyright resolves its interpreter from `PATH` and does **not** read a virtualenv on its own;
`.venv/bin/pyright` is a wrapper and changes nothing. `pyrightconfig.json` therefore pins it
with `venvPath` + `venv`, which is the one place that reaches every caller — the pre-commit
hook is `language: node` with `pass_filenames: false` and cannot pass a per-machine path.
`tests/test_pyright_scope.py` holds that rule: the config pins, **or** every caller passes
`--pythonpath`. CI pins its dependency set in `.github/pyright-deps.txt`; keep that a
superset of the unit-test job's installs.

**`--pythonpath` does not override the pin, and the two are not interchangeable.** Measured
on pyright 1.1.411: with `venvPath` + `venv` resolving, passing a deliberately
package-free interpreter to `--pythonpath` still reports **0 errors** — the config wins.
Break the pin and the same flag reports the error, so it governs only where the pin falls
through. `--pythonpath` and `--venvpath` are also mutually exclusive, so no single
invocation both names an interpreter and overrides the config.

So to check against a *different* interpreter than the pinned one, point the pin somewhere
else — `pyright --venvpath <dir>`, or edit the config — rather than reaching for
`--pythonpath` and reading an unchanged result as agreement. The flag's real job is the
checkout where the pin cannot resolve: CI, and any worktree without a `.venv` beside its
copy of the config.

### The pre-flight, and why the errors you see may not be yours

**The pin fixes the checkout it sits in and gives nothing to a checkout without a `.venv`.**
There the fallback to `PATH` is the original behaviour, unchanged, and a bare interpreter is
one shell away — which matters because `reportMissingImports` is `none`, so pyright does not
tell you the interpreter is bare. It degrades every name your packages define to `Unknown`
and reports the *consequences*. In a fresh scaffold, losing `click` alone is **24 errors**:
`click.group` resolves to `Unknown`, so it stops decorating, and every `@group.command()`
becomes an attribute access on a plain function. Not one of those errors names click.

So the commit-time callers run [`scripts/lint_pyright_gate.py`](../../scripts/lint_pyright_gate.py)
rather than pyright directly — the `pyright` pre-commit hook, and `dev check lint`. It
resolves the interpreter pyright *would* use, proves it can import the project's packages,
and only then runs pyright with that interpreter passed explicitly, so what was probed is
what is checked:

```
❌ pyright's interpreter cannot import 'click' — this is an ENVIRONMENT fault,
   not a defect in the tree, and pyright was NOT run.
     interpreter : /usr/bin/python3
     resolved by : PATH (python3)
```

**Not running pyright is the load-bearing half**: two dozen diagnostics naming the wrong
thing are worse than none, because they read as a broken tree. It fails **closed** — an
interpreter that cannot be resolved at all is an error, never a skip, since a gate that
could not run is not a gate that passed.

CI does not call it and should not: that job installs `.github/pyright-deps.txt` onto the
runner's interpreter with no `.venv` in the checkout, so it answers every interpreter
question already, and a wrapper there would add a moving part to the one caller that never
had the problem. `tests/test_pyright_gate_preflight.py` holds the routing, the fail-closed
behaviour, and that every sentinel stays reachable from `.github/pyright-deps.txt` — a
sentinel outside it would block a commit on a correctly provisioned runner.

## Pin the Lint Tools in One Place

Every tool version is pinned in `.pre-commit-config.yaml` (**the source of truth**) and
mirrored into `scripts/requirements.txt` and the CI workflow.
`tests/test_lint_tool_parity.py` fails if they diverge — but **it cannot pin your venv**.
Two isort majors disagree about real formatting, so a stale local venv produces a diff CI
rejects. If `isort --version-number` disagrees with the pin, reinstall from
`scripts/requirements.txt`.

## Configuration — Never `os.getenv()` for App Config

```python
# ✅ validated, typed, fails fast at startup
from config import validated_config
url = validated_config.service_url

# ❌ no validation; a typo becomes a runtime error hours later
url = os.getenv("SERVICE_URL", "http://...")
```

Validation happens once at startup so a misconfigured process refuses to boot rather than
failing on the first request that needs the value.

## Banned Constructs

Each of these is enforced by a pre-commit hook, because each was a real bug:

| Banned                | Use instead                       | Why                                        |
| --------------------- | --------------------------------- | ------------------------------------------ |
| `datetime.utcnow()`   | `datetime.now(timezone.utc)`      | naive UTC compares wrong against aware time |
| bare `except:`        | `except <SpecificError>:`         | swallows `KeyboardInterrupt` and bugs      |
| `assert` for validation | an explicit `raise`             | `-O` strips asserts                        |
