"""A held release is still a tag with no edition, or its entry goes."""

from __future__ import annotations

import pytest

from scripts.allowlist import STALE_ADVICE, read, stale
from scripts.docs.release_window import tags
from scripts.paths import RELEASES_DIR, SCRIPTS_DIR

pytestmark = pytest.mark.unit

RECORD = SCRIPTS_DIR / "release_freeze_allowlist.yaml"


def no_longer_needed(tag: str, existing: list[str]) -> str | None:
    if tag not in existing:
        return "there is no such tag"
    if (RELEASES_DIR / tag).is_dir():
        return "it has an edition now"
    return None


def test_no_held_release_has_outlived_its_reason() -> None:
    existing = tags()
    found = stale(read(RECORD), lambda tag: no_longer_needed(tag, existing))
    assert not found, "\n".join([*found, STALE_ADVICE])
