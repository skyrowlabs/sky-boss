"""sky.boss CLI — the homebase operator tool for a primary workstation.

This package implements the CLI as a collection of command group modules.

Usage: sky.boss [command] [options]
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

from cli.helpers import INVOCATION, PROJECT_ROOT, run_command  # noqa: E402
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


def expand_t(args: list[str]) -> list[str]:
    """`-t` as an argv spelling of `tools`, rewritten before parsing.

    Not a Click alias and not a flag with behavior: the rewrite happens in
    argv, once, here — so `sb -t jam-pr-list --refresh 30` *is*
    `sb tools jam-pr-list --refresh 30` and every downstream consumer sees
    the long form. Options follow the tool name, as on every sky.boss command; the
    prefix form (`sb -t --refresh 30 x`) was rejected — it would teach the
    group a forwarded option that belongs to the leaf, and it falls out as an
    ordinary usage error.

    Only the token standing where a command word could: root flags are
    skipped, and the scan stops at the first command word or `--`, so a `-t`
    belonging to someone else's argv is never touched.
    """
    out = list(args)
    for i, token in enumerate(out):
        if token == "--":
            break
        if token == "-t":
            out[i] = "tools"
            break
        if token.startswith("-"):
            continue
        break
    return out


class Root(click.RichGroup):
    """The root group: the `-t` spelling rewritten ahead of Click, and the mark.

    The mark is drawn here rather than written into the help text because it
    is *painted* — per-cell colour, a background of its own — and a help string
    is one styled block. Only the root has it: `sb read --help` is a reference
    page you may be reading for the third time today, and a banner over every
    one of them is a banner nobody sees. See [[header]].
    """

    def main(self, args=None, *pargs, **kwargs):
        if args is None:
            args = sys.argv[1:]
        expanded = expand_t(list(args))
        # Recorded before Click sees it, so `--save` can write down the line
        # the operator typed rather than one rebuilt from parsed options.
        # See `INVOCATION` in cli/helpers.py and [[tools]] round 3.
        INVOCATION[:] = expanded
        return super().main(expanded, *pargs, **kwargs)

    def format_help(self, ctx, formatter):
        from rich.console import Console

        from cli import banner

        # `--json` says a machine is reading, and a machine reading help is
        # already in trouble — but painting a logo into its pipe is sky.boss making
        # it worse. The same reflex as everywhere else: nothing decorative
        # goes out when the envelope was asked for.
        if not (ctx.find_root().obj or {}).get("as_json"):
            console = Console()
            version = get_version()
            if not banner.show(console, version):
                console.print(banner.plain(version))
        super().format_help(ctx, formatter)


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


@click.group(cls=Root)
@rich_config(help_config=HELP_CONFIG)
@click.version_option(version=get_version(), prog_name="sky.boss")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON on stdout.")
@click.pass_context
def cli(ctx: click.Context, as_json: bool) -> None:
    # The title and subtitle that used to sit here are the mark now — drawn by
    # `Root.format_help` above, see [[header]]. What is left is the one line
    # that still earns its place under a logo: what this thing does.
    """Deterministic scripts and agentic automations, one command each."""
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json


# ============================================================================
# Register command groups and top-level commands
# ============================================================================

from cli.canvas import ui as ui_cmd  # noqa: E402

# Aliased on import — `from cli.data import data` would rebind this package's
# `data` attribute from the module to the Command and shadow the module, the
# same gotcha `read` and `tools` dodge below.
from cli.data import data as data_cmd  # noqa: E402
from cli.read import read_ as read_cmd  # noqa: E402
from cli.run import run as run_cmd  # noqa: E402

# `run` acts; `data` reads. That split is what the canvas reads to decide
# whether a window may be given a refresh cadence. See cli/data.py.
cli.add_command(run_cmd)
cli.add_command(data_cmd)

# `read` shows what a tool printed and is a *read*, so a window may pin it.
# `run` remains the only command that acts; carrying output is not what makes
# a command a write. See [[text-reads]].
cli.add_command(read_cmd)

# One verb, two mechanisms: a path is the file cursor, anything else is the
# process stream. Resident by nature, so it takes no cadence. See [[follow]].
from cli.agents import agents as agents_cmd  # noqa: E402
from cli.follow import follow as follow_cmd  # noqa: E402
from cli.mcp import mcp as mcp_cmd  # noqa: E402
from cli.rollcall import roll_call as roll_call_cmd  # noqa: E402
from cli.schedule import schedule as schedule_cmd  # noqa: E402

cli.add_command(follow_cmd)
cli.add_command(roll_call_cmd)
cli.add_command(schedule_cmd)
# The same fold as roll-call over a different population: who is running, rather
# than how each project is. See [[agent-sessions]].
cli.add_command(agents_cmd)
cli.add_command(mcp_cmd)

# A surface, not a verb. It renders the same envelope every command returns
# rather than adding one of its own, which is why `sb run` stays the only door
# that acts even with the canvas in front of it.
cli.add_command(ui_cmd)

# Aliased on import — `from cli.tools import tools` would rebind this package's
# `tools` attribute from the module to the Command and shadow the module.
from cli.tools import PROBLEMS, register, tools as tools_cmd  # noqa: E402

cli.add_command(tools_cmd)

# The operator's own commands, registered onto the tree *after* every builtin,
# so a builtin always wins a name collision. This is the whole of what makes
# the tools work: the palette, `--help` and shell completion all walk the
# real tree, so none of them needed a line of code for tools to appear in them.
#
# Problems are collected rather than printed. Nothing has a Click context yet,
# and stdout must stay clean for `--json`; `sb tools` reports them.
PROBLEMS.extend(register(cli))

