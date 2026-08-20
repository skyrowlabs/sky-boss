"""What the surface verbs actually do.

Separate from `verbs.py` so that module can be imported by completion without
dragging in the app, and so the table stays readable as it grows.
"""

from __future__ import annotations

import json

from rich.text import Text

from cli.output import TUI_THEME
from cli.tui.verbs import Verb

MUTED = TUI_THEME.styles["tb.muted"]


def _inspect(app, args: list[str]) -> Text | None:
    """The last envelope, as `--json` would have printed it.

    Never re-runs. That is the entire point — for a `check` a second run is
    merely wasteful, and for `tb run` it is a second execution of the job.
    """
    envelopes = app.last_envelopes
    if not envelopes:
        return Text(
            "nothing captured yet — run a command first (inspect never re-runs one)",
            style=MUTED,
        )
    payload = envelopes[0] if len(envelopes) == 1 else list(envelopes)
    app.expand(
        f"envelope — {app.last_envelope_line}",
        Text(json.dumps(payload, indent=2, default=str)),
    )
    return None


ACTIONS: tuple[Verb, ...] = (
    Verb("inspect", "The last command's envelope, without running it again.", _inspect),
)
