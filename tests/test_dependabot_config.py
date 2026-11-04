"""The workflow that merges Dependabot pull requests runs after CI, as the App, on its own code.

Nothing here reads `.github/dependabot.yml`: a tree may own that file (`skeletor-upgrade
--own`), and its cooldown and ignores are checked where skeletor renders them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.paths import GITHUB_DIR  # noqa: E402
from scripts.yaml_text import read_uncommented  # noqa: E402
from tests.scanning import scanned  # noqa: E402

MERGER = GITHUB_DIR / "workflows" / "dependabot-auto-merge.yml"


def test_the_merger_runs_after_ci_passes_and_merges_with_the_app_token():
    text = read_uncommented(MERGER)
    ci_name = re.search(r"^name:\s*(.+?)\s*$", read_uncommented(GITHUB_DIR / "workflows" / "ci.yml"), re.MULTILINE)
    follows = ci_name and re.search(rf"workflows:\s*\[\s*['\"]{re.escape(ci_name.group(1))}['\"]\s*\]", text)
    assert follows, "it must follow the workflow named in ci.yml"
    assert "workflow_run.conclusion == 'success'" in text
    assert re.search(r"GH_TOKEN:\s*\$\{\{\s*steps\.app-token\.outputs\.token", text), "a GITHUB_TOKEN merge runs no CI"


def test_the_merger_never_checks_out_the_pull_requests_code():
    """It runs with write access; the script it loads must be the default branch's."""
    text = read_uncommented(MERGER)
    # A step's own keys sit deeper than the `- ` that starts the next one.
    checkouts = scanned(re.findall(r"- uses: actions/checkout@[^\n]*\n((?:[ ]{8,}[^\n]*\n)*)", text), "checkouts")
    assert not any("ref:" in block for block in checkouts)
    assert (GITHUB_DIR / "scripts" / "dependabot-hold.cjs").exists()
