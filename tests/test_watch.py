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
    path = _write(tmp_path, "gpu", {"command": "check drift", "hosts": ["node-01"]})
    watch = parse_watch(yaml.safe_load(path.read_text()), path)
    assert watch.applies_to("node-01")
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
