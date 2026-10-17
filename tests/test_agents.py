"""`sb agents` — who is running right now. See [[agent-sessions]].

**The suite never reads the operator's real registry.** `~/.claude/sessions` is a
fourth environment beside `SB_STATE`, `SB_HOME` and `SL_AGENT_LOGS`, and it has
no sky.boss-owned knob to redirect: the adapter resolves it from `Path.home()`.
So every test here either constructs the adapter with its own directory or
replaces `providers()`, and none asserts a global fact that the machine could
answer differently from a runner. A test whose environment differs from CI's is
a test about your machine.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from click.testing import CliRunner

from skyboss import cli
from skyboss.agents import (
    CannotTell,
    Claude,
    Scan,
    Session,
    alive,
    claims,
    empty_reason,
    epoch_ms,
    fold,
    git_common_dir,
    order,
    proc_start,
    rows_of,
    view_of,
)

#: Every test here is host-side and needs no services up.
pytestmark = [pytest.mark.unit]

LIVE = "4242"


def a_proc(root, pid: int, start: str = LIVE, comm: str = "claude (worker) x"):
    """A `/proc/<pid>/stat` with field 22 set.

    The comm carries spaces *and* a nested `)` on purpose: that is the whole
    reason the reader cannot be a `split()`, and a fixture with a tidy name
    would let the naive implementation pass.
    """
    entry = root / str(pid)
    entry.mkdir(parents=True)
    fields = ["0"] * 18 + [start] + ["0"] * 8
    (entry / "stat").write_text(f"{pid} ({comm}) S " + " ".join(fields) + "\n")
    return root


def a_record(directory, pid: int, **over):
    directory.mkdir(parents=True, exist_ok=True)
    record = {
        "sessionId": f"id-{pid}",
        "pid": pid,
        "procStart": LIVE,
        "name": f"session-{pid}",
        "cwd": f"/src/p{pid}",
        "status": "idle",
        "startedAt": 1788229475837,
    }
    record.update(over)
    (directory / f"{pid}.json").write_text(json.dumps(record))
    return record


# ============================================================================
# Liveness — the two fields, and the third answer
# ============================================================================


def test_field_22_survives_a_comm_with_spaces_and_parentheses(tmp_path):
    """A process named `(claude (worker) x)` is not exotic — an executable name
    may hold anything, and every field before it is unreachable by position."""
    a_proc(tmp_path, 7, start="991")
    assert proc_start(7, tmp_path) == "991"


def test_a_live_record_is_reported(tmp_path):
    proc = a_proc(tmp_path / "proc", 7)
    a_record(tmp_path / "s", 7)
    sessions = Claude(directory=tmp_path / "s", proc=proc).scan().sessions
    assert [s.name for s in sessions] == ["session-7"]


def test_a_stale_record_on_a_recycled_pid_is_not_reported(tmp_path):
    """**The headline defect this feature exists to avoid.** The PID is live —
    something is running under it — and it is not what wrote the record. A
    reader that trusts the PID alone reports a dead session as running, which is
    *worked fine, told nobody* in its most confident form."""
    proc = a_proc(tmp_path / "proc", 7, start="99999")  # the kernel reused 7
    a_record(tmp_path / "s", 7, procStart=LIVE)  # the record pinned the old one
    scan = Claude(directory=tmp_path / "s", proc=proc).scan()
    assert scan.sessions == []
    # Counted as looked-at, so the empty answer can say it looked.
    assert scan.read == 1
    # Not a *problem*: a stale file after a session ends is the normal aftermath.
    assert scan.problems == []


def test_a_pid_that_is_gone_is_dead_not_unverified(tmp_path):
    proc = tmp_path / "proc"
    a_proc(proc, 9)
    assert alive(7, LIVE, proc) is False


def test_no_proc_at_all_is_cannot_tell_rather_than_dead(tmp_path):
    """Collapsing `None` into `False` would report a machine sky.boss cannot
    inspect as a machine with nothing running."""
    assert alive(7, LIVE, tmp_path / "nowhere") is None


def test_a_record_that_pinned_no_start_tick_is_cannot_tell(tmp_path):
    proc = a_proc(tmp_path / "proc", 7)
    assert alive(7, "", proc) is None


def test_an_unverified_session_is_drawn_and_counted(tmp_path):
    """Drawn, because the record is evidence; counted, because a row sky.boss
    could not verify looks exactly like one it did."""
    a_record(tmp_path / "s", 7)
    scan = Claude(directory=tmp_path / "s", proc=tmp_path / "nowhere").scan()
    assert [s.name for s in scan.sessions] == ["session-7"]
    assert scan.unverified == 1


# ============================================================================
# Degrading — every path silent, named, and never an empty success
# ============================================================================


def test_an_absent_registry_is_silent(tmp_path):
    """Not present is the common case — nobody has five agent CLIs installed —
    so the adapter says nothing at all about it."""
    scan = Claude(directory=tmp_path / "gone", proc=tmp_path).scan()
    assert scan.sessions == [] and scan.problems == []
    assert scan.present is False and scan.read == 0


def test_an_unreadable_record_is_named_and_the_others_are_still_read(tmp_path):
    proc = a_proc(tmp_path / "proc", 7)
    a_proc(proc, 8)
    directory = tmp_path / "s"
    a_record(directory, 7)
    (directory / "8.json").write_text("{not json")
    scan = Claude(directory=directory, proc=proc).scan()
    assert [s.name for s in scan.sessions] == ["session-7"]
    assert len(scan.problems) == 1 and "8.json" in scan.problems[0]
    assert scan.read == 2


def test_a_record_that_is_not_a_mapping_is_named(tmp_path):
    directory = tmp_path / "s"
    directory.mkdir()
    (directory / "8.json").write_text("[1, 2]")
    scan = Claude(directory=directory, proc=tmp_path).scan()
    assert scan.sessions == [] and len(scan.problems) == 1


def test_a_record_with_no_session_id_or_pid_is_named(tmp_path):
    """Without these two a row cannot be identified or checked, so it is skipped
    and named rather than drawn as a session nobody can find."""
    proc = a_proc(tmp_path / "proc", 7)
    directory = tmp_path / "s"
    a_record(directory, 7, sessionId="")
    scan = Claude(directory=directory, proc=proc).scan()
    assert scan.sessions == [] and len(scan.problems) == 1


def test_a_null_status_draws_empty_and_raises_no_warning(tmp_path):
    """One of the live records carries `null` here today, from the `sdk-cli`
    entrypoint. An empty cell beside `busy` and `idle` already reads as
    *unknown*; a warning per invocation about a field the provider chose not to
    set would be noise."""
    proc = a_proc(tmp_path / "proc", 7)
    a_record(tmp_path / "s", 7, status=None)
    scan = Claude(directory=tmp_path / "s", proc=proc).scan()
    assert scan.sessions[0].status == ""
    assert scan.problems == []


def test_the_glob_ignores_everything_that_is_not_a_record(tmp_path):
    """`.key` files sit beside the JSON, and arrived after the spec was
    written. An internal format with no contract will do that again."""
    proc = a_proc(tmp_path / "proc", 7)
    directory = tmp_path / "s"
    a_record(directory, 7)
    (directory / "7.abc.key").write_text("not json at all")
    scan = Claude(directory=directory, proc=proc).scan()
    assert len(scan.sessions) == 1 and scan.problems == []
    assert scan.read == 1


# ============================================================================
# The fold
# ============================================================================


def at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=timezone.utc)


class Fake:
    """An adapter with no filesystem under it — which is the property that makes
    the fold's ordering and tally testable at all."""

    def __init__(self, provider, sessions=(), problems=(), present=True, read=0):
        self.provider = provider
        self._scan = Scan(
            provider=provider,
            sessions=list(sessions),
            problems=list(problems),
            present=present,
            read=read,
        )

    def scan(self):
        return self._scan


def test_the_fold_orders_oldest_first_across_providers():
    """Oldest first, because the session that has been going longest is the one
    whose context is nearest the bottom."""
    old = Session(provider="a", id="1", name="old", started=at(100))
    new = Session(provider="b", id="2", name="new", started=at(900))
    sessions, _, _ = fold([Fake("a", [new]), Fake("b", [old])])
    assert [s.name for s in sessions] == ["old", "new"]


def test_a_session_with_no_start_time_sorts_last():
    """Among rows ordered by time, a row with no time has nowhere honest to sit,
    and putting it first makes the least certain thing look the most imminent."""
    dated = Session(provider="a", id="1", name="dated", started=at(100))
    undated = Session(provider="a", id="2", name="undated")
    assert [s.name for s in order([undated, dated])] == ["dated", "undated"]


def test_the_fold_tallies_the_looking_across_providers():
    _, _, tally = fold([Fake("a", present=False), Fake("b", present=True, read=3)])
    assert tally.present is True and tally.read == 3


def test_the_fold_keeps_every_provider_problem():
    _, problems, _ = fold([Fake("a", problems=["a: bad"]), Fake("b", problems=["b: bad"])])
    assert problems == ["a: bad", "b: bad"]


# ============================================================================
# Timestamps
# ============================================================================


def test_epoch_milliseconds_become_an_instant():
    assert epoch_ms(1788229475837) == datetime(2026, 9, 1, 2, 24, 35, 837000, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", [None, 0, "", "later", [], float("nan")])
def test_a_start_time_that_is_not_a_number_is_absent_not_an_error(value):
    assert epoch_ms(value) is None


# ============================================================================
# The envelope
# ============================================================================


def test_the_view_is_authored_and_hides_identity_without_dropping_it():
    """Hidden rather than dropped: a machine reading the envelope still gets the
    id and the pid. A view describes; it never filters."""
    rows = rows_of([Session(provider="a", id="x", name="n", started=at(0))], at(60))
    view = view_of(rows)
    assert view["authored"] is True
    assert [c["key"] for c in view["columns"]] == ["provider", "name", "status", "up", "cwd"]
    assert view["hidden"] == ["id", "pid", "started", "claim"]
    assert rows[0]["id"] == "x" and rows[0]["up"] == "1m"


def test_an_absent_registry_and_an_empty_one_say_different_things():
    """Three endings for one empty table, because they are three different
    facts — and a bare empty table would have implied the third for all of
    them."""
    absent = empty_reason(Scan(provider="", present=False), 1)
    empty = empty_reason(Scan(provider="", present=True), 1)
    ended = empty_reason(Scan(provider="", present=True, read=4), 1)
    assert absent != empty != ended != absent
    assert "no registry present" in absent
    assert "registry present and empty" in empty
    assert "4 record(s) read, none live" in ended


def test_the_command_says_which_kind_of_empty_it_is(monkeypatch, said):
    monkeypatch.setattr("skyboss.agents.providers", lambda: [Fake("claude", present=False)])
    result = CliRunner().invoke(cli, ["agents"])
    assert result.exit_code == 0
    assert "no registry present" in said(result)


def test_only_refuses_a_provider_that_does_not_exist(monkeypatch, said):
    monkeypatch.setattr("skyboss.agents.providers", lambda: [Fake("claude")])
    result = CliRunner().invoke(cli, ["agents", "--only", "cursor"])
    assert result.exit_code == 2
    assert "no such provider: cursor" in said(result)


def test_only_narrows_to_the_named_provider(monkeypatch):
    a = Session(provider="a", id="1", name="a-one", started=at(100))
    b = Session(provider="b", id="2", name="b-one", started=at(200))
    monkeypatch.setattr("skyboss.agents.providers", lambda: [Fake("a", [a]), Fake("b", [b])])
    result = CliRunner().invoke(cli, ["--json", "agents", "--only", "a"])
    assert result.exit_code == 0
    assert [r["name"] for r in json.loads(result.stdout)["data"]] == ["a-one"]


def test_an_unverified_row_is_reported_in_the_envelope(monkeypatch, said):
    session = Session(provider="a", id="1", name="one", started=at(100))
    monkeypatch.setattr(
        "skyboss.agents.providers",
        lambda: [Fake("a", [session], present=True, read=1)],
    )
    from skyboss import agents as agents_

    def scan_with_unverified(self=None):
        scan = Scan(provider="a", sessions=[session], present=True, read=1, unverified=1)
        return scan

    monkeypatch.setattr(agents_.providers()[0].__class__, "scan", scan_with_unverified)
    result = CliRunner().invoke(cli, ["agents"])
    assert "drawn unverified" in said(result)


# ============================================================================
# Claims — round 3
# ============================================================================


def in_dir(ident: str, cwd: str) -> Session:
    return Session(provider="a", id=ident, name=ident, cwd=cwd, started=at(int(ident)))


def test_sessions_sharing_a_repository_share_a_letter_and_a_lone_one_has_none():
    sessions = [in_dir("1", "/r1/a"), in_dir("2", "/lone"), in_dir("3", "/r1/b")]
    repo = {"/r1/a": "/r1/.git", "/r1/b": "/r1/.git", "/lone": "/lone/.git"}
    letters, unknown = claims(sessions, probe=repo.get)
    assert letters == {"1": "A", "3": "A"} and unknown == 0


def test_letters_run_in_session_order_so_a_is_the_claim_held_longest():
    sessions = [in_dir(str(n), cwd) for n, cwd in enumerate(["/x", "/y", "/x", "/y"], 1)]
    letters, _ = claims(sessions, probe=lambda cwd: cwd + "/.git")
    assert letters == {"1": "A", "3": "A", "2": "B", "4": "B"}


def test_a_directory_in_no_repository_is_no_claim_and_no_warning():
    letters, unknown = claims([in_dir("1", "/t"), in_dir("2", "/t")], probe=lambda _: None)
    assert letters == {} and unknown == 0


def test_a_probe_that_cannot_ask_is_counted_once_per_directory():
    def blind(_):
        raise CannotTell("no git")

    letters, unknown = claims([in_dir("1", "/t"), in_dir("2", "/t"), in_dir("3", "/u")], blind)
    assert letters == {} and unknown == 2


def git(*args, cwd):
    import subprocess

    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def test_real_git_puts_a_worktree_in_its_main_checkouts_repository(tmp_path):
    """The worktree case is the one a `cwd` comparison misses and the reason
    this asks git, so it is checked against git rather than a fixture of it."""
    main, other, plain = tmp_path / "main", tmp_path / "other", tmp_path / "plain"
    for d in (main, other, plain):
        d.mkdir()
    for d in (main, other):
        git("init", "-q", cwd=d)
        git("commit", "-q", "--allow-empty", "-m", "x", cwd=d)
    git("worktree", "add", "-q", str(tmp_path / "pool"), cwd=main)
    assert git_common_dir(str(plain)) is None
    assert git_common_dir(str(tmp_path / "gone")) is None
    sessions = [
        in_dir("1", str(main)),
        in_dir("2", str(tmp_path / "pool")),
        in_dir("3", str(other)),
        in_dir("4", str(plain)),
    ]
    letters, unknown = claims(sessions)
    assert letters == {"1": "A", "2": "A"} and unknown == 0


def test_an_inherited_git_dir_does_not_put_every_session_in_one_repository(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        git("init", "-q", cwd=d)
    monkeypatch.setenv("GIT_DIR", str(a / ".git"))
    assert git_common_dir(str(a)) != git_common_dir(str(b))


def test_what_git_printed_never_reaches_the_envelope(monkeypatch, tmp_path):
    """Run on sky.boss's own initiative, so its output is a key and never data —
    a probe that printed a token must not put the token in front of a reader."""
    secret = "TOKEN-must-not-leak"
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    fake = bin_ / "git"
    fake.write_text(f"#!/bin/sh\necho {secret}\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}:/usr/bin:/bin")
    sessions = [in_dir("1", str(tmp_path)), in_dir("2", str(tmp_path))]
    monkeypatch.setattr("skyboss.agents.providers", lambda: [Fake("a", sessions)])
    result = CliRunner().invoke(cli, ["--json", "agents"])
    body = json.loads(result.stdout)
    assert [r["claim"] for r in body["data"]] == ["A", "A"]
    assert secret not in result.stdout
    assert "claim" in [c["key"] for c in body["view"]["columns"]]


def test_no_git_on_path_is_said_rather_than_drawn_as_no_contention(monkeypatch, tmp_path, said):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    sessions = [in_dir("1", str(tmp_path)), in_dir("2", str(tmp_path))]
    monkeypatch.setattr("skyboss.agents.providers", lambda: [Fake("a", sessions)])
    result = CliRunner().invoke(cli, ["agents"])
    assert "claims not derived for 1 directory(ies)" in said(result)
