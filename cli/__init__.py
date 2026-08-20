"""tackle-box CLI — homebase operator tool for workstation.

This package implements the CLI as a collection of command group modules.

Usage: tb [command] [options]
"""

import subprocess
import sys

# Check for required dependencies before importing them.
try:
    # rich_click re-exports the whole click API, so decorators are unchanged; it
    # only swaps the Command/Group classes so --help renders through rich.
    import rich_click as click
    from rich_click import RichHelpConfiguration, rich_config
except ImportError:
    print("Error: missing required Python dependencies", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with:", file=sys.stderr)
    print("  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)

from cli.helpers import PROJECT_ROOT, run_command  # noqa: E402
from cli.theme import (  # noqa: E402
    CLI_BRAND,
    CLI_DANGER,
    CLI_FAINT,
    CLI_LABEL,
    CLI_OK,
)

# --help styled from the same palette as everything else (cli/theme.py). These
# values used to be hexes written out by hand, which agreed with the output
# theme only because both were typed the same afternoon. They take the CLI
# derivations rather than the raw tokens: --help prints into a terminal whose
# background nobody here knows. rich-click 1.9 replaced
# the old module-global STYLE_* knobs with this dataclass; it is attached to the
# root group and inherited by every subcommand through context.
HELP_CONFIG = RichHelpConfiguration(
    style_option=f"bold {CLI_BRAND}",
    style_argument=f"bold {CLI_BRAND}",
    style_command=f"bold {CLI_BRAND}",
    style_switch=f"bold {CLI_OK}",
    style_usage=f"bold {CLI_LABEL}",
    style_usage_command="bold",
    style_helptext="",
    style_option_help=CLI_LABEL,
    style_command_help=CLI_LABEL,
    style_header_text="bold",
    style_option_default=CLI_FAINT,
    style_options_panel_border="dim",
    style_commands_panel_border="dim",
    style_errors_panel_border=CLI_DANGER,
    # "BLANK" is rich-click's own borderless box — help then matches the
    # borderless status-list output instead of sitting in rounded panels.
    style_options_table_box="BLANK",
    style_commands_table_box="BLANK",
    style_options_panel_box="BLANK",
    style_commands_panel_box="BLANK",
    max_width=88,
)


def get_version() -> str:
    """Version from git describe, falling back to 'dev'."""
    try:
        result = run_command(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=PROJECT_ROOT,
            timeout=1,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "dev"


@click.group()
@rich_config(help_config=HELP_CONFIG)
@click.version_option(version=get_version(), prog_name="tackle-box")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON on stdout.")
@click.pass_context
def cli(ctx: click.Context, as_json: bool) -> None:
    """tackle-box — homebase operator CLI for workstation.

    Deterministic scripts and agentic automations across the home network.
    """
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json


# ============================================================================
# Register command groups and top-level commands
# ============================================================================

from cli.jobs import auto as auto_group  # noqa: E402
from cli.run import run as run_cmd  # noqa: E402
from cli.tui import tui as tui_cmd  # noqa: E402

cli.add_command(run_cmd)
cli.add_command(auto_group)

# A surface, not a mood. `tb mcp serve` will land beside it. Both render the
# same envelope every command returns rather than adding a verb, which is why
# neither belongs in run/auto/info/check.
cli.add_command(tui_cmd)

