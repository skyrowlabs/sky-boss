"""A baseline is a claim about a population, and this pins whose code it counts.

The percentage a coverage ratchet stores is meaningless without the set it was
measured over, and the one day that set is guaranteed wrong is the day the tree
is scaffolded: everything measured is the shell, covered by the shell's own
tests, at a rate this project did nothing to earn. Recording it then makes the
first lightly-tested module of your own read as a regression you caused.

Nothing about that is visible in the number, which is why it is a test rather
than a paragraph. The three cases below are the only three there are — none of
it is yours, some of it is yours, and there is no manifest to ask — and the
third is deliberately not the second: *I cannot tell* and *none of this is
yours* license different behaviour, so they are different values.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import check_coverage_budget as budget  # noqa: E402
from tests.scanning import scanned  # noqa: E402
from tests.shell import SHELL_PACKAGE  # noqa: E402

#: Two scaffold files and one of the project's own. Two rather than one on
#: purpose: with a single scaffold file, "every measured file is scaffolded" and
#: "the one file matched" are the same set, so the filter would pass whether it
#: filtered or not.
SCAFFOLDED = {f"{SHELL_PACKAGE}/check.py": 4, "scripts/output.py": 6}
OURS = {"app/engine.py": 5}


def coverage_xml(path: Path, files: dict) -> Path:
    """A Cobertura report naming `files`, one `<line>` per statement.

    A value is a statement count, all of them hit, or `(statements, hit)`. The
    report's `line-rate` is computed from those lines rather than written down:
    it used to be a fixed `0.5`, which cannot express the case this file exists
    for — the whole set falling while your own code holds still.
    """
    shaped = {name: value if isinstance(value, tuple) else (value, value) for name, value in files.items()}
    total = sum(statements for statements, _ in shaped.values())
    covered = sum(hit for _, hit in shaped.values())
    root = ET.Element("coverage", {"line-rate": str(covered / total if total else 0), "lines-valid": str(total)})
    classes = ET.SubElement(ET.SubElement(ET.SubElement(root, "packages"), "package"), "classes")
    for name, (statements, hit) in shaped.items():
        lines = ET.SubElement(ET.SubElement(classes, "class", {"filename": name}), "lines")
        for number in range(1, statements + 1):
            ET.SubElement(lines, "line", {"number": str(number), "hits": "1" if number <= hit else "0"})
    path.write_bytes(ET.tostring(root))
    return path


@pytest.fixture
def manifest(tmp_path):
    """The scaffolder's record, naming the two files it wrote."""
    path = tmp_path / ".skeletor.json"
    path.write_text(json.dumps({"files": {name: "sha" for name in SCAFFOLDED}}), encoding="utf-8")
    return path


@pytest.fixture
def tree(tmp_path, monkeypatch, manifest):
    """A tree whose manifest and budget the checker reads instead of ours.

    `--update` writes, so a test that let it reach the real `coverage_budget.json`
    would ratchet this repository while asserting about a fixture.
    """
    monkeypatch.setattr(budget, "SCAFFOLD_MANIFEST", manifest)

    budget_file = tmp_path / "coverage_budget.json"
    budget_file.write_text(json.dumps({"tolerance_pts": 0.5, "suites": {"unit": {"baseline_pct": 0.0}}}))
    monkeypatch.setattr(budget, "BUDGET", budget_file)

    def run(files: dict, *flags: str, entry: Optional[dict] = None) -> tuple[int, dict]:
        if entry is not None:
            budget_file.write_text(json.dumps({"tolerance_pts": 0.5, "suites": {"unit": entry}}))
        xml = coverage_xml(tmp_path / "coverage.xml", files)
        monkeypatch.setattr(sys, "argv", ["check", "--xml", str(xml), "--json", *flags])
        return budget.main(), json.loads(budget_file.read_text())

    return run


def test_a_scaffold_only_population_has_none_of_ours(tree):
    """The shipped state of every tree on its first coverage run."""
    code, stored = tree(SCAFFOLDED)
    assert code == 0
    assert stored["suites"]["unit"]["baseline_pct"] == 0.0


def test_the_baseline_is_refused_while_none_of_it_is_ours(tree):
    """The write that poisons the ratchet, and the only one worth blocking.

    Red rather than a warning: `--update` is a request to record a fact, and a
    request that cannot be honoured has not been honoured. A warning here would
    print beside a file that had already been written.
    """
    code, stored = tree(SCAFFOLDED, "--update")
    assert code == 1
    assert stored["suites"]["unit"]["baseline_pct"] == 0.0, "refused and wrote anyway"


def test_the_baseline_is_recorded_once_some_of_it_is_ours(tree):
    """The other direction, and the reason this is not simply `--update` removed.

    A rule that only ever refuses is being agreed with rather than applied.
    """
    code, stored = tree({**SCAFFOLDED, **OURS}, "--update")
    assert code == 0
    assert stored["suites"]["unit"] == {"own_baseline_pct": 100.0}, "recorded over the whole set, or kept the old key"


def test_no_manifest_is_not_the_same_answer_as_none_of_it_is_ours(tree, manifest, tmp_path):
    """A tree can be adopted by hand, or delete the file; both are supported.

    Refusing without a manifest would make an optional file load-bearing for an
    unrelated command — so the answer is `None`, the update proceeds, and the
    envelope says the split is unknown rather than claiming a zero.
    """
    manifest.unlink()
    code, stored = tree({f"{SHELL_PACKAGE}/check.py": (4, 1), "scripts/output.py": (6, 4)}, "--update")
    assert code == 0
    assert stored["suites"]["unit"] == {"baseline_pct": 50.0}, "without a manifest the whole set is all there is"

    xml = ET.parse(coverage_xml(tmp_path / "c.xml", SCAFFOLDED))
    assert budget.own_statements(xml.getroot()) is None


def test_the_composition_is_stated_wherever_the_number_is_written_down(tree, capsys):
    """The named edge of the refusal, answered without inventing a threshold.

    One test file of your own lifts the tree out of the degenerate case while
    leaving the baseline 99% about the shell. No percentage separates those
    honestly, so the reader gets the composition and decides.
    """
    everything = {**SCAFFOLDED, **OURS}
    split = f"{sum(OURS.values())} of {sum(everything.values())} measured statements are your own"

    # The recommendation, which has to come first: `--update` moves the
    # baseline to the observed value, and this branch needs to be above it.
    tree(everything)
    assert split in capsys.readouterr().err

    tree(everything, "--update")
    assert split in capsys.readouterr().err


def test_the_split_is_counted_in_statements_not_files(tree, tmp_path):
    """One large module of ours against many small ones of theirs, and back.

    A file count would call a tree with one 500-line module of its own "mostly
    scaffold" and refuse a baseline that is perfectly representative.
    """
    xml = ET.parse(coverage_xml(tmp_path / "c.xml", {**SCAFFOLDED, **OURS}))
    assert budget.own_statements(xml.getroot()) == sum(OURS.values())


#: A shell that got bigger and worse-tested under an upgrade, beside an own
#: module that did not move — proto.pilot's nightly, in miniature.
UPGRADED = {f"{SHELL_PACKAGE}/check.py": (40, 10), "scripts/output.py": (60, 20)}


def test_an_upgrade_that_lowers_the_shell_does_not_fail_your_baseline(tree):
    """The defect: the whole set falls, your own code holds, and the ratchet is green."""
    code, _ = tree({**SCAFFOLDED, **OURS}, "--update")
    assert code == 0
    code, stored = tree({**UPGRADED, **OURS})
    assert code == 0, "the shell's coverage fell and the adopter's ratchet went red"
    assert stored["suites"]["unit"] == {"own_baseline_pct": 100.0}


def test_your_own_code_falling_still_fails(tree):
    """The other direction — a ratchet that stopped failing is not a fix."""
    tree({**SCAFFOLDED, **OURS}, "--update")
    code, _ = tree({**SCAFFOLDED, "app/engine.py": (5, 3)})
    assert code == 1


def test_the_old_key_is_not_reinterpreted(tree, capsys):
    """`baseline_pct` was recorded over the whole set and is compared over it,
    with the split and the command that migrates it."""
    code, stored = tree({**UPGRADED, **OURS}, entry={"baseline_pct": 87.43})
    assert code == 1, "an old whole-set baseline was compared against the own-code rate"
    err = capsys.readouterr().err
    assert "measured statements are your own" in err and "--update" in err, err
    assert stored["suites"]["unit"] == {"baseline_pct": 87.43}, "a comparison rewrote the budget"


def test_the_shipped_floor_does_not_ask_to_migrate(tree, capsys):
    """`0.0` is the floor every scaffold ships, not a recording on the old basis."""
    tree({**SCAFFOLDED, **OURS})
    assert "over the whole measured set" not in capsys.readouterr().err


def test_your_tests_are_not_your_code(tree):
    """A test file is nearly all executed by running it, so counting it lifts
    the rate with how much testing you write, not with what it reaches."""
    code, stored = tree({**SCAFFOLDED, "app/engine.py": (10, 5), "tests/test_engine.py": (90, 90)}, "--update")
    assert code == 0
    assert stored["suites"]["unit"] == {"own_baseline_pct": 50.0}


def test_an_own_baseline_with_nothing_of_yours_measured_fails(tree):
    """Not the fresh-tree pass it resembles: the suite stopped reaching your code."""
    code, _ = tree(SCAFFOLDED, entry={"own_baseline_pct": 80.0})
    assert code == 1
    code, _ = tree(SCAFFOLDED, entry={"own_baseline_pct": 0.0})
    assert code == 0


def test_every_json_key_names_one_population(tree, capsys):
    """`baseline_pct` is the whole set and `own_baseline_pct` is your code, on
    every path, as in the budget file — never one key for both."""

    def payload(*args, **kwargs) -> dict:
        tree(*args, **kwargs)
        return json.loads(capsys.readouterr().out)

    everything = {**SCAFFOLDED, **OURS}
    paths = {
        "own, within": payload(everything, entry={"own_baseline_pct": 100.0}),
        "own, below": payload({**SCAFFOLDED, "app/engine.py": (5, 1)}, entry={"own_baseline_pct": 100.0}),
        "own, none measured": payload(SCAFFOLDED, entry={"own_baseline_pct": 80.0}),
        "own, recorded": payload(everything, "--update", entry={"baseline_pct": 0.0}),
    }
    scanned(paths, "own-basis payloads", least=4)
    for name, body in paths.items():
        assert "own_baseline_pct" in body, f"{name}: {body}"
        assert "baseline_pct" not in body and "observed_pct" not in body, f"{name} reused a whole-set key: {body}"

    whole = payload(everything, entry={"baseline_pct": 10.0})
    assert whole["basis"] == "whole" and "baseline_pct" in whole and "own_baseline_pct" not in whole, whole
