"""The pre-flight is only worth having if every commit-time caller goes through it.

`scripts/lint_pyright_gate.py` exists because `reportMissingImports` is `none`:
an interpreter without this project's packages does not fail the type check, it
degrades every name those packages define to `Unknown` and reports the fallout
as errors in files the commit never touched. Losing `click` alone turns a clean
scaffold into 24 of them, and not one names click.

A wrapper that one caller bypasses gives that caller the old behaviour back,
silently — the bypassing path is the one that reports an environment fault as
two dozen tree defects, and it looks exactly like the tree being broken. So the
routing is asserted rather than remembered.

## What each test here is for

* **Routing.** Enrolment is by pattern over the files that invoke pyright, so a
  caller added later is covered without editing a list. The commit command
  ships only at the higher tiers, so the scan takes what exists and
  `scanned(...)` refuses an enumeration too small to prove anything.
* **The sentinels are installable.** Every sentinel must be reachable from
  `.github/pyright-deps.txt`, which is what CI installs. A sentinel outside it
  is a gate that fails on a correctly provisioned runner — the pre-flight would
  block a commit pyright would have checked fine.
* **The resolution order.** `venvPath` + `venv` outranks `PATH`, measured
  against pyright itself. Resolving `PATH` first would probe an interpreter
  pyright ignores, which is a green probe followed by a red check.
* **Fail closed, and do not run pyright.** A probe failure must not reach
  pyright at all. Two dozen diagnostics naming the wrong thing are worse than
  none, and a gate that could not run is not a gate that passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts import lint_pyright_gate as gate  # noqa: E402
from scripts.paths import GITHUB_DIR, PROJECT_ROOT, SHELL_PACKAGE  # noqa: E402

pytestmark = [pytest.mark.unit]

#: The wrapper, as a caller would spell it.
WRAPPER = "scripts/lint_pyright_gate.py"

#: Where a commit-time pyright caller can live: the hook definition, and the
#: CLI's own commands. **Discovered, never listed**, and the first draft was a
#: list of three literal paths, which was wrong twice for two different reasons
#: this template already has names for.
#:
#: The shell package's directory name is the DEFAULT of `--shell-package`, not
#: the name, so a renamed tree found one caller instead of three and
#: `scanned()` refused the scan. And the commit command ships only above
#: `core`, so naming its file made every `core` configuration cite something it
#: does not ship — a tier-composition failure, in a test whose whole subject is
#: that this set varies by tier.
#:
#: Neither path is spelled even here. The gate that caught the second one reads
#: prose as well as code, so a note explaining the removed literal reintroduces
#: it — and the fix for that is a sentence that does not need the literal, not
#: an exemption for a sentence that does.
#:
#: `.github/workflows/` is deliberately out of scope rather than exempted: that
#: job installs `.github/pyright-deps.txt` onto the runner's interpreter with no
#: `.venv` in the checkout, so it answers every interpreter question in the
#: workflow and is outside this failure mode by construction.
_CALLER_SOURCES = (".pre-commit-config.yaml", f"{SHELL_PACKAGE}/**/*.py")


def _present_callers() -> dict:
    """Every file that invokes pyright at commit time, as `path -> its text`.

    Enrolment is `pyright` plus `--project` in the same file, which is what
    distinguishes a call from a mention of `pyrightconfig.json`.
    """
    paths = []
    for pattern in _CALLER_SOURCES:
        paths.extend(sorted(PROJECT_ROOT.glob(pattern)) if "*" in pattern else [PROJECT_ROOT / pattern])

    found = {}
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "pyright" in text and "--project" in text:
            found[path.relative_to(PROJECT_ROOT).as_posix()] = text

    # Two at `core` (the hook and `check lint`), three above it. Above 1 because
    # the assertion below is a filter over this set, and one caller cannot show
    # that the filter selects anything.
    return scanned(found, "commit-time pyright callers", least=2)


def test_every_commit_time_caller_routes_through_the_wrapper():
    """A caller that still invokes `pyright` directly has the old behaviour back."""
    bypassing = sorted(name for name, text in _present_callers().items() if WRAPPER not in text)
    assert not bypassing, (
        f"these run pyright without the pre-flight: {bypassing}\n"
        f"Route them through {WRAPPER}. A bare interpreter there reports an environment "
        "fault as errors in files the commit never touched, because reportMissingImports is 'none'."
    )


def test_the_sentinels_are_installed_by_the_dependency_set_ci_uses():
    """A sentinel CI does not install is a gate that blocks a correct commit.

    Followed through the `-r` chain, because `.github/pyright-deps.txt` is one
    line of includes rather than a package list — asserting against its literal
    text would pass only while it happens to name packages directly.
    """

    def packages(path: Path, seen: set) -> set:
        if path in seen or not path.exists():
            return set()
        seen.add(path)
        names: set = set()
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#")[0].strip()
            if not line:
                continue
            if line.startswith("-r"):
                names |= packages((path.parent / line[2:].strip()).resolve(), seen)
            else:
                names.add(line.split("==")[0].split(">=")[0].split("[")[0].strip().lower())
        return names

    declared = scanned(sorted(packages(GITHUB_DIR / "pyright-deps.txt", set())), "packages CI installs", least=2)
    missing = sorted(s for s in gate.SENTINEL_IMPORTS if s.lower() not in declared)
    assert not missing, (
        f"sentinels not reachable from .github/pyright-deps.txt: {missing}\n"
        f"CI installs that file, so the pre-flight would fail on a correctly provisioned runner. "
        f"Add them there, or drop them from SENTINEL_IMPORTS."
    )


def test_the_config_venv_outranks_path(tmp_path, monkeypatch):
    """`venvPath` + `venv` wins, because that is what pyright itself does.

    Measured on pyright 1.1.411: with the pin resolving, an interpreter passed
    as `--pythonpath` is ignored. Probing `PATH` first would prove something
    true about an interpreter the type check never uses.
    """
    pinned = tmp_path / ".venv" / "bin"
    pinned.mkdir(parents=True)
    (pinned / "python").write_text("", encoding="utf-8")
    config = tmp_path / "pyrightconfig.json"
    config.write_text(
        '{\n  // a comment, because this file is JSONC\n  "venvPath": ".",\n  "venv": ".venv"\n}\n', encoding="utf-8"
    )

    monkeypatch.setattr(gate.shutil, "which", lambda _name: "/usr/bin/python3")
    interpreter, source = gate.resolve_interpreter(config)

    assert interpreter == pinned / "python", f"resolved {interpreter}, not the pinned venv"
    assert "venvPath" in source, source


def test_a_config_that_pins_nothing_falls_through_to_path(tmp_path, monkeypatch):
    """The other direction, so the test above is about precedence and not about PATH being unreachable."""
    config = tmp_path / "pyrightconfig.json"
    config.write_text('{\n  "include": ["scripts"]\n}\n', encoding="utf-8")

    monkeypatch.setattr(gate.shutil, "which", lambda name: "/usr/bin/python3" if name == "python3" else None)
    interpreter, source = gate.resolve_interpreter(config)

    assert interpreter == Path("/usr/bin/python3")
    assert "PATH" in source, source


def test_an_unresolvable_interpreter_fails_closed(tmp_path, monkeypatch):
    """Never a skip. A gate that could not run is not a gate that passed."""
    config = tmp_path / "pyrightconfig.json"
    config.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(gate.shutil, "which", lambda _name: None)

    interpreter, message = gate.preflight(config)
    assert interpreter is None
    assert message and "could not be resolved" in message[0]


def test_a_failed_probe_never_reaches_pyright(tmp_path, monkeypatch):
    """The load-bearing half: pyright must not run, not merely be reported around.

    Asserted by making `shutil.which` explode. `main` looks pyright up only
    after the pre-flight passes, so reaching that lookup at all is the failure —
    which is a stronger claim than checking the exit code, since exit 1 is also
    what a genuine type error returns.
    """
    config = tmp_path / "pyrightconfig.json"
    config.write_text('{\n  "include": ["scripts"]\n}\n', encoding="utf-8")

    monkeypatch.setattr(gate, "SENTINEL_IMPORTS", ("a_module_that_cannot_possibly_be_installed",))

    def explode(_name):
        raise AssertionError("pyright was looked up — the probe failure did not stop the run")

    monkeypatch.setattr(gate.shutil, "which", explode)
    # `which` is also how PATH resolution works, so the config must pin an
    # interpreter that exists — otherwise this passes for the wrong reason,
    # failing in resolution before the probe is ever attempted.
    pinned = tmp_path / ".venv" / "bin"
    pinned.mkdir(parents=True)
    (pinned / "python").symlink_to(sys.executable)
    config.write_text('{\n  "venvPath": ".",\n  "venv": ".venv"\n}\n', encoding="utf-8")

    assert gate.main(["--project", str(config)]) == 1


def test_the_probe_reports_a_missing_module_rather_than_raising():
    """A probe that raises is a gate that crashes instead of explaining itself."""
    sound, why = gate.probe(Path(sys.executable), "a_module_that_cannot_possibly_be_installed")
    assert sound is False
    assert why, "a failed probe must say what went wrong"

    sound, why = gate.probe(Path(sys.executable), "json")
    assert sound is True, why
