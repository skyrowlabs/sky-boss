"""``dev settings`` — bring this repository's GitHub settings to `scripts/repo_settings.py`.

Previews by default and changes nothing until `--apply`, because every write here
lands on the account rather than in the tree, where no `git` command can undo it.
`dev doctor` reads the same declaration, so after an apply it should report
every setting as fine. Writing needs an admin token.
"""

from __future__ import annotations

import json
import subprocess

import click

from scripts.repo_settings import DESCRIPTION, compare, patch_body

from .doctor import Unreadable, gh_api
from .helpers import PROJECT_ROOT, detail, fail, ok, warn


def gh_write(method: str, path: str, body: dict | None = None) -> None:
    command = ["gh", "api", "-X", method, path] + (["--input", "-"] if body is not None else [])
    stdin = json.dumps(body) if body is not None else None
    result = subprocess.run(command, cwd=str(PROJECT_ROOT), input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        said = (result.stderr or result.stdout).strip().splitlines()
        raise Unreadable(said[-1] if said else f"gh api -X {method} {path} exited {result.returncode}")


def planned() -> tuple[dict, bool]:
    """The repository PATCH body, and whether Dependabot alerts need turning on."""
    repo = gh_api("repos/{owner}/{repo}")
    body = patch_body(compare(repo))
    if not (repo.get("description") or "").strip() and DESCRIPTION:
        body["description"] = DESCRIPTION
    try:
        gh_api("repos/{owner}/{repo}/vulnerability-alerts")
        alerts_off = False
    except Unreadable as error:
        if error.status != 404:
            raise
        alerts_off = True
    return body, alerts_off


@click.command()
@click.option("--apply", "write", is_flag=True, help="Make the changes instead of listing them.")
def settings(write: bool) -> None:
    """Set this repository's GitHub settings to the declared profile.

    \b
    Lists what would change, and changes nothing without --apply.
    The profile, and the reason for each setting, is scripts/repo_settings.py.
    """
    try:
        body, alerts_off = planned()
    except Unreadable as error:
        fail(f"could not read the repository's settings: {error}")
        raise SystemExit(1) from None
    changes = [f"{key} → {json.dumps(value)}" for key, value in body.items()]
    changes += ["Dependabot alerts → on"] if alerts_off else []
    if not changes:
        ok("every declared setting already matches")
        return
    for change in changes:
        detail(f"  {change}")
    if not write:
        warn(f"{len(changes)} change(s) to make; nothing written. Run again with --apply.")
        return
    try:
        if body:
            gh_write("PATCH", "repos/{owner}/{repo}", body)
        if alerts_off:
            gh_write("PUT", "repos/{owner}/{repo}/vulnerability-alerts")
    except Unreadable as error:
        fail(f"GitHub refused the change: {error}")
        raise SystemExit(1) from None
    ok(f"{len(changes)} change(s) made; `dev doctor` should now report each setting as fine")
