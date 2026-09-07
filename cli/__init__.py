"""sky.boss CLI — one entry point for everything you do in this repo.

Implemented as a package of command-group modules, one per domain. The rule that
keeps it useful is in ``AGENTS.md``: **adding or changing a script means updating
this package in the same commit.** A script nobody can discover is a script
nobody runs, and the second person to need it writes it again.
"""

from __future__ import annotations

import subprocess
import sys

# Before the click guard, so the guard can speak in the same voice as everything
# else. `.helpers` reaches `scripts/output.py`, which is stdlib-only —
# a dependency-missing message that itself needs a dependency is no message.
from .helpers import PROJECT_ROOT, detail, fail

try:
    import click
except ImportError:  # pragma: no cover - dependency guard
    fail("The sky.boss CLI requires 'click'.")
    detail("Install with: pip install -r scripts/requirements.txt")
    sys.exit(1)


def get_version() -> str:
    """``git describe`` against a RELEASE tag, else the VERSION file.

    ``git describe`` is preferred because it says how far past the tag you are —
    ``v1.4.0-5-gabc1234-dirty`` is the difference between "the released code" and
    "something that looks like it".

    Two arguments here are load-bearing and both were wrong.

    ``--match v[0-9]*`` restricts this to release tags. Bare ``--tags`` takes the
    nearest tag of *any* shape, so a repository that tags anything else — an
    ``archive/v1`` marker, a ``last-known-good``, an environment pin — reports it
    as a version. stash.flow hit exactly that: ``version archive/v1-3-ga363012``,
    which is worse than an obviously wrong answer because nothing about it reads
    as broken. The pattern is not a house preference: ``release-please`` with
    ``release-type: simple`` creates ``v${version}``, so this matches the tags
    this repository's own release machinery makes and skips the ones it does not.

    **``--always`` is gone**, and its absence is what makes the sentence above
    true. With it, ``git describe`` never fails inside a checkout — it falls back
    to an abbreviated sha — so the ``VERSION`` fallback was unreachable from any
    checkout, and a freshly scaffolded tree reported ``version 4f2a91c`` while
    shipping a ``VERSION`` file that said ``0.1.0``. The function described a
    fallback its own arguments prevented it from taking, on every tree, from the
    first commit.
    """
    try:
        described = subprocess.run(
            ["git", "describe", "--tags", "--match", "v[0-9]*", "--dirty"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        ).stdout.strip()
        if described:
            return described
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # No file is the ordinary state under `--versioning tag`, which ships none:
    # a repository whose version IS its tag has nothing to fall back to before
    # the first tag exists, and `unknown` is the true answer there. Inventing a
    # `0.0.0` would be a version nobody chose, reported as though somebody had.
    version_file = PROJECT_ROOT / "VERSION"
    return version_file.read_text().strip() if version_file.exists() else "unknown"


@click.group()
# `prog_name` is the COMMAND, not the wordmark, and this is the only place in
# this file where that is true. The module docstring, the `requires 'click'`
# message and the group docstring below are all prose *about the product*, where
# the dotted form is correct — a file-wide substitution would fix this line and
# break those three, in the direction the naming canon actually warns about.
#
# What a program prints when announcing itself is the thing you type. It shipped
# as `sky.boss`, so `./mh --version` said `mind.head, version unknown`
# two lines from a `Usage: mh` that was right — and in an adopted tree that is
# two commands both claiming to report the version of one product and
# disagreeing, because they are answering different questions: this reports the
# REPOSITORY's version and the product's CLI reports the product's.
#
# It survived because the file contains no correct instance to copy from. click
# derives the usage line from `sys.argv[0]` itself, so the neighbouring
# correctness is the framework's, and a reader who checks `--help` sees the
# right answer and stops. mind.head's, from a tree where both commands exist.
@click.version_option(version=get_version(), prog_name="dev")
def cli() -> None:
    """sky.boss — One CLI for watching what other tools do, here and across these repos"""


#: Command groups are DISCOVERED, not listed.
#:
#: A hand-written import list here would be a registry — and the second half of
#: this project's tooling exists because forgetting to update a registry is
#: silent. A module that exports a click Group or Command whose name matches the
#: module (or the documented alias below) is registered by existing, which is the
#: same rule the test suite uses for markers.
#:
#: The alias map is for the few modules whose Python name cannot be the command
#: name (`test` shadows nothing useful; `test_cmds` avoids pytest collection).
_ALIASES = {"test_cmds": "test", "pr_train": "train"}


def _discover() -> None:
    """Register every command group in this package, by finding it.

    **This package never names itself.** `__name__` and `__path__` are what the
    interpreter already knows about the module it is executing, so the three
    places that used to spell `cli` as a literal now read the truth instead of
    repeating it. That is not tidiness — `cli` is the most collided-with package
    name in a Python monorepo, which is why `./dev` sets `PYTHONSAFEPATH=1`
    at all, and a shell that hardcodes the name is a shell that cannot be moved
    out of the way of the product it is shipped alongside.

    Reported by sky.boss, who had to move their own product out of `cli/` to
    adopt this template and then found the shell sitting in the name they
    vacated. The rename cost them 119 failing tests mid-flight and a `sed` whose
    worst artefact was `from cli import cli` becoming `from x import x` — the
    package and the click group share a name and only one of them was moving.
    Relative imports leave the group alone by construction.
    """
    import importlib
    import pkgutil

    package = sys.modules[__name__]

    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda m: m.name):
        name = info.name
        if name.startswith("_") or name == "helpers":
            continue
        module = importlib.import_module(f"{__name__}.{name}")
        command_name = _ALIASES.get(name, name)
        candidate = getattr(module, command_name, None) or getattr(module, name, None)
        if isinstance(candidate, click.Command):
            cli.add_command(candidate, name=command_name)


_discover()
