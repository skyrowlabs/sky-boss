"""tb tui — a persistent surface over the Result envelope.

Not a second CLI. Everything here dispatches strings through the real Click
tree and renders what `cli/output.py` produced, which is what keeps the surface
from drifting away from the command line it fronts.

See `cli/tui/app.py` for the design and the surprises.
"""

import rich_click as click


@click.command()
def tui() -> None:
    """Open the interactive surface — input on top, newest result under it.

    Not a second CLI: it dispatches strings through the real Click tree and
    renders what `cli/output.py` produced, so `tb run` remains the only command
    that acts even with the surface in front of it.
    """
    try:
        from cli.tui.app import run
    except ImportError:
        raise click.ClickException(
            "the interactive surface needs 'textual'\n\n"
            "Install with:\n"
            "  .venv/bin/pip install -r requirements.txt"
        ) from None
    run()
