"""Enumerate, and refuse to enumerate nothing.

Every check in this suite that scans the tree is a **negative** assertion — no
test file lacks a marker, no source outside the resolver names the state root,
no documented command is missing. A negative over an empty set is a tautology,
and nothing in a pass distinguishes *the thing did not happen* from *nobody
looked*. That is the `filesAnalyzed` lesson this repository states for pyright
and for its lint gates.

## Why a wrapper rather than a companion test

The convention was a companion — `test_the_walk_found_commands` beside the walk.
It works and it is omissible, and two shipped suites here were found scanning
with no companion at all: `test_marker_coverage` passed 2/2 and
`test_state_paths` 5/5 with their enumerations forced empty. proto.pilot ran the
same sweep and found **seven** unguarded sites in their tree, including one
written the day before.

Seven is what forgetting looks like, so the guard moved to where it cannot be
forgotten without also deleting the loop. Theirs, and the argument is better than
the helper: a convention you must remember to apply is a registry with no
enforcement, which is the thing Rule 2 of this repository exists to prevent.

## Why `least`

A filter tested against one item is unobservable: with a single candidate,
"everything" and "the one match" are the same set, so a check that is supposed
to *select* passes whether it selects or not. That was already here as a
hand-written `len(COMMANDS) >= 5`; `least` is that threshold with a name and a
reason attached, so the next scan gets it without anybody rediscovering why.

Raise it above 1 wherever the scan feeds a filter, and say why at the call site.
"""

from __future__ import annotations

from typing import Sized, TypeVar

#: Bound to `Sized`, and returned unchanged, so a scan keeps the type it had. A
#: mapping of `path → where it was found` must not come back as a list of keys
#: merely to be counted, and a caller's annotation must stay true.
#:
#: The first version accepted any iterable and materialised it, which reads as
#: convenience and is not: a generator that must be consumed to be measured is
#: a scan the caller cannot iterate twice, and pyright caught the fallout —
#: `invocations() -> dict` returning `Collection`. Requiring something sized is
#: the smaller contract and the honest one.
#:
#: **So wrap a generator at the call site**, and expect to: a scaffold's own
#: scans pass a list or a dict, and that is a survey of one tree. proto.pilot
#: adopted this and eight of their fourteen call sites were genexps or a bare
#: `rglob`, every one of which raises `TypeError: object of type 'generator'
#: has no len()`. Loud, and at call time, which is the right kind of breakage —
#: but "nobody passes a generator" was a claim about the tree that ships the
#: helper, and a template helper's callers are mostly in trees it cannot see.
#:
#: `sorted(...)` is the wrapper to reach for rather than `list(...)`. It costs
#: the same and it fixes a second thing: `Path.rglob` yields in filesystem
#: order, so several of those scans were iterating nondeterministically and the
#: `len()` error was the first thing to say so.
C = TypeVar("C", bound=Sized)


def scanned(items: C, what: str, least: int = 1) -> C:
    """`items`, refused if the scan is too small to prove anything."""
    assert len(items) >= least, (
        f"found {len(items)} {what}, expected at least {least} — the scan matched too little "
        f"to assert anything. Every check over this set is a negative, so an empty or "
        f"near-empty scan passes them all while looking at nothing."
    )
    return items
