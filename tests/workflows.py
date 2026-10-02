"""A workflow split into its jobs, with comments blanked.

One home rather than a copy per consumer, for the reason `scripts/allowlist.py`
and `scripts/yaml_text.py` exist: each copy of a parser is correct about its own
caller's input and nothing compares them.

Scoped deliberately narrowly — this is the split *plus* the mask, which is the
pair a check needs when it asks what a job **runs**. Several suites here match a
job header for other purposes and are left alone; a header regex is not a parser
and consolidating it would be a different change.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.yaml_text import read_uncommented  # noqa: E402

__all__ = ["jobs"]

#: A job header: two spaces, an identifier, a colon, nothing else on the line.
_JOB = re.compile(r"^  (?P<id>[A-Za-z_][A-Za-z0-9_-]*):\s*$", re.MULTILINE)


def jobs(path: Path) -> dict:
    """`{job id: the job's text}`, split on the job headers, comments blanked.

    Offsets within a returned body are meaningful and are the point: *earlier in
    the job's text* is the same thing as *an earlier step*, and a later job is a
    different runner with a different filesystem.
    """
    text = read_uncommented(path)
    starts = [(m.group("id"), m.start()) for m in _JOB.finditer(text)]
    bounds = [
        (name, start, starts[i + 1][1] if i + 1 < len(starts) else len(text)) for i, (name, start) in enumerate(starts)
    ]
    return {name: text[start:end] for name, start, end in bounds}
