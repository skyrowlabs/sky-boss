"""Tests for tb assets update — drift between a record and reality.

This command updates tb's record of a machine, never the machine.
"""

import pytest
import yaml

from cli.assets import compare_record, flatten_record, load_inventory, write_seed


RECORDED = {
    "hostname": "workstation",
    "kernel": "7.1.8",
    "login_shell": "/bin/fish",
    "disks": [
        {"name": "nvme0n1", "size_bytes": 400, "model": "Samsung"},
        {"name": "zram0", "size_bytes": 100, "model": None},
    ],
    "runtimes": {"python": "3.14.7", "node": "22.23.2"},
}


# ---------------------------------------------------------------- flatten


def test_flatten_names_the_specific_runtime():
    """A Python bump should name Python, not dump every interpreter as one blob."""
    flat = flatten_record(RECORDED)
    assert flat["runtimes.python"] == "3.14.7"
    assert flat["runtimes.node"] == "22.23.2"
    assert "runtimes" not in flat


def test_flatten_list_order_does_not_matter():
    """Comparing lists positionally would make a reordering look like a change."""
    reordered = dict(RECORDED, disks=list(reversed(RECORDED["disks"])))
    assert flatten_record(RECORDED)["disks"] == flatten_record(reordered)["disks"]


def test_flatten_empty_list_is_none():
    assert flatten_record({"gpus": []})["gpus"] is None


# ---------------------------------------------------------------- compare


def test_identical_records_have_no_drift():
    assert compare_record(RECORDED, RECORDED) == []


def test_changed_field_is_drift():
    current = dict(RECORDED, kernel="7.2.0")
    drift = compare_record(RECORDED, current)
    assert drift == [{"field": "kernel", "recorded": "7.1.8", "current": "7.2.0"}]


def test_nested_runtime_change_is_named_precisely():
    current = dict(RECORDED, runtimes={"python": "3.15.0", "node": "22.23.2"})
    drift = compare_record(RECORDED, current)
    assert [d["field"] for d in drift] == ["runtimes.python"]


def test_disappearing_field_is_drift_too():
    """A runtime that vanished matters as much as one that changed."""
    current = dict(RECORDED, runtimes={"python": "3.14.7"})
    drift = compare_record(RECORDED, current)
    assert drift == [{"field": "runtimes.node", "recorded": "22.23.2", "current": None}]


def test_reordered_disks_are_not_drift():
    current = dict(RECORDED, disks=list(reversed(RECORDED["disks"])))
    assert compare_record(RECORDED, current) == []


def test_section_filter_scopes_the_comparison():
    """A field whose source section was not collected must be skipped.

    Otherwise --section would report everything it did not look at as drift
    against nothing.
    """
    current = dict(RECORDED, kernel="7.2.0", login_shell="/bin/bash")
    assert [d["field"] for d in compare_record(RECORDED, current, {"os"})] == ["kernel"]
    assert [d["field"] for d in compare_record(RECORDED, current, {"shell"})] == ["login_shell"]
    assert len(compare_record(RECORDED, current, None)) == 2


# ---------------------------------------------------------------- load


def test_load_inventory_returns_none_for_unrecorded_host(tmp_path):
    assert load_inventory("nosuchhost", directory=tmp_path) is None


def test_load_inventory_reads_only_the_derived_block(tmp_path):
    """Declared fields are the human's; the comparison must not see them."""
    write_seed(RECORDED, directory=tmp_path)
    path = tmp_path / "workstation.yaml"
    parsed = yaml.safe_load(path.read_text())
    assert "declared" in parsed

    loaded = load_inventory("workstation", directory=tmp_path)
    assert loaded["kernel"] == "7.1.8"
    assert "role" not in loaded


def test_seed_then_compare_is_clean(tmp_path):
    """A record written from a state must show no drift against that state."""
    write_seed(RECORDED, directory=tmp_path)
    loaded = load_inventory("workstation", directory=tmp_path)
    assert compare_record(loaded, RECORDED) == []


# ---------------------------------------------------------------- apply


from cli.assets import rewrite_derived  # noqa: E402


def test_apply_leaves_declared_and_comments_byte_identical(tmp_path):
    """The declared block and every comment are the operator's.

    A YAML round-trip would silently discard them — including notes written
    beside a field, which are the maintenance log this repo keeps.
    """
    write_seed(RECORDED, directory=tmp_path)
    path = tmp_path / "workstation.yaml"

    # the operator fills in declared fields and leaves a note
    text = path.read_text().replace(
        "  role:           # what this machine is for",
        "  role: gpu prototype   # moved from the closet 2026-07-02, runs hot",
    )
    path.write_text(text)
    declared_before = text[text.index("declared:"):]

    rewrite_derived(path, dict(RECORDED, kernel="7.2.0"))

    after = path.read_text()
    assert after[after.index("declared:"):] == declared_before
    assert "moved from the closet 2026-07-02, runs hot" in after
    assert after.startswith("# tackle-box machine record")
    assert yaml.safe_load(after)["derived"]["kernel"] == "7.2.0"


def test_apply_is_idempotent(tmp_path):
    write_seed(RECORDED, directory=tmp_path)
    path = tmp_path / "workstation.yaml"
    rewrite_derived(path, RECORDED)
    once = path.read_text()
    rewrite_derived(path, RECORDED)
    assert path.read_text() == once


def test_rewrite_refuses_a_file_with_no_derived_block(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("declared:\n  role: x\n")
    with pytest.raises(ValueError):
        rewrite_derived(path, RECORDED)
