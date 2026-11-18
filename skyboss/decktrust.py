"""Claude Code's workspace trust for a folder the deck opens an agent in.

On unless `trust = false` in deck.toml (Jeston's ruling, 2026-11-08). A tab in a
folder Claude Code has never trusted stops at its trust prompt and loads the
deck's plugin without its hooks, so the deck sets
`projects[<folder>].hasTrustDialogAccepted` in Claude Code's own config, the
route Claude Code's messages name, and says so. Nothing else in that file is
touched, and it is backed up first.

Claude Code merges each of its writes against the file on disk, so an entry
written here survives the running tabs; and a write of theirs that lands while
this one is in flight is re-read and kept. See [[command-deck]].
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

#: The entry Claude Code gives a project it has not seen, as of 2.1.319.
DEFAULT_PROJECT = {
    "allowedTools": [],
    "mcpContextUris": [],
    "mcpServers": {},
    "enabledMcpjsonServers": [],
    "disabledMcpjsonServers": [],
    "hasTrustDialogAccepted": False,
    "hasClaudeMdExternalIncludesApproved": False,
    "hasClaudeMdExternalIncludesWarningShown": False,
}
#: How many backups of the config sky.boss keeps.
KEEP = 5
#: How many times trust() re-reads a config another writer changed under it.
RETRIES = 3


def config_file() -> Path:
    """`$CLAUDE_CONFIG_DIR/.claude.json` when set, else `~/.claude.json`. Read at call time."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(configured).expanduser() if configured else Path.home()) / ".claude.json"


def is_trusted(data: dict, folder: str) -> bool:
    """Whether `folder` itself carries an accepted trust dialog."""
    entry = (data.get("projects") or {}).get(folder)
    return isinstance(entry, dict) and entry.get("hasTrustDialogAccepted") is True


def trusted(data: dict, folder: str) -> dict:
    """`data` with `folder` trusted: its entry kept, or Claude Code's default entry made."""
    projects = dict(data.get("projects") or {})
    entry = dict(projects.get(folder) or DEFAULT_PROJECT)
    entry["hasTrustDialogAccepted"] = True
    projects[folder] = entry
    return {**data, "projects": projects}


def trust(folder: str, path: Path | None = None, backups: Path | None = None) -> str:
    """Trust `folder` in Claude Code's config. What to tell the operator: empty when it already was.

    A write another tab makes during this one is kept: the file is read again just before
    the replace and the entry re-applied to what is there (#84).
    Raises OSError or ValueError when the config cannot be read or written, or keeps moving.
    """
    path = path or config_file()
    folder = os.path.realpath(folder)
    text = _read(path)
    for attempt in range(RETRIES):
        data = json.loads(text) if text is not None else {}
        if not isinstance(data, dict):
            raise ValueError(f"{path} is not a JSON object")
        if is_trusted(data, folder):
            return ""
        if attempt == 0 and text is not None:
            keep_copy(path, backups or path.parent / ".claude-backups")
        handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".claude.json.", suffix=".sb")
        with os.fdopen(handle, "w") as out:
            json.dump(trusted(data, folder), out, indent=2, ensure_ascii=False)
        now = _read(path)
        if now != text:
            os.unlink(temp)
            text = now
            continue
        if now is not None:
            shutil.copymode(path, temp)
        os.replace(temp, path)
        return f"trusted {folder} for Claude Code (trust = false in deck.toml turns this off)"
    raise OSError(f"{path} kept changing while the deck tried to trust {folder}")


def _read(path: Path) -> str | None:
    """The config's text, or None when there is no file yet."""
    return path.read_text() if path.exists() else None


def keep_copy(path: Path, into: Path) -> Path:
    """Copy the config into `into` as `claude.json.N`, keeping the newest `KEEP`."""
    into.mkdir(parents=True, exist_ok=True)
    taken = sorted(into.glob("claude.json.*"), key=lambda p: p.stat().st_mtime)
    for old in taken[: max(0, len(taken) - KEEP + 1)]:
        old.unlink()
    n = 1 + max([int(p.suffix[1:]) for p in taken if p.suffix[1:].isdigit()] or [0])
    kept = into / f"claude.json.{n}"
    shutil.copy2(path, kept)
    return kept
