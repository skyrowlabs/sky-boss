"""Type-checking view of `rich_click`, which is click's API with a rich renderer.

**This stub exists because rich_click's own annotations discard the decoration.**
Its `group()` and `command()` are declared as returning
`Union[Group, Callable[..., Union[RichCommand, C]]]` — a union whose first
member is itself callable and returns `Any`. Pyright cannot resolve applying
that as a decorator, so it falls back to the *undecorated* function type and,
with `reportUntypedFunctionDecorator` off, says nothing at all. Every `sb`
command in this tree came out typed as a plain function: `cli.commands` was an
attribute on `FunctionType`, and `CliRunner().invoke(cli, ...)` was passing a
function where a `BaseCommand` was expected. That single cause accounted for
roughly 140 of the errors in this repository.

The claim it makes is the one `skyboss/__init__.py` already states in a comment
and has always relied on: *rich_click re-exports the whole click API, and only
swaps the Command/Group classes so `--help` renders through rich.* Checked
against click's real, correct annotations rather than re-stating them.

**It is a stub, so it binds pyright and nothing else** — the interpreter imports
the real package. If rich_click ever diverges from click on a name this tree
uses, the divergence is invisible here and visible at runtime, which is the
wrong way round; `tests/test_output.py` and the help-rendering tests are what
actually exercise the rich half.

Only the rich-specific names this tree names are declared. Adding one is a line;
inventing a signature for one it does not use is how a stub starts lying.
"""

from collections.abc import Callable
from typing import Any, TypeVar

from click import *  # noqa: F403
# Redundant `X as X` form on purpose: in a stub, a plain `from … import X`
# marks X *private* to the stub and overrides what the star re-exported, so
# `click.Context` stops resolving. The alias is what re-exports.
from click import Argument as Argument
from click import Command as Command
from click import CommandCollection as CommandCollection
from click import Context as Context
from click import Group as Group
from click import Option as Option
from click import Parameter as Parameter

class RichContext(Context): ...
class RichCommand(Command): ...
class RichGroup(Group): ...
class RichCommandCollection(CommandCollection): ...
class RichParameter(Parameter): ...
class RichArgument(Argument): ...
class RichOption(Option): ...
class RichHelpConfiguration:
    def __init__(self, **kwargs: Any) -> None: ...

_F = TypeVar("_F")

# An identity decorator: it attaches configuration to whatever it is given
# and hands the same object back. Typing it as returning `Any` would erase
# the function underneath it, which is the exact failure this stub exists
# to fix — one decorator in the stack is enough to lose the whole thing.
def rich_config(help_config: RichHelpConfiguration | None = ..., **kwargs: Any) -> Callable[[_F], _F]: ...
