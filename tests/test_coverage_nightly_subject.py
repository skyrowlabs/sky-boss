"""The nightly reads the ratchet's exit 3 as a notice, and every other code as itself."""

from __future__ import annotations

import pytest
import yaml

from scripts.paths import GITHUB_DIR
from scripts.yaml_text import read_uncommented

pytestmark = pytest.mark.unit

NIGHTLY = GITHUB_DIR / "workflows" / "coverage-nightly.yml"


def ratchet_step() -> str:
    jobs = yaml.safe_load(read_uncommented(NIGHTLY))["jobs"]
    runs = [step.get("run", "") for job in jobs.values() for step in job.get("steps", [])]
    found = [run for run in runs if "check_coverage_budget.py" in run]
    assert len(found) == 1, f"{NIGHTLY.name}: want one step running the ratchet, found {len(found)}"
    return found[0]


def test_no_subject_is_a_notice_and_the_rest_keep_their_code() -> None:
    run = ratchet_step()
    assert "|| status=$?" in run and '[ "$status" -eq 3 ]' in run, run
    assert "::notice::" in run and 'exit "$status"' in run, run
