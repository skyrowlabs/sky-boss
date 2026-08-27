"""The roll-call — many projects, one answer.

**sb federates. It never owns.** Each project stays the authority on its own
state; this asks all of them and folds the answers together. There is no ledger
here, no history, no cache — and that is what keeps sb stateless. A central
store would be a *copy*, and a copy of a schedule that agents rewrite goes stale
without announcing it. Unreachability is visible; staleness is not.

**A source is an argv or a path.** Most projects have no CLI, and a contract
that required one would stall on exactly the young projects where visibility is
most wanted. A project declares where its status comes from and sb does not care
which kind it is — the reader is `sb data`'s, whole, in both cases.

**sb folds sources, not semantics.** No common status vocabulary, no cross-project
verdict, no totalling of anyone's `red`. sb does not get to decide what another
tool's word means — the same refusal [[highlight]] made about severity, one level
up. One block per project, each under its own name, in its own words.

**One project down is `partial`, never blank.** A roll-call that goes dark when a
single source fails would fail exactly when something is wrong. See [[roll-call]].
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import rich_click as click

from cli.helpers import SB_HOME
from cli.output import Result, emit

PROJECTS_FILE = "projects.toml"


@dataclass
class Project:
    """One declared source. Exactly one of `argv` / `path`, never both."""

    name: str
    argv: list[str] = field(default_factory=list)
    path: str = ""
    cwd: str = ""
    from_: str = "json"
    rows: str = ""
    cols: str = ""
    timeout: int = 60
    description: str = ""

    @property
    def source(self) -> str:
        """What this project is read from, for a warning that has to name it."""
        import shlex

        return shlex.join(self.argv) if self.argv else self.path


def home_file(home: Path | None = None) -> Path:
    return (home or SB_HOME) / PROJECTS_FILE


def read(home: Path | None = None) -> dict:
    """The raw TOML, or an empty mapping.

    An absent file degrades to nothing declared rather than raising — a fresh
    clone federates over no projects, and saying so every invocation is noise.
    The same rule `tools.toml` is read under.
    """
    path = home_file(home)
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"__error__": f"{path}: {exc}"}


def parse(raw: dict) -> tuple[list[Project], list[str]]:
    """Validate declarations. Pure — reads no file.

    **One bad entry must not cost the operator the other five.** Nothing here
    raises: a malformed project is skipped and named, which is the pattern
    `sb tools` already sets for a tool that would not load.
    """
    if "__error__" in raw:
        return [], [raw["__error__"]]

    projects: list[Project] = []
    problems: list[str] = []

    for name, body in (raw.get("project") or {}).items():
        problem = _check(name, body)
        if problem:
            problems.append(f"project {name!r}: {problem}")
            continue
        projects.append(
            Project(
                name=name,
                argv=[str(part) for part in body.get("argv", [])],
                path=str(body.get("path", "")),
                cwd=str(body.get("cwd", "")),
                from_=str(body.get("from", "json")),
                rows=str(body.get("rows", "")),
                cols=str(body.get("cols", "")),
                timeout=int(body.get("timeout", 60)),
                description=str(body.get("description", "")),
            )
        )

    return projects, problems


def _check(name: str, body) -> str | None:
    if not isinstance(body, dict):
        return "not a table"
    has_argv = bool(body.get("argv"))
    has_path = bool(body.get("path"))
    # Exactly one, and the refusal is deliberate rather than a precedence rule:
    # a project declaring both has said two different things about where its
    # truth lives, and picking one for them would be sb guessing which.
    if has_argv and has_path:
        return "declares both argv and path — a source is one or the other"
    if not has_argv and not has_path:
        return "declares neither argv nor path"
    if has_argv:
        argv = body["argv"]
        if not isinstance(argv, list) or not all(isinstance(p, str) for p in argv):
            return "argv must be a list of strings"
    if "timeout" in body and not isinstance(body["timeout"], int):
        return "timeout must be a whole number of seconds"
    return None


def load(home: Path | None = None) -> tuple[list[Project], list[str]]:
    return parse(read(home))


def ask(project: Project) -> Result:
    """One project's answer, or the reason it did not give one.

    **The reader is `sb data`'s, whole.** A command source is `_once`; a file
    source is the same parse path with the bytes read off disk instead of off a
    pipe. Neither grows its own notion of `--from`, of when a view is attached,
    or of what a failed read looks like — a second opinion about any of those is
    how two commands come to disagree about the same payload.
    """
    from cli import capture as capture_
    from cli.data import _once, parse_text

    if project.argv:
        return _once(
            tuple(project.argv),
            project.timeout,
            _expand(project.cwd) or None,
            project.cols or None,
            project.rows or None,
            None,
            False,
            project.from_,
        )

    result = Result()
    path = Path(_expand(project.path))
    fmt, problem = capture_.resolve(project.from_)
    if problem:
        result.ok = False
        result.data = {"error": problem}
        return result
    try:
        text = path.read_text()
    except OSError as exc:
        result.ok = False
        # A project that publishes a file and has not written one yet is the
        # normal early state, not an exception — it reports like any other
        # source that could not answer.
        result.data = {"source": str(path), "error": exc.strerror or str(exc)}
        return result

    meta = {"source": str(path)}
    return parse_text(
        text, meta, fmt, result, project.cols or None, project.rows or None, None, False
    )


def _expand(value: str) -> str:
    """`~` and `$VAR` in a declared path. The operator wrote this by hand in
    their own editor; making them spell out a home directory would be the tool
    being awkward about the one place a path is most natural."""
    import os

    return os.path.expandvars(os.path.expanduser(value)) if value else ""


@click.command(name="roll-call")
@click.option("--only", metavar="NAMES", help="Ask only these projects, comma-separated.")
@emit
def roll_call(only: str | None) -> Result:
    """Ask every declared project how it is, and fold the answers.

    An observe — a window may pin it and refresh it on a cadence. It runs each
    project's own status command; it never schedules, generates, or edits one.

        sb roll-call
        sb roll-call --only jam-sense

    Projects are declared in `$SB_HOME/projects.toml`, each naming an argv or a
    path. One project failing is `partial`, never blank.
    """
    result = Result()
    projects, problems = load()
    for problem in problems:
        result.warn(problem)

    wanted = {n.strip() for n in only.split(",")} if only else None
    if wanted:
        missing = wanted - {p.name for p in projects}
        if missing:
            raise click.UsageError(f"no such project: {', '.join(sorted(missing))}")
        projects = [p for p in projects if p.name in wanted]

    if not projects:
        # Nothing declared is not a failure. It is a fresh clone, and the answer
        # to "how are my projects" is honestly "you have not named any".
        result.data = {}
        if not problems:
            result.warn(f"no projects declared — see {home_file()}")
        return result

    blocks: dict = {}
    views: dict = {}
    for project in projects:
        answer = ask(project)
        if not answer.ok:
            # Named, never omitted. A roll-call that quietly drops the project
            # that could not answer is worse than one that says so, because the
            # silence looks exactly like health.
            reason = (answer.data or {}).get("error", "did not answer")
            result.warn(f"{project.name}: {reason}")
            result.partial = True
            blocks[project.name] = {"error": reason, "source": project.source}
            continue
        blocks[project.name] = answer.data
        if answer.view:
            views[project.name] = answer.view

    result.data = blocks
    # One view per block. Six independent payloads cannot share a column list,
    # and picking one project's would draw the other five wrong. Omitted when no
    # project produced one, so an envelope stays unshaped rather than empty.
    if views:
        result.view = {"blocks": views}
    return result


# Offered to an agent. `roll-call` reads only what the operator declared in
# `projects.toml` and takes no argv from its caller, which is the property that
# decides exposure — not "is it saved". See [[mcp]] round 1.
roll_call.sb_mcp = True
