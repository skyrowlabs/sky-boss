#!/usr/bin/env python3
"""Read a YAML file as code, with its comments blanked.

Every check that greps a workflow matches against text, and **a comment is
text**. Two shipped gates read comments as code and both passed while the thing
they guard was absent:

* `check_workflow_drift.py` required `actions/setup-python` in any job that
  stands the stack up. A job with no such step, carrying
  `# TODO: we should add actions/setup-python here one day`, was green. The
  string most likely to appear in a job that has **not** done the thing is a
  comment saying it should — so the false pass is perfectly correlated with the
  defect, which is the worst arrangement available.
* `tests/test_ci_draft_gate.py` asserted `"ready_for_review" in ci.yml`. Deleting
  the trigger and leaving `# note: ready_for_review used to be here` kept all
  five of its tests green. That gate exists specifically to catch a deleted
  trigger.

jam.sense supplied the general form, from a naive grep that hit their worktree
command twice — on an error message and a docstring — while missing
the call it was looking for: **a detector validated by "it found the file I
expected" is not validated; it has to find the site.**

This repository already held the rule twice and had not joined it up.
`check_output_discipline.py` masks prose before scanning and `check_doc_links.py`
blanks fences and comments before matching — so the two checkers that scan for a
*mistake* were careful, and the two that scan for a *requirement* were not. That
asymmetry is not a coincidence: a false positive gets reported and fixed, and a
false negative is silence.

One home rather than a copy per consumer, for the reason `scripts/allowlist.py`
exists: four copies of one parser is how a shared format drifts, since each copy
is correct about its own caller's input and nothing compares them.
"""

from __future__ import annotations

from pathlib import Path


def uncommented(text: str) -> str:
    """`text` with comments removed **as a reader sees them**, one line per line.

    Not a YAML-preserving transformation, and the difference is deliberate. In a
    block scalar — `run: |` — YAML treats `#` as literal content, so a shell
    comment inside a script is *data* to a parser and *prose* to a person. This
    strips it, which changes what `yaml.safe_load` returns for several of the
    workflows here. No count: this file ships at `core` and higher tiers add
    workflows, so a number written here is true in one tier and false in the
    others, stated by a file all of them carry.

    That is the behaviour both consumers need. A job carrying

        - run: |
            # docker compose up -d   <- commented out
            ./run-tests.sh

    must not be enrolled by `check_workflow_drift.py` on the strength of a line
    that does not run. Enrollment asks what a job *runs*, and a parser-faithful
    mask would answer with what it *contains*.

    Worth stating because the obvious validation is a trap: comparing
    `safe_load(raw)` to `safe_load(uncommented(raw))` is ground truth against
    the wrong ground. It fails on this template today, correctly, and "fixing"
    it would break the enrollment predicate. A future consumer that genuinely
    needs YAML fidelity wants a parser, not this.

    Blanked rather than deleted so line numbers keep meaning something, and a
    `#` inside quotes is left alone so `run: echo "# heading"` stays code.

    A `#` only opens a comment **at the start of a line or after whitespace**,
    which is YAML's actual rule and not a refinement of it. Without that test
    this over-masks: `run: curl https://host/page#frag` became
    `run: curl https://host/page`, and `sed -i s#a#b#g` loses its delimiters.
    Over-masking breaks the gate in the opposite direction — a silent pass
    becomes a noisy false failure — and a shared masker that eats real content
    is worse than the bug it fixes, because every future consumer inherits it.
    jam.sense named that direction before it had cost anything here; their
    labels are short words that appear legitimately inside strings and dict
    values, so they would have met it first.

    Deliberately not a YAML parser. This runs on any host with no dependency,
    it is checking text that a parser would have already normalised past, and a
    mis-strip fails loudly — the required step goes missing — rather than
    passing wrongly, which is the direction that matters here.
    """
    out = []
    for line in text.splitlines():
        quote = ""
        cut = None
        for i, char in enumerate(line):
            if quote:
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "#" and (i == 0 or line[i - 1] in " \t"):
                cut = i
                break
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def read_uncommented(path: Path) -> str:
    """A workflow's code, with its comments gone."""
    return uncommented(path.read_text(encoding="utf-8"))
