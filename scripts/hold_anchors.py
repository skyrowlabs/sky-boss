"""Anchors that tie a labelled hold in the divergence record to a region of its file.

`path:label:anchor: "<one template line>"` marks where the hold `path:label` starts.
A markdown heading opens its section, up to the next heading at its level or above;
any other line opens its block, up to the next blank line. `skeletor-upgrade` loads
this module from the render it upgrades to and uses it to say which region a
conflicting hunk falls in. An anchor changes no merge, classification or exit code.
"""

from __future__ import annotations

import re

#: The last segment of an anchor's key.
SUFFIX = "anchor"
_HEADING = re.compile(r"^(#{1,6})\s")


def split(entries: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """The record's entries as `(holds, {"path:label": anchor line})`."""
    holds: dict[str, str] = {}
    anchors: dict[str, str] = {}
    for key, value in entries.items():
        path, _, rest = key.partition(":")
        label, sep, last = rest.rpartition(":")
        if sep and label and last == SUFFIX:
            anchors[f"{path}:{label}"] = value
        else:
            holds[key] = value
    return holds, anchors


def unanchored(entries: dict[str, str]) -> list[str]:
    """Anchors whose `path:label` is not itself an entry, so they name no hold."""
    holds, anchors = split(entries)
    return sorted(label for label in anchors if label not in holds)


def region(lines: list[str], anchor: str, markdown: bool) -> tuple[int, int] | None:
    """`(start, end)` of the anchor's region as 0-based line indexes, end exclusive.

    `None` unless the anchor is exactly one line of `lines`, because a missing or
    repeated anchor names no single region.
    """
    found = [i for i, line in enumerate(lines) if line.strip() == anchor.strip()]
    if len(found) != 1:
        return None
    start = found[0]
    heading = _HEADING.match(lines[start]) if markdown else None
    for end in range(start + 1, len(lines)):
        if heading:
            other = _HEADING.match(lines[end])
            if other and len(other.group(1)) <= len(heading.group(1)):
                return start, end
        elif not lines[end].strip():
            return start, end
    return start, len(lines)


def hunk_regions(
    base: list[str], head: list[str], anchors: dict[str, str], markdown: bool
) -> list[tuple[str, list[str]]]:
    """Each base-to-head hunk as `(head lines, labels it falls inside)`.

    Looked up in the base, which still holds the anchor when the hunk rewords it.
    An insertion is inside a block strictly within it, or at its end when it adds
    no blank line; inside a section anywhere up to the next heading.
    """
    import difflib

    regions = {label: region(base, anchor, markdown) for label, anchor in anchors.items()}
    out = []
    matcher = difflib.SequenceMatcher(a=base, b=head, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        inside = []
        for label, span in regions.items():
            if span is None:
                continue
            start, end = span
            section = markdown and bool(_HEADING.match(base[start]))
            if i1 < i2:
                hit = i1 < end and i2 > start
            elif section:
                hit = start < i1 <= end
            else:
                hit = start < i1 < end or (i1 == end and all(line.strip() for line in head[j1:j2]))
            if hit:
                inside.append(label)
        low, high = j1 + 1, max(j2, j1 + 1)
        out.append((str(low) if low == high else f"{low}-{high}", sorted(inside)))
    return out
