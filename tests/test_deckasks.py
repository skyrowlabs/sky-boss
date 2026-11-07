"""Every ask of the operator in one queue: kinds, hook rows, closing by observation, held state."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from skyboss import deck as deck_
from skyboss import deckasks
from skyboss import todos as todos_
from skyboss.output import Result

pytestmark = [pytest.mark.unit]

S = "probe"


@pytest.fixture(autouse=True)
def fresh(sb_state):
    """State is shared across the suite, so this deck starts empty each time."""
    shutil.rmtree(sb_state / "deck" / S, ignore_errors=True)


def answers(table: dict[str, tuple[int, str]]):
    """A reader answering by the first word of the argv after the tool."""

    def reader(args: list[str], cwd: str) -> subprocess.CompletedProcess:
        code, out = next((v for k, v in table.items() if k in " ".join(args)), (1, ""))
        return subprocess.CompletedProcess(args, code, out, "boom" if code else "")

    return reader


@pytest.mark.parametrize("text", ["a | b", "a && b", "a > f", "a ; b", ""])
def test_a_command_with_shell_syntax_or_no_words_is_refused(text):
    with pytest.raises(ValueError):
        deckasks.parse_run(text)


def test_a_quoted_command_becomes_an_argv():
    assert deckasks.parse_run("gh pr merge 49 --body 'a b'") == ["gh", "pr", "merge", "49", "--body", "a b"]


def test_a_control_character_cannot_hide_in_a_command():
    with pytest.raises(ValueError):
        deckasks.parse_run("echo '\x1b[2Jhidden'")


@pytest.mark.parametrize("until", ["pr:49", "pr:49@abc1234", "pushed:abc1234", "gone:feat/x"])
def test_the_closing_tests_parse(until):
    assert deckasks.check_until(until) == until


@pytest.mark.parametrize("until", ["pr:x", "pushed:zz", "gone:-x", "ci:green"])
def test_anything_else_is_refused(until):
    with pytest.raises(ValueError):
        deckasks.check_until(until)


def test_a_merged_pr_closes_and_a_moved_head_reads_stale():
    merged = answers({"pr view": (0, '{"state": "MERGED", "headRefOid": "abc1234ff"}')})
    assert deckasks.observe("pr:49", ".", merged).closed == "PR #49 merged"
    moved = answers({"pr view": (0, '{"state": "OPEN", "headRefOid": "def5678ff"}')})
    assert deckasks.observe("pr:49@abc1234", ".", moved).stale == "head moved to def5678"
    assert not deckasks.observe("pr:49", ".", moved).note


def test_a_test_that_could_not_be_read_never_reads_as_open_and_good():
    assert deckasks.observe("pr:49", ".", answers({})).note.startswith("could not check")


def test_a_pushed_sha_and_a_gone_branch_close():
    assert deckasks.observe("pushed:abc1234", ".", answers({"branch -r": (0, "  origin/develop\n")})).closed
    assert not deckasks.observe("pushed:abc1234", ".", answers({"branch -r": (0, "")})).closed
    assert deckasks.observe("gone:x", ".", answers({"show-ref": (1, "")})).closed == "x is gone"


def test_an_observed_action_closes_and_its_agent_is_told(sb_state):
    todos_.add(S, "a", "merge it", todos_.DECISIONS, kind=todos_.ACTION, until="pr:49", cwd=".")
    merged = answers({"pr view": (0, '{"state": "MERGED"}')})
    assert deckasks.sweep_actions(S, "a", merged) == 1
    found = todos_.next_untold(S, "a")
    assert found is not None and deck_.ruling_line(*found) == 'Your action 1, "merge it", is closed: PR #49 merged'


def test_an_agent_cannot_close_an_action_a_test_can_observe(sb_state):
    todos_.add(S, "a", "merge it", todos_.DECISIONS, kind=todos_.ACTION, until="pr:49")
    with pytest.raises(ValueError):
        todos_.done(S, "a", 1, book=todos_.DECISIONS)


def test_a_notice_dismissed_tells_nobody(sb_state):
    todos_.add(S, "a", "fyi", todos_.DECISIONS, kind=todos_.NOTICE)
    todos_.close_action(S, "a", 1, "dismissed")
    assert todos_.next_untold(S, "a") is None


def request(tool: str, given: dict) -> dict:
    return {"hook_event_name": "PermissionRequest", "tool_name": tool, "tool_input": given}


def test_a_prompt_says_what_it_waits_on():
    asked = request("AskUserQuestion", {"questions": [{"question": "Red or blue?"}]})
    assert deckasks.prompt_text(asked) == "Red or blue?"
    assert deckasks.prompt_text(request("Bash", {"command": "touch x"})) == "Bash: touch x"


@pytest.mark.parametrize(
    "said, found",
    [("Done. Shall I push?", "Shall I push?"), ("Done.", ""), ("Merge it?**", "Merge it?"), ("", "")],
)
def test_only_a_turn_ending_on_a_question_counts(said, found):
    assert deckasks.last_question(said) == found


def asks(agent: str = "a") -> list[str]:
    todo = todos_.load(S, agent, todos_.ASKS)
    return [item.kind for item in todo.items] if todo else []


def test_a_prompt_row_goes_when_the_turn_ends_and_a_question_comes(sb_state):
    deckasks.on_hook(S, "a", request("Bash", {"command": "ls"}))
    assert asks() == [todos_.ASKED]
    deckasks.on_hook(S, "a", {"hook_event_name": "Stop", "last_assistant_message": "Shall I?"})
    assert asks() == [todos_.PROSE]
    deckasks.on_hook(S, "a", {"hook_event_name": "UserPromptSubmit"})
    assert asks() == []


def test_a_denial_offers_its_command_only_when_no_shell_is_needed(sb_state):
    event = {"hook_event_name": "PermissionDenied", "tool_name": "Bash", "cwd": "/w"}
    deckasks.on_hook(S, "a", {**event, "tool_input": {"command": "gh pr merge 4"}})
    deckasks.on_hook(S, "a", {**event, "tool_input": {"command": "gh pr merge 4"}})
    deckasks.on_hook(S, "a", {**event, "tool_input": {"command": "a | b"}})
    todo = todos_.load(S, "a", todos_.DECISIONS)
    assert todo is not None and [i.run for i in todo.items] == [["gh", "pr", "merge", "4"], []]


def test_a_refused_prompt_fires_no_hook_so_the_registry_closes_its_row(sb_state):
    deckasks.on_hook(S, "a", request("Bash", {"command": "ls"}))
    now = datetime.now(timezone.utc)
    deckasks.settle(S, "a", "idle", "waiting", now)
    assert asks() == [todos_.ASKED]
    later = now + timedelta(seconds=deckasks.ASK_GRACE + 1)
    deckasks.settle(S, "a", "waiting", "waiting", later)
    assert asks() == [todos_.ASKED]
    deckasks.settle(S, "a", "idle", "waiting", later)
    assert asks() == []


def texts(rows: list[dict]) -> list[str]:
    return [row["text"] for row in rows if row["text"]]


def test_a_notice_cannot_sit_above_a_choice(sb_state):
    todos_.add(S, "a", "fyi", todos_.DECISIONS, kind=todos_.NOTICE)
    todos_.add(S, "a", "run it", todos_.DECISIONS, kind=todos_.ACTION)
    todos_.add(S, "a", "pick", todos_.DECISIONS)
    todos_.add(S, "b", "other fyi", todos_.DECISIONS, kind=todos_.NOTICE)
    todos_.add(S, "c", "other pick", todos_.DECISIONS)
    rows, _ = todos_.rows_of(S, [("a", 0), ("b", 1), ("c", 2)], datetime.now(timezone.utc), book=todos_.DECISIONS)
    assert texts(rows).index("pick") < texts(rows).index("run it") < texts(rows).index("fyi")
    assert texts(rows).index("other pick") < texts(rows).index("other fyi")
    assert next(r for r in rows if r["text"] == "fyi")["n"] == 1


def test_a_tab_with_only_a_hook_row_still_shows(sb_state):
    deckasks.on_hook(S, "a", request("Bash", {"command": "ls"}))
    rows, _ = todos_.rows_of(S, [("a", 0)], datetime.now(timezone.utc), book=todos_.DECISIONS)
    assert "waiting: Bash: ls" in rows[-1]["decisions"]


def test_held_says_when_it_could_not_read_a_repo():
    reader = answers({"for-each-ref": (0, "develop\nnew\n"), "rev-list": (0, "2\n"), "pr list": (0, "[]")})
    held = deckasks.held_of("/x/repo", reader)
    assert held["rows"][0] == "2 unpushed on develop" and held["unread"] == ["alerts: boom"]
    now = datetime.now(timezone.utc)
    rows = todos_._held_rows({"checked": now.isoformat(), "repos": [held]}, now)
    assert "2 · 1 could not be read" in rows[0]["decisions"]


def test_only_a_green_undrafted_pr_is_held():
    pulls = (
        '[{"number": 1, "isDraft": false, "statusCheckRollup": [{"conclusion": "SUCCESS"}]},'
        '{"number": 2, "isDraft": false, "statusCheckRollup": [{"conclusion": "FAILURE"}]},'
        '{"number": 3, "isDraft": true, "statusCheckRollup": [{"conclusion": "SUCCESS"}]},'
        '{"number": 4, "isDraft": false, "statusCheckRollup": []}]'
    )
    assert deckasks._pulls(".", answers({"pr list": (0, pulls)})) == (["PR #1 green, unmerged"], "")


def test_held_reads_not_yet_rather_than_none_before_its_first_sweep():
    assert "not read yet" in todos_._held_rows({}, datetime.now(timezone.utc))[0]["decisions"]


def test_zero_repos_read_is_not_a_clear_reading():
    now = datetime.now(timezone.utc)
    assert "no repo read" in todos_._held_rows({"checked": now.isoformat(), "repos": []}, now)[0]["decisions"]


def test_the_held_line_stays_at_the_foot_of_a_short_pane():
    pane = deck_.DeckPane(S, lambda row: True, scroll=True, top=True, role=todos_.DECISIONS)
    rows = [{"kind": "item"}, {"kind": "item"}, {"kind": "item"}, {"kind": todos_.HELD}]
    shown, _ = deck_.keep_from_top("row(s)", pane)(Result(data=rows), 2)
    assert [row["kind"] for row in shown.data] == ["item", todos_.HELD]


def test_a_click_on_the_held_line_unfolds_it():
    pane = deck_.DeckPane(S, lambda row: True, scroll=True, top=True, role=todos_.DECISIONS)
    assert pane.decision_click({"kind": todos_.HELD}) and deck_.HELD_FOLD in pane.open


def test_a_click_dismisses_a_notice_and_a_prose_row():
    pane = deck_.DeckPane(S, lambda row: True, scroll=True, top=True, role=todos_.DECISIONS)
    todos_.add(S, "a", "fyi", todos_.DECISIONS, kind=todos_.NOTICE)
    assert pane.decision_click({"kind": "item", "ask": todos_.NOTICE, "agent": "a", "n": 1, "done": False})
    deckasks.on_hook(S, "a", {"hook_event_name": "Stop", "last_assistant_message": "Well?"})
    assert pane.decision_click({"kind": "ask", "ask": todos_.PROSE, "agent": "a"}) and asks() == []


def item(**kwargs) -> todos_.Item:
    return todos_.Item(text="merge it", kind=todos_.ACTION, **kwargs)


def test_the_popup_shows_the_exact_command_and_folder():
    lines = [line for line, _ in deck_.action_screen("a", 1, item(run=["gh", "x y"], cwd="/w"), deckasks.Seen(), 80)]
    assert "  gh 'x y'" in lines and "in /w" in lines and "[r] run it" in lines


def test_a_stale_row_offers_no_run():
    keys = {key for _, key in deck_.action_screen("a", 1, item(run=["gh"]), deckasks.Seen(stale="moved"), 80)}
    assert "r" not in keys and "d" in keys


def test_a_row_with_no_command_offers_no_run():
    assert "r" not in {key for _, key in deck_.action_screen("a", 1, item(), deckasks.Seen(), 80)}


def test_the_hooks_stay_off_the_per_tool_events():
    import json

    hooks = json.loads((deck_.PLUGIN_DIR / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) == {"PermissionRequest", "PermissionDenied", "UserPromptSubmit", "Stop", "SessionStart"}


def test_a_resumed_cleared_or_compacted_tab_gets_todays_brief_and_a_fresh_one_does_not(monkeypatch):
    import json

    monkeypatch.setattr(deck_, "current_brief", lambda config, who: ("ws", [], f"brief for {who}"))
    for source in ("resume", "clear", "compact"):
        reply = json.loads(deck_.rebrief(deck_.Config(), "a", {"hook_event_name": "SessionStart", "source": source}))
        assert reply["hookSpecificOutput"]["additionalContext"].endswith("brief for a")
    assert deck_.rebrief(deck_.Config(), "a", {"hook_event_name": "SessionStart", "source": "startup"}) == ""
    assert deck_.rebrief(deck_.Config(), "a", {"hook_event_name": "Stop", "source": "clear"}) == ""
