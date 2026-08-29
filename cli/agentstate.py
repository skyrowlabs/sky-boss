"""The agent-state root — where the sibling repos' automation writes. See [[state-root]].

**sky.boss reads this root; it never writes into it and never assumes where it
is.** The producing repos each carry a default of their own, and sky.boss must
not copy it: a writer may hardcode a path because it lives there, where sky.boss
ships to machines with no such directory. A workspace layout baked into a
published tool is the same class of leak as a host name in a tracked file.

**Two levels and no default.** `SL_AGENT_LOGS` first — the same name the writers
honour, so one knob points the producers and the reader at the same scratch
directory — then `state_root` in `$SB_HOME/projects.toml`, then nothing. The
environment wins because the case that decides it is a redirected test run: if
the file won, sky.boss would carry on reading the real root while the producers
wrote to scratch, and report a ledger nothing was writing to. The file is the
fallback because a variable is a *snapshot* and a file is not: an env-only knob
would be frozen at launch for every long-lived window, so a `sb ui` open for
hours would hold what was set when it started while a fresh shell saw something
else. This is re-read at use. (A launcher-started window inheriting no shell
environment is a second reason and a weaker one — see [[state-root]] Notes.)

**Resolved at use, never at import.** `SB_HOME` and `SB_STATE` are module
constants because they are sky.boss's own. This one is read from a file the
operator edits under a pinned window, so it is a function and the next tick
picks up the edit. It is also the trap `agent-state.md` names by hand: a root
frozen at import is a root a test cannot redirect.

**No class names live here.** `log/`, `ledger/` and the rest are the seam's
vocabulary. This joins whatever it is handed, so it reads a shape rather than
one workspace's convention.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_ENV = "SL_AGENT_LOGS"
ROOT_KEY = "state_root"


@dataclass(frozen=True)
class Root:
    """The state root, and which of the two levels supplied it.

    `source` is reported rather than inferred. Two levels with no way to see
    which applied is the failure this was designed against — a long-lived
    `sb ui` holding what was set when it launched while a fresh shell sees
    something else, both correct and neither visible.
    """

    path: Path | None
    source: str = ""  # "SL_AGENT_LOGS", "projects.toml", or "" when undeclared

    def __bool__(self) -> bool:
        return self.path is not None


def root(home: Path | None = None) -> Root:
    """The declared root, or an undeclared one. Never raises, never defaults."""
    from cli.rollcall import _expand, read

    declared = os.environ.get(ROOT_ENV)
    if declared and declared.strip():
        return Root(Path(_expand(declared)), ROOT_ENV)

    value = read(home).get(ROOT_KEY)
    if isinstance(value, str) and value.strip():
        return Root(Path(_expand(value)), "projects.toml")
    return Root(None)


@dataclass(frozen=True)
class Found:
    """A project's state directory, or the reason there is not one.

    Both fields, rather than a union: the caller that reports a problem and the
    caller that uses a path are frequently the same caller, and a `None` with
    no sentence attached is how "nothing to follow" comes to mean four
    different things.
    """

    path: Path | None
    problem: str | None = None


def directory(slug: str, home: Path | None = None) -> Found:
    """`<root>/<slug>`, or a sentence naming what is wrong.

    **The failure worth designing around is not the derivation, it is that its
    failure is invisible.** An operator who writes `[project.jam]` for brevity
    gets a lookup in `<root>/jam/`, which is not there, which would report
    *nothing to follow* — the exact sentence a project that genuinely has no
    logs yet gets. So an absent directory lists what the root *does* hold,
    which is a directory read with no schema knowledge in it and makes a naming
    mismatch self-evident in one line.

    Deriving the slug is safe here in a way it was not for the writers, and the
    asymmetry is the reason: a writer runs inside one tree and cannot see the
    others, so it has no way to check a guess. A reader sees the whole root, so
    it can derive *and verify*.
    """
    found = root(home)
    if not found:
        return Found(
            None,
            f"no state root; set {ROOT_ENV} or {ROOT_KEY} in projects.toml",
        )

    base = found.path
    target = base / slug
    if target.is_dir():
        return Found(target)

    if not base.is_dir():
        return Found(None, f"state root {str(base)!r} is not a directory ({found.source})")

    siblings = sorted(child.name for child in base.iterdir() if child.is_dir())
    if not siblings:
        return Found(None, f"no state directory {slug!r}; the root is empty")
    return Found(
        None,
        f"no state directory {slug!r}; the root holds {', '.join(siblings)}",
    )


# ============================================================================
# The address form — <project>:<path>
# ============================================================================


def _split(target: str, home: Path | None = None) -> tuple[str, str] | None:
    """`<name>:<rest>` where `<name>` is a **declared project**, or None.

    The lookup is what makes this a resolution rather than a guess: the set of
    project names is closed and operator-authored, exactly like the formats
    `--from <name>` resolves against. A prefix matching no declared project is
    not a project reference, and the whole string stays the literal path it
    always was — so this can never take an address away from someone who was
    not asking for one.
    """
    name, sep, rest = target.partition(":")
    if not sep or not name:
        return None
    from cli.rollcall import load

    projects, _ = load(home)
    if name not in {project.name for project in projects}:
        return None
    return name, rest


def is_project_form(target: str, home: Path | None = None) -> bool:
    """Does this name a declared project's state directory?

    Asked by `is_file_form` in both commands, because a reference with no
    slash — `jam-sense:runs.jsonl` — would otherwise fall through to the
    argv side and be reported as a missing command.
    """
    if Path(target).exists():
        return False
    return _split(target, home) is not None


def resolve(target: str, home: Path | None = None) -> tuple[str, str | None]:
    """A typed path down to a real one: `(path, None)` or `(target, reason)`.

    **An existing file always wins**, so a directory genuinely named
    `jam-sense:log` resolves to itself. Same precedence `is_file_form` applies
    when a bare word is both an executable and a file: the concrete thing wins,
    and `./name` is how you are explicit.

    Anything that is not a project reference is returned untouched. This is on
    the path of every file read, so it has to be inert for the ordinary case.
    """
    if Path(target).exists():
        return target, None
    split = _split(target, home)
    if split is None:
        return target, None

    slug, rest = split
    found = directory(slug, home)
    if found.path is None:
        return target, found.problem
    if not rest:
        return str(found.path), None
    return str(found.path / rest), None


def unresolved_hint(target: str, home: Path | None = None) -> str:
    """The clause a failed *path* is owed when it looks like a project
    reference and no such project is declared. Empty when it does not.

    `resolve` leaves an undeclared prefix alone on purpose — the set of project
    names is closed, so a prefix outside it is not a reference and the string
    stays the literal path it always was. That is right, and on its own it
    produces `no such file: jam:ledger/runs.jsonl`: a path error naming a file
    that could never exist, which is the "wrong but looks right" failure in the
    one place this feature was built to remove it.

    So the file error stays true and gains the reason the other reading did not
    happen — the same courtesy `capture.resolve` extends when it lists the
    formats that do exist. Worded as an addition rather than a replacement,
    because a genuine path that merely contains a colon is still what the
    operator typed.
    """
    name, sep, _ = target.partition(":")
    if not sep or not name or "/" in name:
        return ""
    from cli.rollcall import load

    projects, _ = load(home)
    names = sorted(project.name for project in projects)
    if name in names:
        return ""
    if not names:
        return f" — and no projects are declared, so {name!r} is not a project reference"
    return f" — and no project {name!r} is declared (declared: {', '.join(names)})"
