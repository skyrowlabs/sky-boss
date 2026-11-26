"""A committed `.skeletor.json` records a finished upgrade.

A held-back upgrade leaves `pending_added` behind and does not move the base, and a
commit of that state reads as current. The badge disagreeing with `skeletor_ref` is
the same signal from the README's side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.manifest import badge_says, badge_value, unfinished_upgrade

pytestmark = pytest.mark.unit


def remedy() -> str:
    tag = badge_says()
    tag = tag if tag and tag != "untagged" else "<the tag you upgraded to>"
    return (
        "An upgrade is unfinished: run the re-run line the held-back run printed. Without it, "
        f"`skeletor-upgrade . --ref {tag} --dry-run` says what is still pending."
    )


def test_the_recorded_upgrade_is_finished() -> None:
    found = unfinished_upgrade()
    assert not found, "\n".join([*found, remedy()])


def write(tmp_path: Path, record: object, badge: str | None = None) -> tuple[Path, Path]:
    manifest, svg = tmp_path / ".skeletor.json", tmp_path / "skeletor-version.svg"
    manifest.write_text(json.dumps(record), encoding="utf-8")
    if badge is not None:
        svg.write_text(f'<svg aria-label="skeletor: {badge}"></svg>\n', encoding="utf-8")
    return manifest, svg


def test_pending_added_is_unfinished(tmp_path: Path) -> None:
    manifest, svg = write(tmp_path, {"skeletor_ref": "v1.2.3", "pending_added": {"a.md": "0" * 64}})
    assert unfinished_upgrade(manifest, svg) == ["pending_added holds 1 file(s) a held-back run added: ['a.md']"]


def test_a_badge_that_disagrees_with_the_ref_is_unfinished(tmp_path: Path) -> None:
    manifest, svg = write(tmp_path, {"skeletor_ref": "v1.2.3"}, badge="v1.3.0")
    assert unfinished_upgrade(manifest, svg) == ["skeletor-version.svg says v1.3.0, and skeletor_ref is v1.2.3"]


def test_a_badge_names_the_tag_a_described_ref_starts_with(tmp_path: Path) -> None:
    for ref, badge in (("v1.2.3", "v1.2.3"), ("v1.2.3-4-gabc1234", "v1.2.3"), ("abc1234", "untagged")):
        assert badge_value(ref) == badge
        assert unfinished_upgrade(*write(tmp_path, {"skeletor_ref": ref}, badge=badge)) == []


def test_no_manifest_and_no_badge_ask_nothing(tmp_path: Path) -> None:
    assert unfinished_upgrade(tmp_path / "absent.json", tmp_path / "absent.svg") == []
    assert unfinished_upgrade(*write(tmp_path, {"skeletor_ref": "v1.2.3"})) == []
