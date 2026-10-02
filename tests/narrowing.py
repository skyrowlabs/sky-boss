"""Assert a value is present, and say so when it is not.

Every use of this is a test that already assumed something is not None and
proved it by subscripting or by `in`. That works — it fails when the assumption
is wrong — but it fails as `TypeError: 'NoneType' object is not subscriptable`
or `argument of type 'NoneType' is not iterable`, which names neither the value
nor what was expected of it. The assumption was also invisible to a reader and
to a type checker: the suite carried about a hundred of them and the checker had
been pointed at the wrong package, so nothing said so.

This is not a cast. It asserts, in the test, at the point the assumption is
made, and the message is the sentence the old failure did not have.
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def present(value: T | None, what: str = "value") -> T:
    """`value`, having asserted it is not None."""
    assert value is not None, f"expected {what}, got None"
    return value


def group(parent, name: str):
    """The named subgroup of a Click group, asserted to be a group.

    `Group.commands` is a `MutableMapping[str, Command]`, so `cli.commands["tools"]`
    is a `Command` and reaching `.commands` on it is a claim the mapping does not
    carry. Every use here is a test that already knows `tools` is a group; this
    says so, and names it when a refactor makes it false.
    """
    import click

    command = parent.commands[name]
    assert isinstance(command, click.Group), f"{name} is not a group, it is a {type(command).__name__}"
    return command
