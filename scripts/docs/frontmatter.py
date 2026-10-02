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

## What it refuses, and why refusing is not the same as being tolerant

`parse()` is tolerant of a block it cannot **find** — no frontmatter, or an
unterminated one — and returns `({}, text)`, so one unreadable document does not
crash an index build for every other one. That tolerance was written for
*absence*, and it was silently doing a second job: covering constructs this
parser can read and cannot represent, where it returned a **plausible wrong
value** instead of nothing.

Reported by sky.boss, from 24 documents they folded into a scaffolded tree, and
reproduced here. Three shapes, all legal YAML, none of which failed:

===  written                      this returned              consequence
  `agent_value: 3  # four rounds`  `'3  # four rounds'`     `gen_impl_index.py` does
                                                            `int(...)` inside an
                                                            `except ValueError` that
                                                            defaults to 1 — so the
                                                            archive labelled its four
                                                            densest documents
                                                            "historical only"
  `key_files: [a, b,` / `  c]`     `'[a, b,'`               rest of the list read as body
  `key_files:` / `  - a` / `  - b` `''`                     the whole list, gone

The first is the one that matters, and not because it loses data: it
**manufactures a judgment about how much a document is worth reading**, out of a
`try/except` written to be forgiving. A trailing `#` comment is the one scalar
decoration `_scalar` did not handle, and `int()` failing is where the silence
got installed.

So: a trailing comment is *stripped*, because that is what YAML means and this
schema is flat enough for the rule to be unambiguous. Everything else this
cannot represent raises `FrontmatterError` naming the file, the line and the
key. **"I could not read this" and "this key is empty" are different answers**,
and only one of them can be noticed.

(A trailing comment is a habit this template teaches: `docs/TODO/_TEMPLATE.md`
shows `> **Queue-Order**: 40   # only on a ready plan` on a header line, where it
is fine, four lines under a frontmatter block where it was not.)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Tuple

DELIM = "---"

_TRUE = {"true", "yes", "on"}
_FALSE = {"false", "no", "off"}


class FrontmatterError(ValueError):
    """A frontmatter block this parser can read and cannot represent.

    Raised rather than returned, because the alternative is a value: an empty
    string for a list that has items, a string for a number. A caller cannot
    tell those from the real thing, which is the whole defect.
    """


def _strip_comment(raw: str) -> str:
    """Drop a trailing YAML comment — a `#` at the start or after whitespace.

    Quote-aware, because a value that genuinely contains a `#` is quoted (see
    :func:`_emit`, which quotes for exactly this reason), and stripping inside
    the quotes would trade one silent corruption for another.
    """
    quote = ""
    for index, char in enumerate(raw):
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == "#" and (index == 0 or raw[index - 1].isspace()):
            return raw[:index].rstrip()
    return raw


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


def parse(text: str, where_from: str = "") -> Tuple[Dict[str, Any], str]:
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
    last_key = ""

    data: Dict[str, Any] = {}
    for number, line in enumerate(block.splitlines(), start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        where = f"{where_from} line {number}: " if where_from else f"line {number}: "
        if stripped.startswith("- "):
            raise FrontmatterError(
                f"{where}block sequences are not supported. This schema is flat and one level of "
                f"INLINE list — write `{last_key or 'key'}: [a, b]` on one line."
            )
        if ":" not in stripped:
            raise FrontmatterError(
                f"{where}{stripped!r} is not `key: value`. A continuation line (a wrapped list, a "
                "folded string) is not supported — keep each value on its own line."
            )
        key, _, raw = line.partition(":")
        key = key.strip()
        raw = _strip_comment(raw.strip())
        if raw.startswith("[") and not raw.endswith("]"):
            raise FrontmatterError(
                f"{where}`{key}` opens an inline list that does not close on the same line. "
                "This schema has no multi-line values."
            )
        data[key] = _inline_list(raw) if raw.startswith("[") and raw.endswith("]") else _scalar(raw)
        last_key = key
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
        # ` #` would be read back as the start of a comment — see `_strip_comment`.
        or "#" in text
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
