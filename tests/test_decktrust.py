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


def test_a_write_that_lands_mid_trust_is_kept(tmp_path, monkeypatch):
    path = config(tmp_path, {"theme": "dark"})
    real = decktrust.keep_copy

    def another_tab_writes(*args):
        kept = real(*args)
        path.write_text(json.dumps({"theme": "dark", "numStartups": 7}))
        return kept

    monkeypatch.setattr(decktrust, "keep_copy", another_tab_writes)
    decktrust.trust(str(tmp_path), path, tmp_path / "backups")
    data = json.loads(path.read_text())
    assert data["numStartups"] == 7 and data["projects"][str(tmp_path.resolve())]["hasTrustDialogAccepted"] is True


def test_a_config_that_never_settles_is_left_alone_and_refused(tmp_path, monkeypatch):
    path = config(tmp_path, {})
    writes = iter(range(100))
    real = decktrust._read

    def always_moving(p):
        text = real(p)
        p.write_text(json.dumps({"n": next(writes)}))
        return text

    monkeypatch.setattr(decktrust, "_read", always_moving)
    with pytest.raises(OSError):
        decktrust.trust(str(tmp_path), path, tmp_path / "backups")
    assert "projects" not in json.loads(path.read_text())
    assert not list(tmp_path.glob(".claude.json.*.sb"))
