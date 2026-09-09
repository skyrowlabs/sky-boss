"""``dev task`` — capture small, self-contained work that is not a defect.

The third intake, and the one the other two leave a gap between. ``dev bug``
requires ``--reproduce``, and a task has no failure to reproduce: for "rename
this helper", "add a test for X", "delete the flag nothing reads", you either
write something false in that field or you do not file at all. And nobody writes
a 150-line ``docs/TODO`` plan for twenty minutes of work. So small work went into
a sentence in a session, and the session ended — which is precisely the failure
``dev bug`` exists to prevent, one size down.

**Why a second lane rather than a ``--kind`` flag on the bug intake.** The label
is what gives each queue its own drain: a task drainer takes only ``agent-task``,
a fix drainer takes only ``agent-bug``, and neither can consume the other's lane
by accident. Two subcommands make that split legible from the command line,
which is where it is read. jam.sense's reasoning, and their measured shape.

``--why`` is not decoration. It is what stops a task queue becoming a wish list:
state what is worse today because this has not been done.
"""

from scripts.lanes import LANES_BY_KEY

from ._capture import capture_command

task = capture_command(
    LANES_BY_KEY["task"],
    help_text="""Capture small work that is not a defect, for a task drainer to pick up.

    \b
    Files a GitHub issue labelled `agent-task`. For the twenty-minute change
    that fits neither existing intake — too small for a plan, not a defect, and
    unable to answer `dev bug --reproduce` honestly.
    """,
    epilog=(
        "\b\n"
        "Example:\n"
        '  dev task "delete the ROLLOUT_PHASE_LEGACY flag" \\\n'
        '      --what "config/flags.py: drop the flag and its two readers" \\\n'
        '      --why "it has read false for six releases and every reader still has to be checked" \\\n'
        '      --acceptance "no reference outside CHANGELOG; dev test unit green"'
    ),
)
