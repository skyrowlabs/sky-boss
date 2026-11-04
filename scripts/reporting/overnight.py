#!/usr/bin/env python3
"""`overnight` — what every job did in the last day, written down even when nothing happened.

No agent stage: the facts are the ledger and the schedule, and summarising them
needs no judgement. Every night writes a digest, because "no digest" reads the
same as "this job died" and only one of those is fine. jam.sense's rollup has the
same rule, and its "🟡 idle" line for a night with nothing due is the shape here
(`jam-sense@6cda3ca04`, `scripts/reporting/overnight_rollup.py`).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.output import line  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402
from scripts.reporting import agent_runner, run_ledger, status  # noqa: E402
from scripts.reporting.jobs import JOBS_BY_KEY  # noqa: E402

KEY = "overnight"
WINDOW = timedelta(hours=24)


def digest(now: datetime | None = None) -> str:
    """The digest's markdown: a verdict line, then one line per job."""
    now = now or datetime.now(UTC)
    since = (now - WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs = [r for r in run_ledger.recent(2000) if r.get("started", "") >= since and r.get("job") != KEY]
    rows = [entry for entry in status.jobs(now) if entry["job"] != KEY]
    failed = sorted({r["job"] for r in runs if r.get("outcome") == "failed"})
    overdue = [entry["job"] for entry in rows if entry["overdue"]]
    if failed or overdue:
        verdict = f"🔴 attention: failed {', '.join(failed) or 'none'}; overdue {', '.join(overdue) or 'none'}"
    elif not runs:
        verdict = f"🟡 idle: no job ran in the last {int(WINDOW.total_seconds() // 3600)}h, and none was overdue"
    else:
        verdict = f"✅ green: {len(runs)} run(s), none failed, none overdue"
    lines = [f"# Overnight, {now:%Y-%m-%d %H:%M} UTC", "", verdict, ""]
    for entry in rows:
        mark = "off" if entry["intentionally_off"] else entry["result"]
        lines.append(f"- `{entry['job']}`: {mark}, last {entry['last_age']}, next {entry['next_run'] or '—'}")
    return "\n".join(lines) + "\n"


def main() -> int:
    job = JOBS_BY_KEY[KEY]
    started = run_ledger.now()
    text = digest()
    line(text)
    if agent_runner.dry_run():
        return 0
    target = PROJECT_ROOT / job.writes
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    branch = agent_runner.current_branch() or ""
    run_ledger.record(run_ledger.Run(job=KEY, outcome="ok", started=started, finished=run_ledger.now(), branch=branch))
    agent_runner.heartbeat(os.environ.get(job.heartbeat_var or ""), "up")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
