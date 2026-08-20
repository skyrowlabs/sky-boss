"""tb unpushed — work that exists on only one disk.

Not project orchestration: this asks a data-risk question. A repo with
uncommitted changes, unpushed commits, or no remote at all is work that a disk
failure would take with it, and nothing else on this machine notices.
"""

from __future__ import annotations

from pathlib import Path

import rich_click as click

from cli.helpers import run_command
from cli.output import Result, emit

# One root, because tackle-box lives under it now. SCAN_DEPTH reaches it as a
# child, so this scans itself — which is correct: its own unpushed work is work
# on a single disk like any other.
DEFAULT_ROOTS = (Path.home() / "skyrow.labs",)
SCAN_DEPTH = 2


def find_repos(roots: tuple[Path, ...] = DEFAULT_ROOTS, depth: int = SCAN_DEPTH) -> list[Path]:
    """Git working trees under the given roots.

    Shallow on purpose: nested repos inside a checkout are usually vendored
    dependencies, not work.
    """
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if (root / ".git").exists():
            found.append(root)
            continue
        for candidate in sorted(root.iterdir()):
            if candidate.is_dir() and (candidate / ".git").exists():
                found.append(candidate)
    return found


def _git(repo: Path, *args: str):
    return run_command(["git", "-C", str(repo), *args], timeout=15)


def inspect_repo(repo: Path) -> dict:
    """One repo's exposure."""
    status = _git(repo, "status", "--porcelain")
    uncommitted = len([l for l in status.stdout.splitlines() if l.strip()]) if status.returncode == 0 else None

    remotes = _git(repo, "remote")
    has_remote = bool(remotes.stdout.strip()) if remotes.returncode == 0 else False

    unpushed = None
    if has_remote:
        # @{u} fails when the branch has no upstream, which is itself exposure.
        ahead = _git(repo, "rev-list", "--count", "@{u}..HEAD")
        unpushed = int(ahead.stdout.strip()) if ahead.returncode == 0 and ahead.stdout.strip().isdigit() else None

    if not has_remote:
        detail = "no remote — exists only on this disk"
    elif unpushed is None:
        detail = "no upstream branch"
    else:
        parts = []
        if unpushed:
            parts.append(f"{unpushed} unpushed")
        if uncommitted:
            parts.append(f"{uncommitted} uncommitted")
        detail = ", ".join(parts) if parts else "clean"

    at_risk = (not has_remote) or unpushed is None or bool(unpushed) or bool(uncommitted)

    return {
        "repo": repo.name,
        "ok": not at_risk,
        "detail": detail,
        "path": str(repo),
        "has_remote": has_remote,
        "unpushed": unpushed,
        "uncommitted": uncommitted,
    }


def check_unpushed(roots: tuple[Path, ...] = ()) -> Result:
    """The check body, callable without a Click context.

    Split from the command so `tb check` can roll it up alongside the others.
    `roots` must keep a default: the rollup invokes every check with no
    arguments.
    """
    repos = find_repos(roots or DEFAULT_ROOTS)
    if not repos:
        return Result(data="no git repositories found")

    rows = [inspect_repo(repo) for repo in repos]
    rows.sort(key=lambda r: (r["ok"], r["repo"]))

    result = Result(data=rows)
    for row in rows:
        if not row["ok"]:
            result.degrade(f"{row['repo']}: {row['detail']}")
    return result


@click.command()
@click.option(
    "--root",
    "roots",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help=f"Directory to scan. Repeatable. Default: {', '.join(str(r) for r in DEFAULT_ROOTS)}",
)
@emit
def unpushed(roots: tuple[Path, ...]) -> Result:
    """Find work that exists on only one disk."""
    return check_unpushed(roots)
