"""`sb schedule` — what fires next, folded across projects. See [[schedule]].

The properties worth defending: ordering is on the parsed instant and not the
string, a naive timestamp is a reported declaration error rather than a guess,
a project that declares no schedule is counted and never drawn, and nothing
here parses a cron expression or computes a fire time.
"""

import json

from click.testing import CliRunner

from cli import cli
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
