"""tb info — the descriptive mood.

What is this machine, this network, this house. Reads and reports; never judges
and never writes. The judging lives in `tb check`, and the writing lives behind
`tb run`.

The split matters most where it is least convenient. `tb assets describe --seed`
and `tb assets update --apply` used to write from inside a read verb, which is
exactly how a group loses the property that makes it safe to expose. Both are now
internal tasks reached through `tb run`.
"""

from __future__ import annotations

import rich_click as click

from cli.assets import assets_info


@click.group()
def info() -> None:
    """Describe things. Reads only — never judges, never writes."""


info.add_command(assets_info)
