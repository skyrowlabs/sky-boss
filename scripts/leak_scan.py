#!/usr/bin/env python3
"""Whether the commits this change adds introduce a secret, asked of gitleaks.

The commit range only, never all history: a repository adopting this template
has history written before any scanner, and a gate red on arrival is one people
learn to ignore. The range is `check_commit_subjects.default_range`'s, so "what
this push sends" has one definition.

The version is the `rev:` of the gitleaks hook in `.pre-commit-config.yaml`, its
one home; `--pinned` prints it so CI installs that binary. A hand run finds the
binary pre-commit built for that rev through pre-commit's own database, which
proves the pin, since the binary cannot report its version. Otherwise it takes
what is on PATH, unproven. A missing binary is a failure, never a pass: "could
not scan" is not "nothing found". Locally the commit hook scans every staged
change, which is why `check pre-push` does not run this. A false positive on a line you are adding takes an inline
`gitleaks:allow` comment. One already in history cannot: that commit's patch is
fixed, so its fingerprint (`<commit>:<file>:<rule>:<line>`, printed per finding)
goes in `.gitleaksignore` at the root (stash.flow#280). Never quote the value in
that file; gitleaks scans it too.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_commit_subjects import default_range  # noqa: E402
from scripts.output import EXIT_REFUSED, detail, emit, fail, item, line, ok, step  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402

PRE_COMMIT_CONFIG = PROJECT_ROOT / ".pre-commit-config.yaml"
GITLEAKS_REPO = "https://github.com/gitleaks/gitleaks"
_PIN = re.compile(r"repo:\s*https://github\.com/gitleaks/gitleaks\s*\n\s*rev:\s*v?(?P<version>[\d.]+)")


def pinned_version() -> str | None:
    match = _PIN.search(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    return match.group("version") if match else None


def pre_commit_home() -> Path:
    """Where pre-commit keeps its cache, by pre-commit's own rule."""
    home = os.environ.get("PRE_COMMIT_HOME")
    return Path(home) if home else Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser() / "pre-commit"


def prebuilt_binary(version: str | None) -> str | None:
    """The gitleaks pre-commit built at this exact rev, or None for any miss.

    `db.db` is pre-commit's internal format, so a schema it no longer has is a miss
    rather than an error, and a rev it did not build is a miss rather than a guess.
    """
    database = pre_commit_home() / "db.db"
    if not version or not database.exists():
        return None
    try:
        connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
        try:
            query = "SELECT path FROM repos WHERE repo = ? AND ref IN (?, ?)"
            row = connection.execute(query, (GITLEAKS_REPO, version, f"v{version}")).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    built = sorted(Path(row[0]).glob("golangenv-*/bin/gitleaks")) if row else []
    return str(built[0]) if built and os.access(built[0], os.X_OK) else None


def scan(binary: str, commit_range: str) -> tuple[int, list[dict], str]:
    """gitleaks' exit code, its findings (values redacted), and its stderr."""
    with tempfile.TemporaryDirectory() as scratch:
        report = Path(scratch) / "report.json"
        command = [binary, "git", "--no-banner", "--redact", "--exit-code", "1", "--log-opts", commit_range]
        command += ["--report-format", "json", "--report-path", str(report), str(PROJECT_ROOT)]
        proc = subprocess.run(command, capture_output=True, text=True)
        findings = json.loads(report.read_text(encoding="utf-8") or "[]") if report.exists() else []
    return proc.returncode, findings, proc.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--range", dest="commit_range", help="git range (default: what a push would send)")
    parser.add_argument("--pinned", action="store_true", help="print the pinned gitleaks version and stop")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    version = pinned_version()
    if args.pinned:
        if not version:
            fail(f"no gitleaks hook with a `rev:` in {PRE_COMMIT_CONFIG.name}")
            return EXIT_REFUSED
        line(version)
        return 0

    commit_range = args.commit_range or default_range()
    prebuilt = prebuilt_binary(version)
    binary = prebuilt or shutil.which("gitleaks")
    if not binary:
        if args.json:
            emit({"range": commit_range, "scanned": False, "findings": []})
        fail("gitleaks is not on PATH, so nothing was scanned")
        detail(f"CI installs the pinned binary ({version}); locally the commit hook scans staged changes.")
        return EXIT_REFUSED
    step(f"gitleaks: {binary} ({f'v{version}, by pre-commit' if prebuilt else 'from PATH, version unproven'})")
    code, findings, stderr = scan(binary, commit_range)
    rows = [
        {
            "rule": f.get("RuleID"),
            "file": f.get("File"),
            "line": f.get("StartLine"),
            "commit": (f.get("Commit") or "")[:8],
            "fingerprint": f.get("Fingerprint"),
        }
        for f in findings
    ]
    if args.json:
        emit({"range": commit_range, "scanned": code in (0, 1), "findings": rows})
    if code == 0:
        ok(f"no secrets in {commit_range}")
        return 0
    if code == 1 and rows:
        fail(f"{len(rows)} possible secret(s) in {commit_range}")
        for row in rows:
            item(f"{row['file']}:{row['line']} ({row['rule']}, commit {row['commit']})")
            if row["fingerprint"]:
                detail(f"fingerprint: {row['fingerprint']}")
        detail("Rotate a real credential. A false positive on a line you are adding takes an inline")
        detail("`gitleaks:allow` comment; one in a commit already made takes its fingerprint as a line")
        detail("in .gitleaksignore. Never quote the value there: that file is scanned too.")
        return 1
    fail(f"gitleaks exited {code} without a report")
    detail(stderr.strip())
    return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
