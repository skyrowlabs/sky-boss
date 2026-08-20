"""Tests for tb doctor.

The load-bearing one is `test_probe_output_never_reaches_envelope` — doctor
probes a tool that prints API keys, and its result goes to stdout and over MCP.
"""

import json
import shutil
import subprocess

import pytest
from click.testing import CliRunner

from cli import cli
from cli.doctor import _check, _rc_ok, _stripe_ok, CHECKS, ToolCheck

FAKE_SECRET = "sk_live_THIS_MUST_NEVER_APPEAR"


def proc(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["fake"], returncode, stdout, stderr)


# ---------------------------------------------------------------- verifiers


def test_rc_ok():
    assert _rc_ok(proc(0)) is True
    assert _rc_ok(proc(1)) is False


def test_stripe_ok_requires_a_profile_section():
    """`stripe config --list` exits 0 with nothing configured.

    The exit code is therefore not a signal; a profile section is. If the stripe
    CLI ever changes that output shape, this test is the thing that notices.
    """
    assert _stripe_ok(proc(0, "[default]\napi_key = x\n")) is True
    assert _stripe_ok(proc(0, "")) is False
    assert _stripe_ok(proc(0, "no sections here\n")) is False
    assert _stripe_ok(proc(1, "[default]\n")) is False


# ---------------------------------------------------------------- _check


@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")


def test_check_reports_missing_tool(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    row = _check(CHECKS[0], quick=False)
    assert row["installed"] is False
    assert row["authenticated"] is None
    assert row["detail"] == "not installed"


def test_check_quick_skips_the_probe(installed, monkeypatch):
    def explode(*a, **k):
        raise AssertionError("--quick must not run an auth probe")

    monkeypatch.setattr("cli.doctor.run_command", explode)
    row = _check(CHECKS[0], quick=True)
    assert row["installed"] is True
    assert row["authenticated"] is None


def test_check_timeout_is_not_authenticated(installed, monkeypatch):
    def timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=12)

    monkeypatch.setattr("cli.doctor.run_command", timeout)
    row = _check(CHECKS[0], quick=False)
    assert row["authenticated"] is False
    assert "timed out" in row["detail"]


def test_check_unrunnable_probe_is_not_authenticated(installed, monkeypatch):
    monkeypatch.setattr("cli.doctor.run_command", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    row = _check(CHECKS[0], quick=False)
    assert row["authenticated"] is False


def test_check_authenticated(installed, monkeypatch):
    monkeypatch.setattr("cli.doctor.run_command", lambda *a, **k: proc(0))
    row = _check(ToolCheck("aws", ["aws"]), quick=False)
    assert row["authenticated"] is True
    assert row["detail"] is None


def test_check_unauthenticated_carries_the_hint(installed, monkeypatch):
    monkeypatch.setattr("cli.doctor.run_command", lambda *a, **k: proc(1))
    row = _check(ToolCheck("gh", ["gh"], hint="run: gh auth login"), quick=False)
    assert row["authenticated"] is False
    assert row["detail"] == "run: gh auth login"


# ---------------------------------------------------------------- command


def test_probe_output_never_reaches_envelope(installed, monkeypatch):
    """Probe output is inspected locally and discarded — never carried.

    `stripe config --list` prints API keys, and this envelope goes to stdout and
    over MCP. Only tb's own strings may reach `data`.
    """
    monkeypatch.setattr(
        "cli.doctor.run_command",
        lambda *a, **k: proc(0, f"[default]\napi_key = {FAKE_SECRET}\n"),
    )
    res = CliRunner().invoke(cli, ["--json", "doctor"])
    assert FAKE_SECRET not in res.stdout
    assert FAKE_SECRET not in res.stderr
    assert FAKE_SECRET not in json.dumps(json.loads(res.stdout))


def test_unhealthy_tool_degrades_but_doctor_still_succeeded(installed, monkeypatch):
    """doctor reports; it does not fail. partial describes what it looked at."""
    monkeypatch.setattr("cli.doctor.run_command", lambda *a, **k: proc(1))
    res = CliRunner().invoke(cli, ["--json", "doctor"])
    envelope = json.loads(res.stdout)
    assert envelope["ok"] is True
    assert envelope["partial"] is True
    assert len(envelope["warnings"]) == len(CHECKS)
    assert res.exit_code == 3


def test_all_healthy_exits_zero(installed, monkeypatch):
    monkeypatch.setattr(
        "cli.doctor.run_command", lambda *a, **k: proc(0, "[default]\n")
    )
    res = CliRunner().invoke(cli, ["--json", "doctor"])
    assert json.loads(res.stdout)["partial"] is False
    assert res.exit_code == 0
