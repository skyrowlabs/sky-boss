"""``dev bug`` — capture a bug you found on the way, without widening your scope.

A bug you hit that is **not** what you were asked to work on has three bad
homes: your current change (which now does two things), a sentence in a session
that is about to end, and your memory. This gives it a fourth.

All four sections are **required**. A capture without a reproduction is a rumour;
one without acceptance criteria cannot be closed by anyone but its author; one
without a scope grows into a refactor. The refusal is the feature.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone

import click

from cli.helpers import PROJECT_ROOT, current_branch, detail, git, ok, warn
from scripts.paths import TMP_DIR

QUEUE = TMP_DIR / "bugs"


@click.command()
@click.argument("summary")
@click.option("--finding", required=True, help="path:line + what is wrong")
@click.option("--reproduce", required=True, help="exact command; observed vs expected")
@click.option("--scope", required=True, help="what is in, and what is explicitly out")
@click.option("--acceptance", required=True, help="the assertions; the command that must pass")
@click.option("--label", default="agent-bug", show_default=True)
@click.option("--local", is_flag=True, help="write to tmp/bugs/ instead of opening an issue")
def bug(summary: str, finding: str, reproduce: str, scope: str, acceptance: str, label: str, local: bool) -> None:
    """File a bug found outside the scope of what you were doing."""
    body = "\n".join(
        [
            "## Finding",
            finding,
            "",
            "## Reproduce",
            f"```\n{reproduce}\n```",
            "",
            "## Scope",
            scope,
            "",
            "## Acceptance",
            acceptance,
            "",
            "---",
            f"_Captured on `{current_branch()}` at `{git('rev-parse', '--short', 'HEAD')}`_",
        ]
    )

    if not local:
        result = subprocess.run(
            ["gh", "issue", "create", "--title", summary, "--body", body, "--label", label],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            ok(f"captured: {result.stdout.strip()}")
            detail("Mention this in your response so the user can kill it if they disagree.")
            return
        warn(
            f"gh failed ({result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown'}) — falling back to a local capture"
        )

    QUEUE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = QUEUE / f"{stamp}.json"
    path.write_text(
        json.dumps(
            {"summary": summary, "finding": finding, "reproduce": reproduce, "scope": scope, "acceptance": acceptance},
            indent=2,
        ),
        encoding="utf-8",
    )
    ok(f"captured locally: {path.relative_to(PROJECT_ROOT)}")
