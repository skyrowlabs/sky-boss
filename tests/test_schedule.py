"""`sb schedule` — what fires next, folded across projects. See [[schedule]].

The properties worth defending: ordering is on the parsed instant and not the
string, a naive timestamp is a reported declaration error rather than a guess,
a project that declares no schedule is counted and never drawn, and nothing
here parses a cron expression or computes a fire time.
"""

import json
from datetime import datetime

from click.testing import CliRunner

from cli import cli, schedule
from cli.schedule import order, parse_instant, rows_of
from cli.rollcall import Project


def _home(tmp_path, projects: str, **files) -> None:
    (tmp_path / "projects.toml").write_text(projects.replace("HOME", str(tmp_path)))
    for name, body in files.items():
        (tmp_path / f"{name}.json").write_text(body)


ALPHA = """
[project.alpha]
path = "HOME/alpha.json"

[project.alpha.schedule]
rows = "jobs"
name = "job"
schedule = "schedule"
next = "next_run"
last = "last_run"
"""


def test_ordering_is_on_the_instant_not_the_string(tmp_path, monkeypatch):
    """The payload already carries this trap: one response, `next_run` stamped
    -05:00 and `last_run` stamped +00:00. A lexical sort is correct only while
    every value happens to share an offset.

    Here the *earlier* instant has the *later* string: 20:00-06:00 is 02:00Z the
    next day, which falls after 23:00+00:00 — and sorts before it lexically.
    """
    _home(
        tmp_path,
        ALPHA,
        alpha=json.dumps(
            {
                "jobs": [
                    {"job": "later-instant", "next_run": "2026-08-31T20:00:00-06:00"},
                    {"job": "earlier-instant", "next_run": "2026-08-31T23:00:00+00:00"},
                ]
            }
        ),
    )
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)

    out = json.loads(CliRunner().invoke(cli, ["--json", "schedule"]).stdout)
    assert [r["name"] for r in out["data"]] == ["earlier-instant", "later-instant"]

    # And the string order is the other way, which is what makes this a test.
    lexical = sorted(out["data"], key=lambda r: r["next"])
    assert [r["name"] for r in lexical] == ["later-instant", "earlier-instant"]


def test_a_naive_timestamp_is_a_reported_error_not_a_guess():
    """Guessing a zone is how a view is confidently six hours wrong."""
    when, problem = parse_instant("2026-08-31T05:15:00")
    assert when is None
    assert "will not guess" in problem

    when, problem = parse_instant("2026-08-31T05:15:00-05:00")
    assert problem is None and when is not None


def test_an_unparseable_timestamp_is_named_rather_than_dropped():
    when, problem = parse_instant("next tuesday")
    assert when is None and "not a timestamp" in problem


def test_an_absent_timestamp_is_absence_and_not_an_error():
    """A job with no `next` is a state the view has a word for — distinct from a
    malformed one, and the only one sky.boss could paper over by computing."""
    assert parse_instant("") == (None, None)


def test_a_row_with_no_next_sorts_after_every_row_that_has_one():
    """It has nowhere honest to sit among rows ordered by time, and putting it
    first would make the least certain thing look the most imminent."""
    import datetime as dt

    early = {"name": "a", "_at": dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)}
    late = {"name": "b", "_at": dt.datetime(2026, 9, 2, tzinfo=dt.timezone.utc)}
    none = {"name": "c", "_at": None}
    assert [r["name"] for r in order([none, late, early])] == ["a", "b", "c"]


def test_a_project_declaring_no_schedule_is_counted_and_never_drawn(tmp_path, monkeypatch):
    """Silence about it is indistinguishable from a project whose schedule is
    empty. Not a blank row, because rows sort by time and a row with no time has
    nowhere honest to go — [[roll-call]]'s *report an absence, do not render it*."""
    _home(
        tmp_path,
        ALPHA + '\n[project.beta]\npath = "HOME/beta.json"\n',
        alpha=json.dumps({"jobs": [{"job": "one", "next_run": "2026-08-31T05:00:00+00:00"}]}),
        beta=json.dumps({"anything": 1}),
    )
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)

    result = CliRunner().invoke(cli, ["--json", "schedule"])
    out = json.loads(result.stdout)
    assert [r["project"] for r in out["data"]] == ["alpha"]
    assert any("1 of 2 projects declare a schedule" in w for w in out["warnings"])
    assert any("beta" in w for w in out["warnings"])


def test_the_schedule_string_is_drawn_exactly_as_the_provider_wrote_it(tmp_path, monkeypatch):
    """Never parsed. A second implementation of cron semantics will be wrong
    about DST before it is wrong about anything else."""
    _home(
        tmp_path,
        ALPHA,
        alpha=json.dumps(
            {"jobs": [{"job": "j", "schedule": "15 5 * * *", "next_run": "2026-08-31T05:15:00+00:00"}]}
        ),
    )
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)

    out = json.loads(CliRunner().invoke(cli, ["--json", "schedule"]).stdout)
    assert out["data"][0]["schedule"] == "15 5 * * *"


def test_next_is_never_computed_from_the_schedule(tmp_path, monkeypatch):
    """A *wrong* next-fire time is worse than none, because it looks like an
    answer. A provider that supplies none leaves the field empty."""
    _home(
        tmp_path,
        ALPHA,
        alpha=json.dumps({"jobs": [{"job": "j", "schedule": "15 5 * * *", "next_run": ""}]}),
    )
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)

    out = json.loads(CliRunner().invoke(cli, ["--json", "schedule"]).stdout)
    assert out["data"][0]["next"] == ""


def test_rows_names_a_missing_container_rather_than_returning_nothing():
    """A payload that does not carry the declared `rows` key is a declaration
    that has drifted from its source — the silence would look like an empty
    calendar."""
    project = Project(name="p", path="x", schedule={"rows": "jobs", "name": "job"})
    rows, problems = rows_of(project, {"other": []})
    assert rows == []
    assert problems and "no 'jobs'" in problems[0]


def test_schedule_is_an_observe_so_a_window_may_pin_it():
    """`acts` decides whether the canvas will offer a cadence. A viewer that
    read as a write could never be refreshed."""
    from cli.schedule import schedule as cmd

    assert not getattr(cmd, "sb_acts", False)


# ---------------------------------------------------------------- round 3


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def test_relative_reads_forward_and_backward():
    """Arithmetic on two instants, in the vocabulary the bands already use."""
    now = _at("2026-08-30T12:00:00+00:00")
    assert schedule.relative(_at("2026-08-30T12:26:00+00:00"), now) == "in 26m"
    assert schedule.relative(_at("2026-08-31T12:00:00+00:00"), now) == "in 1d"
    # `late`, not a negative duration: the word is chrome's, so the two
    # surfaces cannot grow separate vocabularies for one idea.
    assert schedule.relative(_at("2026-08-30T11:46:00+00:00"), now) == "late 14m"
    assert schedule.relative(None, now) == ""


def test_relative_is_offset_correct_not_lexical():
    """The trap round 1 measured, now reaching the drawn column.

    `-05:00` and `+00:00` sort one way as strings and the other as instants.
    A row 5 minutes away must not read as 5 hours away because of its offset.
    """
    now = _at("2026-08-30T17:00:00+00:00")
    assert schedule.relative(_at("2026-08-30T12:05:00-05:00"), now) == "in 5m"


def test_elapsed_reads_behind():
    now = _at("2026-08-30T12:00:00+00:00")
    assert schedule.elapsed(_at("2026-08-30T09:00:00+00:00"), now) == "3h ago"
    assert schedule.elapsed(None, now) == ""


def test_view_is_authored_and_hides_the_absolutes():
    """The five drawn columns are sky.boss's own, and the two it keeps are the
    provider's untouched strings — a view describes, it never filters."""
    rows = [{"project": "p", "name": "j", "fires": "in 1h", "schedule": "0 * * * *",
             "ran": "2h ago", "next": "2026-08-30T13:00:00+00:00",
             "last": "2026-08-30T10:00:00+00:00"}]
    v = schedule.view_of(rows)
    assert [c["key"] for c in v["columns"]] == list(schedule.INLINE)
    assert v["hidden"] == list(schedule.HIDDEN)
    # Widths come from cli/view.py, not from a second opinion here.
    assert all("flex" in c and "min" in c for c in v["columns"])


def test_band_says_drawn_of_arrived():
    """Five under the word seven is the confusion; the band answers it."""
    from cli.output import _dimensions
    rows = [{k: "x" for k in ("a", "b", "c")}]
    view = {"columns": [{"key": "a"}], "details": [], "hidden": ["b", "c"]}
    assert _dimensions(rows, view) == "table · 1 row · 1 of 3 columns"
    # Unchanged when nothing is hidden, so every envelope written before this
    # round reads exactly as it did.
    whole = {"columns": [{"key": k} for k in ("a", "b", "c")], "details": [], "hidden": []}
    assert _dimensions(rows, whole) == "table · 1 row · 3 columns"
    assert _dimensions(rows, None) == "table · 1 row · 3 columns"


# ============================================================================
# Round 10 — two populations in one table
# ============================================================================

import pytest  # noqa: E402
from datetime import timedelta, timezone as tz  # noqa: E402

import cli.jobs as jobs_  # noqa: E402
from cli.jobs import Unit  # noqa: E402
from cli.schedule import _systemd_instant, now_utc  # noqa: E402


def test_a_provider_row_says_it_is_watched():
    """A row sky.boss *fires* and a row it merely *watches* are two different
    claims arriving in one table, and a reader cannot tell them apart from a
    time."""
    rows, _ = rows_of(
        Project(name="alpha", path="x", schedule={"name": "job", "next": "next_run"}),
        [{"job": "j", "next_run": "2026-08-31T23:00:00+00:00"}],
    )
    assert rows[0]["clock"] == "watched"


def test_the_clock_column_is_drawn(tmp_path, monkeypatch):
    from cli.schedule import INLINE

    assert "clock" in INLINE


# ------------------------------------------------ systemd's own time format


def test_systemd_time_becomes_an_instant():
    """`systemctl` prints a different string shape from a provider's ISO stamp,
    and the one thing that must not differ is how the two are ordered."""
    when = _systemd_instant("Wed 2026-09-02 06:00:00 CDT")
    assert when is not None and when.tzinfo is not None
    assert (when.year, when.month, when.day, when.hour) == (2026, 9, 2, 6)


def test_the_zone_abbreviation_is_dropped_rather_than_resolved():
    """`CDT` is ambiguous across the world's timezone databases and guessing is
    how a view is confidently six hours wrong. The local zone is safe *here*
    where it would not be for a provider: systemd printed this for this machine,
    in this machine's zone."""
    assert _systemd_instant("Wed 2026-09-02 06:00:00 CDT") == _systemd_instant(
        "Wed 2026-09-02 06:00:00 XYZ"
    )


@pytest.mark.parametrize("value", ["", "n/a", "-", "not a time", "Wed"])
def test_an_unorderable_systemd_time_is_none_rather_than_a_guess(value):
    assert _systemd_instant(value) is None


# ------------------------------------------------------ only what fires


def _jobs(monkeypatch, tmp_path, toml: str, *, enabled=(), elapses=None, ledger=""):
    """A scratch `$SB_HOME` for jobs, with systemd's answers injected — enabling
    a real timer on the machine running the suite is not a test."""
    (tmp_path / "jobs.toml").write_text(toml)
    monkeypatch.setattr("cli.jobs.SB_HOME", tmp_path)
    monkeypatch.setattr("cli.jobs.STATE_DIR", tmp_path / "state")
    if ledger:
        (tmp_path / "state" / "jobs").mkdir(parents=True, exist_ok=True)
        (tmp_path / "state" / "jobs" / "ledger.jsonl").write_text(ledger)
    monkeypatch.setattr("cli.jobs.timer_elapses", lambda: (dict(elapses or {}), True))
    monkeypatch.setattr(
        "cli.jobs.unit_state",
        lambda name, e=None: Unit(
            file=name in enabled,
            enabled="enabled" if name in enabled else "disabled",
            next_run=(elapses or {}).get(f"sb-{name}.timer", ""),
        ),
    )


TWO_JOBS = """
[job.armed]
argv     = ["run", "--", "echo", "a"]
schedule = "06:00"

[job.idle]
argv     = ["run", "--", "echo", "b"]
schedule = "07:00"
"""


def test_only_an_enabled_job_is_drawn(tmp_path, monkeypatch):
    """**The correctness argument of this round.** A declared job does not fire.
    An installed-but-not-enabled job does not fire — `install` deliberately
    stops one step short. Drawing either in a table headed *what fires next*
    would be a false claim in the least checkable place there is."""
    _jobs(
        monkeypatch,
        tmp_path,
        TWO_JOBS,
        enabled=("armed",),
        elapses={"sb-armed.timer": "Wed 2026-09-02 06:00:00 CDT"},
    )
    rows, problems, withheld = jobs_.schedule_rows()
    assert [r["name"] for r in rows] == ["armed"]
    assert withheld == 1 and problems == []


def test_the_withheld_are_counted_never_silent(tmp_path, monkeypatch):
    _jobs(monkeypatch, tmp_path, TWO_JOBS)
    rows, _, withheld = jobs_.schedule_rows()
    assert rows == [] and withheld == 2


def test_a_fire_time_is_systemds_and_never_computed(tmp_path, monkeypatch):
    """The refusal [[schedule]] makes about cron, applied to sky.boss's own
    clock: `next` is read back, not derived from `06:00`."""
    _jobs(monkeypatch, tmp_path, TWO_JOBS, enabled=("armed",), elapses={})
    rows, _, _ = jobs_.schedule_rows()
    assert rows[0]["next"] == "", "no read-back means no next, never a computed one"
    assert rows[0]["schedule"] == "06:00"


def test_the_last_run_comes_from_the_ledger(tmp_path, monkeypatch):
    _jobs(
        monkeypatch,
        tmp_path,
        TWO_JOBS,
        enabled=("armed",),
        ledger=(
            '{"job": "armed", "finished": "2026-09-01T06:00:01+00:00"}\n'
            '{"job": "armed", "finished": "2026-09-02T06:00:02+00:00"}\n'
        ),
    )
    rows, _, _ = jobs_.schedule_rows()
    assert rows[0]["last"] == "2026-09-02T06:00:02+00:00", "append-only, so later wins"


def test_a_torn_ledger_line_does_not_lose_the_whole_history(tmp_path, monkeypatch):
    """The file is appended to while it is read. Going through `sb data`'s JSONL
    parser is what keeps a half-written last line from taking the rest with
    it."""
    _jobs(
        monkeypatch,
        tmp_path,
        TWO_JOBS,
        enabled=("armed",),
        ledger='{"job": "armed", "finished": "2026-09-01T06:00:01+00:00"}\n{"job": "arm',
    )
    rows, _, _ = jobs_.schedule_rows()
    assert rows[0]["last"] == "2026-09-01T06:00:01+00:00"


# ----------------------------------------------------------- the fold


ALPHA_ROWS = json.dumps(
    {"jobs": [{"job": "theirs", "next_run": "2026-08-31T23:00:00+00:00"}]}
)


def test_both_populations_land_in_one_table(tmp_path, monkeypatch):
    _home(tmp_path, ALPHA, alpha=ALPHA_ROWS)
    _jobs(
        monkeypatch,
        tmp_path,
        TWO_JOBS,
        enabled=("armed",),
        elapses={"sb-armed.timer": "Wed 2026-09-02 06:00:00 CDT"},
    )
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)
    body = json.loads(CliRunner().invoke(cli, ["--json", "schedule"]).stdout)
    clocks = {r["name"]: r["clock"] for r in body["data"]}
    assert clocks == {"theirs": "watched", "armed": "sb"}


def test_only_sb_narrows_to_our_own(tmp_path, monkeypatch):
    _home(tmp_path, ALPHA, alpha=ALPHA_ROWS)
    _jobs(monkeypatch, tmp_path, TWO_JOBS, enabled=("armed",))
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)
    body = json.loads(CliRunner().invoke(cli, ["--json", "schedule", "--only", "sb"]).stdout)
    assert [r["name"] for r in body["data"]] == ["armed"]


def test_only_a_project_leaves_our_own_out(tmp_path, monkeypatch):
    _home(tmp_path, ALPHA, alpha=ALPHA_ROWS)
    _jobs(monkeypatch, tmp_path, TWO_JOBS, enabled=("armed",))
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)
    body = json.loads(CliRunner().invoke(cli, ["--json", "schedule", "--only", "alpha"]).stdout)
    assert [r["name"] for r in body["data"]] == ["theirs"]
    assert not any("not drawn" in w for w in body["warnings"]), (
        "a withheld count for a population nobody asked about is noise"
    )


def test_only_sb_is_a_name_even_with_nothing_armed(tmp_path, monkeypatch):
    """*Nothing of mine fires* and *no such thing as mine* are different facts,
    and the second is never true."""
    _home(tmp_path, ALPHA, alpha=ALPHA_ROWS)
    _jobs(monkeypatch, tmp_path, TWO_JOBS)
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)
    result = CliRunner().invoke(cli, ["--json", "schedule", "--only", "sb"])
    body = json.loads(result.stdout)
    assert result.exit_code == 0 and body["data"] == []
    assert any("not drawn" in w for w in body["warnings"])
    assert not any("no projects declared" in w for w in body["warnings"])


def test_an_armed_job_shows_up_with_no_projects_declared_at_all(tmp_path, monkeypatch):
    """A table saying *no projects declared* while a timer was armed would be
    the one sentence this whole feature exists to prevent."""
    (tmp_path / "projects.toml").write_text("")
    _jobs(
        monkeypatch,
        tmp_path,
        TWO_JOBS,
        enabled=("armed",),
        elapses={"sb-armed.timer": "Wed 2026-09-02 06:00:00 CDT"},
    )
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)
    body = json.loads(CliRunner().invoke(cli, ["--json", "schedule"]).stdout)
    assert [r["name"] for r in body["data"]] == ["armed"]
    assert not any("no projects declared" in w for w in body["warnings"])


def test_a_project_called_sb_is_reported_rather_than_silently_confusing(tmp_path, monkeypatch):
    collide = ALPHA.replace("[project.alpha]", "[project.sb]").replace(
        "HOME/alpha.json", "HOME/alpha.json"
    )
    (tmp_path / "projects.toml").write_text(collide.replace("HOME", str(tmp_path)))
    (tmp_path / "alpha.json").write_text(ALPHA_ROWS)
    _jobs(
        monkeypatch,
        tmp_path,
        TWO_JOBS,
        enabled=("armed",),
        elapses={"sb-armed.timer": "Wed 2026-09-02 06:00:00 CDT"},
    )
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)
    body = json.loads(CliRunner().invoke(cli, ["--json", "schedule"]).stdout)
    assert any("read the `clock` column" in w for w in body["warnings"])


def test_both_populations_sort_on_one_instant(tmp_path, monkeypatch):
    """Two string shapes, one order. This is the whole reason sky.boss's rows go
    through a parse rather than being appended after the providers'."""
    soon = (now_utc() + timedelta(minutes=5)).astimezone(tz.utc).isoformat()
    later = (datetime.now().astimezone() + timedelta(hours=9)).strftime(
        "%a %Y-%m-%d %H:%M:%S %Z"
    )
    (tmp_path / "projects.toml").write_text(ALPHA.replace("HOME", str(tmp_path)))
    (tmp_path / "alpha.json").write_text(json.dumps({"jobs": [{"job": "theirs", "next_run": soon}]}))
    _jobs(
        monkeypatch,
        tmp_path,
        TWO_JOBS,
        enabled=("armed",),
        elapses={"sb-armed.timer": later},
    )
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)
    body = json.loads(CliRunner().invoke(cli, ["--json", "schedule"]).stdout)
    assert [r["name"] for r in body["data"]] == ["theirs", "armed"]
