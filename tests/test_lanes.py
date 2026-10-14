"""The capture lanes, their intakes and the editor views are one set.

``scripts/lanes.py`` is a registry, so the failure it exists to prevent is the
one every registry has: an entry that half-exists. Three things read it and each
can be right on its own while disagreeing with the others —

* a lane with no intake command is a **write-only queue that nobody can fill**,
* an intake with no lane is a command filing into a label no view shows,
* a view generated before a lane changed is a pane that is silently incomplete.

All three render as *an empty pane in the editor*, which is also what a healthy,
drained queue renders as. That is the whole reason these are assertions rather
than a convention: **the failure and the success look identical from the place
you would notice.**

The drift assertion here overlaps `dev check docs` on purpose. The gate is
what a person runs; this is what CI runs, and a generated artifact that only one
of them checks is one an adopter can push past.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import click
import pytest

from scanning import scanned

pytestmark = [pytest.mark.unit]

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import gen_vscode_queries as gen  # noqa: E402
from scripts.lanes import LANES, LANES_BY_KEY, Section, drain_note, drainer_of, labels  # noqa: E402
from tests.shell import module  # noqa: E402


def intake(lane) -> click.Command:
    """The command that files into ``lane``, or a failure that says what is missing.

    `module()` raises `ModuleNotFoundError` for a lane whose intake was never
    written, and that traceback names an import rather than the mistake. Somebody
    adding a lane and forgetting its command is the exact reader these
    assertions are for, so the message they get is the message written here —
    measured by planting a third lane and reading what pytest actually printed,
    which was the bare import error and nothing else.
    """
    try:
        found = getattr(module(lane.key), lane.key, None)
    except ModuleNotFoundError:
        found = None
    assert isinstance(found, click.Command), (
        f"lane {lane.key!r} has no intake: the shell has no module exporting a click command "
        f"named {lane.key!r}. A lane nothing files into is a pane that is empty forever, and an "
        f"empty pane is what a drained queue looks like — add the intake, or drop the lane."
    )
    return found


def test_every_lane_has_an_intake_command() -> None:
    """A lane is only real if something files into it.

    The enrolment rule, and the one that keeps the editor honest: a pane whose
    label nothing can produce is empty forever, and looks exactly like a queue
    you have kept clear. Reached through `tests.shell` rather than by importing
    the package name, because the shell package is renameable.
    """
    for lane in scanned(LANES, "capture lanes"):
        assert intake(lane).name == lane.key


def test_intake_options_are_the_lane_sections() -> None:
    """The refusal and the registry are the same list.

    `capture_command` generates the options from `lane.sections`, so this is
    what stops that generation quietly drifting from what the body composes —
    a section present in one and absent in the other means a heading with no
    value under it, or a flag whose answer is discarded.
    """
    for lane in scanned(LANES, "capture lanes"):
        command = intake(lane)
        flags = {param.name for param in command.params if param.name not in ("summary", "local")}
        assert flags == {section.name for section in scanned(lane.sections, f"{lane.key} sections")}
        required = {param.name for param in command.params if getattr(param, "required", False)}
        assert {s.name for s in lane.sections} <= required, (
            "every section is required — a capture missing one is a capture whose reader "
            "has to come back and ask, and the person who could answer has moved on"
        )


def test_lane_identifiers_are_unique_and_usable() -> None:
    """Two lanes sharing a label share a queue, and neither one says so."""
    assert len({lane.label for lane in LANES}) == len(LANES)
    assert len({lane.key for lane in LANES}) == len(LANES)
    for lane in scanned(LANES, "capture lanes"):
        # The label reaches a `gh` argument and a GitHub search query, and the
        # key becomes a subcommand. A space or a quote in either is a defect
        # that surfaces as an unquoted-shell problem somewhere else entirely.
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", lane.label), lane.label
        assert re.fullmatch(r"[a-z][a-z0-9-]*", lane.key), lane.key
        assert re.fullmatch(r"[0-9a-f]{6}", lane.color), f"{lane.key}: not a gh label colour"
        for section in lane.sections:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", section.name), section.name
            assert section.help.strip(), f"{lane.key}.{section.name} has no help"


def test_every_lane_has_a_view_and_the_rest_query_is_its_complement() -> None:
    """The generated views partition the open issues, with nothing outside them.

    "Everything Else" is the assertion that matters. It is built by negating the
    registry, so it is a true complement for free — and if it were ever written
    by hand, an issue opened in the browser under no lane label would sit in no
    pane at all, which is how people stop trusting an issue tracker.
    """
    queries = scanned(gen.issue_queries(), "generated issue queries", least=len(LANES) + 2)
    by_label = {query["label"]: query["query"] for query in queries}

    for lane in LANES:
        # `(?<!-)` is load-bearing: `label:agent-bug` is a substring of
        # `-label:agent-bug`, so the obvious `in` test counts the complement
        # query as a second view of every lane. The first draft of this
        # assertion did exactly that and failed on a correct generator.
        selects = re.compile(rf"(?<!-)\blabel:{re.escape(lane.label)}\b")
        matching = [text for text in by_label.values() if selects.search(str(text))]
        assert len(matching) == 1, f"{lane.label} should have exactly one view, found {len(matching)}"

    rest = next(text for name, text in by_label.items() if name == "Everything Else")
    negated = set(re.findall(r"-label:([a-z0-9-]+)", str(rest)))
    assert negated == set(labels()), (
        f"the complement query negates {sorted(negated)} but the registry holds {sorted(labels())} — "
        "an issue under a lane label the complement forgets appears in two panes, and one under a "
        "label it invents appears in none"
    )


def test_pr_views_name_a_state_that_exists() -> None:
    """Four views, and the draft one's NAME is derived rather than asserted.

    "Overnight Drafts" is only true in a tree with something committing on a
    schedule. The value here is not the string — it is that the string is a
    function of the job registry, so it cannot become a small lie about the
    tree by sitting still while the tree changes.
    """
    queries = scanned(gen.pr_queries(), "generated pull-request queries", least=4)
    drafts = queries[0]["label"]
    assert drafts == ("Overnight Drafts" if gen._has_unattended_committer() else "Drafts (iterating)")
    assert all(str(query["query"]).strip() for query in queries), "a view with an empty query shows everything"


def test_drain_note_reports_the_registry_rather_than_a_stored_sentence() -> None:
    """Whatever the note says, the job registry is where it came from.

    Both branches are asserted because both ship: a tier with no
    `scripts/reporting/` has no drainer and must say so, and one that has
    claimed a lane's key must name its schedule instead. jam.sense's incident is
    the reason — their stored copy of a drain time said 07:00 for two weeks
    after that fire was retired, one import from the field that said 07:45.
    """
    for lane in scanned(LANES, "capture lanes"):
        job = drainer_of(lane)
        note = drain_note(lane)
        if job is None:
            assert note == "nothing drains these"
        else:
            assert note != "nothing drains these"
            assert getattr(job, "key", None) == lane.drainer_job


def test_the_generated_region_is_current() -> None:
    """`.vscode/settings.json` matches what the registry renders today.

    Regenerating is one command and is named in the failure, because a gate
    whose remedy you have to go and look up is a gate people delete.
    """
    settings = PROJECT_ROOT / ".vscode" / "settings.json"
    assert settings.exists(), (
        "the editor settings were not created — the scaffolder runs "
        "scripts/gen_vscode_queries.py after copying; see scripts/lanes.py"
    )
    current = settings.read_text(encoding="utf-8")
    assert gen.splice(current, gen.region()) == current, (
        "the editor views have drifted from scripts/lanes.py — "
        "regenerate with: python3 scripts/gen_vscode_queries.py"
    )


def test_only_the_marked_region_is_generated() -> None:
    """Regenerating preserves every byte outside the markers, comments included.

    This is why the generator splices text instead of round-tripping the JSON.
    A round-trip keeps the keys and drops the comments, and the file still
    parses and still works afterwards — the quiet kind of damage, where what is
    lost is the reasons somebody wrote down.
    """
    original = (PROJECT_ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8")
    head, _, _ = original.partition(gen.BEGIN)
    _, _, tail = original.rpartition(gen.END)
    rebuilt = gen.splice(original, gen.region())
    assert rebuilt.startswith(head) and rebuilt.endswith(tail)
    # Deliberately NOT an assertion that `head` contains comments. It does in a
    # tree this generator created, and need not in one that already had its own
    # settings file when this template arrived — which is the population the
    # splice exists for. Asserting the convenient case would have been a gate
    # that is red only for adopters.


def test_the_generator_refuses_a_file_with_no_region() -> None:
    """Missing markers is a refusal, never a silent no-op.

    A generator that finds nothing to replace and exits 0 is indistinguishable
    from one that had nothing to do, and it would leave `--check` green over a
    file it never looked at.
    """
    with pytest.raises(SystemExit):
        gen.splice("{\n  // nothing to replace here\n}\n", gen.region())


def test_the_settings_file_parses_once_the_comments_are_stripped() -> None:
    """It is JSONC, so this strips `//` lines before parsing — nothing else.

    Enough to catch the failure that actually happens: a generated region that
    renders a trailing comma before the closing brace, or unbalanced brackets.
    Both make the editor drop every setting in the file and say nothing.
    """
    text = (PROJECT_ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8")
    # The generator's own reader, not a second copy of it here. Two
    # implementations of one rule agree with each other, and this file exists
    # because that is how a registry's readers drift apart.
    parsed = json.loads(gen.strip_comments(text))
    assert set(parsed) >= {"githubIssues.queries", "githubPullRequests.queries"}
    assert len(parsed["githubIssues.queries"]) == len(LANES) + 2


def test_regeneration_is_a_fixed_point() -> None:
    """Applying the generator twice is the same bytes as applying it once.

    Rule 4 of this template: a generated artifact whose regeneration produces a
    diff makes every commit a fight, and the first thing people do about that
    is stop regenerating.

    **In-process, and never by running the writer.** The first draft of this
    shelled out to `scripts/gen_vscode_queries.py` with no `--check` — a real
    write to the real file — so the suite repaired the drift that
    `test_the_generated_region_is_current` had just failed on, two tests
    earlier. It was caught by planting a lane rename: pytest went red, and the
    `--check` run straight after it came back green over a file the suite had
    silently regenerated in between. A test that repairs what it checks is worse
    than an absent one, because the repair also lands in the working tree of
    whoever ran it.
    """
    original = (PROJECT_ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8")
    once = gen.splice(original, gen.region())
    assert gen.splice(once, gen.region()) == once


def test_the_check_flag_reports_without_writing() -> None:
    """The script runs, and `--check` leaves the file exactly as it found it.

    The one place the generator is executed as a program rather than imported,
    because `dev check docs` runs it that way and an import-only test would
    not notice a broken `__main__` guard or a bad `sys.path` bootstrap.
    """
    settings = PROJECT_ROOT / ".vscode" / "settings.json"
    before = settings.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "scripts/gen_vscode_queries.py", "--check"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert settings.read_text(encoding="utf-8") == before


def test_sections_are_declared_not_inferred() -> None:
    """`Section.fenced` defaults off, and the one that is on is a command.

    The default matters more than the value: a section is prose unless somebody
    said otherwise, so a new section cannot accidentally acquire a code fence
    that eats its formatting.
    """
    assert Section("x", "y").fenced is False
    fenced = [(lane.key, s.name) for lane in LANES for s in lane.sections if s.fenced]
    assert fenced == [("bug", "reproduce")], (
        "a fenced section is one whose value is a command somebody will copy; "
        f"found {fenced} — if that is deliberate, this assertion is the record of it"
    )


def test_lookup_maps_cover_the_registry() -> None:
    """The by-key map is derived, so this catches only a hand-edited one."""
    assert set(LANES_BY_KEY) == {lane.key for lane in scanned(LANES, "capture lanes")}


def test_an_existing_settings_file_keeps_every_key_and_comment() -> None:
    """The case an adopter actually hits: they already had editor settings.

    `AGENTS.md` calls a `--force` scaffold into a working repository *the usual
    case*, and `.vscode/settings.json` is among the likeliest files to be there
    already. This template shipped it as a plain overlay file for exactly one
    afternoon, which replaced it — measured on a tree carrying
    `editor.formatOnSave` and a strict type-checking mode, both silently gone.
    The generator creates or splices now, and the overlay ships no such file.
    """
    theirs = '{\n  // mine, and I care about it\n  "editor.formatOnSave": true\n}\n'
    result = gen.splice(gen.ensure_region(theirs), gen.region())
    assert "// mine, and I care about it" in result
    parsed = json.loads(gen.strip_comments(result))
    assert parsed["editor.formatOnSave"] is True
    assert "githubIssues.queries" in parsed


def test_the_region_is_added_without_breaking_the_object() -> None:
    """Every shape of prior file still parses once the region is in it.

    The comma before the inserted block is the whole hazard, and the first
    draft decided it by looking at the last character — a tuple ending
    `"e", "l"` to cover `true` and `null`, which is a guess at JSON's grammar
    in the one place a wrong answer yields a file the editor silently refuses
    to load. It asks whether what is there parses to an empty object instead.
    """
    for prior in (
        "{}\n",
        '{\n  "a": 1\n}\n',
        '{\n  "a": true\n}\n',
        '{\n  "a": null\n}\n',
        "{\n  // only a comment\n}\n",
        '{\n  "a": [1, 2]\n}\n',
        '{\n  "a": {"b": 1}\n}\n',
        # A key AND a comment after it. The seven shapes above contained the
        # one that triggers the misclassification (`// only a comment`) and
        # none where it has a consequence: with no prior key, a spurious comma
        # has nothing to fail to separate. These are that population.
        '{\n  "editor.formatOnSave": true\n  // keep this on\n}\n',
        '{\n  "a": 1\n  // one\n  // two\n}\n',
        # Legal JSONC, and this file's own header tells the reader so.
        '{\n  "a": 1,\n}\n',
        '{\n  "a": {\n    "b": 1\n  }\n}\n',
    ):
        result = gen.splice(gen.ensure_region(prior), gen.region())
        parsed = json.loads(gen.strip_comments(result))
        assert "githubIssues.queries" in parsed, prior
        assert "githubPullRequests.queries" in parsed, prior


def test_the_file_this_generator_writes_is_one_it_can_read_back() -> None:
    """`HEADER` ends in a comment, which is the shape that broke `ensure_region`.

    The probe was `head + "}"`, gluing the brace onto the last line; when that
    line is a `//` comment `strip_comments` blanks the brace with it, the parse
    raises, and the "hand-edit mid-flight" fallback adds a comma to a file that
    is empty. So every fresh tree carried a stray comma inside the final
    sentence of its own header — in the file whose entire audience is somebody
    opening the repository for the first time.

    Asserting the file parses is not enough to catch it: a comma inside a
    comment is invisible to the parser, which is exactly why it survived. The
    site has to be named.
    """
    fresh = gen.ensure_region(gen.HEADER + "}\n")
    assert gen.BEGIN in fresh
    for line in fresh.splitlines():
        if line.lstrip().startswith("//") and "drifted apart" in line:
            assert not line.rstrip().endswith(","), "comma written into the header's prose"
            break
    else:  # pragma: no cover - the header changed shape
        raise AssertionError("HEADER no longer ends in the sentence this pins")
    assert json.loads(gen.strip_comments(gen.splice(fresh, gen.region()))) != {}


def test_adding_the_region_twice_adds_it_once() -> None:
    """`ensure_region` is a no-op on a file that already has one."""
    once = gen.ensure_region('{\n  "a": 1\n}\n')
    assert gen.ensure_region(once) == once
    assert once.count(gen.BEGIN) == 1


def test_a_file_that_is_not_an_object_is_refused() -> None:
    """No closing brace is a refusal, not a rewrite of somebody's file."""
    with pytest.raises(SystemExit):
        gen.ensure_region("this is not settings at all\n")
