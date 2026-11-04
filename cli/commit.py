"""``dev commit`` — commit safely in a tree other agents may be editing.

pre-commit **stashes every unstaged change in the repo** while its hooks run. In
a shared tree that deletes another agent's in-flight work from disk for the
duration of the hooks, and silently discards anything they write in that window
— including on files your commit never touches.

This runs the same checks against **only the paths you name**, then commits with
`--no-verify`, so no stash ever happens. It also reads the branch twice: once
before the checks and once immediately before staging. The checks take tens of
seconds, and that window is the whole exposure — a branch that moved under you
means your commit would land somewhere nobody expects.
"""

from __future__ import annotations

import sys

import click

from scripts.paths import TMP_DIR

from .helpers import PROJECT_ROOT, current_branch, detail, fail, ok, run, script, step, summarize


def _staged_check(paths: list, message: str) -> int:
    """The pre-commit hook set, scoped to the given paths."""
    py = [p for p in paths if p.endswith(".py")]
    results = []

    if py:
        results.append(("flake8", run(["flake8", "--select=E9,F63,F7,F82,F401", "--show-source", *py]).returncode))
        results.append(("isort", run(["isort", "--check-only", "--diff", *py]).returncode))
        results.append(("black", run(["black", "--check", *py]).returncode))
        # Pyright is whole-project by construction — it has no per-file scoping,
        # and running it on a subset would report errors from imports rather
        # than from the files you changed.
        if (PROJECT_ROOT / "pyrightconfig.json").exists():
            # The wrapper, not pyright directly — the same entry the pre-commit
            # hook runs, and this command is a re-implementation of that hook.
            # It pre-flights the interpreter pyright would resolve, because a
            # bare one reports an environment fault as errors in files this
            # commit never touched. scripts/lint_pyright_gate.py.
            results.append(("pyright", script("scripts/lint_pyright_gate.py", "--project", "pyrightconfig.json")))

    if any(p.startswith("docs/") for p in paths):
        results.append(("docs indexes", run([sys.executable, "scripts/docs/regen.py", "--check"]).returncode))
        results.append(("doc tables", run([sys.executable, "scripts/check_doc_tables.py"]).returncode))

    # The commit-msg hook, run here because --no-verify will skip it later.
    msg_file = TMP_DIR / ".commit-msg"
    msg_file.parent.mkdir(parents=True, exist_ok=True)
    msg_file.write_text(message, encoding="utf-8")
    results.append(
        ("commit message", run(["bash", "scripts/hooks/conventional-commit-check.sh", str(msg_file)]).returncode)
    )

    # `summarize`, not a second copy of its table: the gate table had been
    # reimplemented here, and two renderings of one result drift — which is the
    # rule the rest of this tier exists to enforce.
    return summarize(results)


@click.command()
@click.option("-m", "--message", required=True, help="conventional commit message")
@click.option("--dry-run", is_flag=True, help="run the checks without staging or committing")
@click.argument("paths", nargs=-1, required=True)
def commit(message: str, dry_run: bool, paths: tuple) -> None:
    """Run the hook checks on PATHS only, then commit them without a stash."""
    path_list = list(paths)

    for path in path_list:
        if path in {".", "-A", "--all", "-a"}:
            fail(f"'{path}' stages the whole tree — in a shared tree that commits somebody else's work.")
            detail("Name the paths you touched.")
            sys.exit(1)
        if not (PROJECT_ROOT / path).exists():
            fail(f"no such path: {path}")
            sys.exit(1)

    branch_before = current_branch()
    step(f"checking {len(path_list)} path(s) on '{branch_before}'")

    if _staged_check(path_list, message) != 0:
        fail("checks failed — nothing staged, nothing committed")
        sys.exit(1)

    if dry_run:
        ok("dry run — checks passed, nothing staged")
        return

    # Read the branch again. The checks above took tens of seconds; if the tree
    # moved in that window, this commit would land on a branch nobody expects.
    branch_after = current_branch()
    if branch_after != branch_before:
        fail(f"the branch moved while the checks ran: '{branch_before}' → '{branch_after}'")
        detail("Somebody else is using this tree. Refusing to commit — re-run when it settles,")
        detail("or take your own tree with `dev worktree new <branch>`.")
        sys.exit(1)

    if run(["git", "add", "--", *path_list]).returncode != 0:
        fail("git add failed")
        sys.exit(1)

    # --no-verify is the whole point: the hooks already ran, scoped, above.
    # Letting pre-commit run them again would reintroduce the stash.
    result = run(["git", "commit", "--no-verify", "-m", message])
    if result.returncode != 0:
        fail("git commit failed — your paths are staged; nothing was stashed")
        sys.exit(1)

    ok(f"committed {len(paths)} path(s) on '{branch_after}'")
