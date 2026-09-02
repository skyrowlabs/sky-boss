"""`sb history` — a project's own run ledger, newest first. See [[history]].

The properties worth defending: newest first on the *instant* and not the
string, a truncation that says so, a project with no ledger counted rather than
drawn as an empty table, the provider's word carried through unjudged, and the
torn last line of a file that is being appended to while it is read still
reported — which is the whole reason this goes through `sb data`'s reader
rather than a loop of its own.
"""

import json

from click.testing import CliRunner

from cli import cli
from cli.history import DEFAULT_LAST, order, rows_of, view_of
from cli.rollcall import Project, parse
from cli.schedule import now_utc

DECL = """
state_root = "ROOT"

[project.alpha]
path = "ROOT/status.json"

[project.alpha.history]
path = "runs.jsonl"
when = "started"
name = "job"
outcome = "status"

[project.beta]
path = "ROOT/status.json"
"""


def _home(tmp_path, rows=None, *, decl: str = DECL, ledger: str | None = None):
    """A scratch `$SB_HOME` and a state root beside it, wired the way the
    operator's own file is: a history `path` is relative to the project's state
    directory, never joined here."""
    root = tmp_path / "root"
    (root / "alpha").mkdir(parents=True)
    (tmp_path / "status.json").write_text("{}")
    (root / "status.json").write_text("{}")
    if ledger is None and rows is not None:
        ledger = "\n".join(json.dumps(r) for r in rows) + "\n"
    if ledger is not None:
        (root / "alpha" / "runs.jsonl").write_text(ledger)
    (tmp_path / "projects.toml").write_text(decl.replace("ROOT", str(root)))
    return tmp_path


def _at(tmp_path, monkeypatch):
    monkeypatch.setenv("SB_HOME", str(tmp_path))
    monkeypatch.setattr("cli.rollcall.SB_HOME", tmp_path)


def run(tmp_path, monkeypatch, *args):
    _at(tmp_path, monkeypatch)
    return CliRunner().invoke(cli, ["--json", "history", *args])


def envelope(result):
    return json.loads(result.stdout)


# ============================================================================
# The declaration
# ============================================================================


def test_a_history_block_is_parsed():
    projects, problems = parse(
        {"project": {"a": {"path": "x", "history": {"path": "r.jsonl", "when": "t", "name": "j"}}}}
    )
    assert problems == []
    assert projects[0].history == {"path": "r.jsonl", "when": "t", "name": "j"}


def test_an_unknown_history_key_is_named_and_ignored():
    """Reported rather than refused, and *ignored* rather than *invalid*, so the
    check cannot become the thing that rejects a file written for a newer
    sky.boss."""
    _, problems = parse(
        {
            "project": {
                "a": {
                    "path": "x",
                    "history": {"path": "r", "when": "t", "name": "j", "verdict": "v"},
                }
            }
        }
    )
    assert problems == ["project 'a': history has unknown key 'verdict' — ignored"]


def test_the_three_fields_with_no_word_for_their_absence_are_required():
    """Without `path` there is no file; without `when` the rows can only be
    ordered by their position in the file, which is sky.boss inferring that an
    append-only ledger is chronological; without `name` a row has nothing to
    call what ran."""
    _, problems = parse({"project": {"a": {"path": "x", "history": {"outcome": "s"}}}})
    assert problems == ["project 'a': history must declare path, when, name"]


def test_an_outcome_is_optional():
    """A ledger that records only what ran and when is a legitimate ledger."""
    projects, problems = parse(
        {"project": {"a": {"path": "x", "history": {"path": "r", "when": "t", "name": "j"}}}}
    )
    assert problems == [] and projects[0].history is not None


# ============================================================================
# Ordering
# ============================================================================


def a_project(**over):
    mapping = {"path": "r.jsonl", "when": "started", "name": "job", "outcome": "status"}
    mapping.update(over)
    return Project(name="alpha", path="x", history=mapping)


def test_newest_first_on_the_instant_not_the_string():
    """The trap [[schedule]] measured, arriving on the other sort direction:
    `20:00-06:00` is `02:00Z` the next day, so it is the *later* instant while
    being the *earlier* string."""
    rows, _ = rows_of(
        a_project(),
        [
            {"job": "earlier", "started": "2026-08-31T23:00:00+00:00"},
            {"job": "later", "started": "2026-08-31T20:00:00-06:00"},
        ],
        now_utc(),
    )
    assert [r["name"] for r in order(rows)] == ["later", "earlier"]


def test_a_row_sky_boss_cannot_place_in_time_goes_last():
    """Putting it first would make the least certain thing look like the most
    recent."""
    rows, problems = rows_of(
        a_project(),
        [
            {"job": "undated", "started": ""},
            {"job": "dated", "started": "2026-08-31T23:00:00+00:00"},
        ],
        now_utc(),
    )
    assert [r["name"] for r in order(rows)] == ["dated", "undated"]
    assert problems == []


def test_a_naive_timestamp_is_reported_rather_than_guessed():
    _, problems = rows_of(
        a_project(), [{"job": "j", "started": "2026-08-31T23:00:00"}], now_utc()
    )
    assert len(problems) == 1 and "will not guess" in problems[0]


def test_the_provider_string_survives_with_its_offset():
    """Never normalised. Two projects disagreeing about what time it is should
    be visible rather than merged into a resolution nobody made."""
    rows, _ = rows_of(a_project(), [{"job": "j", "started": "2026-08-31T20:00:00-06:00"}], now_utc())
    assert rows[0]["when"] == "2026-08-31T20:00:00-06:00"


def test_a_declared_field_that_is_missing_draws_empty_rather_than_raising():
    rows, _ = rows_of(a_project(), [{"started": "2026-08-31T23:00:00+00:00"}], now_utc())
    assert rows[0]["name"] == "" and rows[0]["outcome"] == ""


def test_a_project_that_declares_no_outcome_draws_no_outcome():
    rows, _ = rows_of(
        Project(name="alpha", path="x", history={"path": "r", "when": "started", "name": "job"}),
        [{"job": "j", "started": "2026-08-31T23:00:00+00:00", "status": "ok"}],
        now_utc(),
    )
    assert rows[0]["outcome"] == ""


# ============================================================================
# The command
# ============================================================================


def a_run(job="j", when="2026-08-31T23:00:00+00:00", status="ok"):
    return {"job": job, "started": when, "status": status, "rc": 0}


def test_the_ledger_is_read_and_ordered(tmp_path, monkeypatch):
    _home(
        tmp_path,
        [
            a_run("old", "2026-08-30T01:00:00+00:00"),
            a_run("new", "2026-08-31T01:00:00+00:00"),
        ],
    )
    body = envelope(run(tmp_path, monkeypatch, "alpha"))
    assert body["ok"] is True
    assert [r["name"] for r in body["data"]] == ["new", "old"]


def test_the_providers_word_is_carried_through_unjudged(tmp_path, monkeypatch):
    """Drawn as written and never totalled, ranked, or coloured into a verdict.
    `red` is jam.sense's word and sky.boss does not know what it is worth."""
    _home(tmp_path, [a_run(status="red"), a_run(status="skipped")])
    body = envelope(run(tmp_path, monkeypatch, "alpha"))
    assert {r["outcome"] for r in body["data"]} == {"red", "skipped"}
    assert body["partial"] is False


def test_truncation_is_never_silent(tmp_path, monkeypatch):
    """A truncated table that does not say so reads as the whole history, which
    is the one thing a history must not do."""
    _home(tmp_path, [a_run(f"j{n}") for n in range(30)])
    body = envelope(run(tmp_path, monkeypatch, "alpha", "--last", "5"))
    assert len(body["data"]) == 5
    assert any("showing the last 5 of 30 runs" in w for w in body["warnings"])


def test_last_zero_draws_everything_and_says_nothing(tmp_path, monkeypatch):
    _home(tmp_path, [a_run(f"j{n}") for n in range(30)])
    body = envelope(run(tmp_path, monkeypatch, "alpha", "--last", "0"))
    assert len(body["data"]) == 30 and body["warnings"] == []


def test_a_short_ledger_is_not_reported_as_truncated(tmp_path, monkeypatch):
    _home(tmp_path, [a_run()])
    body = envelope(run(tmp_path, monkeypatch, "alpha"))
    assert body["warnings"] == [] and len(body["data"]) == 1
    assert DEFAULT_LAST > 1


def test_a_project_with_no_ledger_declared_is_counted_never_drawn(tmp_path, monkeypatch):
    """Not an error: the project exists and publishes no ledger. An empty table
    would read as *this project has never run anything*."""
    _home(tmp_path, [a_run()])
    body = envelope(run(tmp_path, monkeypatch, "beta"))
    assert body["ok"] is True and body["data"] == []
    assert any("declares no history" in w for w in body["warnings"])


def test_an_empty_ledger_says_so(tmp_path, monkeypatch):
    _home(tmp_path, ledger="")
    body = envelope(run(tmp_path, monkeypatch, "alpha"))
    assert body["data"] == []
    assert any("no runs recorded" in w for w in body["warnings"])


def test_an_absent_ledger_is_a_failure_that_names_the_file(tmp_path, monkeypatch):
    _home(tmp_path)
    result = run(tmp_path, monkeypatch, "alpha")
    body = envelope(result)
    assert body["ok"] is False and result.exit_code == 1
    assert "runs.jsonl" in body["data"]["source"]


def test_a_torn_last_line_is_still_reported(tmp_path, monkeypatch):
    """**The reason this goes through `sb data`'s reader whole.** The ledger is
    appended to while it is read, so the last line can be half-written. A
    private `splitlines` loop here would drop it in silence — the class
    [[jsonl-reads]] round 4 exists for."""
    good = json.dumps(a_run("whole"))
    _home(tmp_path, ledger=f"{good}\n{good[:20]}")
    body = envelope(run(tmp_path, monkeypatch, "alpha"))
    assert len(body["data"]) == 1
    assert body["warnings"], "a torn line must be reported, not dropped"


def test_an_unknown_project_names_the_declared_ones(tmp_path, monkeypatch):
    _home(tmp_path, [a_run()])
    result = run(tmp_path, monkeypatch, "nope")
    assert result.exit_code == 2
    assert "alpha" in result.output and "beta" in result.output


def test_no_argument_names_the_candidates(tmp_path, monkeypatch):
    """Click's own 'Missing argument' is true and tells you nothing about which
    words would have worked."""
    _home(tmp_path, [a_run()])
    result = run(tmp_path, monkeypatch)
    assert result.exit_code == 2
    assert "name a project" in result.output and "alpha" in result.output


def test_the_view_is_authored_and_hides_the_absolutes(tmp_path, monkeypatch):
    _home(tmp_path, [a_run()])
    body = envelope(run(tmp_path, monkeypatch, "alpha"))
    view = body["view"]
    assert view["authored"] is True
    assert [c["key"] for c in view["columns"]] == ["project", "name", "outcome", "ago"]
    assert view["hidden"] == ["when", "at"]
    assert body["data"][0]["at"] and body["data"][0]["when"]


def test_no_private_key_reaches_the_envelope(tmp_path, monkeypatch):
    """`_at` is the parsed instant used for ordering. It is a datetime, and a
    datetime in the envelope is a `default=str` away from being a string nobody
    declared."""
    _home(tmp_path, [a_run()])
    body = envelope(run(tmp_path, monkeypatch, "alpha"))
    assert not [k for k in body["data"][0] if k.startswith("_")]


def test_the_view_columns_match_what_the_rows_carry():
    rows, _ = rows_of(a_project(), [a_run()], now_utc())
    drawn = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    view = view_of(drawn)
    named = {c["key"] for c in view["columns"]} | set(view["hidden"])
    assert named == set(drawn[0]), "a view must describe every key and invent none"
