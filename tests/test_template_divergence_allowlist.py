"""The divergence record stays between its rules and holds only what still differs.

The rules are what keep the record itself off an upgrade's standing list: an upgrade
sets aside what sits between a frozen pair, and an entry outside them makes the
record read as a fork of the template's file.

`scripts/seams.py` finds python seams and parses them, so this YAML seam is held here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.allowlist import STALE_ADVICE, read, stale
from scripts.manifest import recorded_hashes
from scripts.paths import PROJECT_ROOT, SCRIPTS_DIR
from scripts.seams import bounds

pytestmark = pytest.mark.unit

RECORD = SCRIPTS_DIR / "template_divergence_allowlist.yaml"


def no_longer_needed(key: str, root: Path, recorded: dict[str, str] | None) -> str | None:
    """Why the entry `key` is stale, or None. A label rides the path, so the path decides."""
    path = key.partition(":")[0]
    live = root / path
    if not live.exists():
        return None if path in (recorded or {}) else "that path is neither in this tree nor recorded"
    if (recorded or {}).get(path) == hashlib.sha256(live.read_bytes()).hexdigest():
        return "the file is byte-for-byte what skeletor wrote"
    return None


def outside_the_rules(lines: list[str]) -> list[str]:
    """Entries above the opening rule or below the closing one."""
    found = bounds(lines)
    opening, closing = found["opening"][0], found["closing"][0]
    outside = lines[: opening - 1] + lines[closing:]
    return [line for line in outside if line.strip() and not line.lstrip().startswith("#")]


def test_the_record_has_one_of_each_rule_in_order() -> None:
    found = bounds(RECORD.read_text(encoding="utf-8").splitlines())
    assert len(found["opening"]) == 1 and len(found["closing"]) == 1, found
    assert found["opening"][0] < found["closing"][0], found


def test_your_entries_are_between_the_rules() -> None:
    strays = outside_the_rules(RECORD.read_text(encoding="utf-8").splitlines())
    assert not strays, f"{RECORD.name}: these sit outside the two rules, so the file reads as a fork: {strays}"


def test_no_entry_has_outlived_its_reason() -> None:
    recorded = recorded_hashes()
    found = stale(read(RECORD), lambda key: no_longer_needed(key, PROJECT_ROOT, recorded))
    assert not found, "\n".join([*found, STALE_ADVICE])


def test_an_entry_is_stale_only_for_a_file_that_stopped_differing_or_never_existed(tmp_path: Path) -> None:
    (tmp_path / "same.md").write_text("as rendered\n", encoding="utf-8")
    (tmp_path / "edited.md").write_text("mine\n", encoding="utf-8")
    (tmp_path / "their-own.md").write_text("never rendered\n", encoding="utf-8")
    rendered = hashlib.sha256(b"as rendered\n").hexdigest()
    recorded = {"same.md": rendered, "edited.md": rendered, "deleted.md": rendered}
    assert no_longer_needed("same.md", tmp_path, recorded)
    assert no_longer_needed("same.md:label", tmp_path, recorded)
    assert no_longer_needed("nowhere.md", tmp_path, recorded)
    assert no_longer_needed("edited.md", tmp_path, recorded) is None
    assert no_longer_needed("edited.md:label", tmp_path, recorded) is None
    assert no_longer_needed("deleted.md", tmp_path, recorded) is None
    assert no_longer_needed("their-own.md", tmp_path, recorded) is None


def test_with_no_manifest_only_a_missing_path_is_stale(tmp_path: Path) -> None:
    (tmp_path / "here.md").write_text("x\n", encoding="utf-8")
    assert no_longer_needed("here.md", tmp_path, None) is None
    assert no_longer_needed("gone.md", tmp_path, None)


def test_an_entry_outside_the_rules_is_named() -> None:
    lines = RECORD.read_text(encoding="utf-8").splitlines()
    assert outside_the_rules(lines) == []
    assert outside_the_rules(["above: a reason", *lines]) == ["above: a reason"]
    assert outside_the_rules([*lines, "below: a reason"]) == ["below: a reason"]
