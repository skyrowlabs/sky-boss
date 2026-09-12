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
#:
#: `research` is here for exactly the reason `reports` is, and its absence was
#: an oversight rather than a decision. stash.flow filed 17 documents of concept
#: work into the folder `docs/rules/docs.md` tells them to use, and watched
#: `test_docs_name_real_paths` redden on one of them for citing a path that is
#: *supposed* to be dead. That folder's own description is the whole argument:
#: it holds "a thing that is **not a plan**", where "rejected ideas keep their
#: memo rather than being deleted" — and a memo about what was ruled out names
#: the code it ruled out.
#:
#: `docs/business-planning/` is the other folder in that table and is
#: deliberately NOT here, stated so its absence is a decision somebody can
#: disagree with rather than the same oversight one folder over. It is not a
#: stage of the *document* lifecycle — nothing moves into or out of it — and
#: market or pricing work does not cite the tree. An adopter who keeps
#: code-shaped proposals there should append it, which is what the block below
#: is for — and drop it from `PRESENT_TENSE` further down, since one folder gets
#: one role. `tests/test_narrative_covers_lifecycle_folders.py` holds that
#: partition, so a folder added to the table later cannot be silently
#: unclassified the way this one was.
NARRATIVE = (TODO_DIR, IMPL_DIR, DOCS_DIR / "reports", DOCS_DIR / "research")

#: **Add your own stages as an append, below the
#: `Nothing below this line is skeletor's` rule at the end of this section. Do
#: not edit the tuple above.**
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
#: **Put it below the `Nothing below this line is skeletor's` rule at the end of
#: this section, not here.** The reason is written there. Briefly: a blank line
#: between your block and the template's does work — measured — and it is a
#: first-merge guarantee that nothing can enforce, so a frozen rule with nothing
#: below it replaces the separation somebody has to remember with the separation
#: itself.
#:
#: The per-line audit that used to be the rule is why: the unit of collision is
#: the line, so stash.flow's five-line explanation sat hard against the constant
#: above and conflicted anyway, and mind.head's single `#:` separator cost
#: exactly the same. proto.pilot's landed clean on one blank line, and nothing
#: recorded that the line was load-bearing.

#: The other half of the partition: folders in that table that describe the
#: PRESENT, with the reason each one does.
#:
#: **This lived in `tests/test_narrative_covers_lifecycle_folders.py` and was a
#: second home for the decision the block above already argues.** The comment on
#: `NARRATIVE` says `docs/business-planning/` is deliberately not narrative and
#: says why; the test shipped the same ruling again, in its own dict, in a file
#: an adopter has no other reason to open. So accepting the invitation two
#: paragraphs up — append your stage, do not edit the tuple — turned that test
#: red with `delete the entry`, and the only way to close it was editing a
#: template-owned literal inside a shipped test: the divergence the append seam
#: exists to avoid, one file over. dream.doll and stash.flow each hit a
#: different one of the two assertions, independently, from real runs.
#:
#: Both halves live here now, so a folder is classified once, in the file that
#: carries the argument, and an adopter's edit is an append either way:
#:
#:     PRESENT_TENSE |= {"docs/pricing": "market work; it does not cite the tree"}
#:
#: An entry is a decision and nothing keeps a decision true, so
#: `tests/test_narrative_covers_lifecycle_folders.py` checks every entry against
#: the table on every run, in both directions.
PRESENT_TENSE = {
    "docs/business-planning": (
        "Not a stage of the document lifecycle — nothing moves into or out of "
        "it — and market or pricing work does not cite the tree. An adopter who "
        "keeps code-shaped proposals here should move it to NARRATIVE instead, "
        "which means appending it there AND dropping this entry: one folder, "
        "one role, and the check below fails while both name it."
    ),
}

#: **Add your own present-tense folders as an append, below the
#: `Nothing below this line is skeletor's` rule at the end of this section.** An
#: append is a different line from the template's and stays clean when upstream
#: edits its own; the frozen rule is what keeps the two from arriving at one
#: insertion point on a re-merge. The reason is written once, there.
#:
#: This block used to say *"for the reason the `NARRATIVE` block gives"* and
#: never repeat it — so the load-bearing half of the rule was stated at one of
#: the two sites that needed it, and an adopter reading only this one got the
#: invitation without the constraint. skyrow-workspace found that; it is the
#: same second-home failure the `PRESENT_TENSE` table itself was moved here to
#: fix, in the prose rather than in the data.
#:
#: ## Removing one is an append too, and it did not used to be
#:
#: The seam above was built for the adopter who **adds** a folder, and nobody
#: walked the one who **takes a shipped entry out**. Both constants ship with
#: content, so that is not a hypothetical adopter: `docs/business-planning`'s
#: own reason ends by telling you to move it to `NARRATIVE`, which means
#: dropping it from here — and the only spelling on offer was editing the
#: literal above. **The seam sent its reader into the exact divergence it
#: exists to prevent**, and the two shipped checks below said `drop it` and
#: `delete the entry` in as many words.
#:
#: A removal has an append-shaped spelling in both cases, and it is the one to
#: use. It is a different line from the template's, so it survives upstream
#: editing its own:
#:
#:     PRESENT_TENSE.pop("docs/business-planning", None)
#:     NARRATIVE = tuple(role for role in NARRATIVE if role != DOCS_DIR / "reports")
#:
#: `pop` takes a default so the line is idempotent — an entry the template
#: later stops shipping must not turn an adopter's removal into a `KeyError`,
#: which is the same failure one release further on.
#:
#: The rebuilt tuple reads as editing `NARRATIVE` and is not: the name on the
#: left is assigned on a **new line below the template's**, and git merges
#: lines.
#:
#: ## `!=`, and this line shipped as `is not` for a release
#:
#: The argument for identity was that these are directory objects whose equality
#: is by path, so identity is what an adopter means when they name the constant
#: the template defined. That is true about **intent** and false about the
#: objects: half the tuple above has no name to be identical to.
#: `DOCS_DIR / "reports"` builds a new `Path` on every evaluation, so
#: `role is not DOCS_DIR / "reports"` is true for every element and the removal
#: **silently does nothing** — the filter runs, the tuple comes back the same
#: length, and nothing anywhere says so.
#:
#: Measured on a fresh tree, 2 of the 4 shipped entries are anonymous
#: expressions and 2 are named constants. `is not` works for the named half;
#: `!=` works for all four. So the idiom that reads as more precise was correct
#: for the entries somebody would reach for first and inert for the rest, which
#: is the shape this repository keeps meeting: the convenient example cannot
#: discriminate. proto.pilot found it.
#:
#: `tests/test_narrative_covers_lifecycle_folders.py` executes the spellings in
#: this comment against the real constants now, so an example that stops working
#: fails rather than waiting for somebody to paste it.


# ── Extending NARRATIVE and PRESENT_TENSE ────────────────────────────────────
#
# **Put every append to NARRATIVE and PRESENT_TENSE below the frozen rule at the
# bottom of this block**, not directly under this heading. Both constants are
# defined above, so both spellings reach from there.
#
# skeletor renders nothing below that rule, ever. That is the whole mechanism: a
# three-way merge collides when two changes land at one insertion point, and an
# upgrade has no change down there to collide with — so your line is never
# adjacent to a template line, whatever the template does to its own text above.
# The rule is at the bottom of this block rather than the top for the reason the
# next section measures.
#
# ## What this replaces, because the old rule worked and could not be enforced
#
# The seams above used to end with an invitation and a request to keep a blank
# line between your block and the template's. Measured, that rule is correct:
# an adjacent append conflicts and a blank-line append merges clean. It had two
# problems and neither was the rule.
#
# It was unenforceable. Nothing could check it, and a whitespace tidy-up would
# have brought the conflict back looking like housekeeping — which the NARRATIVE
# block said in as many words, one release before this arrived.
#
# And it was a FIRST-merge guarantee. Two adopters found the second half
# independently: dream.doll, that a round with a conflict anywhere forces a
# re-run, and re-running re-merges a file the previous run had merged cleanly;
# proto.pilot, that the trigger is any re-run before the base advances, not
# `--ported` and not a hand-port. Both land on the same shape — the blank line
# survives one merge, and the insertion points coincide again on the next.
#
# A frozen rule with nothing below it is that same guarantee holding on every
# merge after the first, because the separation stops being a blank line somebody
# has to remember and becomes where the two changes are.
#
# ## Where your existing append lands is NOT guaranteed — move it, and check
#
# This block used to be *headed* by the rule, with the explanation between it and
# your append. **That layout could not give safe advice**, because "below this
# line" then named a position inside template prose, and which position is safe
# turns on which paragraph the last release rewrote. Measured, same append, same
# two merges, base `v0.27.0`: against `v0.28.0` the position just under the old
# marker re-conflicted while the end of the prose was clean, and against the
# release after it the two swapped. proto.pilot measured the first pair; the
# inversion turned up while reproducing it, and both readings were correct.
#
# An earlier version of this section also claimed an append that merged cleanly
# ended up below the marker and needed no moving. That was generalised from one
# synthetic case and is false: git orders the two additions at a shared anchor
# rather than colliding on them, and which side yours lands on depends on where
# exactly it sits. dream.doll merged cleanly and landed above; mind.head found
# the same from a tree that conflicted.
#
# **If you extended this file before the rule moved, your appends are interleaved
# with this prose and have to be moved below it.** The bad outcome is silent,
# which is why it earns a check rather than a sentence: an append above the rule
# keeps the pre-region behaviour — clean first merge, conflict on the next re-run
# — while the release notes say you are covered, so it is paid for later as a
# conflict that looks new. `tests/test_narrative_covers_lifecycle_folders.py`
# asserts every append is below the rule, making placement a question your own
# suite answers rather than a claim you are asked to believe. dream.doll's
# remedy, and the right shape: placement is a fact about your file.
#
# ## What the move costs, measured against the real trees
#
# Six real adopter trees, each at its own recorded base of `v0.28.0`, dry-run
# through `bin/skeletor-upgrade` against this release and against `v0.28.0`:
#
#     four trees   extend this file; two of those four conflict on it
#     two trees    ship it unextended and are clean
#
# Which two is **not** a function of how far down the append sits — one
# conflicting append is two lines above the old block's end and two clean ones
# are three. It is a function of which prose this release happened to rewrite
# next to them, which is the whole argument for moving the rule: afterwards there
# is no template prose below your appends for a later release to edit.
#
# ## What the rule buys, narrowly, because the wider claim measured false
#
# **The re-run, and nothing on a first merge.** Measured in both layouts against
# every upstream edit that is legal above the rule:
#
#     blank line only   first merge clean, re-run before the base advances CONFLICTS
#     frozen rule       first merge clean, re-run clean
#
# A first-merge probe cannot tell the layouts apart, because there is nothing
# there to buy. proto.pilot established that with three probes, and it is why the
# "measured across five offsets" claim that sat here is withdrawn: those five
# offsets returned an identical answer five times, which is the tell that the
# parameter varied nothing — *undistinguished, not confirmed*, in a harness
# rather than in a flag.
#
# One earlier estimate of the cost said "all six, including the four that are
# clean", and it was wrong because the harness measuring it appended at the wrong
# line — outside the block the template keeps editing, on the far side of the
# lines the previous release had inserted into precisely that gap. Every number
# here comes from running the real tool against the real trees instead.
#
# ── Nothing below this line is skeletor's ────────────────────────────────────
#
# Put your appends below this block. The block itself is frozen — skeletor does
# not rewrite these lines and renders nothing below them, so your insertion point
# is never adjacent to template text a release might edit. The explanation above
# is ordinary prose and does get rewritten; that is why the rule sits at the
# bottom of it rather than at the top.


# ── Code and configuration ───────────────────────────────────────────────────


#: The shell's package, written here by the scaffolder.
#:
#: It ships as `cli/` and `--shell-package` renames it, because `cli` is the
#: most collided-with package name in a python monorepo and a shell that cannot
#: move out of the way costs an adopter a rename mid-flight.
#:
#: ## This was discovered by walking for `__main__.py`, and that shipped broken
#:
#: The first version took the one root directory containing a `__main__.py` and
#: raised when there was not exactly one. Its comment named the ambiguous case
#: and treated it as unreachable. It is the **ordinary** case: `__main__.py` is
#: what `python -m` needs, so any adopter whose own product is a `python -m`
#: CLI has a second one — and the failure was not a wrong answer but a dead
#: tree, since this module is imported by the CLI, every gate and the suite's
#: collection. sky.boss upgraded, lost the whole toolchain, and reverted.
#:
#: The record beats the inference, which is their sentence: an inference that
#: can be ambiguous must not outrank a record that cannot. The record is here
#: rather than in `.skeletor.json` because that file is a **supported
#: deletion** (see `SCAFFOLD_MANIFEST` below) and because reading its arg list
#: would make this a second reader of the generator's format. A rendered
#: literal is written by the same render that created the directory and
#: survives both.
#:
#: ## Why it was not simply substituted the first time
#:
#: Because a placeholder cannot go in an *import statement* — `from <token>.x
#: import y` does not parse, and this template's python is read with `ast`.
#: That is true, and it was carried to every construct instead of the one it
#: was proven about. It was never true of a string constant. Nothing imports
#: through this name: the package finds its own command groups via `__name__`
#: and `__path__`, `__main__.py` imports relatively, and `tests/shell.py` goes
#: through `importlib`.
SHELL_PACKAGE = "cli"
CLI_DIR = PROJECT_ROOT / SHELL_PACKAGE
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
