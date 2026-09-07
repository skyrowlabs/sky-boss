#!/usr/bin/env python3
"""Scanning and classification for plan documents — the shared half of the
holding tank and the archive.

Every generator in this package reads plans through here so that "what is a
plan, and what does it say about itself" is answered once. The two index
generators, the two README builders and the freshness checks are then thin.

Two classes of metadata, and the difference is load-bearing:

* **Frontmatter** is machine state. It is generated, backfilled and rewritten.
* **Header lines** (``> **Shelf-Status**: blocked``) are the author's explicit
  override, and they always win. A human correcting a heuristic must not have
  their correction erased by the next backfill run.

What is inferred and what is not is a deliberate split. ``shelf_status`` has a
heuristic because it had to backfill an existing tank. ``blocked_on``,
``queue_order`` and ``review_pr`` are **never** inferred: a guessed gate files a
plan under a session nobody will hold, a guessed running order is precisely the
accident the numbering replaces, and a guessed PR number sends a reviewer to the
wrong diff — all three worse than an honest blank.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.docs import frontmatter  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402

#: Files in the plan trees that are not plans.
NOT_A_PLAN = {"README.md", "_TEMPLATE.md"}

SHELF_STATUSES = [
    "ready",
    "in-progress",
    "in-review",
    "planned",
    "blocked",
    "shelved",
    "deferred",
]

GATES = [
    "none",
    "time-window",
    "owner-ops",
    "owner-cloud",
    "product-decision",
    "upstream",
    "unclassified",
]

#: Statuses that must carry a gate, and the ones that must not. A gate is only
#: meaningful for a gated status; one on a `ready` plan is a contradiction the
#: index test fails on rather than rendering.
GATED = {"blocked", "shelved", "deferred"}

PRIORITIES = ["critical", "high", "medium", "low"]

#: Fields that answer a **tank** question and nothing else: which shelf a plan
#: is on, what it is waiting for, and where it sits in the ready queue. A filed
#: plan has left the tank, so all three are meaningless in the archive — and a
#: stale `shelf_status: in-progress` on a finished plan is worse than
#: meaningless, because it reads as a claim about work that is done.
#:
#: One owner, because this set was spelled out in three files: the backfill that
#: strips it, the index that declines to publish it, and the test that holds the
#: line. Two copies of a set drift; three had already started to.
TANK_ONLY = ("shelf_status", "blocked_on", "queue_order")

#: The same three as author-written header lines (`> **Shelf-Status**: ...`),
#: derived rather than listed for the reason above.
TANK_ONLY_HEADERS = tuple(key.replace("_", "-") for key in TANK_ONLY)

_HEADER = re.compile(r"^>\s*\*\*(?P<key>[A-Za-z-]+)\*\*:\s*(?P<value>.+?)\s*$", re.MULTILINE)
_TASK = re.compile(r"^\s*-\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$", re.MULTILINE)
_H1 = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.MULTILINE)

#: Task markers that exempt an unchecked task from blocking a plan's filing.
#: `(~operator)` is work only a human can do; `(~deferred)` is a deliberate
#: non-goal. Both are the author saying "this will never be ticked here".
EXEMPT_TASK_MARKERS = ("(~operator)", "(~deferred)")

_STATUS_HINTS = [
    ("ready", ("ready for agent", "🚀")),
    ("in-review", ("awaiting review", "in review", "🔎")),
    ("in-progress", ("in progress", "🟡")),
    ("blocked", ("blocked", "⛔")),
    ("shelved", ("shelved", "parked", "🟣")),
    ("deferred", ("deferred", "follow-up", "🟢")),
    ("planned", ("planned", "not started", "🔴", "📋")),
]


@dataclass
class Plan:
    """One plan document, as both files and generators see it."""

    path: Path
    slug: str
    title: str
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    body: str = ""
    headers: Dict[str, str] = field(default_factory=dict)

    # -- classification ---------------------------------------------------

    @property
    def shelf_status(self) -> str:
        explicit = self.headers.get("shelf-status") or self.frontmatter.get("shelf_status")
        if explicit and str(explicit).lower() in SHELF_STATUSES:
            return str(explicit).lower()
        return self._infer_status()

    def _infer_status(self) -> str:
        """Guess a status from the free-form Status line and the filename.

        Only ever a backfill: an explicit ``> **Shelf-Status**:`` line beats it,
        and a doc whose prose would mislead the heuristic is expected to carry
        one. `planned` is the fallback because it claims the least.
        """
        if self.slug.endswith("-deferred"):
            return "deferred"
        haystack = (self.headers.get("status", "") + " " + self.title).lower()
        for status, hints in _STATUS_HINTS:
            if any(h in haystack for h in hints):
                return status
        return "planned"

    @property
    def blocked_on(self) -> Optional[str]:
        """The gate, read **only** from an explicit line — never inferred."""
        raw = self.headers.get("blocked-on") or self.frontmatter.get("blocked_on")
        if not raw:
            return "unclassified" if self.shelf_status in GATED else None
        value = str(raw).strip().lower()
        return value if value in GATES else "unclassified"

    @property
    def queue_order(self) -> Optional[int]:
        """The declared position, read **only** from an explicit line."""
        raw = self.headers.get("queue-order") or self.frontmatter.get("queue_order")
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            return None

    @property
    def priority(self) -> str:
        raw = str(self.headers.get("priority") or self.frontmatter.get("priority") or "").strip().lower()
        # Header lines carry prose after the priority word ("High — three plans
        # depend on it"), so match the leading token rather than the whole line.
        for name in PRIORITIES:
            if raw.startswith(name):
                return name
        return "medium"

    @property
    def review_pr(self) -> Optional[str]:
        raw = self.headers.get("review-pr") or self.frontmatter.get("review_pr")
        return str(raw).strip() if raw else None

    @property
    def auto_generated(self) -> bool:
        return bool(self.frontmatter.get("auto_generated"))

    @property
    def updated(self) -> str:
        return str(self.headers.get("updated") or self.frontmatter.get("updated") or "")

    @property
    def summary(self) -> str:
        return str(self.frontmatter.get("summary") or "")

    @property
    def tags(self) -> List[str]:
        raw = self.frontmatter.get("tags") or []
        return [str(t) for t in raw] if isinstance(raw, list) else []

    # -- tasks ------------------------------------------------------------

    def open_tasks(self, include_exempt: bool = False) -> List[str]:
        """Unchecked tasks, minus the ones marked as never-ticked-here."""
        out = []
        for m in _TASK.finditer(self.body):
            if m.group("mark").strip():
                continue
            text = m.group("text")
            if not include_exempt and any(marker in text for marker in EXEMPT_TASK_MARKERS):
                continue
            out.append(text)
        return out

    def to_entry(self) -> Dict[str, Any]:
        """The machine-readable record written into the index JSON."""
        entry: Dict[str, Any] = {
            "slug": self.slug,
            "title": self.title,
            "path": str(self.path.relative_to(PROJECT_ROOT)),
            "shelf_status": self.shelf_status,
            "priority": self.priority,
            "queue_order": self.queue_order,
            "blocked_on": self.blocked_on,
            "updated": self.updated,
            "tags": self.tags,
            "summary": self.summary,
            "open_tasks": len(self.open_tasks()),
            "auto_generated": self.auto_generated,
        }
        if self.review_pr:
            entry["review_pr"] = self.review_pr
        return entry


def strip_tank_headers(text: str) -> str:
    """Remove the tank-only ``> **Header**:`` lines from a plan document.

    Header lines beat frontmatter everywhere else in this package — that is the
    whole point of them — which is why stripping the frontmatter alone does not
    file a plan. ``Plan.shelf_status`` reads the header first, so a document
    whose frontmatter has been cleaned goes on reporting the shelf it was on,
    to every reader, human and machine alike.

    So the two forms have to go together, and only one moment knows the plan has
    left the tank: the move itself. This is called by ``dev docs file`` and
    deliberately not by the backfill, which runs on every ``docs index`` and has
    no business rewriting anybody's prose.

    The free-form ``> **Status**:`` line is left alone. It is a sentence a human
    wrote, not one of the three machine taxonomies, and "Shipped 2026-04-01" is
    a perfectly good thing for an archived plan to say.
    """
    drop = {key.lower() for key in TANK_ONLY_HEADERS}
    kept = [line for line in text.splitlines(keepends=True) if not _is_header_for(line, drop)]
    return "".join(kept)


def _is_header_for(line: str, keys: set) -> bool:
    match = _HEADER.match(line)
    return bool(match) and match.group("key").lower() in keys


def load(path: Path) -> Plan:
    text = path.read_text(encoding="utf-8")
    # The path is passed so a `FrontmatterError` names the document. This is the
    # only caller, and it is the only one holding the name — a refusal that says
    # "line 4" and not which file is a refusal somebody has to hunt for across
    # every plan in the tree.
    fm, body = frontmatter.parse(text, where_from=str(path))
    headers = {m.group("key").lower(): m.group("value") for m in _HEADER.finditer(body)}
    h1 = _H1.search(body)
    title = str(fm.get("title") or (h1.group("title") if h1 else path.stem.replace("-", " ").title()))
    return Plan(path=path, slug=path.stem, title=title, frontmatter=fm, body=body, headers=headers)


def scan(directory: Path, recursive: bool = False) -> List[Plan]:
    """Every plan under ``directory``, sorted by slug for a stable index."""
    if not directory.exists():
        return []
    paths = directory.rglob("*.md") if recursive else directory.glob("*.md")
    return sorted(
        (load(p) for p in paths if p.name not in NOT_A_PLAN),
        key=lambda plan: plan.slug,
    )
