"""``dev worktree`` — a second checkout, so two agents never share one branch.

A linked worktree is the answer to "I need a different branch" in a tree
somebody else is standing in. It costs disk and a provisioning step; it does not
cost the other agent their uncommitted work, which a `git switch` does.

**Remove it when the work is done.** A stranded tree holds hundreds of megabytes
and possibly a whole running stack.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import click

from .helpers import PROJECT_ROOT, detail, fail, git, item, line, ok, run

# Bootstrap only: `scripts/` is not a package on the path for a CLI module.
sys.path.insert(0, str(PROJECT_ROOT))
from scripts import tree_lock  # noqa: E402
from scripts.paths import REQUIREMENTS  # noqa: E402

#: tests/test_cli_smoke.py runs this module's argument-less commands for real.
SMOKE_EXECUTES = True


def _venv_inputs(root: Path) -> dict:
    """`{repo-relative path: bytes}` for everything the host venv is built from.

    Anchored on `scripts.paths.REQUIREMENTS` — the file that module declares as
    *the host toolchain this tree installs* — and then follows `-r` includes, so
    an adopter who splits their requirements is covered without a registry and
    without this function being edited.

    **It is deliberately not a glob**, and jam.sense is why. `git ls-files
    "*requirements*.txt"` was the first version: correct in a scaffold, where the
    tree has one Python environment, and wrong in a multi-service repository,
    where six of their ten tracked requirements files describe *container images*
    and resolve nowhere near the host venv. Digesting those means a dependency
    bump to a service — most weeks — declines the link forever, for a reason with
    nothing to do with the environment being borrowed. A scaffold cannot exhibit
    that shape, so nothing here could have found it.

    **The limit, and it is the opposite error to the one above.** The setup
    block installs the requirements file and, once `pyproject.toml` declares
    `[project]`, the project itself (`scripts/install_project.py`), so that file
    is an input too. A set that is too narrow **links** where it should decline,
    which is the quiet direction: too wide declines loudly and gets fixed; too
    narrow borrows the wrong environment and says nothing. Extend this when the
    setup block grows another kind of install.
    """
    seen: dict = {}
    pending = [root / REQUIREMENTS.relative_to(PROJECT_ROOT)]
    while pending:
        path = pending.pop()
        try:
            key = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            continue  # a `-r` reaching outside the tree is not this tree's input
        if key in seen or not path.is_file():
            continue
        seen[key] = path.read_bytes()
        for entry in seen[key].decode("utf-8", "replace").splitlines():
            stripped = entry.strip()
            if stripped.startswith("-r "):
                pending.append(path.parent / stripped[3:].strip())
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and "[project]" in pyproject.read_text(encoding="utf-8").splitlines():
        seen["pyproject.toml"] = pyproject.read_bytes()
    return seen


def _requirements_agree(target: Path) -> bool:
    """Does `target` install the same host toolchain as the primary?

    Compared by content rather than by mtime or by branch name: the question is
    whether the primary's installed packages are the right ones for this
    checkout, and only the requirements text answers it.

    A file present on one side and absent on the other counts as a difference,
    which is the safe direction — a new requirements file is exactly the change
    that makes a borrowed environment wrong.
    """
    return _venv_inputs(PROJECT_ROOT) == _venv_inputs(target)


def _link_node_modules(target: Path) -> None:
    """Borrow the primary's `node_modules` when the lockfiles agree, as `.venv` is borrowed.

    `check pre-push` runs eslint out of it, so a worktree without one fails on
    `command not found` (sky.boss).
    """
    modules = PROJECT_ROOT / "node_modules"
    if not modules.is_dir() or (target / "node_modules").exists():
        return
    locks = [root / "package-lock.json" for root in (PROJECT_ROOT, target)]
    if [lock.read_bytes() if lock.exists() else None for lock in locks] == [None, None] or (
        all(lock.exists() for lock in locks) and locks[0].read_bytes() == locks[1].read_bytes()
    ):
        (target / "node_modules").symlink_to(modules.resolve())
        item("linked node_modules (the primary's)")
    else:
        item("did NOT link node_modules — this branch's package-lock.json differs from the primary's")
        detail("  npm ci")


def start_point(base: str) -> str:
    """What `worktree new` cuts from: origin's branch, or the local one if origin says it has none.

    Only that answer falls back. An unreachable origin keeps failing, because a
    stale local branch would be cut from without a word.
    """
    asked = ["git", "ls-remote", "--exit-code", "origin", f"refs/heads/{base}"]
    local = ["git", "rev-parse", "-q", "--verify", f"refs/heads/{base}"]
    absent = subprocess.run(asked, cwd=str(PROJECT_ROOT), capture_output=True).returncode == 2
    if absent and subprocess.run(local, cwd=str(PROJECT_ROOT), capture_output=True).returncode == 0:
        return base
    run(["git", "fetch", "origin", base])
    return f"origin/{base}"


@click.group()
def worktree() -> None:
    """Linked worktrees — one checkout per branch."""


@worktree.command()
@click.argument("path")
@click.option("-b", "--branch", help="branch to create (defaults to the directory name)")
@click.option(
    "--base",
    default="develop",
    show_default=True,
    help="branch to cut from: origin's, or the local one when origin has no such branch",
)
def new(path: str, branch: str, base: str) -> None:
    """Create a worktree with its own branch, .env and scratch space."""
    target = Path(path).expanduser().resolve()
    branch = branch or target.name

    if target.exists():
        fail(f"{target} already exists")
        sys.exit(1)

    start = start_point(base)
    if run(["git", "worktree", "add", "-b", branch, str(target), start]).returncode != 0:
        fail("git worktree add failed")
        sys.exit(1)
    item(f"cut from {start}")

    # The .env is untracked, so a new tree has none — and a tree that cannot
    # boot is a tree whose suite silently skips everything.
    env = PROJECT_ROOT / ".env"
    if env.exists():
        shutil.copy2(env, target / ".env")
        item("copied .env")

    # The .venv is the same class of untracked-but-required, and its absence is
    # louder than a skip: `pyrightconfig.json` pins the interpreter with
    # `venvPath: "."`, which pyright resolves **relative to the config file** —
    # so in a worktree it points at a directory that does not exist, pyright
    # prints one line about it and falls back to whatever python is on PATH.
    # Measured on a scaffold of this template: 0 errors in the primary and 27 in
    # a fresh worktree, same commit, same pyright, every one of them `click`
    # resolving to Unknown. It reads as a broken branch rather than a missing
    # directory. Reported by jam.sense, who found it in four checkouts of five.
    #
    # Linked rather than built, and guarded rather than warned about. The first
    # version of this said "rebuild it here if this branch changes requirements",
    # which puts the one case that is silently wrong on the user to notice — and
    # the branch most likely to change requirements is the branch somebody cut a
    # worktree for. jam.sense already did this for `node_modules`, digesting
    # `package-lock.json` on both sides; this is that step for Python, and the
    # asymmetry is the finding: they had the pattern and had never applied it to
    # Python, and this template had the command that creates the exposure and not
    # the pattern.
    #
    # Declining by name beats linking quietly, and the asymmetry is what makes it
    # safe: a missing .venv makes pyright print `venv .venv subdirectory not
    # found in venv path <this tree>` on the line above its errors, which is the
    # thread back to this decision. A silently borrowed environment for the wrong
    # requirements prints nothing at all, and under `reportMissingImports: none`
    # a package it should have had simply stops constraining anything.
    venv = PROJECT_ROOT / ".venv"
    if venv.is_dir() and not (target / ".venv").exists():
        if _requirements_agree(target):
            (target / ".venv").symlink_to(venv.resolve())
            item("linked .venv (the primary's)")
        else:
            item("did NOT link .venv — this branch's requirements differ from the primary's")
            detail("  python3.12 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt")

    _link_node_modules(target)

    (target / "tmp").mkdir(exist_ok=True)

    ok(f"worktree at {target} on branch '{branch}'")
    detail()
    detail(f"cd {target}")
    detail("./dev check pre-push")
    detail()
    detail(f"When you are done:  dev worktree drop {target}")


def stranded(target: Path) -> list[str]:
    """Commits that removing `target` would lose: those only its detached HEAD reaches.

    A worktree on a branch loses nothing, because the branch outlives `git
    worktree remove`; branches are shared by every worktree of a repository, so
    counting unpushed branches blocked a clean tree for work in another
    (sky.boss). Only a detached HEAD can strand commits.
    """
    on_branch = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=str(target), capture_output=True)
    if on_branch.returncode == 0:
        return []
    found = subprocess.run(
        ["git", "log", "HEAD", "--not", "--branches", "--tags", "--remotes", "--oneline"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    return found.stdout.splitlines()


@worktree.command()
@click.argument("path")
@click.option("--force", is_flag=True, help="remove even with uncommitted work or stranded commits")
def drop(path: str, force: bool) -> None:
    """Remove a worktree, refusing if it still holds work.

    The refusal on stranded commits is the important half: a detached
    worktree's commits are reachable from nothing but its own HEAD, so that
    refusal is the only thing between them and silent deletion.
    """
    target = Path(path).expanduser().resolve()
    if not target.exists():
        fail(f"no such worktree: {target}")
        sys.exit(1)

    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(target), capture_output=True, text=True
    ).stdout.strip()
    if dirty and not force:
        fail(f"{target} has {len(dirty.splitlines())} uncommitted change(s) — refusing")
        detail("That work belongs to somebody. Commit it, or pass --force if you are sure.")
        sys.exit(1)

    # The third guard, and the one that was missing. `git status` and stranded
    # commits both describe the tree's *contents*; neither says whether somebody
    # is using it right now. A suite run does not dirty a tree and does not
    # create commits, so a checkout with a live `suite` hold is clean, pushed,
    # and was removed here with a green tick — out from under a running job.
    #
    # `root=target`, not a bare `holders()`. Holds are per-checkout, so the
    # module constant answers about *this* tree: the obvious fix would have
    # returned an empty list and reported "nothing holding it" about a tree it
    # never looked at. Naming the tree is the whole point of the guard.
    held = tree_lock.holders(root=target)
    if held and not force:
        fail(f"{target} has {len(held)} live hold(s):")
        for hold in held:
            item(f"{hold.owner} (pid {hold.pid}, {hold.kind} hold)")
        detail("Something is working in there now. Wait for it, or pass --force if you are sure.")
        sys.exit(1)

    lost = stranded(target)
    if lost and not force:
        fail(f"{target} has a detached HEAD holding {len(lost)} commit(s) on no branch, tag or remote:")
        for commit_line in lost[:5]:
            item(commit_line)
        detail("Removing the worktree loses them. Put a branch on HEAD and push it, or --force.")
        sys.exit(1)

    run(["git", "worktree", "remove", *(["--force"] if force else []), str(target)])
    ok(f"removed {target}")


@worktree.command(name="list")
def list_cmd() -> None:
    """Every worktree, and whether it holds anything."""
    line(git("worktree", "list"))


@worktree.command()
def holders() -> None:
    """Who is holding the primary tree right now."""
    sys.exit(subprocess.run([sys.executable, "scripts/tree_lock.py"], cwd=str(PROJECT_ROOT)).returncode)
