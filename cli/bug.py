"""``dev bug`` — capture a bug you found on the way, without widening your scope.

A bug you hit that is **not** what you were asked to work on has three bad
homes: your current change (which now does two things), a sentence in a session
that is about to end, and your memory. This gives it a fourth.

All four sections are **required**. A capture without a reproduction is a rumour;
one without acceptance criteria cannot be closed by anyone but its author; one
without a scope grows into a refactor. The refusal is the feature.

The command itself is built from ``scripts/lanes.py`` — the label, the sections
and the refusal all come from the registry, so this module is the prose and the
binding and nothing else. See ``cli/_capture.py`` for the mechanism, and
``dev task`` for the intake that takes work which is not a defect.
"""

from scripts.lanes import LANES_BY_KEY

from ._capture import capture_command

bug = capture_command(
    LANES_BY_KEY["bug"],
    help_text="""File a bug found outside the scope of what you were doing.

    \b
    Files a GitHub issue labelled `agent-bug`. Every section is required, and
    `--reproduce` is the one that separates a bug report from a rumour: if
    there is no failure to reproduce, this is not the intake — see
    `dev task`.
    """,
    epilog=(
        "\b\n"
        "Example:\n"
        '  dev bug "check docs is green over an empty scan" \\\n'
        '      --finding "scripts/check_doc_links.py:88 — skips by name, so a parent '
        'directory sharing one empties the scan" \\\n'
        '      --reproduce "mkdir -p node_modules/x && cp -r . node_modules/x && '
        'cd node_modules/x && ./dev check docs" \\\n'
        '      --scope "the scan filter only; the fix flag is out" \\\n'
        '      --acceptance "the run reports the real document count; dev test unit green"'
    ),
)
