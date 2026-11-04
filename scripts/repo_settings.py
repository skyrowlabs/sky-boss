"""The GitHub settings this repository expects, declared once.

`dev doctor` reports each one as a fact and `dev settings --apply` writes
them, so a value changed here changes both. A setting deleted here is neither
checked nor applied. Each carries its reason, so it can be judged when it is in
the way. Before this file existed the same template ran under five different
GitHub configurations across seven repositories, and nothing could tell.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Written only when GitHub's description is empty: it is the scaffold's tagline,
#: and a description somebody wrote since is theirs.
DESCRIPTION = "One CLI for watching what other tools do, here and across these repos"


@dataclass(frozen=True)
class Setting:
    #: The field on `GET repos/{owner}/{repo}`, and the key `PATCH` takes.
    key: str
    want: bool
    why: str


REPOSITORY = (
    Setting("allow_merge_commit", True, "a merge commit keeps every commit's conventional subject for the changelog"),
    Setting("allow_squash_merge", False, "a squash replaces the reviewed commits with one subject nobody reviewed"),
    Setting("allow_rebase_merge", False, "a rebase rewrites the SHAs a reviewer and CI saw"),
    Setting("delete_branch_on_merge", True, "a merged branch left behind reads as work still in progress"),
    Setting("allow_auto_merge", True, "a pull request marked to merge does so once its required checks pass"),
    Setting("has_wiki", False, "the docs live in docs/, where `check docs` can see them and a wiki cannot be"),
)

#: On only where the repository is public, judged by GitHub's own `visibility` at
#: the time of asking: a value recorded at scaffold time goes stale when it flips.
PUBLIC_ONLY = (
    Setting("secret_scanning", True, "a credential pushed to a public repository is published"),
    Setting("secret_scanning_push_protection", True, "refusing the push beats finding the secret after it"),
)

#: Dependabot alerts have their own endpoint and are not a field on the repository.
ALERTS_WHY = "a known-vulnerable dependency is reported here rather than found by somebody else"


@dataclass(frozen=True)
class Row:
    setting: Setting
    #: What GitHub reports, or `None` when the answer was not in what it returned.
    have: bool | None
    applies: bool = True


def compare(repo: dict[str, Any]) -> list[Row]:
    """Every declared setting against `repo`, the JSON of `GET repos/{owner}/{repo}`."""
    rows = [Row(s, repo[s.key] if isinstance(repo.get(s.key), bool) else None) for s in REPOSITORY]
    public = repo.get("visibility") == "public"
    analysis = repo.get("security_and_analysis")
    for setting in PUBLIC_ONLY:
        status = (analysis or {}).get(setting.key, {}).get("status") if isinstance(analysis, dict) else None
        have = None if status is None else status == "enabled"
        rows.append(Row(setting, have, applies=public))
    return rows


def patch_body(rows: list[Row]) -> dict[str, Any]:
    """The one `PATCH repos/{owner}/{repo}` body that brings every applicable row to what it wants."""
    body: dict[str, Any] = {}
    for row in rows:
        if not row.applies or row.have == row.setting.want:
            continue
        if row.setting in PUBLIC_ONLY:
            status = "enabled" if row.setting.want else "disabled"
            body.setdefault("security_and_analysis", {})[row.setting.key] = {"status": status}
        else:
            body[row.setting.key] = row.setting.want
    return body
