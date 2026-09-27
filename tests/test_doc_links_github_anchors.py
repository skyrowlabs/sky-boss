"""`check_doc_links.py` computes the anchors GitHub computes — held to GitHub's own output.

The checker decides whether `[text](doc.md#some-heading)` is dead by slugifying
the target's headings. For a release that slugify collapsed whitespace, turned
`_` into `-` and stripped edge hyphens, none of which GitHub does, so it rejected
GitHub-correct anchors and accepted ones GitHub will not resolve. stash.flow
found it by writing four correct links and watching all four fail.

**The expected values here did not come from the code under test.** The old tests
built their anchors with the same `slugify` they checked, so both sides agreed
by construction — the seam defect's exact shape, with GitHub's renderer as the
second consumer holding a different assumption. Every id below was read out of
GitHub's rendered HTML (`id="user-content-…"`, from the contents API with
`Accept: application/vnd.github.html` — `POST /markdown` emits no ids), for
headings in this template's own docs, on 2026-09-27. Measured at the same time:
the previous slugify was wrong on 54 of 351 headings, this one on none.

If GitHub changes its slugger this table goes stale, and the only fix is to
capture it again the same way — not to regenerate it from `slugify`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.check_doc_links as links  # noqa: E402

#: heading source text → the id GitHub gave it. Chosen to cover each rule that
#: differed: a spaced dash, slash and ampersand each leave two spaces and so two
#: hyphens; underscores inside code survive; leading hyphens survive; code spans
#: and parentheses lose their punctuation but keep their words.
FROM_GITHUB = {
    "Design Rationale — Where Each Mechanism Came From": "design-rationale--where-each-mechanism-came-from",
    "Phase 1 — Planning & Context": "phase-1--planning--context",
    "Agents, Skills & Shared Assets": "agents-skills--shared-assets",
    "JavaScript / TypeScript Rules": "javascript--typescript-rules",
    "/implement — Plan Orchestrator": "implement--plan-orchestrator",
    "`--mode=current` (default)": "--modecurrent-default",
    "`--mode=repository-report`": "--moderepository-report",
    "Env-Gate Skips: `require_or_skip`, Not `pytest.skip`": "env-gate-skips-require_or_skip-not-pytestskip",
    "Configuration — Never `os.getenv()` for App Config": "configuration--never-osgetenv-for-app-config",
    # HTML in a heading renders away (stash.flow, measured against GitHub).
    "Phase 1 — <name>": "phase-1--",
}


def test_every_heading_slugifies_to_githubs_id():
    wrong = {heading: (links.slugify(heading), expected) for heading, expected in FROM_GITHUB.items()}
    wrong = {heading: pair for heading, pair in wrong.items() if pair[0] != pair[1]}
    assert not wrong, "slugify disagrees with GitHub (ours, GitHub's):\n" + "\n".join(
        f"  {heading!r}: {ours!r} vs {theirs!r}" for heading, (ours, theirs) in wrong.items()
    )


def test_a_repeated_heading_takes_the_next_suffix(tmp_path):
    """GitHub numbers a repeat `-1`, `-2` … in document order; this template has one."""
    doc = tmp_path / "doc.md"
    doc.write_text(
        "# Guide\n\n## Phase D — STOP. The human merges.\n\ntext\n\n## Phase D — STOP. The human merges.\n",
        encoding="utf-8",
    )
    assert links.headings(doc) == [
        "guide",
        "phase-d--stop-the-human-merges",
        "phase-d--stop-the-human-merges-1",  # the id GitHub gave the second one
    ]


def test_a_heading_that_renders_empty_has_no_anchor(tmp_path):
    """`# <Human Title>` is all markup, so GitHub gives it no id; neither may this."""
    doc = tmp_path / "doc.md"
    doc.write_text("# <Human Title>\n\n## Real\n", encoding="utf-8")
    assert links.headings(doc) == ["real"]


def test_fix_prefers_the_exact_heading_over_one_it_contains():
    """mind.head's case: the anchor lost a doubled hyphen, and a shorter heading shares its prefix.

    Tokens equal to the anchor's are not ambiguous; containment in either direction
    is what a human has to choose between, and only when there is no exact one.
    """
    available = ["resolved-2026-06-14", "resolved-2026-06-14-round-2--design-deep-dive"]
    assert (
        links._successor("resolved-2026-06-14-round-2-design-deep-dive", available)
        == "resolved-2026-06-14-round-2--design-deep-dive"
    )
    assert links._successor("resolved-2026", available) is None, "containment in two headings stays a human's call"
