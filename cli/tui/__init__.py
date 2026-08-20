"""tb tui — a persistent surface over the Result envelope.

Not a second CLI. Everything here dispatches strings through the real Click
tree and renders what `cli/output.py` produced, which is what keeps the surface
from drifting away from the command line it fronts.

See docs/features/tui.md.
"""

import rich_click as click


@click.command()
def tui() -> None:
    """Open the interactive surface — input below, transcript above.

    The second honest exception to the mood taxonomy, alongside `tb mcp serve`.
    Neither is a command in a mood: they are surfaces over the same envelope
    every command returns, and `tb run` remains the only door that writes.
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
