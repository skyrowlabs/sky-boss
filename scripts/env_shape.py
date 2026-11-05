#!/usr/bin/env python3
"""The names `.env.example` declares, and which of them are secrets.

The one reader of that file's shape. `tests/test_env_example_parity.py` imports
it, and a credentials registry reads a tree through `--json` rather than parsing
the file itself: two parsers of one format each agree with their own caller
and nothing compares them.

A declaration is `NAME=` or `# NAME=` (an optional value, commented out). A line
that is exactly `# secret` marks the declaration directly below it as a
credential. Own line, never trailing: Docker `--env-file` and systemd
`EnvironmentFile` keep an inline comment as part of the value. Directly below,
never a section: a name's status must not change because it moved.

Problems, each a reason to exit 1: a tag with no declaration directly below it,
and a tagged name with a value in the example.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.output import detail, emit, fail, ok  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402

ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
DECLARATION = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=(.*)$")
TAG = re.compile(r"^\s*#\s*secret\s*$")


@dataclass
class Shape:
    names: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def parse(text: str) -> Shape:
    shape = Shape()
    tagged_at = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if TAG.match(line):
            if tagged_at:
                shape.problems.append(f"line {tagged_at}: `# secret` is not directly above a declaration")
            tagged_at = number
            continue
        match = DECLARATION.match(line)
        if match:
            name, value = match.group(1), match.group(2).strip()
            if name not in shape.names:
                shape.names.append(name)
            if tagged_at:
                shape.secrets.append(name)
                if value:
                    shape.problems.append(f"line {number}: {name} is tagged secret and has a value in the example")
        elif tagged_at:
            shape.problems.append(f"line {tagged_at}: `# secret` is not directly above a declaration")
        tagged_at = 0
    if tagged_at:
        shape.problems.append(f"line {tagged_at}: `# secret` is not directly above a declaration")
    return shape


def read(path: Path = ENV_EXAMPLE) -> Shape:
    return parse(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=ENV_EXAMPLE, help="default: the tree's .env.example")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.path.is_file():
        fail(f"{args.path} does not exist")
        return 1
    shape = read(args.path)
    if args.json:
        emit({"names": shape.names, "secrets": shape.secrets, "problems": shape.problems})
    if shape.problems:
        fail(f"{args.path.name}: {len(shape.problems)} problem(s)")
        for problem in shape.problems:
            detail(problem)
        return 1
    ok(f"{args.path.name}: {len(shape.names)} name(s), {len(shape.secrets)} secret")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
