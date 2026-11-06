#!/usr/bin/env python3
"""Your product's own gates, run by `dev check docs` and `dev check pre-push`.

The gate lists in `cli/check.py` are the template's, and a line
edited into them conflicts with every release that adds a gate there. So a gate of
yours is an entry appended here, and `check.py` runs every entry after its own.

`DOCS_GATES` run in `check docs` and so in `check pre-push`, which runs `check
docs` whole. `PRE_PUSH_GATES` run in `check pre-push` alone. An entry names a
script and its arguments, run the way `check.py` runs its own: from the project
root, with this tree's interpreter.

A gate that can legitimately find nothing to measure exits 3 and sets `no_subject`,
which is what makes `check` pass it. Without that a 3 is red, because pytest and
pyright exit 3 when they crash. `docs/rules/output.md` has the contract.

`tests/test_pre_push_covers_ci.py` reads both lists, so a CI-blocking gate listed
here counts as one `check pre-push` runs. `tests/test_ci_job_settings.py` reads
them too, so a history-reading script here makes a job running `check docs` need
`fetch-depth: 0`.
"""

from __future__ import annotations

from typing import NamedTuple


class Gate(NamedTuple):
    """One gate: the label `check` prints, its script and arguments, and whether exit 3 is no subject."""

    label: str
    script: str
    args: tuple[str, ...] = ()
    no_subject: bool = False


DOCS_GATES: list[Gate] = []
PRE_PUSH_GATES: list[Gate] = []

#: **Add your own gates as an append, in the space between the two frozen rules
#: at the end of this section.** skeletor ships both lists empty and never adds an
#: entry, so an append here is a line no release writes beside.
#:
#:     DOCS_GATES += [Gate("corpus manifest", "scripts/check_corpus.py")]
#:     PRE_PUSH_GATES += [Gate("model card", "scripts/check_model_card.py", ("--strict",))]


# ── Extending the gate lists ─────────────────────────────────────────────────
#
# **Put every append to DOCS_GATES or PRE_PUSH_GATES, and any comment you write
# about it, in the space between the two frozen rules at the bottom of this
# block.** skeletor ships that space empty and never adds a line to it;
# `scripts/paths.py` records why there are two rules and what the space buys.
#
# ── Nothing below this line is skeletor's ────────────────────────────────────
#
# Everything of yours goes between this rule and the closing one below: appends,
# and any prose you write about them. Both rules are frozen — skeletor does not
# rewrite either block and renders nothing between them, so your insertion point
# is never adjacent to a template line that a release might edit. The
# explanation above IS ordinary prose and does get rewritten, which is why the
# rule sits at the bottom of it rather than at the top.


# ── Skeletor's again below this line ─────────────────────────────────────────
#
# The space is bounded on both sides for the reason `scripts/paths.py` measures:
# one rule alone would certify everything below it as yours, including whatever
# a later release adds here.

__all__ = ["DOCS_GATES", "PRE_PUSH_GATES", "Gate"]
