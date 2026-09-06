"""A reference doc may not name a callable this repo used to define and no longer does.

The narrow, decidable half of a problem whose useful half is not.

**When you fix a defect, everything justified by it is now justified by nothing** —
and the dangerous case is the one where the conclusion survives, because then
nothing goes red and nobody re-reads the reason. No test can find that: it would
have to read "because X is broken" and go check whether X is still broken, which
is semantic, and the input is prose. That belongs to something which reads across
the repo periodically and *reports*.

What a test can do is catch the mechanical cousin — a doc that tells you to call
something that has been renamed or deleted.

## Why the predicate is "it was ours, and now it isn't"

The obvious version, every backticked ``foo()`` in the docs must resolve, has a
false-positive rate that makes it useless: it flags the standard library, other
people's libraries, and anything you referred to in passing. A gate you have to
allowlist four things into on its first run is describing the wrong shape.

Asking git instead makes it exact. A name this repository once defined and no
longer defines is unambiguously ours and unambiguously gone. Everything that was
never ours is excluded by construction rather than by exemption, which is why
there is no allowlist here to keep up to date.

## Why narrative documents are out of scope

A plan in ``docs/TODO/`` saying "this phase takes ``old_helper()`` and moves it"
is *correct*, and naming the dead symbol is the entire point of the sentence.
Same for the archive and the reports: their job is to describe what happened, not
what is. Those stages are excluded by role, and the set of them is read from
``scripts.paths`` rather than spelled again here.

Everything else is enrolled by default. That direction is the one that matters —
a reference doc added next month is covered without anybody remembering to add
it, which is the same reason the suites are marker-based rather than listed.

## What it costs

Nothing on a fresh tree: a scaffold has one commit, so a symbol that was ever
defined is still defined and this finds zero. It is a ratchet at 0, and it starts
paying the first time you delete something.

## Its neighbour is not a copy of it

``test_docs_name_real_commands.py`` sits beside this and the two names differ by
one word, which is a shape somebody eventually "de-duplicates" by reading the
filenames. They share a scoping rule and nothing else. That one asks whether a
command inside a fenced ``bash`` block resolves to a subcommand the CLI has
**now**; this one asks whether a doc names a *callable* this repository once
defined and has since removed. Different inputs, different oracles — a click
group versus ``git log`` — and neither subsumes the other. Delete one and the
gate it was holding is simply gone.

This one arrived here from a consumer's tree, at the path they had picked; the
neighbour was written here afterwards. That is why they are adjacent and why
they look related, and it is not a reason to merge them.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_files import reference_docs, tracked  # noqa: E402

from scripts.paths import PROJECT_ROOT  # noqa: E402

#: A backticked call. The parentheses are the whole signal — they are what
#: separates a code reference from a word that happens to sit in a code span.
CALL = re.compile(r"`([A-Za-z_][\w.]*)\(\)`")

#: `def` and `class`, because a doc says `Thing()` for a constructor too.
DEFINITION = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", re.M)


def _git(*args: str, root: Path = PROJECT_ROOT) -> str:
    return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, check=True).stdout


def defined_now(root: Path = PROJECT_ROOT) -> set[str]:
    """Every callable this repo currently defines."""
    names: set[str] = set()
    for path in tracked("*.py", root=root):
        names.update(DEFINITION.findall(path.read_text(encoding="utf-8", errors="replace")))
    return names


def was_ever_ours(symbol: str, root: Path = PROJECT_ROOT) -> bool:
    """Did this repository ever define `symbol`?

    `-S` against the *definition* line, not the bare name: a symbol merely
    mentioned in some commit was never ours, and matching it would put every
    third-party call back in scope — the false-positive problem this predicate
    exists to avoid.
    """
    return bool(_git("log", "--all", "-S", f"def {symbol}", "--oneline", "--", "*.py", root=root).strip())


def dead_references(root: Path = PROJECT_ROOT, docs: list[Path] | None = None) -> list[tuple[str, str]]:
    live = defined_now(root=root)
    found: list[tuple[str, str]] = []
    for path in reference_docs(root=root) if docs is None else docs:
        for match in CALL.finditer(path.read_text(encoding="utf-8")):
            symbol = match.group(1).rsplit(".", 1)[-1]
            if symbol in live:
                continue
            if was_ever_ours(symbol, root=root):
                found.append((str(path.relative_to(root)), match.group(1)))
    return sorted(set(found))


def test_history_is_available():
    """Worthless against a shallow clone, and silently so.

    `git log --all` finds nothing in one, so every reference would look like it
    was never ours and this file would pass by *seeing* nothing rather than by
    *finding* nothing. That is the "green because it never ran" shape, so it is
    asserted rather than assumed — and ci.yml checks the unit job out with
    `fetch-depth: 0` to keep it true.
    """
    assert not (PROJECT_ROOT / ".git" / "shallow").exists(), (
        "shallow clone: this check needs history and would pass without it, having looked at nothing. "
        "Fetch the full history (`fetch-depth: 0`) or run it somewhere that has it."
    )


def test_no_reference_doc_names_a_callable_we_removed():
    dead = dead_references()
    assert not dead, "docs naming a callable this repo used to define:\n" + "\n".join(
        f"  {where}: {symbol}()" for where, symbol in dead
    )


def test_the_check_would_actually_catch_one(tmp_path):
    """A gate nobody has seen fail is a gate nobody knows works.

    Driven against a real throwaway repository rather than a stubbed predicate,
    because the predicate *is* the interesting part: it has to tell a name this
    repo deleted from a name that was never ours, and only git history can. The
    stdlib reference alongside is the negative half — it must not be flagged.
    """
    identity = ["-c", "user.name=t", "-c", "user.email=t@t.invalid"]
    _git("init", "-q", "-b", "main", root=tmp_path)

    (tmp_path / "mod.py").write_text("def gone_away():\n    return 1\n", encoding="utf-8")
    (tmp_path / "REFERENCE.md").write_text(
        "Call `gone_away()` for that, and `os.getenv()` for config.\n", encoding="utf-8"
    )
    _git("add", "-A", root=tmp_path)
    _git(*identity, "commit", "-q", "-m", "add it", root=tmp_path)

    (tmp_path / "mod.py").write_text("def something_else():\n    return 1\n", encoding="utf-8")
    _git("add", "-A", root=tmp_path)
    _git(*identity, "commit", "-q", "-m", "remove it", root=tmp_path)

    found = dead_references(root=tmp_path)
    assert [symbol for _, symbol in found] == [
        "gone_away"
    ], f"expected exactly the removed symbol and not the stdlib one, got {found}"
