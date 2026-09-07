"""The commit-msg hook accepts exactly the types Release Please can read.

Two artifacts in this tree hold a commit-type vocabulary, and until they were
wired to the same source they held different ones:

- `scripts/hooks/conventional-commit-check.sh`, which binds a contributor at
  `git commit` and used to carry a hardcoded eleven-type list;
- `scripts/check_commit_subjects.py`, which CI runs over the pushed range and
  derives its set from `changelog-sections` in the Release Please config.

`style` and `revert` were in the first and not the second, so a
`style(lint): …` subject was accepted locally and rejected in CI — same rule,
same name, two answers, and the second one arrives after the push.

## Why this test exists when the hook now derives

Deriving makes the two agree *by construction*, and the version that drifted
also looked correct from inside either file. What no file could state is the
relationship, and a relationship is measured by an attempt: this runs the hook
on a real subject of every configured type and on two conventional types the
config deliberately gives no section.

The second half is what would have failed against the old hook, and it is the
half that stays honest if somebody reintroduces a list — a check that only
asserts *the good types pass* is green under a vocabulary that passes
everything.

## No skips, and that is not a style preference

`--versioning tag` subtracts the Release Please config, so the first draft of
this file opened each test with `pytest.skip("no Release Please config")` —
which ships a `tag` tree with two skips against a `skip_budget.json` of 0, red
on arrival, on a scaffold nobody has touched. That is this template's own
`CANNOT_RUN_ON_HOST` lesson: **an assertion that is correct when it has nothing
to check and a skip that is emitted when it has nothing to check are different
things, and a ratchet only sees the second.**

So the config-less branch asserts something real instead. There the hook is
enforcing style alone, with no CI opinion to agree with, and the invariant is
that its wider fallback is genuinely wider *and still a filter* — a hook that
accepts everything would pass a check that only looked at the configured world.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts.paths import GITHUB_DIR, PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402

HOOK = SCRIPTS_DIR / "hooks" / "conventional-commit-check.sh"
RELEASE_CONFIG = GITHUB_DIR / "release-please-config.json"

#: Conventional types that are real, that a contributor will reach for, and
#: that this repository's config gives no section — so CI drops them. They are
#: named rather than computed because the full conventional-commit vocabulary
#: is an external convention with no machine-readable home in this tree, and
#: inventing a type (`bogus:`) would test the regex instead of the vocabulary.
#: A type here that gains a section is caught by the assertion below, not left
#: to rot.
UNCONFIGURED = ("style", "revert")


def configured_types() -> set:
    """The set CI enforces, read the way `check_commit_subjects.py` reads it."""
    config = json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
    sections = []
    for package in (config.get("packages") or {}).values():
        sections += package.get("changelog-sections") or []
    return {section["type"] for section in sections if "type" in section}


def hook_accepts(subject: str, tmp_path: Path) -> bool:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(subject + "\n", encoding="utf-8")
    return (
        subprocess.run(
            ["bash", str(HOOK), str(message)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def test_the_hook_accepts_every_type_this_tree_enforces(tmp_path):
    """A type CI will read is a type the hook must let through."""
    if RELEASE_CONFIG.exists():
        enforced = sorted(configured_types())
        why = "configured commit types"
    else:
        # A `--versioning tag` tree. CI has no contract to enforce, so the
        # hook's own fallback is the whole vocabulary — and these three are the
        # types any conventional-commit tree must accept whatever it configures.
        enforced = ["feat", "fix", "docs"]
        why = "commit types a tree with no release config must still accept"
    # `least=3`: this scan feeds an acceptance filter, and a filter tested
    # against one type cannot be observed to select. Three is the smallest set
    # in which a hook that accepts a *prefix* of the vocabulary is visible.
    types = scanned(enforced, why, least=3)
    rejected = [t for t in types if not hook_accepts(f"{t}(scope): a summary", tmp_path)]
    assert not rejected, (
        f"the commit-msg hook rejects {rejected}, which Release Please is configured to read — "
        "a contributor cannot commit a change CI would have accepted"
    )


def test_the_hook_rejects_what_ci_would_drop(tmp_path):
    """The half that fails against a hardcoded list, which is the half that drifted."""
    if RELEASE_CONFIG.exists():
        types = configured_types()
        # `least=1` is a staleness assertion on UNCONFIGURED, not a formality:
        # a type here that gains a changelog section leaves this scan empty, and
        # an empty scan of things-that-must-be-rejected passes while looking at
        # nothing. The failure then names the list rather than letting it rot.
        rejectable = scanned(
            [t for t in UNCONFIGURED if t not in types],
            "conventional types with no changelog section",
            least=1,
        )
        because = (
            "`changelog-sections` gives them no section — such a commit passes locally, then CI "
            "rejects it after the push. The hook derives its vocabulary from that config; a "
            "hardcoded list is how the two came apart before."
        )
    else:
        # No CI contract to disagree with, so the thing being asserted is that
        # the fallback is a *filter*: a hook that waved everything through would
        # be invisible to the accepting test above.
        rejectable = ["bogus", "wip", "misc"]
        because = "the fallback vocabulary must still reject a non-type, or it is not a filter"
    accepted = [t for t in rejectable if hook_accepts(f"{t}(scope): a summary", tmp_path)]
    assert not accepted, f"the commit-msg hook accepts {accepted}, and {because}"
