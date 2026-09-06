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
a leaner environment is not a more permissive check, just a *different* one. Pyright resolves
its interpreter from `PATH`, so **pass `--pythonpath` when reproducing a CI result**. CI pins
its set in `.github/pyright-deps.txt`; keep that a superset of the unit-test job's installs.

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
