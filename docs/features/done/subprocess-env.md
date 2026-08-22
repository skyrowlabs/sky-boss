---
status: complete
created: 2026-08-20
updated: 2026-08-21
agent_value: 3
key_files:
  - cli/helpers.py
  - cli/run.py
  - cli/data.py
  - cli/canvas/runner.py
  - tests/test_run.py
---

# The subprocess boundary — what a command tb runs inherits

## Why

tb hands every command it spawns its own bootstrap environment. Measured, from an unrelated
directory:

```
$ cd /tmp && tb run -- python3 -c "import cli; print(cli.__file__)"
   <repo>/cli/__init__.py

$ cd /tmp && python3 -c "import cli"
   ModuleNotFoundError: No module named 'cli'
```

The second line is what should happen. The first is tb putting its own package on a foreign tool's
import path, from anywhere on the machine.

The cause is not a mistake so much as an unexamined inheritance. The `tb` wrapper exports two
variables so that `python -m cli` resolves against the repo rather than against whatever directory
you happen to be standing in:

```bash
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONSAFEPATH=1
```

Both are load-bearing and neither is wrong — `CLAUDE.md` § CLI setup explains at length why
`PYTHONSAFEPATH=1` exists, and it has already prevented one silent bug. What nothing decided is
that a *child* should get them. `subprocess.run` inherits the parent environment by default, so
every `tb run`, every `tb wrap`, and every watcher refresh runs its command with toolbox on
`PYTHONPATH`.

**This was found by manually testing the thing it masks.** `tb wrap -- jam pr list --json`
succeeded from inside this repo without `--cwd`, and it should not have: run directly, `jam` fails
there. The leak was making it work.

Following that down turned up a second thing worth recording, in a different repository. jam's
wrapper does not set `PYTHONSAFEPATH`, so `python -m cli` prepends the current directory to
`sys.path` and **any directory containing a `cli/` package shadows jam's own**:

```
jam from toolbox (has a cli/ package):       exit=1
jam from /tmp (no cli/ package):             exit=0
jam from toolbox, PYTHONSAFEPATH=1:          exit=0
```

The error it printed — `missing required Python dependencies` — is toolbox's own message from
`cli/__init__.py:18`. jam was running tb's CLI. That is jam.sense's bug to fix and this document
does not propose fixing it here, but it is the reason `--cwd` genuinely is needed for jam, and it
is **not** the reason `CLAUDE.local.md` currently records. That note says jam resolves `.venv`
against the cwd; it has not done so for some time — its wrapper uses
`realpath "${BASH_SOURCE[0]}"` and is cwd-independent.

The two together are the worst case: tb's leak silently repairs jam's shadowing, so the argv that
works today is the argv that breaks the moment either bug is fixed.

## Shape

**A command tb spawns gets the operator's environment, not tb's.**

One helper in `cli/helpers.py`:

```python
BOOTSTRAP = ("PYTHONPATH", "PYTHONSAFEPATH")

def child_env() -> dict[str, str]:
    """os.environ minus the variables tb's own wrapper set."""
```

Used by everything that spawns: `run_command`, `tb run`, `tb wrap`, and the canvas runner.

**Why those two and nothing else.** They are exactly what `tb` exports and nothing else on the
machine sets them for this purpose. `PATH` is emphatically *not* on the list — the wrapper prepends
its venv's `bin` to it, and stripping that would be tb deciding which `python3` a foreign tool
should find, which is the operator's business and not tb's. Scrubbing is for variables that exist
only so tb can boot.

**The canvas runner scrubs too, even though it spawns `tb` itself.** The wrapper re-establishes
both variables on the way in, so nothing is lost — and it *appends* to any inherited `PYTHONPATH`,
so without scrubbing a nested invocation accumulates the repo path twice. Scrubbing makes the
child's environment identical whether it was reached from a terminal or from a watcher.

**The test is the demonstration, not a mock.** `tb run -- python3 -c "import cli"` must fail from a
directory that is not the repo, exactly as a plain shell fails. That asserts the property an
operator would check by hand rather than the mechanism, so a future change to *how* the wrapper
bootstraps cannot quietly satisfy it.

**Does not do:**

- **Does not sanitise generally.** Not a clean-room environment, not an allowlist, no `env -i`. A
  wrapped tool needs `HOME`, `PATH`, `SSH_AUTH_SOCK`, its own `*_TOKEN`s and everything else the
  operator's shell would have given it. The two variables removed are the two tb added.
- **Does not touch `PATH`.** See above.
- **Does not fix jam.** `CLAUDE.local.md` gets its note corrected, because a wrong reason recorded
  is worse than no reason, but jam.sense's wrapper is jam.sense's to change.
- **Does not add a `--env` flag.** Nothing has asked to *set* a variable for a wrapped command; if
  it does, that is a separate round and it should be argued on its own.

## Phases

### Round 1 — stop leaking the bootstrap (2026-08-20)

- [x] `BOOTSTRAP` and `child_env()` in `cli/helpers.py`.
- [x] `run_command`, `tb run`, `tb wrap` and `cli/canvas/runner.py` all use it.
- [x] A test that `tb run -- python3 -c "import cli"` fails from outside the repo, and one that
      `PATH` and ordinary variables survive.
- [x] Correct `CLAUDE.local.md`'s account of why `jam` needs `--cwd`, and add the scrub to
      `CLAUDE.md` § Conventions.

## Notes

### Round 1 — found by testing something else (2026-08-20)

The fix is six lines and was never in doubt. What is worth recording is how it was found, because
no test would have caught it and no amount of reading would either.

The task was a manual check of `tb wrap -- jam pr list --json` — the feature's own driving case,
after it had already shipped and passed 191 tests. The first command run was the *failure* case,
`wrap` with no `--cwd`, expected to fail because running `jam` there fails. It succeeded. Two
levels down from that surprise were two separate bugs in two different repositories, each of which
had been hiding the other:

- tb handed every subprocess its own `PYTHONPATH` and `PYTHONSAFEPATH`.
- jam's wrapper does not set `PYTHONSAFEPATH`, so any directory holding a `cli/` package shadows
  jam's own — and tb's leak was supplying the missing variable.

Neither is visible from inside its own repository. tb's suite passes with the leak, because every
test that spawns anything spawns something that does not care. jam works everywhere its author
runs it. **They only appear where the two meet**, which is a place only a person standing in one
repo running the other's binary ever stands.

The scar tissue in `CLAUDE.md` § CLI setup is about exactly this class — a relative `PATH` entry
re-resolving against a child's cwd, 112 tests failing from a tmp dir, systemd units silently
written with the wrong `WorkingDirectory`. It records the lesson as a rule about *tb's own*
bootstrap. What it had not extended is the other direction: tb's bootstrap is also something tb
*exports*, and a variable that is load-bearing for the parent is contamination for the child.

**The wrong reason was recorded, which is worse than none.** `CLAUDE.local.md` said `jam` needs
`--cwd` because its wrapper resolves `.venv` against the cwd. That was presumably true once; jam
now resolves it through `realpath` and is cwd-independent. A note like that is not merely stale —
it actively stops the next person looking, because the question already appears answered. Corrected
in place, with the measurements.

**The argv did not change, and that is the point.** `--cwd ~/src/jam.sense` was already
what the tool declared, and it is still right — it just now works for the reason the operator
thought it did rather than by accident of an inherited variable. The state before this round was
the dangerous one: the argv that worked was the argv that would break the moment *either* bug was
fixed, in either repository, by anyone.

**What is not fixed.** jam's wrapper still lacks `PYTHONSAFEPATH`, so `jam` still fails when run
from any directory containing a `cli/` package. That is jam.sense's to change, and `tb wrap`
without `--cwd` now fails honestly there instead of quietly working.

### 2026-08-21 — the words moved; the history stays (supersession)

`wrap` was renamed `data` and the `every` field renamed `refresh` — hard renames, no aliases;
see [[refresh]]. This doc predates the rename and its prose says `wrap` because it *was*
`wrap`; that is history being accurate, and nothing above has been scrubbed.
