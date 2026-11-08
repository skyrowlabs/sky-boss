"""Workspace trust for a folder the deck opens an agent in."""

import json

import pytest

from skyboss import deck as deck_
from skyboss import decktrust

pytestmark = pytest.mark.unit


def config(tmp_path, data):
    path = tmp_path / ".claude.json"
    path.write_text(json.dumps(data))
    return path


def test_an_untrusted_folder_is_trusted_and_every_other_key_survives(tmp_path):
    path = config(tmp_path, {"theme": "dark", "projects": {"/other": {"hasTrustDialogAccepted": False, "x": 1}}})
    said = decktrust.trust(str(tmp_path), path, tmp_path / "backups")
    data = json.loads(path.read_text())
    entry = data["projects"][str(tmp_path.resolve())]
    assert "trusted" in said and entry["hasTrustDialogAccepted"] is True and entry["allowedTools"] == []
    assert data["theme"] == "dark" and data["projects"]["/other"] == {"hasTrustDialogAccepted": False, "x": 1}
    assert len(list((tmp_path / "backups").glob("claude.json.*"))) == 1


def test_an_existing_entry_keeps_its_keys_when_trusted(tmp_path):
    folder = str(tmp_path.resolve())
    path = config(tmp_path, {"projects": {folder: {"hasTrustDialogAccepted": False, "lastCost": 3}}})
    decktrust.trust(folder, path, tmp_path / "backups")
    assert json.loads(path.read_text())["projects"][folder] == {"hasTrustDialogAccepted": True, "lastCost": 3}


def test_a_trusted_folder_is_left_alone_and_not_backed_up(tmp_path):
    folder = str(tmp_path.resolve())
    path = config(tmp_path, {"projects": {folder: {"hasTrustDialogAccepted": True}}})
    before = path.read_text()
    assert decktrust.trust(folder, path, tmp_path / "backups") == ""
    assert path.read_text() == before and not (tmp_path / "backups").exists()


def test_a_config_that_is_not_an_object_is_refused(tmp_path):
    path = tmp_path / ".claude.json"
    path.write_text("[]")
    with pytest.raises(ValueError):
        decktrust.trust(str(tmp_path), path)


def test_backups_keep_only_the_newest_few(tmp_path):
    path = config(tmp_path, {})
    for _ in range(decktrust.KEEP + 3):
        decktrust.keep_copy(path, tmp_path / "b")
    assert len(list((tmp_path / "b").glob("claude.json.*"))) == decktrust.KEEP


def test_trust_off_writes_nothing_and_says_the_prompt_is_coming(tmp_path, monkeypatch):
    monkeypatch.setattr(decktrust, "config_file", lambda: config(tmp_path, {}))
    said = deck_.trust_folder(False, str(tmp_path))
    assert said and "will ask to trust" in said[0] and json.loads((tmp_path / ".claude.json").read_text()) == {}


def test_an_unwritable_config_is_a_sentence_not_a_crash(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(decktrust, "trust", refuse)
    assert "could not trust" in deck_.trust_folder(True, str(tmp_path))[0]
