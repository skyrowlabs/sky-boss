"""The comment masker cuts comments, and nothing else.

`scripts/yaml_text.py` exists because two gates read comments as code and passed
while the thing they guard was absent. This file guards the other direction,
which is the one that bites second: **an over-eager mask turns a silent pass
into a noisy false failure**, and a shared masker that eats real content is
worse than the bug it fixed, because every consumer inherits it.

The first implementation cut at any unquoted `#`. That is not YAML's rule — a
`#` opens a comment only at the start of a line or after whitespace — so
`run: curl https://host/page#frag` became `run: curl https://host/page` and
`sed -i s#a#b#g` lost its delimiters. jam.sense named that direction from their
own tree, where the matched labels are short words that appear legitimately
inside strings and dict values, before it had cost anything here.

Both directions in one table, because a masker is only correct as a pair: every
comment gone, and every `#` that is not one still there.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.yaml_text import uncommented  # noqa: E402

#: `(line, is_a_comment)`. The False rows are the regression set — each one is a
#: shape that a naive "cut at the first #" gets wrong.
CASES = [
    ("- run: foo  # a real comment", True),
    ("      # whole-line comment", True),
    ("#at column zero", True),
    ("- uses: actions/setup-python@v6\t# tab before it", True),
    ("- run: sed -i 's#a#b#g' f", False),  # delimiters, quoted
    ("- run: sed -i s#a#b#g f", False),  # delimiters, bare
    ("- run: curl https://host/page#frag", False),  # URL fragment
    ('- run: echo "# heading"', False),  # inside double quotes
    ("- run: python -c \"x = '#tag'\"", False),  # quote nested in quote
    ('  color: "#fff"', False),  # a value that starts with #
]


@pytest.mark.parametrize("line,is_comment", CASES, ids=[c[0][:34] for c in CASES])
def test_only_comments_are_masked(line: str, is_comment: bool):
    masked = uncommented(line) != line
    assert masked == is_comment, f"{line!r} -> {uncommented(line)!r}"


def test_a_shell_comment_inside_a_run_block_is_stripped():
    """Deliberate, and not what a YAML parser would do — so it needs a test.

    In a `|` block scalar, `#` is literal content: `yaml.safe_load` keeps this
    line and this function removes it. That is the behaviour the enrollment
    predicate depends on — a commented-out command must not enroll a job — and
    it is exactly the kind of intentional divergence somebody later "corrects"
    toward parser fidelity. A documented decision with nothing asserting it is a
    decision that gets reverted by the next careful reader.
    """
    block = "jobs:\n  a:\n    steps:\n      - run: |\n          # docker compose up -d\n          ./go.sh\n"

    assert "docker compose up" not in uncommented(block)
    assert "./go.sh" in uncommented(block)


def test_line_structure_survives():
    """Blanked, not deleted — line numbers have to keep meaning something."""
    text = "a: 1\n# gone\nb: 2\n"

    assert uncommented(text).splitlines() == ["a: 1", "", "b: 2"]
