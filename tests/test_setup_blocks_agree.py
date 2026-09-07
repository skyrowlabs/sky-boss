"""The setup steps are copied into several documents; nothing keeps them together.

Every document that tells a reader how to start carries the install steps. Which
documents those are is a property of **your** tree, not of this file: enrolment
is by content, and a document is in the comparison for as long as its block
still installs something. A fresh scaffold enrols three; a tree that has since
moved its venv line out of one of them enrols two, correctly and silently.

They were rendered from one source when this repository was scaffolded, and the
generator left. **The drift starts at the moment the guarantee ends**, which is
why this check lives here and not in the generator: there, one substitution
fills every copy, and a check would be asserting that a regex produced the same
value more than once.

That is the coordinate-system rule on a different face from the path gate.
`test_docs_name_real_paths.py` moved into this tree because the population is
larger here. This one is here because the failure mode **does not exist** in the
generator at all — volume was only ever a symptom of where a thing can go wrong.

Rule 11 in `AGENTS.md` already requires this: when two files describe the same
environment, a drift check owns the pair. It went unbuilt because a sentence was
standing in for it — *"rendered from the same source as the README's"* — which
discharged the rule by assertion. Deleting that sentence is what made the
requirement visible and unmet.

## Two checks, because only one half has an authority

**Which requirements file gets installed is checked against the tree**, where
`scripts/paths.py` names one and `ci.yml` calls it the source of truth at its
install step. Three documents disagreeing about a filename is a vote with no
tiebreaker; a document disagreeing with the toolchain is a defect with a
direction. Both directions are checked, and they catch opposite mistakes: a doc
naming a file nothing installs is a *stale* step, and a doc omitting the
toolchain entirely is a *missing* one. The second is not hypothetical — see
`setup_commands()` in the generator, whose docstring records the release where
a whole language shipped without it.

**The shared prefix is checked doc-to-doc**, where no authority exists, so it is
a ratchet rather than an assertion — see `test_the_shared_prefix_has_not_shrunk`.

## Enrolment, and why it names two toolchains

A fenced `bash` block that installs dependencies — `pip install -r <file>` or
`npm install`. Naming only the first is what a python-only reader writes, and it
enrolled **nothing at all** in a node tree, where a scan that finds nothing is a
check that passes having looked at nothing.

One exclusion, and it is a property of the block rather than a name in a list: a
block that opens by changing directory has declared it is setting up something
else. A sub-component with its own toolchain and its own requirements file is
right to differ, and it gets more common as a tree grows rather than less.
Residual, stated because it is real: a block that says "cd there first" in prose
instead of in the fence re-enrols and false-positives. The remedy is to put the
`cd` in the fence, which is better documentation anyway.

Built as a prototype by stash.flow, whose adopted tree is where the drift and
the sub-component false positive both actually existed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which owns
# every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repo_files import reference_docs  # noqa: E402
from scanning import scanned  # noqa: E402
from scripts.paths import GITHUB_DIR, PROJECT_ROOT, REQUIREMENTS, TESTS_DIR  # noqa: E402
from scripts.yaml_text import read_uncommented  # noqa: E402

#: A shell block a reader is meant to run. `bash` only: a ```text block is an
#: illustration and a ```console block is a transcript.
_FENCE = re.compile(r"```bash\n(?P<body>.*?)```", re.DOTALL)

#: A `pip install` and the rest of its command, stopping at a newline or a shell
#: separator so the arguments of one install cannot bleed into the next.
_PIP_INSTALL = re.compile(r"pip install\b(?P<args>[^\n;&|]*)")

#: Every `-r <file>` within those arguments. **Every**, and that is the point:
#: this was one regex, `pip install\s+-r\s+(?P<target>...)`, which matches the
#: first `-r` on a line and stops — `pip install -r a -r b -r c` measured as
#: `['a']`. Two of its three callers fail loudly when they under-collect, so
#: they would have been found; the third checks each documented file against
#: what CI installs and simply never looks at the second one, which is a silent
#: pass on exactly the line most likely to be wrong. sky.boss found it with a
#: CI step installing a toolchain no document was ever checked against.
_DASH_R = re.compile(r"-r\s+(?P<target>[\w./-]+)")

#: Installing dependencies, in either toolchain this tree can carry.
_INSTALLS = re.compile(r"pip install\s+-r\s+[\w./-]+|npm install")


def requirements_in(text: str) -> list:
    """Every requirements file `text` installs from, in order of appearance.

    A list rather than a set because the callers want different things from it
    and one of them reports the offending name — deduplicating here would make
    a message name a file that is not the one on the line.
    """
    return [
        match.group("target")
        for install in _PIP_INSTALL.finditer(text)
        for match in _DASH_R.finditer(install.group("args"))
    ]


#: The ratchet's home. The value is written by the generator, because the number
#: of shared lines depends on which toolchains the tree was scaffolded with.
BUDGET = TESTS_DIR / "setup_block_budget.json"


def _strip_comment(line: str) -> str:
    """`./dev check pre-push   # green on a fresh tree` → the command.

    The comment is the one thing these blocks are *expected* to differ on: the
    same command is annotated for a reader of `AGENTS.md` and left bare in the
    `README`. Comparing them raw would report the annotation as drift, and the
    fix a reader would reach for is to delete the annotation.
    """
    return line.split("#", 1)[0].rstrip()


def setup_blocks() -> dict:
    """`{document: [command lines]}` for blocks that install dependencies.

    Enrolment and its one exclusion are argued in the module docstring.
    """
    found = {}
    for doc in reference_docs():
        for match in _FENCE.finditer(doc.read_text(encoding="utf-8")):
            lines = [_strip_comment(line) for line in match.group("body").splitlines()]
            lines = [line for line in lines if line.strip()]
            if not any(_INSTALLS.search(line) for line in lines):
                continue
            if any(line.strip().startswith("cd ") for line in lines):
                continue
            found[str(doc.relative_to(PROJECT_ROOT))] = lines
    return found


def ci_requirements() -> set:
    """Every requirements file a CI workflow installs from, comments masked.

    `scripts/yaml_text.py` owns the masking and carries the two gates that
    learned it the expensive way: a commented-out `pip install` is prose to a
    reader and a substring match to a naive scan.
    """
    found = set()
    for workflow in sorted((GITHUB_DIR / "workflows").glob("*.yml")):
        found.update(requirements_in(read_uncommented(workflow)))
    return found


def shared_prefix(blocks: dict) -> int:
    """How many leading lines every enrolled block currently agrees on."""
    if len(blocks) < 2:
        return 0
    depth = 0
    for column in zip(*blocks.values()):
        if len(set(column)) != 1:
            break
        depth += 1
    return depth


def test_the_scan_finds_blocks_to_compare():
    """`least=2` because a drift check over one block is not a drift check.

    With a single block every comparison below is between a thing and itself:
    the prefix is its own length and no two lines can disagree. That reads
    identical to agreement, which is the state this file exists to distinguish.
    """
    scanned(setup_blocks(), "fenced bash setup blocks installing dependencies", least=2)
    scanned(ci_requirements(), "requirements files installed by a CI workflow")


def test_the_scan_sees_every_requirements_file_on_a_line():
    """The parser, against the case that produced a silent pass.

    A fixture rather than a tree fact, and deliberately: the template ships no
    multi-`-r` line today, so a check over the tree would be green under the
    broken regex and the correct one alike — the convenient case cannot
    discriminate. The string below is the shape an adopter's CI takes the moment
    it grows a second requirements file, which is when the scan stops looking.
    """
    assert requirements_in("pip install -r a.txt -r b/c.txt -r d.txt") == ["a.txt", "b/c.txt", "d.txt"]
    # Two installs on separate lines are two installs, and neither swallows the
    # other's arguments — `[^\n;&|]` is what stops the first `args` group
    # running to the end of the file.
    assert requirements_in("pip install -r a.txt\nnpm install\npip install -r b.txt") == ["a.txt", "b.txt"]
    assert requirements_in("pip install -r a.txt && pip install -r b.txt") == ["a.txt", "b.txt"]
    # A `pip install` with no `-r` contributes nothing rather than a false one.
    assert requirements_in("pip install pre-commit") == []


def test_no_setup_block_invents_a_requirements_file():
    """A document may not send a reader to a file nothing installs from."""
    authoritative = ci_requirements()
    for doc, lines in sorted(setup_blocks().items()):
        for line in lines:
            # Every `-r` on the line, not the first. A second requirements file
            # is exactly where a document goes stale, because it is the one
            # somebody appended without re-reading the workflow.
            for target in requirements_in(line):
                if target not in authoritative:
                    pytest.fail(
                        f"{doc} tells a reader to install from `{target}`, which no CI "
                        f"workflow installs from. CI installs {sorted(authoritative)}. Either the "
                        "document is stale or the workflow is — they cannot both be the setup."
                    )


def test_every_setup_block_installs_the_host_toolchain():
    """The other direction, which catches a missing step rather than a wrong one.

    This tree's CLI, docs pipeline, lint gates and test suite are python at
    every language — `cli/`, `tests/` and `scripts/` ship at the base tier — so
    a setup block that does not install `scripts/requirements.txt` documents a
    quick start whose next line cannot run. It is checked against the one file
    `scripts/paths.py` names and `ci.yml` calls the source of truth, rather than
    against the other blocks, because "all three agree and all three are wrong"
    is maximally consistent and doc-to-doc has nothing to say about it.
    """
    target = REQUIREMENTS.relative_to(PROJECT_ROOT).as_posix()
    for doc, lines in sorted(setup_blocks().items()):
        installed = {target for line in lines for target in requirements_in(line)}
        assert target in installed, (
            f"{doc}'s setup block never installs `{target}`, so a reader who follows it has no "
            f"CLI, no lint tools and no test runner — it installs {sorted(installed) or 'nothing'}. "
            "Every tier ships a python toolchain whatever `--language` added on top of it."
        )


def test_the_shared_prefix_has_not_shrunk():
    """The half with no authority, so a ratchet rather than an assertion.

    Three documents disagreeing about a command is a vote with no tiebreaker,
    and picking one as canonical would be inventing an authority this check does
    not have. What can be defended without one is that **the agreement does not
    quietly get smaller**: the depth is measured, not chosen, and a commit that
    shortens it has to say so.

    It ratchets **up**, which is the opposite of the skip and coverage budgets
    and for the same reason they go down — the direction that needs no argument
    is the one nobody has to be talked into.

    A block's own tail is deliberately unchecked. A document may add
    `cp .env.example .env` or three commands of its own, and those are per-file
    by design. Only the agreed head is anybody's shared claim.

    **Both messages name the enrolled documents, because a rise has two
    readings.** The blocks got tighter, or one of them left the comparison — and
    a document whose block stops installing anything drops out with nothing said
    about it. That is not invisible, which is the useful part: fewer blocks
    almost always agree further, so the departure surfaces here as a rise. It
    surfaces *unreadably* if the list is missing, and it was: the shrunk branch
    named the blocks and the grown branch did not, so the case an upgrade
    actually produces was the one with no way to tell the two apart.
    proto.pilot met exactly that, arriving at 4 against a floor of 2 with two
    documents enrolled and no line saying which.
    """
    blocks = setup_blocks()
    floor = json.loads(BUDGET.read_text(encoding="utf-8"))["min_shared_prefix"]
    depth = shared_prefix(blocks)
    assert depth >= floor, (
        f"the setup blocks agreed on {floor} leading lines and now agree on {depth}. "
        f"Blocks: {sorted(blocks)}. Either a shared setup step drifted in one document and "
        "not the others — fix it — or the divergence is intended, in which case lower "
        f"`min_shared_prefix` in {BUDGET.name} in the same commit, with the reason in the "
        "commit message."
    )
    assert depth == floor, (
        f"the setup blocks now agree on {depth} leading lines, above the pinned {floor}. "
        f"Blocks: {sorted(blocks)}. Either they got tighter, or a document left the "
        "comparison — its block stopped installing anything, so it is no longer being "
        "checked against the others. Read that list before raising the floor.\n  "
        f"Raise `min_shared_prefix` in {BUDGET.name} to {depth} in this commit, or the gain "
        f"is not locked in and the next drift back to {floor} passes silently."
    )
