"""The CLI is executed here, not merely imported.

Every other test in this suite checks a module or a config file. That leaves the
one surface every user and every agent actually touches — the commands — proven
only by somebody having run them once by hand.

Two bugs of exactly this shape have shipped in this shell's history:

* `script("-m", "pytest", ...)` joined its first argument onto the project root,
  so `check pre-push` — the first command the scaffolder tells you to run — was
  impossible to pass at any tier.
* `check doc-links --fix` forwarded a flag the script had never defined, and
  exited 2 on "unrecognized arguments" for as long as nobody typed it.

The first is caught by executing commands. The second is not — it needs the
flags to be checked against the script that receives them, which is why
`test_forwarded_flags_are_accepted` exists and is the more valuable of the two.

Enrolment is by discovery, never a list: the command tree is walked, so a new
command is covered by existing. Commands that must not run here are named in
`tests/cli_smoke_allowlist.yaml` with a reason.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import click
import pytest

pytestmark = [pytest.mark.unit]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from cli import cli as root  # noqa: E402
from scanning import scanned  # noqa: E402
from scripts import allowlist  # noqa: E402
from scripts.paths import CLI_DIR  # noqa: E402

ALLOWLIST = Path(__file__).resolve().parent / "cli_smoke_allowlist.yaml"


def _allowlist() -> Dict[str, str]:
    """Exemptions, read through the one reader every allowlist here shares."""
    return allowlist.read(ALLOWLIST)


def _walk(command: click.Command, path: Tuple[str, ...] = ()) -> List[Tuple[Tuple[str, ...], click.Command]]:
    """Every leaf command in the tree, with the path you would type to reach it."""
    if isinstance(command, click.Group):
        found: List[Tuple[Tuple[str, ...], click.Command]] = []
        for name, sub in sorted(command.commands.items()):
            found += _walk(sub, path + (name,))
        return found
    return [(path, command)]


# `least=5`: with one or two commands the exemption filter below is
# unobservable, since "every command" and "the runnable ones" are the same set.
COMMANDS = scanned(_walk(root), "commands in the CLI tree", least=5)


def _needs_arguments(command: click.Command) -> bool:
    return any(getattr(p, "required", False) for p in command.params)


def _agent_backed() -> set:
    """Command paths that invoke a headless agent, read from the job registry.

    Not the allowlist, deliberately: `report <job>` subcommands are *generated*
    from the job registry, so an allowlist entry per job would be a
    second registry — and the day somebody forgot one, this suite would sit
    there paying for a real agent run until it timed out. Registering a job
    exempts it by existing.

    The module is agentic-tier only; its absence means there are no such jobs.
    """
    try:
        from scripts.reporting.jobs import JOBS
    except Exception:  # pragma: no cover - tier without scheduled jobs
        return set()
    return {("report", job.key) for job in JOBS}


AGENT_BACKED = _agent_backed()


def _exempt(path: Tuple[str, ...]) -> str:
    """The reason this command is not executed, or ''. A group exempts its children."""
    if path in AGENT_BACKED:
        return "invokes a headless agent (from the job registry)"
    allow = _allowlist()
    for depth in range(1, len(path) + 1):
        reason = allow.get(" ".join(path[:depth]))
        if reason:
            return reason
    return ""


RUNNABLE = [p for p, c in COMMANDS if not _needs_arguments(c) and not _exempt(p)]


def _run(args: List[str], timeout: int = 90) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    return subprocess.run(
        [sys.executable, "-m", "cli", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


@pytest.mark.parametrize("path", [p for p, _ in COMMANDS], ids=lambda p: " ".join(p))
def test_every_command_answers_help(path: Tuple[str, ...]):
    """`--help` proves the module imports and the decorators are well formed.

    Cheap, and it is the check that fails when a command's module grows an
    import error — which otherwise surfaces as the whole CLI refusing to start.
    """
    result = _run([*path, "--help"], timeout=60)
    assert result.returncode == 0, f"`{' '.join(path)} --help` exited {result.returncode}:\n{result.stderr}"
    assert result.stdout.strip(), f"`{' '.join(path)} --help` printed nothing"


def test_every_command_is_either_runnable_or_has_a_reason():
    """No command is skipped silently — it needs arguments, or it is allowlisted."""
    unaccounted = [
        " ".join(p)
        for p, c in COMMANDS
        if not _needs_arguments(c) and not _exempt(p) and " ".join(p) not in [" ".join(r) for r in RUNNABLE]
    ]
    assert not unaccounted, unaccounted


def test_the_allowlist_names_commands_that_exist():
    """An entry naming no command is a stale exemption, and this one has teeth.

    The allowlist here does not soften a check — it says *do not run this
    command at all*. So an entry that outlives its command is not clutter: the
    name can come back for something else, and the new command arrives exempt
    from ever being executed. It would have `--help` proven and nothing else,
    which is the exact gap `test_read_only_commands_succeed` exists to close.

    A group exempts its children, so a key is live if it prefixes any command —
    matched the same way `_exempt` matches, from `COMMANDS`, so the two cannot
    disagree about what an entry covers.
    """
    live = {" ".join(path[:depth]) for path, _ in COMMANDS for depth in range(1, len(path) + 1)}
    stale = allowlist.stale(_allowlist(), lambda key: None if key in live else "no such command")
    assert not stale, "\n".join([*stale, allowlist.STALE_ADVICE])


@pytest.mark.parametrize("path", RUNNABLE, ids=lambda p: " ".join(p))
def test_read_only_commands_succeed(path: Tuple[str, ...]):
    """Run it for real. `--help` proves a command parses; this proves it works."""
    result = _run(list(path))
    assert result.returncode == 0, (
        f"`{' '.join(path)}` exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout[-2000:]}\n--- stderr ---\n{result.stderr[-2000:]}"
    )


def _forwarded_flags() -> List[Tuple[str, str, str]]:
    """Every `(cli module, script path, flag)` the CLI hands to a repo script.

    Read from the source rather than by running commands, because the flags are
    usually behind an option nobody passes in a smoke run — which is exactly how
    `check doc-links --fix` stayed broken.
    """
    found: List[Tuple[str, str, str]] = []
    for module in sorted(CLI_DIR.glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "script" or not node.args:
                continue
            target = node.args[0]
            if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
                continue
            for extra in ast.walk(node):
                if isinstance(extra, ast.Constant) and isinstance(extra.value, str):
                    if extra.value.startswith("--"):
                        found.append((module.name, target.value, extra.value.split("=")[0]))
    return scanned(sorted(set(found)), "flag(s) the CLI forwards to a repo script")


def _accepted_flags(script_path: Path) -> set:
    """Every `--flag` a script's argparse actually defines."""
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    flags = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        attr = getattr(node.func, "attr", None)
        if attr != "add_argument":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("--"):
                flags.add(arg.value)
    return flags


# Guarded by `scanned` inside `_forwarded_flags`. Not hypothetical: the first
# version of the check below compared the flag against the script's `--help`
# text and passed against a deliberately reintroduced bug, because the script's
# *docstring* mentions the flag and argparse prints it as the description.
@pytest.mark.parametrize("case", _forwarded_flags(), ids=lambda c: f"{c[0]}:{Path(c[1]).name} {c[2]}")
def test_forwarded_flags_are_accepted(case: Tuple[str, str, str]):
    """A flag the CLI forwards must be one the receiving script defines.

    This is the check that would have caught `check doc-links --fix`: the CLI
    advertised the flag, forwarded it, and the script had never defined it — so
    the command exited 2 on "unrecognized arguments" at every tier, and nothing
    noticed because no test ever typed it.

    Both sides are read rather than run. Running is what you would prefer, but
    there is no way to *ask* an argparse script whether it accepts a flag:
    `--help` short-circuits before the unknown option is reached, so the command
    exits 0 either way, and the flag usually mutates the tree so passing it for
    real is not an option. This is the same shape as `check_workflow_drift.py` —
    a contract between two source files, checked in the only place it is visible.
    """
    module, target, flag = case
    script_path = PROJECT_ROOT / target
    assert script_path.exists(), f"cli/{module} forwards to {target}, which does not exist"
    accepted = _accepted_flags(script_path)
    assert flag in accepted, (
        f"cli/{module} passes `{flag}` to {target}, which does not define it.\n"
        f"{target} accepts: {sorted(accepted) or '(none)'}"
    )
