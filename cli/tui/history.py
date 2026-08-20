"""Input history for the surface, persisted between sessions.

Lives in the state directory rather than the repo, for the same reason the
stall dump does: `git clean -xdf` must not be able to destroy it, and it
should survive a reclone or the repo moving.
"""

from __future__ import annotations

from pathlib import Path

from cli.helpers import STATE_DIR

HISTORY_PATH = STATE_DIR / "tui-history"

# Enough to reach back through a session or two. The file is rewritten whole on
# trim, so this stays small deliberately.
LIMIT = 500


class History:
    """A recall cursor over past lines.

    The cursor sits one past the end when the user is composing something new,
    which is the position ``reset`` returns to after a line is submitted. That
    off-the-end slot is what makes "press down until the box is empty again"
    work the way every shell does it.
    """

    def __init__(self, path: Path | None = None, limit: int = LIMIT) -> None:
        self.path = HISTORY_PATH if path is None else path
        self.limit = limit
        self.lines: list[str] = self._load()
        self.cursor = len(self.lines)

    def _load(self) -> list[str]:
        try:
            text = self.path.read_text()
        except OSError:
            # No history yet, or unreadable. Neither is worth failing to start
            # over — history is a convenience, not state anything depends on.
            return []
        return [line for line in text.splitlines() if line.strip()][-self.limit :]

    def append(self, line: str) -> None:
        """Record a submitted line and return the cursor to the new-line slot."""
        line = line.strip()
        if not line:
            return
        # Consecutive duplicates are noise: running the same check twice in a
        # row is the single most common thing to do here.
        if not self.lines or self.lines[-1] != line:
            self.lines.append(line)
            self._save()
        self.reset()

    def _save(self) -> None:
        if len(self.lines) > self.limit:
            self.lines = self.lines[-self.limit :]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("\n".join(self.lines) + "\n")
        except OSError:
            pass

    def reset(self) -> None:
        self.cursor = len(self.lines)

    def prev(self) -> str | None:
        """The previous line, or None when already at the oldest."""
        if self.cursor == 0:
            return None
        self.cursor -= 1
        return self.lines[self.cursor]

    def next(self) -> str | None:
        """The next line, "" at the new-line slot, or None when already there."""
        if self.cursor >= len(self.lines):
            return None
        self.cursor += 1
        return "" if self.cursor == len(self.lines) else self.lines[self.cursor]
