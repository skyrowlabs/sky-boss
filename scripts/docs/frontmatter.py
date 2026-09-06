#!/usr/bin/env python3
"""Read and write the YAML frontmatter block on a plan document.

Deliberately **stdlib-only**, and deliberately not a general YAML parser. The
frontmatter this project writes is a fixed, flat schema — strings, ints, bools
and one level of inline lists — emitted by :func:`dumps` in this same module.
A hand-rolled parser for a schema we also generate is a smaller surface than a
dependency every consumer must install, and the docs pipeline runs on hosts and
in CI jobs that would otherwise need one.

If the schema ever needs nesting, replace this module rather than extending it:
half a YAML parser is worse than either whole thing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Tuple

DELIM = "---"

_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}


def _scalar(raw: str) -> Any:
    """Coerce one scalar. Unquoted digits are ints; quoted digits stay strings."""
    text = raw.strip()
    if not text:
        return ""
    if text[0] in "\"'" and text[-1] == text[0] and len(text) >= 2:
        return text[1:-1]
    low = text.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    if low in {"null", "~"}:
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _inline_list(raw: str) -> list:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    # Split on commas that are not inside quotes. The schema has no nested
    # brackets, so a depth counter would be dead code.
    parts, buf, quote = [], "", ""
    for ch in inner:
        if quote:
            buf += ch
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch == ",":
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    return [_scalar(p) for p in parts if p.strip()]


def parse(text: str) -> Tuple[Dict[str, Any], str]:
    """Split a document into ``(frontmatter, body)``.

    A document with no frontmatter returns ``({}, text)`` — never an error. A
    malformed block is treated the same way, because a doc that fails to parse
    must still be listed as *unclassified* rather than crashing the index build
    for every other doc in the tree.
    """
    if not text.startswith(DELIM + "\n"):
        return {}, text
    end = text.find("\n" + DELIM, len(DELIM))
    if end == -1:
        return {}, text
    block = text[len(DELIM) + 1 : end]
    body = text[end + len(DELIM) + 2 :].lstrip("\n")

    data: Dict[str, Any] = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = raw.strip()
        data[key] = _inline_list(raw) if raw.startswith("[") and raw.endswith("]") else _scalar(raw)
    return data, body


def _emit(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    text = "" if value is None else str(value)
    # Quote anything a reader could mistake for structure or another type.
    if (
        text == ""
        or text[0] in "[{#\"'"
        or ":" in text
        or text.lower() in _TRUE | _FALSE
        or re.fullmatch(r"-?\d+", text)
    ):
        return '"' + text.replace('"', '\\"') + '"'
    return text


#: Field order in the emitted block. Fixed so a regeneration produces no diff
#: when nothing changed — a generator whose output reorders is a generator
#: whose diffs nobody reads.
FIELD_ORDER = [
    "title",
    "slug",
    "shelf_status",
    "blocked_on",
    "queue_order",
    "priority",
    "category",
    "agent_value",
    "auto_generated",
    "generated_from",
    "completed",
    "updated",
    "tags",
    "depends_on",
    "summary",
]


def dumps(data: Dict[str, Any]) -> str:
    """Render a frontmatter block, `FIELD_ORDER` first, then anything else."""
    keys = [k for k in FIELD_ORDER if k in data] + sorted(k for k in data if k not in FIELD_ORDER)
    lines = [DELIM] + [f"{k}: {_emit(data[k])}" for k in keys] + [DELIM]
    return "\n".join(lines) + "\n"


def write(path: Path, data: Dict[str, Any], body: str) -> None:
    path.write_text(dumps(data) + "\n" + body.lstrip("\n"), encoding="utf-8")


def read(path: Path) -> Tuple[Dict[str, Any], str]:
    return parse(path.read_text(encoding="utf-8"))
