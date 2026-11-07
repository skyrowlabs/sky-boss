"""A line under the tab row for each message in flight between two tabs. See [[command-deck]].

It lives in the row under the tabs, which is otherwise blank, so it costs no height. Corners
meet the tabs' bottom edges: down from the sender, along, and up into the receiver.

A line draws when the sender's transcript shows the message sent, in the sender's hue, and
holds until the receiver's transcript shows it taken in. Then it takes the receiver's hue and
fades. `msg_id` is what ties the two entries together.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from skyboss import theme
from skyboss.messages import peer_origin

#: Seconds to draw a line out, to show the receiver's hue, and to fade it.
DRAW, HOLD, FADE = 0.4, 0.3, 0.6
#: Seconds between frames, and between looks at the transcripts while nothing moves.
FRAME, POLL = 0.05, 0.5
#: Seconds a line waits for a receiver that never takes the message in.
PATIENCE = 900.0

UP, LEFT, RIGHT = 1, 2, 4
SHAPES = {UP | RIGHT: "╰", UP | LEFT: "╯", UP | LEFT | RIGHT: "┴", UP: "│"}


@dataclass
class Flight:
    """One message between two tabs. `landed` is when the receiver took it in, on the wire's clock."""

    sender: str
    receiver: str
    started: float
    landed: float | None = None

    def lands_at(self) -> float | None:
        """When the hue changes: a message taken in at once still draws out first."""
        return None if self.landed is None else max(self.landed, self.started + DRAW)

    def over(self, now: float) -> bool:
        turned = self.lands_at()
        return now - self.started > PATIENCE if turned is None else now >= turned + HOLD + FADE

    def moving(self, now: float) -> bool:
        return self.landed is not None or now < self.started + DRAW

    def hue(self, hues: dict[str, str], now: float) -> str:
        turned = self.lands_at()
        if turned is None or now < turned:
            return hues[self.sender]
        return theme.fade(hues[self.receiver], 1 - min(1.0, max(0.0, now - turned - HOLD) / FADE))


def compose(flights: list[Flight], centres: dict[str, int], hues: dict[str, str], now: float, ground: str) -> str:
    """The row under the tabs as a tmux format, or empty. Lines sharing a cell join; the newest colours it."""
    bits: dict[int, int] = {}
    paint: dict[int, str] = {}
    for flight in sorted(flights, key=lambda f: f.started):
        if flight.sender not in centres or flight.receiver not in centres:
            continue
        source, target = centres[flight.sender], centres[flight.receiver]
        away, back = (RIGHT, LEFT) if target > source else (LEFT, RIGHT)
        step = 1 if target > source else -1
        length = abs(target - source)
        reach = min(length, math.ceil(length * (now - flight.started) / DRAW))
        colour = flight.hue(hues, now)
        for n in range(reach + 1):
            column = source + n * step
            shape = (UP | away) if n == 0 else (UP | back) if n == length else (LEFT | RIGHT)
            bits[column] = bits.get(column, 0) | shape
            paint[column] = colour
    if not bits:
        return ""
    out, held = f"#[{ground}]{' ' * min(bits)}", ""
    for column in range(min(bits), max(bits) + 1):
        if column not in bits:
            out, held = f"{out}#[{ground}] ", ""
            continue
        if paint[column] != held:
            held = paint[column]
            out += f"#[fg={held}]"
        out += SHAPES.get(bits[column], "─")
    return f"{out}#[{ground}]"


@dataclass
class Tail:
    """The lines appended to transcripts. A file's past is not news, so it starts at the end."""

    offsets: dict[Path, int] = field(default_factory=dict)

    def read(self, path: Path) -> list[str]:
        try:
            size = path.stat().st_size
            start = self.offsets.setdefault(path, size)
            if size <= start:
                return []
            with path.open("rb") as handle:
                handle.seek(start)
                chunk = handle.read(size - start)
        except OSError:
            return []
        whole = chunk.rfind(b"\n") + 1
        self.offsets[path] = start + whole
        return chunk[:whole].decode(errors="replace").splitlines()


@dataclass
class Sent:
    to: str
    msg_id: str


def read_entry(line: str, asked: dict[str, str]) -> Sent | dict | None:
    """What a transcript line says: a `Sent`, a received peer `origin`, or nothing.

    `asked` carries each SendMessage's `to` from its call to its result, where the id arrives.
    """
    if "SendMessage" not in line and "toolUseResult" not in line and '"origin"' not in line:
        return None
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict):
        return None
    origin = peer_origin(entry)
    if origin is not None:
        return origin
    body = (entry.get("message") or {}).get("content")
    for part in body if isinstance(body, list) else []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "tool_use" and part.get("name") == "SendMessage":
            asked[str(part.get("id"))] = str((part.get("input") or {}).get("to") or "")
        result = entry.get("toolUseResult")
        if part.get("type") == "tool_result" and part.get("tool_use_id") in asked and isinstance(result, dict):
            to = asked.pop(part["tool_use_id"])
            return Sent(to, str(result.get("msg_id") or "")) if result.get("success") else None
    return None
