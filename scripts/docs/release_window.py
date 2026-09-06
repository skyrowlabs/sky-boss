#!/usr/bin/env python3
"""Resolve the report window — the single source of truth for "since when".

A report describes a **commit range bounded by release tags**, never "everything
since this last ran". A window that straddles a release boundary cannot answer
the only question that matters about a finding: *is this in production right
now?*

Every consumer — the report generators, the freeze step, CI's anchor check —
imports this module rather than re-deriving the range. That is the same rule as
``queue_order.py``: a value two consumers must agree on is computed once.

| State     | Window               | Lives in                                |
| --------- | -------------------- | --------------------------------------- |
| in-flight | ``<latest tag>..HEAD``   | ``docs/reports/regular/``            |
| released  | ``<prev tag>..<tag>``    | ``docs/reports/releases/<tag>/``     |

Usage:
    python scripts/docs/release_window.py                     # in-flight window as JSON
    python scripts/docs/release_window.py --release v1.4.0    # a frozen window
    python scripts/docs/release_window.py --apply             # stamp regular/*.md
    python scripts/docs/release_window.py --apply --only x.md # stamp ONE report
    python scripts/docs/release_window.py --check             # validate every anchor
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.docs import frontmatter  # noqa: E402
from scripts.output import die, emit, fail, item, ok  # noqa: E402
from scripts.paths import PROJECT_ROOT, REGULAR_DIR, RELEASES_DIR  # noqa: E402

#: Reports that carry an anchor. A new scheduled report is added here so
#: ``--apply`` stamps it and the freeze step archives it; a report absent from
#: this list is refreshed by hand or only at release time, which is the exact
#: condition the anchoring exists to remove — and an invisible one, since the
#: file keeps existing while describing an older and older build.
ANCHORED_REPORTS: List[str] = []

_WINDOW_LINE = re.compile(r"^> \*\*Window:\*\*.*$", re.MULTILINE)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False).stdout.strip()


def tags() -> List[str]:
    """Release tags, newest first. Empty before the first release."""
    raw = _git("tag", "--list", "v*", "--sort=-creatordate")
    return [t for t in raw.splitlines() if t.strip()]


def window(release: Optional[str] = None) -> Dict[str, object]:
    """The window a report should describe.

    Before the first release there is no previous tag, so the range opens at the
    root commit. That is the honest answer: the report genuinely describes
    everything, and inventing a boundary would be worse than a wide one.
    """
    all_tags = tags()
    if release:
        if release not in all_tags:
            die(f"unknown release tag: {release}")
        idx = all_tags.index(release)
        previous = all_tags[idx + 1] if idx + 1 < len(all_tags) else None
        head = release
        status = "released"
    else:
        previous = all_tags[0] if all_tags else None
        head = "HEAD"
        status = "in-flight"

    if previous:
        base = previous
    else:
        # No release yet: open the range at the root commit. That is the honest
        # answer — the report genuinely describes everything — and a wide window
        # is better than an invented boundary.
        roots = _git("rev-list", "--max-parents=0", "HEAD").splitlines()
        base = roots[0][:12] if roots else ""
    commit_range = f"{base}..{head}" if base else head
    count = _git("rev-list", "--count", commit_range) or "0"
    return {
        "status": status,
        "release": release or "unreleased",
        "previous_release": previous or "",
        "commit_range": commit_range,
        "commits": int(count),
        "head_sha": _git("rev-parse", "--short", head),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _prose(win: Dict[str, object]) -> str:
    label = (
        win["release"]
        if win["status"] == "released"
        else f"unreleased (since {win['previous_release'] or 'the first commit'})"
    )
    return f"> **Window:** {label} — `{win['commit_range']}` ({win['commits']} commits, at `{win['head_sha']}`)"


def apply(only: Optional[str] = None) -> int:
    """Stamp the anchor onto in-flight reports.

    ``--only`` exists because ``generated:`` is part of the stamp: a bare
    ``--apply`` rewrites every anchored report, so the first job of the day
    dirties all of them and a job that then commits only its own leaves the rest
    permanently modified — claiming a refresh that never happened. Bulk
    re-anchoring is a release-time operation; a scheduled job scopes to its own
    report.
    """
    win = window()
    targets = [only] if only else ANCHORED_REPORTS
    if only and only not in ANCHORED_REPORTS:
        fail(f"{only} is not in ANCHORED_REPORTS — add it there first")
        return 1

    for name in targets:
        path = REGULAR_DIR / name
        if not path.exists():
            fail(f"missing report: {path.relative_to(PROJECT_ROOT)} — seed it before scheduling its job")
            return 1
        data, body = frontmatter.read(path)
        data.update({k: win[k] for k in ("release", "previous_release", "commit_range", "status", "generated")})
        body = _WINDOW_LINE.sub("", body).strip("\n")
        # The prose line goes immediately under the H1, where a human reads it;
        # the frontmatter is for the checker. Both, because either alone rots.
        lines = body.splitlines()
        if lines and lines[0].startswith("# "):
            body = "\n".join([lines[0], "", _prose(win), *lines[1:]])
        else:
            body = _prose(win) + "\n\n" + body
        frontmatter.write(path, data, body + "\n")
        item(f"anchored {name}")
    return 0


def check() -> int:
    """Every anchored report must exist, parse, and agree with where it lives."""
    failures = []
    for name in ANCHORED_REPORTS:
        path = REGULAR_DIR / name
        if not path.exists():
            failures.append(f"{name}: missing from docs/reports/regular/")
            continue
        data, body = frontmatter.read(path)
        missing = [k for k in ("release", "commit_range", "status", "generated") if not data.get(k)]
        if missing:
            failures.append(f"{name}: frontmatter missing {', '.join(missing)}")
        elif data.get("status") != "in-flight":
            failures.append(f"{name}: status is '{data['status']}' but it lives in regular/ (must be in-flight)")
        if not _WINDOW_LINE.search(body):
            failures.append(f"{name}: no '> **Window:**' line under the H1")

    for edition in sorted(RELEASES_DIR.glob("*/*.md")):
        data, _ = frontmatter.read(edition)
        if data.get("status") != "released":
            failures.append(f"{edition.relative_to(PROJECT_ROOT)}: frozen edition must carry status: released")

    if failures:
        fail("report anchors:")
        for failure in failures:
            item(failure)
        return 1
    ok(f"report anchors: {len(ANCHORED_REPORTS)} in-flight, {len(list(RELEASES_DIR.glob('*/*.md')))} frozen")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", help="resolve a frozen release's window instead of the in-flight one")
    parser.add_argument("--apply", action="store_true", help="stamp the anchor onto in-flight reports")
    parser.add_argument("--only", help="with --apply: stamp exactly one report (what a scheduled job should use)")
    parser.add_argument("--check", action="store_true", help="validate every anchor")
    args = parser.parse_args()

    if args.check:
        return check()
    if args.apply:
        return apply(args.only)
    emit(window(args.release))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
