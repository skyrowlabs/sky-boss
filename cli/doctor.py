"""tb doctor — are the external CLIs installed, authenticated, and usable.

External tools keep their own authentication; tb is never in the credential
path (CLAUDE.md § Scope). Doctor therefore only *asks* each tool about itself.

**Raw tool output is never retained.** `stripe config --list` prints API keys,
and doctor's result goes to stdout and over MCP. Probe output is inspected
locally to derive a boolean and then discarded — only tb's own strings reach
the envelope.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable

import rich_click as click

from cli.helpers import run_command
from cli.output import Result, emit

# Every probe measured under 600ms on workstation. 12s is generous headroom for a
# slow network without letting doctor hang a scheduled job.
AUTH_TIMEOUT = 12


def _rc_ok(proc: subprocess.CompletedProcess) -> bool:
    return proc.returncode == 0


def _stripe_ok(proc: subprocess.CompletedProcess) -> bool:
    """`stripe config --list` exits 0 even with nothing configured.

    The exit code alone says nothing, so presence of a profile section is the
    signal. The output contains API keys and is discarded with this frame.
    """
    return proc.returncode == 0 and any(
        line.startswith("[") for line in proc.stdout.splitlines()
    )


@dataclass(frozen=True)
class ToolCheck:
    name: str
    auth_args: list[str]
    verify: Callable[[subprocess.CompletedProcess], bool] = _rc_ok
    hint: str = "not authenticated"


CHECKS: tuple[ToolCheck, ...] = (
    ToolCheck("aws", ["aws", "sts", "get-caller-identity"], hint="run: aws configure"),
    ToolCheck("bws", ["bws", "project", "list"], hint="BWS_ACCESS_TOKEN unset or invalid"),
    ToolCheck("gh", ["gh", "auth", "status"], hint="run: gh auth login"),
    ToolCheck("stripe", ["stripe", "config", "--list"], verify=_stripe_ok, hint="run: stripe login"),
    ToolCheck("tailscale", ["tailscale", "status", "--json"], hint="run: tailscale up"),
)


def _check(tool: ToolCheck, quick: bool) -> dict[str, Any]:
    if shutil.which(tool.name) is None:
        return {
            "tool": tool.name,
            "ok": False,
            "installed": False,
            "authenticated": None,
            "detail": "not installed",
        }

    if quick:
        return {
            "tool": tool.name,
            "ok": None,
            "installed": True,
            "authenticated": None,
            "detail": "not probed",
        }

    try:
        proc = run_command(tool.auth_args, timeout=AUTH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {
            "tool": tool.name,
            "ok": False,
            "installed": True,
            "authenticated": False,
            "detail": f"probe timed out after {AUTH_TIMEOUT}s",
        }
    except OSError:
        return {
            "tool": tool.name,
            "ok": False,
            "installed": True,
            "authenticated": False,
            "detail": "probe could not run",
        }

    authed = tool.verify(proc)
    return {
        "tool": tool.name,
        # `ok` is the single status the renderer draws; installed/authenticated
        # stay so machine consumers keep the distinction.
        "ok": authed,
        "installed": True,
        "authenticated": authed,
        "detail": None if authed else tool.hint,
    }


def check_tools(quick: bool = False) -> Result:
    """The check body, callable without a Click context.

    Split from the command so `tb check` can roll it up alongside the others.
    `quick` must keep a default: the rollup invokes every check with no
    arguments.
    """
    rows = [_check(tool, quick) for tool in CHECKS]
    result = Result(data=rows)

    # doctor itself succeeded — it is reporting, not failing. `partial` reflects
    # the health of what it looked at, which is what makes `tb doctor` usable as
    # a gate inside a job definition.
    for row in rows:
        if not row["installed"]:
            result.degrade(f"{row['tool']}: not installed")
        elif row["authenticated"] is False:
            result.degrade(f"{row['tool']}: {row['detail']}")

    return result


@click.command(name="tools")
@click.option("--quick", is_flag=True, help="Check installation only; skip auth probes.")
@emit
def tools(quick: bool) -> Result:
    """Check that external CLIs are installed and authenticated."""
    return check_tools(quick)
