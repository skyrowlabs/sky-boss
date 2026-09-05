#!/usr/bin/env python3
"""One reader for every `key: reason` allowlist in this repository.

There were four copies of this function. They agreed on the format and drifted
on the parsing, which is exactly how a shared format fails: each copy is correct
about the keys its own caller happens to use, and nothing compares them.

`check_workflow_drift.py` paid for it. Its keys are `<workflow>.yml:<job-id>` —
they contain a colon — and its copy split each line on the *first* colon, so
`ci.yml:integration: reason` parsed to the key `ci.yml` and matched nothing the
checker ever asked about. The documented escape hatch could not exempt a single
job, in any scaffold, ever. A fresh tree could not show it: no enrolled jobs, an
empty allowlist, green. It waits for the first person with a real divergence to
record, who finds the check will not go quiet and deletes the check.

## Two rules, and they are the whole module

**A reason is not optional.** An intended divergence with a reason is a decision
record somebody can re-evaluate; one without is indistinguishable from a line
somebody half-typed, and it stays forever. An entry with no reason is dropped
rather than honoured — silently exempting something on the strength of a
half-typed line is the failure the allowlist exists to prevent.

**An exemption is checked against the thing it exempts.** A reason makes an
entry a decision; nothing keeps the decision *true*. `stale()` is where each
caller says what "still needed" means for its own domain — that part cannot be
shared, because a file that now passes and a job that no longer diverges are
different questions. What is shared is that the question gets asked at all, and
the shape of the answer.

Both directions matter and they fail differently. An entry whose target was
fixed has outlived its reason. An entry whose target left the tree is worse: the
name can come back for something else and arrive **pre-exempted**, which is an
exemption nobody chose.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

#: `key: reason`, splitting on the first colon **followed by whitespace**.
#: A key may itself contain colons (`ci.yml:integration`) and a reason may
#: contain several, so neither `partition(":")` nor `rsplit` is correct.
_ENTRY = re.compile(r"^(.*?):\s+(.*)$")


def read(path: Path) -> Dict[str, str]:
    """Every `key: reason` in `path`. Missing file, comments and blanks: skipped."""
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENTRY.match(line)
        if not match:
            # A bare key with no reason. Dropped, not honoured — see the
            # module docstring: an exemption with nothing behind it should
            # fail loudly at the check rather than quietly at the allowlist.
            continue
        out[match.group(1).strip()] = match.group(2).strip().strip("\"'")
    return out


def stale(entries: Dict[str, str], still_needed: Callable[[str], Optional[str]]) -> List[str]:
    """Entries that no longer need to exist, as ready-to-print findings.

    `still_needed(key)` returns `None` when the entry is doing its job, or a
    short phrase saying why it is not — "there is no such file", "it passes the
    check now". The phrase is the caller's, because only the caller knows what
    the entry was exempting.
    """
    return [f"{key}: allowlisted, but {why}" for key in sorted(entries) if (why := still_needed(key)) is not None]


#: The sentence every consumer prints when it reports a stale entry. One copy,
#: because the instruction is the part a reader acts on and three wordings of it
#: would be three different instructions.
STALE_ADVICE = (
    "A stale entry is deleted, not re-justified: what it recorded is gone, so it "
    "now exempts something nobody decided to exempt."
)
