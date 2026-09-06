#!/usr/bin/env python3
"""Nobody spells a status symbol, or picks a stream, outside `scripts/output.py`.

The rule this enforces is in `docs/rules/output.md`, and it exists because it
was already broken here. `cli/helpers.py` shipped `ok()` / `fail()` / `warn()`
and roughly twenty call sites retyped `print(f"✅ ...")` anyway; `⏸️` meant
"executed and declined" in three files and was defined in none of them; the gate
table had a second implementation inside the commit command; and four scripts grew a
`--json` flag while writing their human output to the same stdout, so three of
them emitted something no parser could read.

Every one of those is invisible to a linter and to review, because each file is
internally consistent. That is the same shape as the workflow-drift bug, and it
gets the same treatment: enrol by pattern, exempt with a written reason.

**Enrolment is not a registry.** Every `.py` under `cli/` and `scripts/` is
checked. Exemptions live in `scripts/output_allowlist.yaml` WITH A REASON — an
intended divergence is a decision record; an unintended one is a failure.

**And an exemption is checked against the thing it exempts.** A reason makes an
entry a decision; it does not keep the decision true. An entry whose file was
fixed, or whose file was deleted, is reported as stale and deleted rather than
re-justified — the second case being the one with teeth, since a path that
leaves the tree and later comes back for something else would arrive
pre-exempted and nobody chose that.

Usage:  python scripts/check_output_discipline.py [--json]
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Bootstrap only: put the package on sys.path so `scripts.paths` — which
# owns every path below — can be imported. See scripts/paths.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import allowlist  # noqa: E402
from scripts.output import STATE_SYMBOLS, detail, emit, fail, item, ok  # noqa: E402
from scripts.paths import PROJECT_ROOT, SCRIPTS_DIR  # noqa: E402

ALLOWLIST = SCRIPTS_DIR / "output_allowlist.yaml"

#: Where emissions are allowed to originate. `scripts/output.py` owns the
#: streams; it is the one file that must write to them directly.
SCAN_DIRS = ["cli", "scripts"]
OWNER = "scripts/output.py"

#: Anything that puts characters in front of a person or a pipe.
_EMIT = re.compile(r"\b(?:print|(?:click\.)?echo|secho)\s*\(|\braise SystemExit\s*\(\s*[\"'f]")

#: Choosing a stream by hand is the other half of the same mistake: it is how a
#: `--json` payload ends up interleaved with the ❌ lines explaining it.
_STREAM = re.compile(r"file\s*=\s*sys\.(?:stdout|stderr)|sys\.(?:stdout|stderr)\.write\s*\(")

#: The state symbols only, read from the module that owns them. A `→` inside
#: generated prose is punctuation, and a ✅ inside a generated markdown table is
#: content — flagging either would make the docs generators unfixable.
_GLYPHS = tuple(sorted({symbol.strip() for symbol in STATE_SYMBOLS.values()}))


def _allowlist() -> Dict[str, str]:
    """Exemptions, read through the one reader every allowlist here shares."""
    return allowlist.read(ALLOWLIST)


def _prose_lines(text: str) -> set:
    """Line numbers inside a docstring — writing *about* output is not output.

    Without this the checker fails on its own docstring, and on every module
    that documents the rule it enforces. A docstring is exactly a bare string
    expression, so `ast` answers this precisely; a regex would not.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    lines: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def _sources() -> List[Path]:
    found: List[Path] = []
    for directory in SCAN_DIRS:
        root = PROJECT_ROOT / directory
        if root.exists():
            found.extend(sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts))
    return found


def _findings_for(path: Path) -> Dict[str, List[str]]:
    """One file's findings, ignoring the allowlist entirely.

    Split out from `scan()` so `_stale()` below can ask the question the
    allowlist exists to suppress. An exemption is only a decision while the
    thing it exempts is still true.
    """
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    spelled: List[str] = []
    streams: List[str] = []
    unflagged: List[str] = []

    text = path.read_text(encoding="utf-8")
    prose = _prose_lines(text)

    for lineno, source_line in enumerate(text.splitlines(), 1):
        if lineno in prose or source_line.lstrip().startswith("#"):
            continue
        if _EMIT.search(source_line) and any(glyph in source_line for glyph in _GLYPHS):
            spelled.append(f"{rel}:{lineno}: status symbol inside an emission — use scripts/output.py")
        if _STREAM.search(source_line):
            streams.append(f"{rel}:{lineno}: picks a stream by hand — use `line`/`emit` or a status helper")

    # A gate a dashboard cannot read is a gate nobody watches over time.
    if path.name.startswith("check_") and 'add_argument("--json"' not in text:
        unflagged.append(f"{rel}: a check script with no --json")

    return {"spelled": spelled, "streams": streams, "unflagged": unflagged}


def _stale(entries: Dict[str, str]) -> List[str]:
    """Allowlist entries that no longer need to exist.

    A written reason makes an exemption a decision record. It does not make the
    decision *current*, and nothing here ever re-read one: an entry survived the
    file being fixed, and survived the file being deleted. Both are silent, and
    the second is the one with teeth — a path that leaves the tree and later
    comes back for something else arrives pre-exempted, and nobody chose that.

    So the allowlist is checked against the thing it describes, the same way
    `skeletor-upgrade` re-hashes a manifest against the base render: a cache
    validated on every run that does not need it cannot rot unnoticed.

    Both directions, because they fail differently. An entry that starts passing
    is an exemption outliving its reason; an entry naming nothing is an
    exemption looking for a file to attach itself to.
    """

    def why(rel: str) -> Optional[str]:
        path = PROJECT_ROOT / rel
        if not path.exists():
            return "there is no such file"
        if not any(_findings_for(path).values()):
            return "it passes the check now"
        return None

    return allowlist.stale(entries, why)


def scan() -> Dict[str, List[str]]:
    """Every place a symbol is spelled, a stream is picked, or `--json` is absent."""
    # `exempt`, not `allowlist` — the module of that name is imported above, and
    # a local shadowing it inside the one function that also calls it is a trap.
    exempt = _allowlist()
    found: Dict[str, List[str]] = {"spelled": [], "streams": [], "unflagged": []}

    for path in _sources():
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if rel == OWNER or rel in exempt:
            continue
        for group, findings in _findings_for(path).items():
            found[group].extend(findings)

    found["stale"] = _stale(exempt)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = scan()
    checked = len(_sources())
    exempt = _allowlist()

    if args.json:
        emit({"checked": checked, "exempt": sorted(exempt), **findings})

    total = sum(len(v) for v in findings.values())
    if total:
        fail(f"{total} output-discipline finding(s) across {checked} file(s):")
        for group in ("spelled", "streams", "unflagged", "stale"):
            for finding in findings[group]:
                item(finding)
        detail()
        detail("Status lines come from scripts/output.py — see docs/rules/output.md.")
        detail("A deliberate exception goes in scripts/output_allowlist.yaml WITH A REASON.")
        if findings["stale"]:
            detail(allowlist.STALE_ADVICE)
        return 1

    ok(f"{checked} file(s) route output through scripts/output.py ({len(exempt)} exempt by allowlist)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
