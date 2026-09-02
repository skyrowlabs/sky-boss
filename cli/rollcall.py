"""The roll-call — many projects, one answer.

**sky.boss federates. It never owns.** Each project stays the authority on its own
state; this asks all of them and folds the answers together. There is no ledger
here, no history, no cache — and that is what keeps sky.boss stateless. A central
store would be a *copy*, and a copy of a schedule that agents rewrite goes stale
without announcing it. Unreachability is visible; staleness is not.

**A source is an argv or a path.** Most projects have no CLI, and a contract
that required one would stall on exactly the young projects where visibility is
most wanted. A project declares where its status comes from and sky.boss does not care
which kind it is — the reader is `sb data`'s, whole, in both cases.

**sky.boss folds sources, not semantics.** No common status vocabulary, no cross-project
verdict, no totalling of anyone's `red`. sky.boss does not get to decide what another
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

# The keys a project may declare, and the tables the file may hold. Both sets
# are closed and both are small, which is what makes naming an unknown one
# cheap rather than officious.
#
# Spelled out rather than derived from `Project`'s fields because two of them
# do not correspond: `name` is the table's own key, and `from_` carries a
# trailing underscore to clear the keyword. `tests/test_rollcall.py` walks the
# dataclass against this set, so a field added without a key here fails there
# rather than becoming a declaration sky.boss silently ignores.
PROJECT_KEYS = frozenset(
    {"argv", "path", "cwd", "from", "rows", "cols", "timeout", "description", "schedule", "history"}
)

# The keys a `[project.X.schedule]` table may declare. `name` is the only one
# without a sensible absence: a row with nothing to call it cannot be drawn.
# The rest are optional because a provider that supplies no `next` is a state
# the view has a word for, and inventing one would be sky.boss computing a
# fire time from a cron expression — the thing [[schedule]] exists to refuse.
SCHEDULE_KEYS = frozenset({"rows", "name", "schedule", "next", "last"})

# The keys a `[project.X.history]` table may declare. Three are required and the
# reason is the same each time — there is no honest word for their absence.
# Without `path` there is no file; without `when` the rows can only be ordered by
# their position in the file, which is sky.boss inferring that an append-only
# ledger is chronological; without `name` a row has nothing to call what ran.
#
# `from` defaults to `jsonl` rather than being required, and that is a default
# and not an inference: a history is a file of records, `jsonl` is what that
# means, and a wrong guess fails **loudly** in `parse_text` — *no line is a JSON
# object* — rather than producing a plausible wrong table. See [[history]].
HISTORY_KEYS = frozenset({"path", "from", "when", "name", "outcome"})
HISTORY_REQUIRED = ("path", "when", "name")
TOP_LEVEL_TABLES = frozenset({"project"})

# Top-level keys that are not tables. `state_root` is read by cli/agentstate.py
# rather than here — this set exists so the unknown-table check below does not
# report the operator's own declaration as a mistake. See [[state-root]].
TOP_LEVEL_KEYS = frozenset({"state_root"})


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
    # The mapping from this project's payload onto the four schedule fields, or
    # None when it declares none. **A project with no schedule is the common
    # case and is not an error** — it is counted and named by the view rather
    # than drawn as a blank row. See [[schedule]].
    schedule: dict[str, str] | None = None
    # Where this project's run ledger is and what its fields are called, or None
    # when it publishes none. A project with no history is the common case and
    # is counted rather than drawn, exactly as one with no schedule is.
    # See [[history]].
    history: dict[str, str] | None = None
    # Which slot on the surface's project ramp this one draws in — assigned at
    # declaration, stable for the life of the file. See `SHADES` below.
    shade: int = 0

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

    # A typo in a table name used to cost the operator the whole file in
    # silence: `[projct.jam-sense]` parsed clean, declared nothing, and left
    # `roll-call` saying "no projects declared" — the same sentence a fresh
    # clone gets. Named, never fatal: an unfamiliar table is reported and the
    # rest of the file is read, so this can never be the reason a good
    # declaration stops working.
    for table in raw:
        if table in TOP_LEVEL_TABLES or table in TOP_LEVEL_KEYS or table == "__error__":
            continue
        kind = "key" if not isinstance(raw[table], dict) else "table"
        problems.append(f"unknown {kind} {table!r} — ignored")

    for name, body in (raw.get("project") or {}).items():
        problem = _check(name, body)
        if problem:
            problems.append(f"project {name!r}: {problem}")
            continue
        # After `_check`, so a project that is wrong in a way that stops it
        # loading is reported once for that rather than twice.
        for key in _unknown_keys(body):
            problems.append(f"project {name!r}: unknown key {key!r} — ignored")
        for key in _unknown_schedule_keys(body):
            problems.append(f"project {name!r}: schedule has unknown key {key!r} — ignored")
        for key in _unknown_table_keys(body, "history", HISTORY_KEYS):
            problems.append(f"project {name!r}: history has unknown key {key!r} — ignored")
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
                schedule=(
                    {k: str(v) for k, v in body["schedule"].items()}
                    if isinstance(body.get("schedule"), dict)
                    else None
                ),
                history=(
                    {k: str(v) for k, v in body["history"].items()}
                    if isinstance(body.get("history"), dict)
                    else None
                ),
            )
        )

    for slot, project in enumerate(projects):
        project.shade = slot % SHADES

    return projects, problems


# How many distinguishable steps the surface can draw a project in.
#
# **Not a palette, and not four roles.** The design system holds four hues and
# sky.boss spends all four, so inventing a fifth is a brand decision and not
# this tool's — but the three that are free here carry *meaning*: `ok` is green,
# `warn` is what this very screen already uses for a late job, and `danger` is
# red. A project coloured `warn` would be indistinguishable from a job that has
# missed its window, and a project coloured `danger` would read as broken. So
# identity is drawn as steps along the brand rather than as borrowed roles: no
# new hue, no stolen meaning, and the semantic colours stay semantic.
#
# **Assigned by declaration order, not by name.** A hash of the name would be
# stable too and would scatter neighbouring projects across the ramp for no
# reason; order means the first two projects are always the two furthest apart,
# which is the case that matters. Adding a project to the middle of the file
# reshuffles the ones after it — accepted, because the alternative is a colour
# nobody can predict from reading the file.
SHADES = 6


def _unknown_keys(body: dict) -> list[str]:
    """Keys sky.boss does not read, in declaration order.

    Reported rather than refused, and the wording says *ignored* rather than
    *invalid* on purpose: that sentence stays true if an older sky.boss ever
    reads a file written for a newer one, so the check cannot become the thing
    that rejects a file it merely does not understand yet.
    """
    return [key for key in body if key not in PROJECT_KEYS]


def _unknown_schedule_keys(body: dict) -> list[str]:
    """Same contract as `_unknown_keys`, one table down: reported and ignored,
    never fatal, so an older sky.boss reading a newer file is not the thing that
    rejects it."""
    return _unknown_table_keys(body, "schedule", SCHEDULE_KEYS)


def _unknown_table_keys(body: dict, table: str, allowed: frozenset) -> list[str]:
    """The same check for any sub-table, so the second one cannot drift from the
    first. Written when `history` arrived and `schedule` had been alone: two
    copies of one rule is how the wording of the two reports comes apart."""
    found = body.get(table)
    if not isinstance(found, dict):
        return []
    return [key for key in found if key not in allowed]


def _check(name: str, body) -> str | None:
    if not isinstance(body, dict):
        return "not a table"
    has_argv = bool(body.get("argv"))
    has_path = bool(body.get("path"))
    # Exactly one, and the refusal is deliberate rather than a precedence rule:
    # a project declaring both has said two different things about where its
    # truth lives, and picking one for them would be sky.boss guessing which.
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
    if "schedule" in body:
        table = body["schedule"]
        if not isinstance(table, dict):
            return "schedule must be a table"
        if not all(isinstance(v, str) for v in table.values()):
            return "every schedule mapping must be a field name"
        # `name` is the one field a row cannot do without: everything else has a
        # word for its absence, and a row with nothing to call it has none.
        if not table.get("name"):
            return "schedule must name the field its rows are called by"
    if "history" in body:
        table = body["history"]
        if not isinstance(table, dict):
            return "history must be a table"
        if not all(isinstance(v, str) for v in table.values()):
            return "every history mapping must be a field name"
        missing = [key for key in HISTORY_REQUIRED if not table.get(key)]
        if missing:
            return f"history must declare {', '.join(missing)}"
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
