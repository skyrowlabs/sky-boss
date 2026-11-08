"""Claude Code's workspace trust for a folder the deck opens an agent in.

On unless `trust = false` in deck.toml (Jeston's ruling, 2026-11-08). A tab in a
folder Claude Code has never trusted stops at its trust prompt and loads the
deck's plugin without its hooks, so the deck sets
`projects[<folder>].hasTrustDialogAccepted` in Claude Code's own config, the
route Claude Code's messages name, and says so. Nothing else in that file is
touched, and it is backed up first.

Claude Code merges each of its writes against the file on disk, so an entry
written here survives the running tabs. See [[command-deck]].
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

    Raises OSError or ValueError when the config cannot be read or written.
    """
    path = path or config_file()
    folder = os.path.realpath(folder)
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    if is_trusted(data, folder):
        return ""
    if path.exists():
        keep_copy(path, backups or path.parent / ".claude-backups")
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".claude.json.", suffix=".sb")
    with os.fdopen(handle, "w") as out:
        json.dump(trusted(data, folder), out, indent=2, ensure_ascii=False)
    if path.exists():
        shutil.copymode(path, temp)
    os.replace(temp, path)
    return f"trusted {folder} for Claude Code (trust = false in deck.toml turns this off)"


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
