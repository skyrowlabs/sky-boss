#!/usr/bin/env python3
"""Where this project is on disk — derived once, imported everywhere.

This module exists because the root was being recomputed in **25 places**, each
as `Path(__file__).resolve().parents[N]` with `N` chosen from how deep the file
happened to sit. That is Rule 1 with the serial numbers filed off: a value with
no owner, re-derived by every consumer.

The failure it removes is quiet, which is why it was worth removing. Move
`check_doc_links.py` into a subdirectory and its `parents[1]` still resolves —
to `scripts/`, not the repo. Nothing raises. The checker simply scans a `docs/`
that does not exist, finds nothing, and reports green. Every derived directory
below has been wrong the same way at least once in some codebase.

After this, a file in the wrong place fails at **import**, because the
bootstrap that puts the package on `sys.path` is the thing that breaks — and an
`ImportError` names the file, where a silently-empty scan names nothing.

## The one derivation

`PROJECT_ROOT` is `parents[1]` **of this file specifically**, which is exact and
stays exact: this module is `<root>/scripts/paths.py` by definition, because
that is the path every consumer imports it by.

## The `sys.path` line in each consumer is not a second derivation

A script run by path (`python scripts/check_doc_links.py`) gets `scripts/` on
`sys.path`, not the repo, so it cannot import this module until something puts
the repo there. That bootstrap line is unavoidable and depth-dependent. It is
also *only* about imports: get it wrong and nothing resolves at all, which is
the loud failure this module is trading up to.

## Governing a tree other than this one

Everything below is derived from a single name, so pointing this shell at a
different checkout is one function. It is deliberately **not** built yet,
because it needs an answer this module cannot give on its own: `PROJECT_ROOT`
is currently both "where the code is" and "where the content is", and only the
second should move. Splitting them is a decision about every consumer below,
not a config value — see `docs/DEVELOPMENT.md`. This is where it would land.

Stdlib only, and imported by `cli/` and `scripts/` alike.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

#: The repository root. The only place in the tree this is worked out.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Content ──────────────────────────────────────────────────────────────────
DOCS_DIR = PROJECT_ROOT / "docs"

#: The holding tank and the archive — the two halves of the docs lifecycle. A
#: plan **moves** between them, so both are resolved here rather than by each
#: of the six modules that walk them.
TODO_DIR = DOCS_DIR / "TODO"
IMPL_DIR = DOCS_DIR / "implementations"

#: In-flight reports and their frozen per-release editions.
REGULAR_DIR = DOCS_DIR / "reports" / "regular"
RELEASES_DIR = DOCS_DIR / "reports" / "releases"

#: Documents whose job is to describe a state **other than the present one** —
#: a plan for work not yet done, a report frozen at a release, research about a
#: codebase that has since moved. Naming a symbol or a file that no longer
#: exists is what those sentences are FOR, so every check that asks "does this
#: still resolve?" excludes them by role.
#:
#: It lives here, and not in the checks, because **the roles are the part a
#: generator cannot know.** A scaffold ships `docs/TODO/` and can enumerate it;
#: it cannot know that your repository froze its concept work in `explore/`.
#: The alternative was every adopter editing a shipped test, which is a
#: divergence the upgrade's three-way merge then carries forever. stash.flow
#: named the rule after their `explore/` — 19 of their 44 tracked documents —
#: reddened a gate that had no role exclusion at all.
#:
#: `reports` is taken at its parent so the regular, release and occasional
#: editions are covered without naming three constants.
NARRATIVE = (TODO_DIR, IMPL_DIR, DOCS_DIR / "reports")

#: **Add your own stages below, as an append. Do not edit the tuple above.**
#:
#: This used to read "extending this tuple is a one-line change to a file you
#: own", which was true about permission and wrong about merging. stash.flow
#: measured both spellings of the identical intent against the identical
#: upstream change, and so did this repository, with `git merge-file` against a
#: pristine render:
#:
#:     NARRATIVE = (TODO_DIR, IMPL_DIR, DOCS_DIR / "reports", EXPLORE_DIR)   CONFLICT
#:     NARRATIVE += (EXPLORE_DIR,)                                           clean
#:
#: **The discriminator is line disjointness, not permission.** Being invited to
#: edit a line changes nothing about what git does when upstream edits it too,
#: and every future change to the tuple above collides with an adopter who put
#: their stage inside it. An append is a different line and always will be.
#:
#:     EXPLORE_DIR = PROJECT_ROOT / "explore"
#:     NARRATIVE += (EXPLORE_DIR,)
#:
#: **Keep a blank line between your block and the template's**, and audit it per
#: line rather than per block. The unit of collision is the line: stash.flow's
#: five-line explanation sat hard against the constant above and conflicted
#: anyway, and mind.head's was a single `#:` separator, which cost exactly the
#: same. proto.pilot's landed clean on one blank line — and nothing recorded
#: that the line was load-bearing, so a whitespace tidy-up would have brought
#: the conflict back looking like housekeeping.

# ── Code and configuration ───────────────────────────────────────────────────
CLI_DIR = PROJECT_ROOT / "cli"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
TESTS_DIR = PROJECT_ROOT / "tests"
GITHUB_DIR = PROJECT_ROOT / ".github"

#: The host toolchain this tree installs — the CLI, the docs pipeline, the lint
#: gates. `ci.yml` names it as the source of truth at its install step and
#: `tests/test_lint_tool_parity.py` holds it to `.pre-commit-config.yaml`.
#:
#: It lives here because a second test now needs the same file, and two tests
#: each computing `SCRIPTS_DIR / "requirements.txt"` is the shape that goes
#: wrong quietly: each is right about its own caller and nothing compares them.
REQUIREMENTS = SCRIPTS_DIR / "requirements.txt"

#: The scaffolder's record of what it wrote here, or absent if this tree was
#: never scaffolded — or if somebody deleted it, which is a supported choice.
#:
#: It is the only file that can tell **this project's own code from the shell it
#: was started with**, and that distinction is not cosmetic: a measurement over
#: a population that contains none of the subject is not a measurement of the
#: subject. `scripts/check_coverage_budget.py` asks it exactly that.
#:
#: Never read it for anything an upgrade owns. Its contents are the
#: **generator's** business — hashes, arguments, a ref — and a consumer in here
#: that depended on their shape would be a second reader of a format this tree
#: does not control. The one question asked of it is which paths it names.
SCAFFOLD_MANIFEST = PROJECT_ROOT / ".skeletor.json"

#: Scratch, and gitignored. Tree locks, coverage XML, merge markers — everything
#: whose lifetime is a run rather than a commit, and which nothing will want
#: next week. The record of what ran is **not** here; see `state_dir` below.
TMP_DIR = PROJECT_ROOT / "tmp"


# ── State: the record, outside the checkout ──────────────────────────────────
#: The root for the agentic record — transcripts, ledgers, per-job memory, the
#: payloads agent stages read. Deliberately **not** under `PROJECT_ROOT`, and
#: that is the whole point: it outlives any one checkout, is shared by every
#: worktree of this repo, and cannot be reached by `git clean -fdx`.
#:
#: The default is a shared root with `STATE_SLUG` below it, not a private one,
#: so several projects on a machine land side by side and a retention sweep has
#: one directory to walk. `~/.local/state` because that is where a state file
#: that is neither cache nor config belongs on a Linux box, and `agent-logs`
#: because the name has to be distinctive enough for `test_state_paths.py` to
#: recognise a second definition of it.
#:
#: Point it somewhere else with the environment variable — one root shared by
#: every project you run, or a scratch path in a test.
STATE_ROOT_ENV = "SB_STATE_ROOT"
STATE_ROOT_DEFAULT = Path.home() / ".local" / "state" / "agent-logs"

#: This project's directory under that root. Written in rather than taken from
#: `PROJECT_ROOT.name`, because a **linked worktree's directory is not the
#: slug**: a job running in a pool tree would otherwise resolve to a private
#: state root of its own, which is precisely the per-tree scattering this
#: layout exists to end. The slug is a fact about the project, not about which
#: copy of it you happen to be standing in.
STATE_SLUG = "sky-boss"

#: The classes the state root is divided into, named so a caller asks for one
#: rather than spelling a directory — and so a retention sweep has a single list
#: to walk instead of a pattern to guess. Retention differs per class, which is
#: the reason they are directories at all.
LOG = "log"  # the transcript: what every run printed
LEDGER = "ledger"  # append-only structured record, trimmed on write
INPUT = "input"  # the payload an agent stage actually read
MEMORY = "memory"  # what a job saw last time; overwritten every run
INFLIGHT = "inflight"  # what is running right now; removed in a `finally`
PRODUCT = "product"  # a job's own output, overwritten every run


class StateRoot(NamedTuple):
    """The root, and which of the two answers produced it."""

    path: Path
    #: `"environment"` or `"default"`. A string rather than a bool because the
    #: set of answers is not closed — a config file would be a third — and a
    #: bool would have to be renamed to admit one.
    source: str


def state_root() -> StateRoot:
    """The state root, and **where it came from**.

    `state_dir()` returns a `Path`, and a `Path` cannot say which of the
    override and the default produced it. That is not a cosmetic gap:
    jam.sense spent an investigation on a broken pane whose whole answer was
    *the environment variable was not exported here, so the default answered*,
    and the default had moved. One field would have closed it in a line.

    The two are the same lookup by construction — `state_dir()` calls this
    rather than repeating `os.environ.get`. A second copy of the resolution is
    the defect this module exists to prevent, and it would be a particularly
    quiet one here: a provenance function that read the environment separately
    would report the source of a path nobody resolved.

    Reported, never acted on. Nothing in this tree should branch on `source` —
    a caller that behaves differently depending on how the root was found has
    made the override mean two things.
    """
    override = os.environ.get(STATE_ROOT_ENV)
    if override:
        return StateRoot(Path(override), "environment")
    return StateRoot(STATE_ROOT_DEFAULT, "default")


def state_dir(*parts: str) -> Path:
    """This project's state root, plus any path below it.

    A function rather than a constant, unlike everything above, and for one
    reason: a constant freezes the override at import time, so a test that sets
    the environment variable in a fixture gets the live path anyway. The knob
    has to be read when the path is used or it is not a knob.

    **A function here does not save a caller that freezes it.** A module opening
    with ``LEDGER = state_dir(LEDGER, "ledger.jsonl")`` has evaluated this at
    import, and a fixture's ``monkeypatch.setenv`` runs long after that — so the
    suite writes to the live record and every test still passes. Resolve at the
    point of use, or set the variable at ``conftest.py`` import time. It is
    invisible by construction: ``test_state_paths.py`` excludes shared
    append-only files, correctly, which also means it cannot catch a test
    appending to them.

    **One resolver for readers and the writer alike.** Split them — define the
    write path here and the read path in the module that consumes it — and a
    test can point the write at a scratch file while the read still finds the
    live one. It passes, and proves nothing. That is not hypothetical: it is
    why this function exists instead of the three definitions it replaced.
    """
    return Path(state_root().path, STATE_SLUG, *parts)
