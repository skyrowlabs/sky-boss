"""`sb deck` at its edges: the real runner, the terminal probes, the resident path.

`test_deck.py` replaces `RUNNER` wholesale; this file covers what that leaves out
— `deck.system` itself, with `subprocess.run` and `os.execvpe` intercepted, so no
tmux binary is needed and nothing is ever replaced or entered.
"""

from __future__ import annotations

import functools
import json
import subprocess
import sys

import pytest
from click.testing import CliRunner

from skyboss import cli
from skyboss import deck as deck_
from skyboss import output
from skyboss.deck import Answer
from skyboss.output import Result, render, warn_now

#: Host-side; no tmux, no network, no residency entered.
pytestmark = [pytest.mark.unit]


def invoke(*args: str):
    return CliRunner().invoke(cli, list(args))


class Replaced(Exception):
    """Stands in for a successful exec, which never returns."""


@pytest.fixture
def recorder(monkeypatch):
    """Record `subprocess.run` and `os.execvpe` as `deck.system` calls them."""
    calls: dict[str, list] = {"run": [], "exec": []}

    def fake_run(argv, **kwargs):
        calls["run"].append((list(argv), kwargs))
        return subprocess.CompletedProcess(argv, 3, stdout="out\n", stderr="err\n")

    def fake_exec(file, argv, env):
        calls["exec"].append((file, list(argv), env))
        raise Replaced

    monkeypatch.setattr(deck_.subprocess, "run", fake_run)
    monkeypatch.setattr(deck_.os, "execvpe", fake_exec)
    monkeypatch.setenv("PYTHONPATH", "/fx/leak")
    monkeypatch.setenv("PYTHONSAFEPATH", "1")
    monkeypatch.setenv("FX_OPERATOR", "kept")
    return calls


# ============================================================================
# deck.system — the real runner
# ============================================================================


def test_system_runs_the_argv_and_reports_every_stream(recorder):
    answer = deck_.system(["tmux", "has-session", "-t", "=sb"])
    assert answer == Answer(asked=True, code=3, out="out\n", err="err\n")
    assert answer.ok is False
    ((argv, kwargs),) = recorder["run"]
    assert argv == ["tmux", "has-session", "-t", "=sb"]
    assert kwargs["capture_output"] is True and kwargs["text"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL and kwargs["timeout"] == 10
    assert recorder["exec"] == []


def test_system_hands_the_child_the_operators_environment(recorder):
    deck_.system(["tmux", "list-panes"])
    env = recorder["run"][0][1]["env"]
    assert "PYTHONPATH" not in env and "PYTHONSAFEPATH" not in env
    assert env["FX_OPERATOR"] == "kept"


def test_system_with_replace_execs_and_never_falls_through_to_a_run(recorder):
    with pytest.raises(Replaced):
        deck_.system(["tmux", "attach-session", "-t", "=sb"], replace=True)
    ((file, argv, env),) = recorder["exec"]
    assert file == "tmux" and argv == ["tmux", "attach-session", "-t", "=sb"]
    assert "PYTHONPATH" not in env and env["FX_OPERATOR"] == "kept"
    assert recorder["run"] == []


def test_an_exec_that_fails_is_an_unasked_answer(monkeypatch):
    def refuse(file, argv, env):
        raise FileNotFoundError(2, "No such file or directory", file)

    monkeypatch.setattr(deck_.os, "execvpe", refuse)
    answer = deck_.system(["tmux", "attach-session"], replace=True)
    assert answer.asked is False and answer.ok is False
    assert "No such file or directory" in answer.err


@pytest.mark.parametrize(
    "error",
    [FileNotFoundError(2, "No such file or directory", "tmux"), subprocess.TimeoutExpired(["tmux"], 10)],
    ids=["no-binary", "timeout"],
)
def test_a_run_that_cannot_happen_is_an_unasked_answer(monkeypatch, error):
    def explode(argv, **kwargs):
        raise error

    monkeypatch.setattr(deck_.subprocess, "run", explode)
    answer = deck_.system(["tmux", "list-panes"])
    assert answer.asked is False and answer.code == 0 and answer.err == str(error)
    assert deck_._said(answer) == str(error)


def test_tmux_prefixes_the_binary_and_passes_replace_through(monkeypatch):
    seen = []
    monkeypatch.setattr(deck_, "RUNNER", lambda argv, replace=False: seen.append((argv, replace)) or Answer(True))
    deck_.tmux("select-window", "-t", "@1")
    deck_.tmux("attach-session", replace=True)
    assert seen == [(["tmux", "select-window", "-t", "@1"], False), (["tmux", "attach-session"], True)]


# ============================================================================
# The terminal probes
# ============================================================================


class Stdin:
    def __init__(self, tty: bool):
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


@pytest.mark.parametrize("tty", [True, False])
def test_has_terminal_asks_stdin(monkeypatch, tty):
    monkeypatch.setattr(sys, "stdin", Stdin(tty))
    assert deck_.has_terminal() is tty


@pytest.mark.parametrize(("value", "inside"), [("/tmp/fx-sock,1,0", True), ("", False), (None, False)])
def test_inside_tmux_reads_the_tmux_variable(monkeypatch, value, inside):
    if value is None:
        monkeypatch.delenv("TMUX", raising=False)
    else:
        monkeypatch.setenv("TMUX", value)
    assert deck_.inside_tmux() is inside


def test_switch_outside_tmux_calls_nothing(monkeypatch):
    seen = []
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(deck_, "RUNNER", lambda argv, replace=False: seen.append(argv) or Answer(True))
    assert deck_.switch("sb") is False and seen == []


def test_a_refused_switch_is_a_deck_error_naming_tmuxs_reason(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/fx-sock,1,0")
    monkeypatch.setattr(deck_, "RUNNER", lambda argv, replace=False: Answer(True, code=1, err="no client\n"))
    with pytest.raises(deck_.DeckError, match="could not switch to the deck — no client"):
        deck_.switch("sb")


# ============================================================================
# Bare `sb deck` — the refusals
# ============================================================================


class Server:
    """Just enough tmux for `ensure`: no session yet, everything else succeeds."""

    def __init__(self):
        self.calls: list[tuple[list[str], bool]] = []

    def __call__(self, argv, replace=False):
        self.calls.append((list(argv), replace))
        verb = argv[1]
        if verb == "has-session":
            return Answer(True, code=1)
        if verb in ("new-session", "new-window"):
            return Answer(True, out="@1 %1\n")
        if verb == "show-options":
            return Answer(True, out="off\n")
        return Answer(True)


@pytest.fixture
def server(tmp_path, monkeypatch):
    fake = Server()
    monkeypatch.setattr(deck_, "RUNNER", fake)
    monkeypatch.setattr(deck_, "SB_HOME", tmp_path)
    monkeypatch.setattr("skyboss.rollcall.SB_HOME", tmp_path)
    monkeypatch.setattr(deck_.shutil, "which", lambda name, path=None: f"/usr/bin/{name}")
    monkeypatch.delenv("TMUX", raising=False)
    return fake


def test_json_is_refused_before_any_runner_call(server, said):
    result = invoke("--json", "deck")
    assert result.exit_code == 2 and server.calls == []
    assert "--json has no meaning here" in said(result)
    assert result.stdout == ""


def test_no_terminal_exits_1_with_the_attach_sentence_and_never_attaches(server, monkeypatch, said):
    monkeypatch.setattr(deck_, "has_terminal", lambda: False)
    result = invoke("deck")
    assert result.exit_code == 1
    assert "there is no terminal here to attach it to — run `tmux attach -t =sb`" in said(result)
    assert all(not replace for _, replace in server.calls)
    assert [argv for argv, _ in server.calls if argv[1] == "attach-session"] == []


def test_the_deck_warns_on_stderr_before_it_attaches(server, monkeypatch):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)
    result = invoke("deck")
    assert result.exit_code == 0, result.output
    assert "extended-keys" in result.stderr and "⚠️" in result.stderr
    assert result.stdout == ""
    assert server.calls[-1] == (["tmux", "attach-session", "-t", "=sb"], True)


def test_an_attach_that_fails_is_exit_1_with_tmuxs_reason(server, monkeypatch, said):
    monkeypatch.setattr(deck_, "has_terminal", lambda: True)

    def refuse_attach(argv, replace=False):
        if replace:
            return Answer(False, err="exec failed")
        return Server.__call__(server, argv, replace)

    monkeypatch.setattr(deck_, "RUNNER", refuse_attach)
    result = invoke("deck")
    assert result.exit_code == 1 and "could not attach — exec failed" in said(result)


# ============================================================================
# `sb deck queue --refresh` — the resident path, intercepted
# ============================================================================


@pytest.fixture
def quiet_queue(server, monkeypatch):
    """No providers, so `queue_result` reads only the fake tmux."""
    monkeypatch.setattr(deck_.agents_, "providers", lambda: [])


@pytest.fixture
def reside_calls(monkeypatch):
    calls: list[dict] = []

    def fake_reside(source, interval, run_once, **kwargs):
        calls.append({"source": source, "interval": interval, "result": run_once(), **kwargs})

    monkeypatch.setattr("skyboss.resident.reside", fake_reside)
    return calls


@pytest.fixture
def no_sleep(monkeypatch):
    """`resident_ndjson` binds `time.sleep` as a default, so inject it rather than patch the module."""
    monkeypatch.setattr(output, "resident_ndjson", functools.partial(output.resident_ndjson, sleep=lambda s: None))


def test_queue_at_a_terminal_resides_with_its_source_interval_and_runs(quiet_queue, reside_calls, at_a_terminal):
    result = invoke("deck", "queue", "--refresh", "5", "--ticks", "4")
    assert result.exit_code == 0, result.output
    (call,) = reside_calls
    assert call["source"] == "deck queue" and call["interval"] == 5 and call["runs"] == 4
    assert call["result"].data == [] and any("no deck session" in w for w in call["result"].warnings)


def test_screen_reaches_reside_and_is_off_by_default(quiet_queue, reside_calls, at_a_terminal):
    assert invoke("deck", "queue", "--refresh", "5", "--screen").exit_code == 0
    assert invoke("deck", "queue", "--refresh", "5").exit_code == 0
    assert [call["screen"] for call in reside_calls] == [True, False]


def test_queue_at_a_terminal_without_ticks_is_unbounded(quiet_queue, reside_calls, at_a_terminal):
    assert invoke("deck", "queue", "--refresh", "2").exit_code == 0
    assert reside_calls[0]["runs"] is None


def test_json_never_resides_even_at_a_terminal(quiet_queue, reside_calls, at_a_terminal, no_sleep):
    result = invoke("--json", "deck", "queue", "--refresh", "1", "--ticks", "2")
    assert result.exit_code == 0 and reside_calls == []
    assert [json.loads(line)["tick"] for line in result.stdout.splitlines()] == [1, 2]


def test_ticks_reaches_reside_as_runs_exactly_as_data_does(quiet_queue, reside_calls, at_a_terminal):
    assert invoke("deck", "queue", "--refresh", "3", "--ticks", "6").exit_code == 0
    assert invoke("data", "--refresh", "3", "--ticks", "6", "--", "printf", "[]").exit_code == 0
    deck_call, data_call = reside_calls
    assert deck_call["runs"] == data_call["runs"] == 6
    assert deck_call["interval"] == data_call["interval"] == 3


def test_ticks_counts_ndjson_envelopes_exactly_as_data_does(quiet_queue, no_sleep):
    deck_lines = invoke("deck", "queue", "--refresh", "1", "--ticks", "3").stdout.splitlines()
    data_lines = invoke("data", "--refresh", "1", "--ticks", "3", "--", "printf", "[]").stdout.splitlines()
    deck_ticks = [json.loads(line)["tick"] for line in deck_lines]
    data_ticks = [json.loads(line)["tick"] for line in data_lines]
    assert deck_ticks == data_ticks == [1, 2, 3]


def test_a_queue_envelope_under_json_keeps_its_warnings_off_stdout(quiet_queue):
    result = invoke("--json", "deck", "queue")
    envelope = json.loads(result.stdout)
    assert any("no deck session 'sb'" in w for w in envelope["warnings"])
    assert "no deck session" in result.stderr


# ============================================================================
# warn_now / _render_warnings
# ============================================================================


def test_warn_now_writes_each_message_to_stderr_in_order(capsys):
    warn_now(["first", "second"])
    captured = capsys.readouterr()
    assert captured.out == ""
    assert [line for line in captured.err.splitlines() if line] == ["⚠️  first", "⚠️  second"]


def test_warn_now_with_nothing_writes_nothing(capsys):
    warn_now([])
    assert capsys.readouterr() == ("", "")


def test_warn_now_prints_plain_punctuation_verbatim(capsys):
    warn_now(["deck 'sb' at 50% — fine"])
    assert "deck 'sb' at 50% — fine" in capsys.readouterr().err


@pytest.mark.parametrize("as_json", [True, False])
def test_rendered_warnings_end_in_exactly_what_warn_now_writes(capsys, as_json):
    result = Result("x", data=[{"a": 1}])
    result.warn("careful")
    result.degrade("host gone")
    render(result, as_json=as_json)
    rendered = capsys.readouterr()
    warn_now(["careful", "host gone"])
    direct = capsys.readouterr()
    assert rendered.err.endswith(direct.err) and direct.err.count("⚠️") == 2
    assert "careful" not in rendered.out.split('"warnings"')[0]
    if as_json:
        assert json.loads(rendered.out)["warnings"] == ["careful", "host gone"]


def test_a_bracketed_table_name_in_a_warning_survives(capsys):
    warn_now(["pin 'ghost': not declared — add [agent.ghost] to deck.toml"])
    assert "add [agent.ghost] to deck.toml" in " ".join(capsys.readouterr().err.split())


def test_a_closing_tag_shaped_warning_does_not_raise(capsys):
    warn_now(["unknown key '[/x]' — ignored"])
    assert "[/x]" in capsys.readouterr().err


def test_a_closed_stdin_is_no_terminal(monkeypatch):
    monkeypatch.setattr(deck_.sys, "stdin", None)
    assert deck_.has_terminal() is False
