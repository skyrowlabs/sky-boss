"""What the operator is asked and owes, beyond a plain decision. See [[command-deck]] round 18.

A row in HUMAN DECISIONS has a kind. `choice`, `action` and `notice` are written by
an agent and live in the decisions book, so their numbers hold still. `asked` and
`prose` come from Claude Code's hooks, come and go on their own, and live in the
`asks` book, where removing one renumbers nothing an agent has been told.

**An action closes by observation where it can.** An `--until` test names the state
that ends it, read here from git or `gh`, so an agent's word does not close it.

**Held state is computed.** Nobody asks for it, so it is read per repo and cached by
the deck's sweep. A repo that could not be read says so, because a count alone would
read *could not see* as *clear*.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from skyboss import helpers
from skyboss import todos as todos_
from skyboss.helpers import child_env

#: How long a hook's row outlives a tab not reading `waiting`: the registry can lag the hook.
ASK_GRACE = 20.0
#: How long a read of git or `gh` may take.
READ_TIMEOUT = 15
SHELL_WORDS = {"|", "||", "&", "&&", ";", ">", ">>", "<", "<<"}
UNTIL = re.compile(
    r"^(?:pr:(?P<pr>\d+)(?:@(?P<head>[0-9a-f]{7,40}))?|pushed:(?P<sha>[0-9a-f]{7,40})|gone:(?P<branch>[\w./][\w./-]*))$"
)

Reader = Callable[..., subprocess.CompletedProcess]


def read(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    """One read of git or `gh`, in `cwd`. A timeout or a missing tool comes back as a failure."""
    try:
        return subprocess.run(
            args, cwd=cwd, env=child_env(), capture_output=True, text=True, timeout=READ_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(args, 127, "", str(exc))


def printable(text: str) -> bool:
    """Whether every character draws: a control character could hide a command from the operator."""
    return text.isprintable()


def parse_run(text: str) -> list[str]:
    """`--run`'s words as an argv. Raises `ValueError` for shell syntax, as nothing runs in a shell."""
    try:
        argv = shlex.split(text)
    except ValueError as exc:
        raise ValueError(f"--run does not parse — {exc}") from exc
    if not argv:
        raise ValueError("--run needs a command")
    if any(word in SHELL_WORDS for word in argv):
        raise ValueError("--run is one command with no shell, so a pipe, chain or redirect cannot run")
    if not all(printable(word) for word in argv):
        raise ValueError("--run holds a control character")
    return argv


def check_until(until: str) -> str:
    """`until` if it is a test this module can read. Raises `ValueError` naming the set."""
    if not UNTIL.match(until):
        raise ValueError("--until is one of pr:<n>, pr:<n>@<sha>, pushed:<sha> or gone:<branch>")
    return until


@dataclass
class Seen:
    """What an action's test found: at most one of the three is set."""

    closed: str = ""
    stale: str = ""
    unknown: str = ""

    @property
    def note(self) -> str:
        return f"stale: {self.stale}" if self.stale else f"could not check: {self.unknown}" if self.unknown else ""


def _said(answer: subprocess.CompletedProcess) -> str:
    said = (answer.stderr or answer.stdout or "").strip()
    return said.splitlines()[0][:80] if said else f"exit {answer.returncode}"


def observe(until: str, cwd: str, reader: Reader = read) -> Seen:
    """What `until` finds now. Nothing set means the action is still open and still good."""
    match = UNTIL.match(until)
    if match is None:
        return Seen(unknown=f"no such test {until!r}")
    if match["pr"]:
        answer = reader(["gh", "pr", "view", match["pr"], "--json", "state,headRefOid"], cwd)
        if answer.returncode != 0:
            return Seen(unknown=_said(answer))
        try:
            pull = json.loads(answer.stdout)
        except ValueError:
            return Seen(unknown="gh printed no JSON")
        if pull.get("state") == "MERGED":
            return Seen(closed=f"PR #{match['pr']} merged")
        if pull.get("state") == "CLOSED":
            return Seen(closed=f"PR #{match['pr']} closed unmerged")
        head = str(pull.get("headRefOid") or "")
        if match["head"] and not head.startswith(match["head"]):
            return Seen(stale=f"head moved to {head[:7]}")
        return Seen()
    if match["sha"]:
        answer = reader(["git", "branch", "-r", "--contains", match["sha"]], cwd)
        if answer.returncode != 0:
            return Seen(unknown=_said(answer))
        found = answer.stdout.split()
        return Seen(closed=f"{match['sha'][:7]} is on {found[0]}") if found else Seen()
    answer = reader(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{match['branch']}"], cwd)
    if answer.returncode == 0:
        return Seen()
    return Seen(closed=f"{match['branch']} is gone") if answer.returncode == 1 else Seen(unknown=_said(answer))


def sweep_actions(session: str, agent: str, reader: Reader = read) -> int:
    """Read each open action's test on `agent`'s list, closing what is done. How many closed."""
    todo = todos_.load(session, agent, todos_.DECISIONS)
    if todo is None:
        return 0
    changed = closed = 0
    for item in todo.items:
        if item.done or item.kind != todos_.ACTION or not item.until:
            continue
        seen = observe(item.until, item.cwd, reader)
        if seen.closed:
            item.done, item.closed, item.ruling, item.untold = True, todos_.now_iso(), seen.closed, True
            item.state = ""
            changed, closed = changed + 1, closed + 1
        elif item.state != seen.note:
            item.state = seen.note
            changed += 1
    if changed:
        todos_.save(todo)
    return closed


# Hook rows: the `asks` book holds at most one of each kind per agent.


def _one_line(text: str, room: int = 200) -> str:
    line = todos_.clean(text)
    return line if len(line) <= room else line[: room - 1] + "…"


def prompt_text(payload: dict) -> str:
    """What a tab stopped at a prompt is waiting on, from `PermissionRequest`."""
    tool = str(payload.get("tool_name") or "a tool")
    given = payload.get("tool_input")
    given = given if isinstance(given, dict) else {}
    if tool == "AskUserQuestion":
        questions = given.get("questions") or []
        said = [str(q.get("question") or "") for q in questions if isinstance(q, dict)]
        return _one_line(" / ".join(word for word in said if word) or "a question")
    command = given.get("command") or given.get("file_path") or ""
    return _one_line(f"{tool}: {command}" if command else f"{tool} needs permission")


def last_question(message: str) -> str:
    """The sentence a turn ended on, when it ended on a question. Empty otherwise."""
    tail = message.rstrip().rstrip("*_`\"')")
    if not tail.endswith("?"):
        return ""
    return _one_line(re.split(r"(?<=[.!?:])\s+|\n", tail)[-1])


def _put(session: str, agent: str, kind: str, text: str) -> None:
    todo = todos_.load(session, agent, todos_.ASKS) or todos_.TodoList(agent, session, book=todos_.ASKS)
    todo.items = [item for item in todo.items if item.kind != kind]
    todo.items.append(todos_.Item(text=text, added=todos_.now_iso(), kind=kind))
    todos_.save(todo)


def drop(session: str, agent: str, kinds: tuple[str, ...]) -> bool:
    """Remove `agent`'s hook rows of `kinds`. Whether any went."""
    todo = todos_.load(session, agent, todos_.ASKS)
    if todo is None:
        return False
    kept = [item for item in todo.items if item.kind not in kinds]
    if len(kept) == len(todo.items):
        return False
    todo.items = kept
    todos_.save(todo)
    return True


def denied(session: str, agent: str, payload: dict) -> None:
    """A permission denial, as an action row. Its command is offered only when it needs no shell."""
    given = payload.get("tool_input")
    given = given if isinstance(given, dict) else {}
    command = str(given.get("command") or "")
    tool = str(payload.get("tool_name") or "a tool")
    text = _one_line(f"denied: {command or tool}")
    todo = todos_.load(session, agent, todos_.DECISIONS)
    if todo is not None and any(item.text == text and not item.done for item in todo.items):
        return
    try:
        argv = parse_run(command) if command else []
    except ValueError:
        argv = []
    cwd = str(payload.get("cwd") or "")
    todos_.add(session, agent, text, todos_.DECISIONS, kind=todos_.ACTION, run=argv, cwd=cwd)


def on_hook(session: str, agent: str, payload: dict) -> None:
    """One Claude Code hook event from `agent`'s tab, into the queue."""
    event = payload.get("hook_event_name")
    if event == "PermissionRequest":
        _put(session, agent, todos_.ASKED, prompt_text(payload))
    elif event == "PermissionDenied":
        denied(session, agent, payload)
    elif event == "UserPromptSubmit":
        drop(session, agent, (todos_.ASKED, todos_.PROSE))
    elif event == "Stop":
        drop(session, agent, (todos_.ASKED, todos_.PROSE))
        question = last_question(str(payload.get("last_assistant_message") or ""))
        if question:
            _put(session, agent, todos_.PROSE, question)


def settle(session: str, agent: str, state: str, waiting: str, now: datetime) -> None:
    """Drop an `asked` row once its tab stopped waiting. A refused prompt fires no hook, so this closes it."""
    if state == waiting:
        return
    todo = todos_.load(session, agent, todos_.ASKS)
    for item in todo.items if todo else []:
        if item.kind != todos_.ASKED:
            continue
        try:
            age = (now - datetime.fromisoformat(item.added)).total_seconds()
        except ValueError:
            age = ASK_GRACE
        if age >= ASK_GRACE:
            drop(session, agent, (todos_.ASKED,))
        return


# Held state: read per repo by the sweep, drawn from its cache.


def held_path(session: str) -> Path:
    return helpers.STATE_DIR / "deck" / session / "held.json"


def _unpushed(repo: str, reader: Reader) -> tuple[list[str], str]:
    branches = reader(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"], repo)
    if branches.returncode != 0:
        return [], _said(branches)
    rows: list[str] = []
    for branch in branches.stdout.split():
        count = reader(["git", "rev-list", "--count", branch, "--not", "--remotes"], repo)
        if count.returncode != 0:
            return rows, _said(count)
        if count.stdout.strip() not in ("", "0"):
            rows.append(f"{count.stdout.strip()} unpushed on {branch}")
    return rows, ""


def _green(pull: dict) -> bool:
    checks = pull.get("statusCheckRollup") or []
    good = {"SUCCESS", "SKIPPED", "NEUTRAL"}
    return bool(checks) and all((c.get("conclusion") or c.get("state")) in good for c in checks)


def _pulls(repo: str, reader: Reader) -> tuple[list[str], str]:
    answer = reader(["gh", "pr", "list", "--state", "open", "--json", "number,isDraft,statusCheckRollup"], repo)
    if answer.returncode != 0:
        return [], _said(answer)
    try:
        pulls = json.loads(answer.stdout)
    except ValueError:
        return [], "gh printed no JSON"
    return [f"PR #{p['number']} green, unmerged" for p in pulls if not p.get("isDraft") and _green(p)], ""


def _alerts(repo: str, reader: Reader) -> tuple[list[str], str]:
    path = "repos/{owner}/{repo}/dependabot/alerts?state=open&per_page=100"
    answer = reader(["gh", "api", path, "--jq", "length"], repo)
    if answer.returncode != 0:
        return [], _said(answer)
    count = answer.stdout.strip()
    return ([f"{count} open alert(s)"] if count not in ("", "0") else []), ""


def held_of(repo: str, reader: Reader = read) -> dict:
    """What `repo` holds, and which of its reads failed."""
    name = Path(repo).name
    rows: list[str] = []
    unread: list[str] = []
    for label, source in (("branches", _unpushed), ("PRs", _pulls), ("alerts", _alerts)):
        found, why = source(repo, reader)
        rows += found
        if why:
            unread.append(f"{label}: {why}")
    return {"repo": name, "rows": rows, "unread": unread}


def write_held(session: str, repos: list[dict]) -> None:
    path = held_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".held.", suffix=".json")
    with os.fdopen(handle, "w") as out:
        json.dump({"checked": datetime.now(timezone.utc).isoformat(), "repos": repos}, out, indent=1)
    os.replace(temp, path)


def read_held(session: str) -> dict | None:
    """The sweep's last reading, or None when there is none to show."""
    try:
        raw = json.loads(held_path(session).read_text())
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None
