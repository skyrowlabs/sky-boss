"""Every documented lifecycle folder has a role, and the role is written down.

`scripts/paths.py::NARRATIVE` is the set of directories whose documents describe
**a state other than the present one** — a plan naming a file it intends to
create, a memo naming code it ruled out. Every resolve-check excludes them by
role, because firing on them is firing on the thing they exist to do.

`docs/rules/docs.md` publishes the folder table an adopter files by. Those two
have to agree, and for `docs/research/` they did not: it is described there as
holding "a thing that is **not a plan**", where "rejected ideas keep their memo
rather than being deleted", and it was absent from `NARRATIVE`. stash.flow found
it by filing 17 documents of concept work exactly where the table says to and
watching a resolve-check redden on one for citing a path that is supposed to be
dead. Nothing failed upstream, because a fresh scaffold ships that folder empty
— the disagreement is only observable once somebody uses it.

**A partition, not a list.** Every folder in the table is either narrative or
declared present-tense with a reason. The alternative is what happened: a folder
whose absence from `NARRATIVE` is indistinguishable from a decision that it does
not belong there. Both directions are checked, so an entry that stops being true
fails rather than sitting as a decision nobody re-made.

**Both halves of the partition live in `scripts/paths.py`, and this file reads
them.** `PRESENT_TENSE` shipped here for one release and was a second home for a
ruling `NARRATIVE`'s own comment already carries — so an adopter who accepted
that comment's invitation and appended a folder found this file red, telling
them to delete an entry inside a shipped test. That edit is precisely the
divergence the append seam next to `NARRATIVE` exists to prevent. dream.doll and
stash.flow hit the two assertions independently, from real runs, on the same
day. Classify a folder once, in the file that argues the case.
"""

from __future__ import annotations

import ast
import copy
import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import DOCS_DIR, NARRATIVE, PRESENT_TENSE, PROJECT_ROOT  # noqa: E402
from tests.repo_files import present  # noqa: E402
from tests.scanning import scanned  # noqa: E402

RULES = DOCS_DIR / "rules" / "docs.md"

#: The two rules that bound your space. Everything of yours goes between them —
#: appends, and any prose you write about them — and the template renders nothing
#: in there, so your insertion point is never adjacent to a line a release edits.
#:
#: **There are two because one was not a boundary.** For a release the opening
#: rule was the whole mechanism and the seam claimed the template rendered nothing
#: below it, which is false about a file with template-owned sections further
#: down: mind.head found it latent from their own append's lower edge, stash.flow
#: found it by planting below the seam and watching four tests pass. So *below the
#: opening rule* certified the state section eighty lines on.
#:
#: **Assembled from parts, never spelled**, and so is the invitation below. A
#: detector that contains its own needle is its own first finding: spelled
#: contiguously, this file matched `seam_files()` and the suite failed reporting
#: itself. The alternative is an allowlist entry for the detector's source, which
#: is the second entry that means the predicate is wrong —
#: `bin/skeletor-verify`'s `checkout_path_literal_gate` states the same rule
#: about the same hazard, and assembles its needle for the same reason.
TERMINATOR = "# ── " + " ".join(("Nothing below", "this line is", "skeletor's"))
CLOSER = "# ── " + " ".join(("Skeletor's again", "below this line"))

#: What makes a file a seam: it invites an append, in those words. The same
#: predicate `bin/skeletor-verify`'s `append_seam_gate` enumerates seams by, so
#: a third seam is covered here by arriving rather than by being listed.
#:
#: **This file used to name `scripts/paths.py` and nothing else**, while the
#: generator discovered its seams — so the adopter was handed a list of one, and
#: `SCAN_ROOTS += ["src"]` immediately above `check_doc_links.py`'s marker passed
#: the whole suite. dream.doll measured that and filed it: a check whose
#: population is written down covers the seam it was written for and goes quiet
#: on the next one, which is Rule 2 at the one artifact meant to enforce Rule 2.
_INVITATION = (" ".join(("**Add", "your own")), " ".join(("as an", "append")))


def invited_files() -> list:
    """Every file in this tree that invites an append, in those words.

    Read as text and parsed, never imported: the question is where a statement
    SITS, which importing the module cannot answer.

    **This is the population; carrying the rules is the assertion.** The two used
    to be one predicate — invitation `and` terminator — so a seam file that
    shipped the invitation without the rule left the population instead of
    failing, and the only thing between that and silence was `least=2`, a copy of
    today's seam count. dream.doll priced it: stripping the terminator fails today
    through the floor (2 → 1), and with a third seam a fourth arriving without its
    rule leaves 3 ≥ 2 and goes quiet — so keeping the floor honest would mean
    bumping an integer on every new seam, **which is the hardcoded list the
    discovery rewrite just removed, relocated to a number.**
    """
    found = []
    for path in present("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if all(mark in text for mark in _INVITATION):
            found.append(path)
    return sorted(found)


def seam_files() -> list:
    """The invited files, each of which must carry both rules — asserted, not filtered."""
    invited = scanned(invited_files(), "files inviting an append in this tree", least=2)
    missing = []
    for path in invited:
        text = path.read_text(encoding="utf-8")
        absent = [name for name, rule in (("opening", TERMINATOR), ("closing", CLOSER)) if rule not in text]
        if absent:
            missing.append(f"{path.name}: no {' or '.join(absent)} rule")
    assert not missing, (
        "these files invite an append and do not bound a space to put it in:\n  "
        + "\n  ".join(missing)
        + f"\n\nAn invitation without both rules is an invitation to append into template prose. "
        f"Add the `{TERMINATOR}` and `{CLOSER}` blocks, or stop inviting."
    )
    return invited


def _table_folders() -> list:
    """The `docs/...` locations named in the lifecycle table of `docs/rules/docs.md`.

    Scoped to the table whose header names a Location column, so prose
    elsewhere in the file that mentions a folder is not read as a row.
    """
    lines = RULES.read_text(encoding="utf-8").splitlines()
    found, inside = [], False
    for line in lines:
        if line.startswith("|") and "Location" in line:
            inside = True
            continue
        if inside and not line.startswith("|"):
            break
        if inside:
            found += [match.rstrip("/") for match in re.findall(r"`(docs/[^`]+)`", line)]
    return found


def _is_narrative(folder: str) -> bool:
    """True when the folder is in NARRATIVE, or under one taken at its parent."""
    path = PROJECT_ROOT / folder
    return any(path == role or role in path.parents for role in NARRATIVE)


def test_every_lifecycle_folder_is_classified() -> None:
    """No folder in the published table is left without a role."""
    folders = scanned(_table_folders(), f"lifecycle folders in {RULES.name}", least=2)
    unclassified = [f for f in folders if not _is_narrative(f) and f not in PRESENT_TENSE]
    assert not unclassified, (
        f"{RULES.name} tells an adopter to file in {unclassified}, and "
        f"scripts/paths.py says nothing about whether those describe the present. "
        f"Append them to NARRATIVE or PRESENT_TENSE below that file's "
        f"`{TERMINATOR}` rule, with the reason."
    )


def test_no_present_tense_entry_has_gone_stale() -> None:
    """An exemption is checked against the thing it exempts, on every run."""
    folders = _table_folders()
    gone = [f for f in PRESENT_TENSE if f not in folders]
    assert not gone, (
        f"PRESENT_TENSE (scripts/paths.py) names {gone}, which {RULES.name} no longer lists — "
        f"an exemption is a decision only while the thing it exempts exists. Remove it as an "
        f"append below that file's `{TERMINATOR}` rule, rather than as an edit to "
        f"the literal:\n" + "".join(f"    PRESENT_TENSE.pop({f!r}, None)\n" for f in gone)
    )
    both = [f for f in PRESENT_TENSE if _is_narrative(f)]
    assert not both, (
        f"PRESENT_TENSE (scripts/paths.py) names {both}, which NARRATIVE now covers. One folder, "
        f"one role. Remove it as an append below that file's `{TERMINATOR}` rule — the template "
        f"owns the lines inside that literal and edits them, so a removal spelled "
        f"there conflicts on every upgrade:\n" + "".join(f"    PRESENT_TENSE.pop({f!r}, None)\n" for f in both)
    )


def _touched(node) -> list:
    """The names this top-level statement binds or mutates, in mutation position.

    One predicate, two populations, which is what makes both ends discovered.
    Run over the seam's documented examples it answers *which constants does this
    file invite appends to*; run over the file's own body it answers *which
    statements are appends*. A name in a value position — `DOCS_DIR` inside a
    tuple — is neither, and is excluded by construction rather than by a list.
    """

    def target(expr) -> list:
        if isinstance(expr, ast.Name):
            return [expr.id]
        if isinstance(expr, ast.Subscript):
            return target(expr.value)
        if isinstance(expr, (ast.Tuple, ast.List)):
            return [name for element in expr.elts for name in target(element)]
        return []

    if isinstance(node, ast.Assign):
        return [name for expr in node.targets for name in target(expr)]
    if isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        return target(node.target)
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        call = node.value.func
        if isinstance(call, ast.Attribute):
            return target(call.value)
    return []


def _module_constants(tree) -> set:
    """Every ALL_CAPS name this module binds at top level."""
    return {
        name
        for node in tree.body
        for name in _touched(node)
        if name.isupper() and isinstance(node, (ast.Assign, ast.AnnAssign))
    }


def _seam_constants(path: Path, tree) -> set:
    """The constants this seam's own documented examples tell you to append to."""
    shipped = _module_constants(tree)
    named = set()
    for block in _example_blocks(path):
        for statement in block:
            try:
                parsed = ast.parse(statement)
            except SyntaxError:
                continue
            named |= {name for node in parsed.body for name in _touched(node)}
    return named & shipped


def _appends(path: Path, tree) -> list:
    """Top-level statements that extend a seam constant after it is defined.

    The first statement touching a constant is the template's definition; every
    later one is an append. **That holds for the template too** — if a release
    ever shipped a second statement extending one of these constants, it would be
    putting its own line at the adopter's insertion point, and this reports it.
    """
    constants = _seam_constants(path, tree)
    seen, found = set(), []
    for node in tree.body:
        for name in _touched(node):
            if name not in constants:
                continue
            if name in seen:
                found.append(node)
                break
            seen.add(name)
    return found


def test_your_appends_are_inside_your_own_space() -> None:
    """An append outside the two rules keeps the old behaviour and says nothing about it.

    **The silent state this exists for.** An existing append merges cleanly and
    git orders it either side of the template's own new lines depending on exactly
    where it sat — so a tree takes the release, sees zero conflicts, and is still
    holding its append inside the prose block the template edits. It keeps the
    pre-rule behaviour, a clean first merge and a conflict on the next re-run,
    while every signal says it is covered.

    `scripts/paths.py` claimed the append always landed below. It does not, and
    the claim was generalised from one synthetic case. dream.doll measured the
    counterexample and asked for this check instead of a corrected sentence,
    which is the right trade: placement is a fact about this file, so this file's
    own suite can settle it and nobody has to believe a release note.

    Vacuous on a fresh scaffold, which ships no appends — so what is asserted is
    that the seams and their rules were FOUND. Without that this passes on a file
    the rule was deleted from, which is the one edit that would make it matter.
    """
    seams = seam_files()
    outside = []
    for path in seams:
        lines = path.read_text(encoding="utf-8").splitlines()
        where = {}
        for name, rule in (("opening", TERMINATOR), ("closing", CLOSER)):
            found = [number for number, line in enumerate(lines, start=1) if line.startswith(rule)]
            # **The message names the likely cause, which is usually not the template.**
            # It used to read "An adopter cannot be told to append below `the` rule
            # unless there is exactly one" — a description of a template defect, for a
            # condition an adopter's own box rule can create by starting with the same
            # words. node-zero reproduced it and pointed out the reader's first move is
            # to look upstream at a file that is fine.
            assert len(found) == 1, (
                f"{path.name} has {len(found)} lines starting with the {name} rule `{rule}`, and there "
                f"must be exactly one for `between the rules` to mean anything. If you wrote your own "
                f"section heading in this file, give it different words — this rule's text is how the "
                f"boundary is found. If you did not, the template shipped two and that is our bug."
            )
            where[name] = found[0]
        tree = ast.parse("".join(line + chr(10) for line in lines))
        outside += [
            f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}: {lines[node.lineno - 1].strip()}"
            for node in _appends(path, tree)
            if not where["opening"] < node.lineno < where["closing"]
        ]
    assert not outside, (
        f"these appends sit OUTSIDE the space between `{TERMINATOR}` and `{CLOSER}`:\n  "
        + "\n  ".join(outside)
        + "\n\nThey work today and will conflict on the next upgrade that re-runs before the base "
        "advances, because they share an insertion point with the template's own text. Move them "
        "between the two rules — it is a cut and paste, and nothing else has to change. If one "
        "arrived there by an upgrade rather than by you, that is expected: git placed it, and moving "
        "it is the whole remedy."
    )


#: An indented example inside a `#:` block — the spelling the seam hands an
#: adopter to paste. Grouped into contiguous blocks because one example defines a
#: name the next one uses.
_EXAMPLE = re.compile(r"^#:(?P<indent> {4,})(?P<code>\S.*)$")


def _example_blocks(path: Path) -> list:
    """Every contiguous run of indented examples in a seam file, as source."""
    blocks, current = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        found = _EXAMPLE.match(line)
        if found:
            current.append(found.group("code"))
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _shipped_namespace(path: Path) -> dict:
    """The seam file's own source ABOVE the frozen rule, executed fresh.

    **Not the imported module, and an adopter action is what proved it.** The
    examples are evaluated to answer *is this spelling correct*, which is a
    question about the spelling. Evaluated against the live module it becomes *does
    this do something in my tree*, and those differ the moment somebody accepts the
    seam's invitation: the removal example names the seeded `PRESENT_TENSE` key, so
    an adopter who pops that key — following the instruction the failing staleness
    check prints, verbatim — makes the template's own example a no-op and turns
    this test red for doing exactly as they were told.

    `pop` takes a default *because* a no-op is correct once the key is gone. The
    defect this test exists for is different and is never correct: a filter on
    `is not` against an anonymous entry cannot remove anything for anybody.

    Everything above the rule is the template's and everything below is the
    adopter's, so the same line that keeps merges clean draws the boundary this
    needs.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    rule = next(i for i, line in enumerate(lines) if line.startswith(TERMINATOR))
    # `__file__`, because these modules derive PROJECT_ROOT from it and an exec
    # namespace has none — the first run of this helper failed with a NameError
    # rather than a finding, which is the right failure and the wrong report.
    namespace: dict = {"__file__": str(path)}
    exec("".join(lines[:rule]), namespace)  # noqa: S102 - this tree's own source
    return namespace


def test_the_seam_examples_actually_do_something() -> None:
    """A spelling that no-ops is worse than one that errors, and one of these did.

    **`is not` silently did nothing for half the shipped tuple.** The removal
    idiom was `role is not IMPL_DIR`, argued for over `!=` on the grounds that
    these are directory objects whose equality is by path, so identity is what an
    adopter means. True about intent, false about the objects: `DOCS_DIR /
    "reports"` builds a new `Path` on every evaluation, so the comparison is true
    for every element, the filter runs, and the tuple comes back unchanged. Two of
    four entries are anonymous expressions, so the idiom worked for the half
    somebody reaches for first and was inert for the rest. proto.pilot found it.

    So the examples are **executed** rather than read, one statement at a time,
    in every seam file rather than in the one this check was written for.

    ## Per statement, because a block hid the bug it was written to catch

    The first version checked whether a BLOCK left either constant changed. The
    removal block touches both — `PRESENT_TENSE.pop(...)` then the `NARRATIVE`
    rebuild — so the working half satisfied the assertion for the broken half and
    the exact defect under test passed. Two statements, one verdict, and the
    verdict went to whichever succeeded.

    ## One mistake, two red tests — worth knowing before you debug

    This execs the seam file's source **above the opening rule**, so an append that
    landed on the wrong side of it joins that namespace. It can then satisfy the
    template's own documented `PRESENT_TENSE.pop(...)` example in advance and make
    it a no-op — so a misplaced append turns this test red *as well as* the
    placement check, and the finding here is a symptom of the one there. Fix the
    placement first. dream.doll recorded the coupling after meeting it.

    ## What is skipped, and why that cannot go quiet

    A statement that raises is illustrative rather than pasteable: the seam
    carries a comparison of two spellings with `CONFLICT` and `clean` annotated in
    a column, which is prose in code shape and not valid python, and one example
    names a constant defined only in a neighbouring block. Neither is this
    check's business. But "skip what raises" is how a check stops checking, so
    what is asserted is the number of statements that actually RAN — not the
    number found.
    """
    seams = seam_files()
    inert, executed = [], []
    for path in seams:
        blocks = scanned(_example_blocks(path), f"indented examples in {path.name}", least=1)
        shipped = _shipped_namespace(path)
        constants = _seam_constants(path, ast.parse(path.read_text(encoding="utf-8")))
        for block in blocks:
            namespace = dict(shipped)
            namespace.update({name: copy.copy(shipped[name]) for name in constants})
            for statement in block:
                touches = [name for name in constants if name in statement]
                # `copy`, not a reference. `PRESENT_TENSE |= {...}` mutates the dict
                # in place, so a snapshot that aliases it compares the object with
                # itself and every mapping example reads as inert — the harness
                # reporting its own aliasing as a finding about the seam, which it
                # did on first run.
                before = {name: copy.copy(namespace[name]) for name in touches}
                try:
                    exec(statement, namespace)  # noqa: S102 - the file under test is this tree's own
                except Exception:  # noqa: BLE001 - illustrative or context-dependent; see the docstring
                    break
                executed.append(statement)
                unchanged = [name for name in touches if namespace[name] == before[name]]
                if unchanged:
                    inert.append(f"{path.name}: {statement}   ->   {', '.join(unchanged)} unchanged")
    scanned(executed, "seam example statements that ran", least=3)
    assert not inert, (
        "these example statements name a constant and leave it as it was:\n  "
        + "\n  ".join(inert)
        + "\n\nAn adopter pastes one and nothing happens, silently. A removal that filters on identity "
        'is the known case: an anonymous entry like `DOCS_DIR / "reports"` builds a new object on every '
        "evaluation, so `is not` is true for every element. Use `!=`."
    )
