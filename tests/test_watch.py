"""Tests for watched conditions.

The one that matters is the refusal. A watch may name only a read verb, and
that is not merely a safety preference: watches refresh concurrently with
whatever is being typed, and that is only safe because a read verb cannot take
a lane lock or mutate state. If the refusal ever stops holding, the concurrency
stops being safe with it.
"""

import pytest
import yaml

from cli.watch import DEFAULT_EVERY, WatchError, load_watches, parse_every, parse_watch


def _write(tmp_path, name, data):
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


@pytest.mark.parametrize("command", ["run doctor", "tb run doctor", "auto list", "doctor"])
def test_a_watch_may_not_name_anything_but_a_read_verb(tmp_path, command):
    path = _write(tmp_path, "bad", {"command": command})
    with pytest.raises(WatchError) as exc:
        parse_watch(yaml.safe_load(path.read_text()), path)
    assert "bad.yaml" in str(exc.value)


@pytest.mark.parametrize("command", ["check drift", "info assets", "tb check tools"])
def test_the_read_verbs_are_accepted(tmp_path, command):
    path = _write(tmp_path, "ok", {"command": command})
    watch = parse_watch(yaml.safe_load(path.read_text()), path)
    # The optional leading `tb` is dropped, so the stored command is canonical.
    assert not watch.command.startswith("tb ")


def test_a_refused_watch_does_not_hide_the_others(tmp_path):
    _write(tmp_path, "good", {"command": "check drift"})
    _write(tmp_path, "bad", {"command": "run doctor"})
    watches, problems = load_watches(tmp_path)
    assert set(watches) == {"good"}
    assert len(problems) == 1 and "bad.yaml" in problems[0]


def test_a_template_file_is_not_a_watch(tmp_path):
    _write(tmp_path, "_template", {"command": "check drift"})
    watches, problems = load_watches(tmp_path)
    assert not watches and not problems


@pytest.mark.parametrize(
    "value,seconds", [("30s", 30), ("15m", 900), ("1h", 3600), (None, DEFAULT_EVERY), (45, 45)]
)
def test_interval_parsing(value, seconds):
    assert parse_every(value, "x.yaml") == seconds


def test_a_nonsense_interval_is_refused_rather_than_defaulted():
    # Silently falling back would make a watch look like it was on a cadence
    # the file plainly does not say.
    with pytest.raises(WatchError):
        parse_every("every so often", "x.yaml")


def test_hosts_scopes_a_watch_without_a_second_file(tmp_path):
    path = _write(tmp_path, "gpu", {"command": "check drift", "hosts": ["host-2"]})
    watch = parse_watch(yaml.safe_load(path.read_text()), path)
    assert watch.applies_to("host-2")
    assert not watch.applies_to("workstation")
    # No hosts means everywhere — that is how one repo serves several machines.
    everywhere = parse_watch({"command": "check drift"}, path)
    assert everywhere.applies_to("workstation") and everywhere.applies_to("laptop")


def test_an_absent_home_is_empty_rather_than_an_error():
    """A fresh clone has no ~/.tackle-box. Every loader has to survive that:
    the surface asks for watches on its first tick, before you have written
    any, and a raise there would take the whole thing down on first run."""
    watches, problems = load_watches()
    assert watches == {} and problems == []


# ------------------------------------------------------ change detection
#
# The surface re-reads definitions while it is open, guarded by `signature` so
# the parse does not run on every tick. See Round 3 of the tui feature doc.


def _write_watch(directory, name, command="check tools", every="30s"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.yaml").write_text(f"command: {command}\nevery: {every}\n")


def test_an_absent_directory_has_the_empty_signature(tmp_path):
    """The surface asks on its first tick, before any watches exist."""
    from cli.watch import signature

    assert signature(tmp_path / "nothing-here") == ()


def test_the_signature_is_stable_while_nothing_changes(tmp_path):
    from cli.watch import signature

    _write_watch(tmp_path, "tools")
    assert signature(tmp_path) == signature(tmp_path)


def test_adding_a_watch_changes_the_signature(tmp_path):
    from cli.watch import signature

    _write_watch(tmp_path, "tools")
    before = signature(tmp_path)
    _write_watch(tmp_path, "drift", command="check drift")
    assert signature(tmp_path) != before


def test_removing_a_watch_changes_the_signature(tmp_path):
    from cli.watch import signature

    _write_watch(tmp_path, "tools")
    _write_watch(tmp_path, "drift", command="check drift")
    before = signature(tmp_path)
    (tmp_path / "drift.yaml").unlink()
    assert signature(tmp_path) != before


def test_editing_a_watch_in_place_changes_the_signature(tmp_path):
    """The case a directory mtime alone would miss, and the common one — a
    definition edited in place would otherwise keep showing the old command."""
    from cli.watch import signature

    _write_watch(tmp_path, "tools", every="30s")
    before = signature(tmp_path)
    _write_watch(tmp_path, "tools", command="check drift", every="1h")
    assert signature(tmp_path) != before


def test_underscored_files_are_ignored_by_the_signature_too(tmp_path):
    """`load_watches` skips them, so a template being edited must not look like
    a change worth re-parsing for."""
    from cli.watch import signature

    _write_watch(tmp_path, "tools")
    before = signature(tmp_path)
    (tmp_path / "_template.yaml").write_text("command: check tools\n")
    assert signature(tmp_path) == before
