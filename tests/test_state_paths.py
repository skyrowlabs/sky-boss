"""The record does not live in the checkout, and one module says where it does.

Both halves of this fail silently, which is the only reason they are worth a
test. State written under `tmp/` survives until the first `git clean -fdx` and
then does not — nothing raises, the ledger is simply empty and every job looks
like it has never run. And a *second* definition of the state root is the
defect that reads as correct in review: point the writer at one path and a
reader at another and the suite still passes, because each half is internally
consistent. It proves nothing, and it proves it in green.

See AGENTS.md Critical Rule 14 and `scripts/paths.py::state_dir`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scanning import scanned  # noqa: E402
from scripts import paths  # noqa: E402
from scripts.paths import (  # noqa: E402
    CLI_DIR,
    PROJECT_ROOT,
    SCRIPTS_DIR,
    STATE_ROOT_DEFAULT,
    STATE_ROOT_ENV,
    STATE_SLUG,
    state_dir,
    state_root,
)

#: The one module allowed to name the root. Everything else asks it.
RESOLVER = SCRIPTS_DIR / "paths.py"

#: What a second definition looks like: the directory name, or the environment
#: variable, written somewhere that is not the resolver.
#:
#: **Read out of the resolver, not repeated here.** A literal pattern is the
#: second definition this test exists to forbid, wearing the costume of the test
#: that forbids it — and it fails in the safe-looking direction, because a root
#: that was renamed stops matching and the check goes quietly green over a tree
#: full of stale copies.
ROOT_TOKENS = re.compile("|".join(re.escape(token) for token in (STATE_ROOT_ENV, STATE_ROOT_DEFAULT.name)))


def _sources():
    return scanned(
        [p for base in (CLI_DIR, SCRIPTS_DIR) for p in sorted(base.rglob("*.py")) if p != RESOLVER],
        f".py under {CLI_DIR.name}/ or {SCRIPTS_DIR.name}/, excluding the resolver",
    )


def test_state_lives_outside_the_checkout():
    """The whole point. A path under the repo is not state, it is scratch."""
    resolved = state_dir()
    assert PROJECT_ROOT not in resolved.parents and resolved != PROJECT_ROOT, (
        f"state_dir() resolved to {resolved}, which is inside the checkout — " "one `git clean -fdx` from gone"
    )


def test_the_slug_is_not_the_directory_name():
    """A linked worktree's directory is not the slug.

    Deriving it from `PROJECT_ROOT.name` works in the primary checkout and
    gives every pool tree a private state root of its own — the exact
    scattering this layout exists to end, visible only from a tree nobody
    runs the suite in.
    """
    assert STATE_SLUG and "{" not in STATE_SLUG, "STATE_SLUG was never substituted"
    assert state_dir().name == STATE_SLUG


def test_the_override_is_honoured_when_the_path_is_used(monkeypatch, tmp_path):
    """A constant would freeze this at import, and the knob would be a comment."""
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path))
    assert state_dir("ledger").parent == tmp_path / STATE_SLUG


def test_the_root_says_which_answer_produced_it(monkeypatch, tmp_path):
    """Both directions, because a source that is always one value says nothing.

    A `Path` cannot report where it came from, and the question is not academic:
    the whole answer to a broken run can be *the variable was not exported here,
    so the default answered* — and the default may have moved since.
    """
    monkeypatch.delenv(STATE_ROOT_ENV, raising=False)
    assert state_root() == (STATE_ROOT_DEFAULT, "default")

    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path))
    assert state_root() == (tmp_path, "environment")


def test_state_dir_resolves_through_the_reporter(monkeypatch, tmp_path):
    """`state_dir()` goes THROUGH `state_root()`, rather than agreeing with it.

    A `state_root()` that read the environment separately would report the
    source of a path nobody resolved — the split-resolver defect this module
    exists to prevent, wearing the costume of the function that reports on it.

    The obvious test is the one that cannot see it. Setting the variable and
    asserting `state_dir(...) == state_root().path / ...` passes under the
    split, because two independent lookups of one environment agree — it was
    written that way here first, and the plant that should have failed it came
    back green. Two copies of a mistake agree with each other.

    So the assertion is structural: replace the reporter and require the path to
    follow. Nothing but a call can do that.
    """
    monkeypatch.setattr(paths, "state_root", lambda: paths.StateRoot(tmp_path, "planted"))
    assert state_dir("ledger") == tmp_path / STATE_SLUG / "ledger"


def test_nothing_else_names_the_state_root():
    """The second definition. This is the test that earns its keep."""
    offenders = [
        f"{path.relative_to(PROJECT_ROOT)}:{n}"
        for path in _sources()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if ROOT_TOKENS.search(line)
    ]
    assert not offenders, (
        "The state root is named outside scripts/paths.py:\n  "
        + "\n  ".join(offenders)
        + "\n\nAsk `state_dir()` instead. Two definitions stay consistent right up "
        "until one of them moves, and the suite cannot see the difference."
    )
