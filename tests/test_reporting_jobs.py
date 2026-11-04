"""The registry, the CLI and the heartbeat config cannot drift apart.

Each half of this was once silent. The schedule lived as a hand-maintained
string several hundred lines from the commands it described, so a registry entry
with no subcommand produced a cron line pointing at nothing, and a subcommand
with no entry produced a job nobody ever scheduled. Neither fails loudly: the
first fails at 3am in a log nobody reads, and the second never fails at all.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.lanes import LANES, SOURCE_ENV  # noqa: E402
from scripts.paths import PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402
from scripts.reporting.jobs import (  # noqa: E402
    FIX_POLICIES,
    JOBS,
    JOBS_BY_KEY,
    SINK_QUEUE,
    SINK_READER,
    SINKS,
    _allowlisted,
    crontab_block,
    merged_crontab,
)


def _cli_commands():
    from tests.shell import module

    report = module("report").report

    return set(report.commands) - {"cron", "watch", "status"}


def test_every_registry_entry_has_a_subcommand():
    missing = {job.key for job in JOBS} - _cli_commands()
    assert not missing, f"Registered with no `dev report` subcommand: {sorted(missing)}"


def test_every_subcommand_has_a_registry_entry():
    orphans = _cli_commands() - {job.key for job in JOBS}
    assert not orphans, (
        f"`dev report` subcommands with no registry entry: {sorted(orphans)} — "
        "these are commands nobody will ever schedule."
    )


def test_every_job_module_exists():
    missing = [job.key for job in JOBS if not (SCRIPTS_DIR / "reporting" / f"{job.module}.py").exists()]
    assert not missing, f"Jobs whose module file is missing: {missing}"


def test_every_job_has_a_prompt_named_after_its_module():
    """The prompt's filename is how the fix policy is resolved. A prompt named
    anything else is a job whose blast radius nothing can look up."""
    prompts = SCRIPTS_DIR / "reporting" / "prompts"
    missing = [job.key for job in JOBS if job.agent and not (prompts / f"{job.module}.md").exists()]
    assert not missing, f"Jobs with no prompts/<module>.md: {missing}"


def test_fix_policies_are_known():
    unknown = {job.key: job.fix_policy for job in JOBS if job.fix_policy not in FIX_POLICIES}
    assert not unknown, f"Unknown fix policies: {unknown}. Valid: {sorted(FIX_POLICIES)}"


def test_committing_jobs_do_not_share_a_cron_minute():
    """Only one committing job may be in flight at a time.

    Nearly every job spawns an agent that edits and commits the same tree, and
    several regenerate the same derived docs. Run concurrently they race on git
    and on those files — and the loser's work vanishes with no error.
    """
    seen = {}
    for job in (j for j in JOBS if j.commits):
        minute, hour = job.cron.split()[0], job.cron.split()[1]
        days = job.cron.split()[4]
        key = (minute, hour, days)
        assert key not in seen, (
            f"'{job.key}' and '{seen[key]}' both commit and both fire at {hour}:{minute} on day-spec '{days}'. "
            "They will race on the git tree."
        )
        seen[key] = job.key


def test_heartbeat_vars_are_unique():
    seen = {}
    for job in JOBS:
        if not job.heartbeat_var:
            continue
        assert job.heartbeat_var not in seen, (
            f"'{job.key}' and '{seen[job.heartbeat_var]}' share {job.heartbeat_var} — "
            "one dead job would be masked by the other's ping."
        )
        seen[job.heartbeat_var] = job.key


def test_heartbeat_vars_are_documented_in_env_example():
    """A monitor variable no operator can find is a monitor nobody wires up."""
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    missing = [job.heartbeat_var for job in JOBS if job.heartbeat_var and job.heartbeat_var not in env_example]
    assert not missing, f"Heartbeat vars absent from .env.example: {missing}"


def test_allowlisted_jobs_give_a_reason():
    """An unexplained gap in the crontab reads identically to a job that
    silently stopped running. The reason is what distinguishes them."""
    reasonless = [key for key, reason in _allowlisted().items() if not reason]
    assert not reasonless, f"Schedule-allowlist entries with no reason: {reasonless}"


def test_allowlist_names_real_jobs():
    """An entry naming a job that does not exist is a stale exemption.

    The direction with teeth: a job key that leaves the registry and later comes
    back for something else would arrive **pre-exempted from the crontab**, and
    nobody chose that. The job would be registered, documented, and silently
    never scheduled — which is the failure `test_allowlisted_jobs_give_a_reason`
    exists to prevent, arriving through the allowlist instead of past it.
    """
    unknown = set(_allowlisted()) - set(JOBS_BY_KEY)
    assert not unknown, f"Allowlist names jobs that do not exist: {sorted(unknown)} — a stale exemption"


def test_crontab_block_sets_path():
    """cron does not give you your login PATH. A job that works in your shell
    and not under cron is almost always this — and it fails by not finding the
    interpreter, which reads as a broken job rather than a broken PATH."""
    assert "PATH=" in crontab_block()


SIBLING = "\n".join(
    [
        "MAILTO=me",
        "0 3 * * * cd /elsewhere && ./other nightly",
        "# ── BEGIN generated by `dev report cron --print` ──",
        "0 4 * * * cd /a/sibling/tree && ./dev report repo-report >> log 2>&1",
        "# ── END generated ──",
    ]
)


def test_install_keeps_every_line_that_is_not_this_trees():
    """`crontab -` replaces the whole crontab, which held other projects' jobs."""
    merged = merged_crontab(SIBLING + "\n")
    assert merged.startswith(SIBLING + "\n")
    assert crontab_block() in merged


def test_install_replaces_this_trees_block_and_strays_in_place():
    ours = JOBS[0].cron_line()
    stale = crontab_block().replace(ours, "1 1 * * * " + ours.split(" ", 5)[5])
    merged = merged_crontab(f"{stale}{SIBLING}\n{ours}\n")
    assert merged == crontab_block() + SIBLING + "\n"
    assert merged_crontab(merged) == merged


def test_install_saves_the_crontab_it_replaces(monkeypatch, tmp_path):
    import subprocess

    import scripts.paths
    from scripts.reporting import shellout
    from tests.shell import module

    report = module("report")
    calls = []

    def crontab(argv, **kwargs):
        calls.append((argv, kwargs.get("input")))
        return subprocess.CompletedProcess(argv, 0, SIBLING + "\n" if argv[1] == "-l" else "", "")

    monkeypatch.setattr(shellout, "run", crontab)
    monkeypatch.setattr(scripts.paths, "TMP_DIR", tmp_path)
    monkeypatch.setattr(report, "PROJECT_ROOT", tmp_path)
    report._install(SIBLING + "\n")
    assert calls == [(["crontab", "-"], merged_crontab(SIBLING + "\n"))]
    assert [p.read_text(encoding="utf-8") for p in (tmp_path / "reporting").iterdir()] == [SIBLING + "\n"]


def test_agent_argv_substitutes_the_prompt():
    """The default invocation carries the prompt as one argument."""
    from scripts.reporting.agent_runner import agent_argv

    argv = agent_argv("PROMPT-BODY")
    assert "PROMPT-BODY" in argv, argv
    assert "{prompt}" not in " ".join(argv)


def test_agent_argv_honours_the_override(monkeypatch):
    from scripts.reporting.agent_runner import AGENT_CMD_VAR, agent_argv

    monkeypatch.setenv(AGENT_CMD_VAR, "some-agent run --yes {prompt}")
    assert agent_argv("BODY") == ["some-agent", "run", "--yes", "BODY"]


def test_agent_argv_refuses_a_template_with_no_prompt(monkeypatch):
    """The failure that looks most like success.

    An agent invoked with no instruction starts, does nothing, and exits 0 — and
    the ledger then records `ok` for a job that was never asked to do anything.
    Refusing here turns that into a decline with a reason.
    """
    from scripts.reporting.agent_runner import AGENT_CMD_VAR, agent_argv

    monkeypatch.setenv(AGENT_CMD_VAR, "some-agent run --yes")
    with pytest.raises(ValueError, match="no .*prompt.* token"):
        agent_argv("BODY")


def test_agent_command_is_documented_for_operators():
    """A knob no operator can find is a knob nobody turns — the same rule the
    heartbeat variables follow."""
    from scripts.reporting.agent_runner import AGENT_CMD_VAR

    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    assert AGENT_CMD_VAR in env_example


def test_a_siblings_crontab_line_is_not_read_as_ours():
    """A crontab is per-user. Every project on this machine shares one file.

    `report cron --check` matched a bare `report <key>` against all of
    `crontab -l`, so a sibling repository running the same job key answered for
    us — a green check whose entire purpose is to catch a job that is registered
    and **not** installed. The needle is the directory and the wrapper name,
    which are the two things that make a line ours and the two a user has no
    reason to edit.

    The third assertion is the one that keeps the other two honest: the forged
    line must still contain the bare key, because that is what the old
    predicate matched. Without it a typo in the forgery would make this pass by
    testing nothing — a plant that did not land is indistinguishable from a
    gate that works.
    """
    for job in scanned(JOBS, "registered jobs"):
        assert job.needle() in job.cron_line(), f"{job.key}: our own line is not recognised as ours"

        elsewhere = job.cron_line().replace(str(PROJECT_ROOT), "/somewhere/else/another-repo")
        wrapper = job.cron_line().replace("&& ./", "&& ./other-")
        for forged, what in ((elsewhere, "another checkout"), (wrapper, "another wrapper")):
            assert f"report {job.key}" in forged, f"{job.key}: the {what} plant did not land"
            assert job.needle() not in forged, f"{job.key}: a line from {what} read as ours"


def _prompt(job) -> str:
    return (SCRIPTS_DIR / "reporting" / "prompts" / f"{job.module}.md").read_text(encoding="utf-8")


def test_every_report_declares_where_its_findings_go():
    """A report with no sink re-derives the same finding every edition, unacted on."""
    for job in scanned(JOBS, "registered jobs"):
        if job.writes == "—":
            assert job.findings_sink is None, f"{job.key} writes no report but declares a findings_sink"
        else:
            assert job.findings_sink in SINKS, (
                f"{job.key} writes {job.writes} and declares findings_sink={job.findings_sink!r}; "
                f"choose one of {SINKS} — see SINKS in scripts/reporting/jobs.py"
            )


def test_a_reader_sink_names_its_reader():
    """`reader` is the sink that silently stops happening, so it has to say who."""
    for job in scanned(JOBS, "registered jobs"):
        assert (job.findings_sink == SINK_READER) == bool(job.reader.strip()), (
            f"{job.key}: findings_sink={job.findings_sink!r} with reader={job.reader!r} — a "
            "reader sink names who reads it and how often, and only a reader sink does"
        )


def test_a_queue_sink_is_one_the_prompt_files_into():
    """Declared and wired are checked together: the prompt runs a capture command."""
    intake = re.compile(r"\./\S+ (?:{}) ".format("|".join(lane.key for lane in LANES)))
    for job in scanned(JOBS, "registered jobs"):
        files = job.agent and bool(intake.search(_prompt(job)))
        assert (job.findings_sink == SINK_QUEUE) == files, (
            f"{job.key}: findings_sink={job.findings_sink!r}, and its prompt "
            f"{'does' if files else 'does not'} run a capture command"
        )


def test_the_agent_runs_as_its_job(monkeypatch):
    """Every capture the agent files is attributed to, and capped against, this job."""
    import subprocess

    from scripts.reporting import agent_runner

    seen = {}

    def agent(argv, **kwargs):
        seen.update(kwargs.get("env") or {})
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(agent_runner, "current_branch", lambda: "main")
    monkeypatch.setattr(agent_runner, "tree_is_clean", lambda: True)
    monkeypatch.setattr(agent_runner.run_ledger, "record", lambda run: None)
    monkeypatch.setattr(agent_runner.subprocess, "run", agent)
    job = scanned(JOBS, "registered jobs")[0]
    agent_runner.run_triage(job.key, {}, base_branch="main")
    assert seen.get(SOURCE_ENV) == job.key
