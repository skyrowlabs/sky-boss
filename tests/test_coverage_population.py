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

import pytest

pytestmark = [pytest.mark.unit]

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import check_coverage_budget as budget  # noqa: E402

#: Two scaffold files and one of the project's own. Two rather than one on
#: purpose: with a single scaffold file, "every measured file is scaffolded" and
#: "the one file matched" are the same set, so the filter would pass whether it
#: filtered or not.
SCAFFOLDED = {"cli/check.py": 4, "scripts/output.py": 6}
OURS = {"app/engine.py": 5}


def coverage_xml(path: Path, files: dict) -> Path:
    """A Cobertura report naming `files`, one `<line>` per statement."""
    root = ET.Element("coverage", {"line-rate": "0.5", "lines-valid": str(sum(files.values()))})
    classes = ET.SubElement(ET.SubElement(ET.SubElement(root, "packages"), "package"), "classes")
    for name, statements in files.items():
        lines = ET.SubElement(ET.SubElement(classes, "class", {"filename": name}), "lines")
        for number in range(1, statements + 1):
            ET.SubElement(lines, "line", {"number": str(number), "hits": "1"})
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

    def run(files: dict, *flags: str) -> tuple[int, dict]:
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
    assert stored["suites"]["unit"]["baseline_pct"] == 50.0


def test_no_manifest_is_not_the_same_answer_as_none_of_it_is_ours(tree, manifest, tmp_path):
    """A tree can be adopted by hand, or delete the file; both are supported.

    Refusing without a manifest would make an optional file load-bearing for an
    unrelated command — so the answer is `None`, the update proceeds, and the
    envelope says the split is unknown rather than claiming a zero.
    """
    manifest.unlink()
    code, stored = tree(SCAFFOLDED, "--update")
    assert code == 0
    assert stored["suites"]["unit"]["baseline_pct"] == 50.0

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
