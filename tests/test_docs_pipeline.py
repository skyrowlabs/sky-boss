"""Pin the docs pipeline's invariants — the ones a generator cannot self-check.

Each of these was a real failure in the project this was extracted from, and
each is cheap to re-break: they are properties of *documents*, which are edited
far more often than the code that reads them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import check_doc_tables as tables  # noqa: E402
from scripts.docs import frontmatter, plans  # noqa: E402
from scripts.docs.queue_order import UNORDERED, queue_position, run_order  # noqa: E402
from scripts.paths import IMPL_DIR, PROJECT_ROOT, TODO_DIR  # noqa: E402


@pytest.fixture(scope="module")
def tank():
    return [p for p in plans.scan(TODO_DIR) if not p.auto_generated]


#: Every path here is one this template really ships, and — the second half,
#: which proto.pilot paid for — one that structurally *cannot leave*. An invented
#: example reads as a dead reference to `check_source_doc_refs.py`, and the
#: alternative is an allowlist entry for a test fixture, a list where a real path
#: does. But a real path is not enough on its own: they replaced a dead upstream
#: path with a live one of their own, and it broke again the next time they filed
#: a plan, because the path they picked was a plan in `docs/TODO/` — the one
#: directory whose contents are *supposed* to go. `_TEMPLATE.md` and `README.md`
#: are the two things in there that never move, by `plans.NOT_A_PLAN`.
#:
#: `(row text, what it should vouch for)`. The `None` row is the point: a
#: folder routed by something that is not a claim about the folder is a folder
#: nobody has actually indexed, and the gate stays green over it.
DOC_TABLE_ROWS = [
    ("- **Rules** (`docs/rules/`)", "docs/rules"),
    ("- **Backlog** (`docs/TODO/README.md`)", "docs/TODO"),
    ("- **Deep** (`docs/reports/regular/README.md`)", "docs/reports/regular"),
    ("- **A plan template** (`docs/TODO/_TEMPLATE.md`)", None),
]


@pytest.mark.parametrize("row,folder", DOC_TABLE_ROWS, ids=[r[0][:40] for r in DOC_TABLE_ROWS])
def test_only_a_claim_about_a_folder_routes_it(row, folder, tmp_path, monkeypatch):
    """Naming a file inside a folder is not naming the folder.

    `_DOC_DIR` matched the directory portion of any file path, so a row for one
    of seven files in `docs/rules/` routed the whole folder. The comment beside
    it asserted the opposite — the exact property the regex lacked — which is
    the worst place for a gap, because a reviewer checks the code against the
    comment and the comment launders it. Reported by proto.pilot, measured.

    A folder's **own** README still routes it, deliberately: the shipped index
    routes three folders that way and no other, so the pattern could not simply
    be tightened. A deeper README routes its own folder and never a parent.

    The failure was permissive, which is why nothing caught it: `stranded()`
    under-reported and the gate stayed green over a folder nothing points at —
    the thing this check exists to remove, one door along.
    """
    table = tmp_path / "DOCS_INDEX.md"
    table.write_text(row + "\n", encoding="utf-8")
    monkeypatch.setattr(tables, "TABLES", [table])

    routed = tables.referenced()

    # Folders only — a row naming a file legitimately registers that file, and
    # the question here is which folders it vouches for.
    folders = {ref for ref in routed if not ref.endswith(".md")}

    if folder is None:
        assert not folders, f"{row!r} names a file and should route no folder, got {sorted(folders)}"
    else:
        assert folders == {folder}, f"{row!r} should route exactly {folder!r}, got {sorted(folders)}"


def test_every_gated_plan_names_its_gate(tank):
    """`blocked`/`shelved`/`deferred` must say what they are waiting for.

    A plan filed under no gate is a plan nobody picks up: the whole point of the
    gate is that plans sharing one clear together in a single sitting.
    """
    unclassified = [p.slug for p in tank if p.shelf_status in plans.GATED and p.blocked_on == "unclassified"]
    assert not unclassified, (
        "Gated plans with no `> **Blocked-On**:` line: "
        + ", ".join(unclassified)
        + f"\nValid gates: {', '.join(plans.GATES)}"
    )


def test_ungated_statuses_carry_no_gate(tank):
    """A gate on a `ready`/`planned`/`in-progress` plan is a contradiction."""
    contradictions = [p.slug for p in tank if p.shelf_status not in plans.GATED and p.blocked_on]
    assert not contradictions, f"Non-gated plans carrying a gate: {contradictions}"


def test_ready_means_an_agent_can_actually_take_it(tank):
    """`ready` is a work queue, not a label.

    Promoting a plan to `ready` *is* the act of handing it to an agent. A plan
    whose remaining work needs a human is `blocked`, however agent-doable the
    rest of it is — an agent that does the agent-half alone leaves the system in
    a state neither half describes.
    """
    offenders = {}
    for plan in tank:
        if plan.shelf_status != "ready":
            continue
        human_tasks = [t for t in plan.open_tasks(include_exempt=True) if "(~operator)" in t]
        if human_tasks:
            offenders[plan.slug] = human_tasks
    assert (
        not offenders
    ), "These plans are `ready` but still carry operator-only tasks — mark them `blocked`:\n" + "\n".join(
        f"  {slug}: {tasks}" for slug, tasks in offenders.items()
    )


def test_queue_order_is_never_inferred_and_never_duplicated(tank):
    """Two plans at one number reintroduces the alphabetical tiebreak the
    numbering exists to remove — and does it invisibly."""
    seen = {}
    for plan in tank:
        if plan.queue_order is None:
            continue
        assert plan.queue_order not in seen, (
            f"queue position {plan.queue_order} claimed by both '{seen[plan.queue_order]}' and '{plan.slug}' "
            f"— use `dev docs queue-order <slug> <n>`, which refuses a taken position"
        )
        seen[plan.queue_order] = plan.slug


def test_unnumbered_plans_never_displace_numbered_ones():
    """Absence is not a choice, so it sorts last."""
    numbered = {"slug": "z-numbered", "queue_order": 999, "priority": "low"}
    unnumbered = {"slug": "a-unnumbered", "queue_order": None, "priority": "critical"}
    assert run_order(numbered) < run_order(unnumbered)
    assert queue_position(unnumbered) == UNORDERED


def test_a_malformed_queue_order_sorts_last_rather_than_winning():
    assert queue_position({"queue_order": "soon"}) == UNORDERED
    assert queue_position({"queue_order": []}) == UNORDERED


def test_generated_docs_are_current():
    """The indexes and READMEs must match the plan tree in the commit that
    changed it — a stale generated file lands inside something nobody reviews."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "scripts/docs/regen.py", "--check"], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    )
    assert result.returncode == 0, f"Generated docs are stale — run `dev docs index`:\n{result.stdout}"


def test_no_filed_plan_still_claims_a_shelf():
    """Nothing in the archive carries a tank-only field, in either form.

    `dev docs file` removes both, so this is a ratchet at 0 — an empty
    archive passes it vacuously, which is right for a fresh tree and is not a
    hole, because `tests/test_docs_lifecycle.py` proves the check has teeth
    against a document it files itself. What this catches is the other route
    in: a plan moved by hand with `git mv`, which skips the one step that knows
    the plan has left the tank.

    Both forms, for the reason the whole taxonomy has two: the frontmatter is
    machine state and the header outranks it, so a doc with a clean frontmatter
    and a surviving `> **Shelf-Status**:` line still reports the old shelf to
    every reader.
    """
    stale = []
    for plan in plans.scan(IMPL_DIR, recursive=True):
        where = plan.path.relative_to(PROJECT_ROOT)
        stale += [f"{where}: {key} (frontmatter)" for key in plans.TANK_ONLY if key in plan.frontmatter]
        stale += [f"{where}: > **{key}**: (header)" for key in plans.TANK_ONLY_HEADERS if key in plan.headers]
    assert not stale, "Filed plans still carrying tank-only fields — delete the lines:\n  " + "\n  ".join(stale)


def test_no_plan_exists_in_both_trees():
    """A plan moves; it never copies. Two copies makes 'what is left to do'
    unanswerable, and the archive copy is the one people read."""
    tank_slugs = {p.slug for p in plans.scan(TODO_DIR)}
    archive_slugs = {p.slug for p in plans.scan(IMPL_DIR, recursive=True)}
    both = tank_slugs & archive_slugs
    assert not both, f"Plans present in BOTH docs/TODO/ and docs/implementations/: {sorted(both)}"


#: The three shapes a hand-written frontmatter block takes that this parser can
#: read and cannot represent. Reported by sky.boss from 24 real documents folded
#: into a scaffolded tree; **none of the three failed**, and each returned a
#: value a caller could not tell from the real thing.
#:
#: Written here as data rather than three tests because they are one claim —
#: *"I could not read this" and "this key is empty" are different answers* — and
#: the parser's job is to give the first when it means the first.
UNREPRESENTABLE = [
    ("a block sequence", "key_files:\n  - a.py\n  - b.py", "block sequences"),
    ("a wrapped inline list", "key_files: [a.py, b.py,\n  c.py]", "does not close"),
]


@pytest.mark.parametrize("case", UNREPRESENTABLE, ids=lambda c: c[0])
def test_frontmatter_refuses_what_it_cannot_represent(case):
    """It raises, and the refusal names the document.

    The refusal is the point. Before this, the block sequence returned `''` and
    the wrapped list returned `'[a.py, b.py,'` — a caller sees an empty field
    and a truncated one, and both read as the document's own content.
    """
    _, block, expected = case
    with pytest.raises(frontmatter.FrontmatterError) as raised:
        frontmatter.parse(f"---\n{block}\n---\nbody\n", where_from="plans/example.md")
    message = str(raised.value)
    assert expected in message, message
    assert "plans/example.md" in message, f"the refusal must name the document: {message}"


def test_a_trailing_comment_is_stripped_and_not_read_as_the_value():
    """`agent_value: 3  # why` is a 3, not the string `'3  # why'`.

    This one is stripped rather than refused, because that is what YAML means
    and this schema is flat enough for the rule to be unambiguous — and because
    it is a habit the template itself teaches, on the header lines in
    `docs/TODO/_TEMPLATE.md`.

    It is the shape that mattered most and looked least like a bug: the string
    reached `gen_impl_index.py`, whose `int()` sits inside an `except ValueError`
    that defaults to `1` — *historical only*. So a comment explaining why a
    document was rated highest was the thing that rated it lowest.
    """
    data, _ = frontmatter.parse("---\nagent_value: 3  # four rounds; the tty verdict\n---\nb\n")
    assert data["agent_value"] == 3, data

    # And the round trip holds, which is what stops the fix trading one silent
    # corruption for another: a value that really contains a `#` is quoted on
    # the way out and survives on the way back.
    for value in ("Fix # 42", "a#b", "plain"):
        back, _ = frontmatter.parse(f"---\ntitle: {frontmatter._emit(value)}\n---\nb\n")
        assert back["title"] == value, f"{value!r} did not survive the round trip: {back}"


def test_a_block_it_cannot_find_is_still_tolerated():
    """The tolerance that was already there, kept — and this is the line between.

    A missing or unterminated block is an *absence*, and one unreadable document
    must not crash an index build for every other one. What changed is that the
    same tolerance was covering constructs the parser could read and misrepresent,
    which is not an absence but a claim.
    """
    assert frontmatter.parse("just a body\n") == ({}, "just a body\n")
    assert frontmatter.parse("---\ntitle: x\nnever closed\n")[0] == {}
