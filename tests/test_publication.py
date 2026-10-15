"""No tracked file names the machine it was written on.

A tree is scaffolded on somebody's workstation and may later be made public. The
scan checks **shapes**, never names: a home directory, a path built on the home
directory outside a tool's own dotfile, a private or routable IPv4 literal, a
committed `CLAUDE.local.md`. Real host names cannot go here, because a tracked
list of them would itself be the leak; keep those in an untracked grep of your own.
From sky.boss, whose version found five leaks after four audits called the tree clean.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import allowlist  # noqa: E402
from scripts.paths import PROJECT_ROOT  # noqa: E402
from tests.scanning import scanned  # noqa: E402

ALLOWLIST = Path(__file__).with_name("publication_allowlist.yaml")

# Not after a word character, `.` or `}`: a URL's `/home/` and a templated `{HOME}/home/` name nobody (stash.flow).
HOME_DIR = re.compile(r"(?<![\w.}])/(?:home|Users)/[A-Za-z][\w.-]*")
# A tool owns a dotted directory under the home; any other first segment describes somebody's disk.
TILDE_PATH = re.compile(r"~/[A-Za-z0-9][\w.-]*")
HOME_JOIN = re.compile(r'Path\.home\(\)\s*/\s*"[A-Za-z0-9][\w.-]*"')
# Not after `=`, `@` or `v`, which is how a four-part version pin is spelled, nor `§`, a section number.
IPV4 = re.compile(r"(?<![\w.=@§-])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])")
LOCAL_NOTES = re.compile(r"(^|/)CLAUDE\.local\.md$")


#: A name rather than a parenthesised tuple in the `except`: at a 3.14 target black
#: rewrites `except (A, B):` into PEP 758's `except A, B:`. A name formats the same everywhere.
_UNREADABLE = (UnicodeDecodeError, OSError)


def _harmless(address: str) -> bool:
    """Loopback, unspecified, broadcast and the RFC 5737 documentation ranges name no network."""
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        return True
    documentation = ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
    return (
        ip.is_loopback
        or ip.is_unspecified
        or ip == ipaddress.IPv4Address("255.255.255.255")
        or any(ip in ipaddress.IPv4Network(net) for net in documentation)
    )


def _tracked() -> list[str]:
    """What git would publish, which is the only definition of tracked that cannot drift."""
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return [name for name in listed.stdout.split("\0") if name]


def findings() -> list[tuple[str, str]]:
    """Every shape in every tracked text file, as `(path, match)`."""
    found = [(name, name) for name in _tracked() if LOCAL_NOTES.search(name)]
    for name in scanned(_tracked(), "tracked files", least=20):
        # The allowlist quotes the findings it exempts, and each of those is held to a real one below.
        if PROJECT_ROOT / name == ALLOWLIST:
            continue
        try:
            text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        except _UNREADABLE:
            continue
        for pattern in (HOME_DIR, TILDE_PATH, HOME_JOIN):
            found += [(name, m.group(0)) for m in pattern.finditer(text)]
        found += [(name, m.group(0)) for m in IPV4.finditer(text) if not _harmless(m.group(0))]
    return sorted(set(found))


def exempts(key: str, finding: tuple[str, str]) -> bool:
    """A key is `<path> <match>` for one finding, a tracked path for a whole file, or a bare match anywhere."""
    path, match = finding
    return key in (f"{path} {match}", path, match)


def test_no_tracked_file_names_this_machine():
    keys = allowlist.read(ALLOWLIST)
    leaks = [f"{path} {match}" for path, match in findings() if not any(exempts(key, (path, match)) for key in keys)]
    assert not leaks, "a tracked file names a machine:\n" + "\n".join(leaks)


def test_every_exemption_still_exempts_something():
    current = findings()

    def still_needed(key: str) -> str | None:
        return None if any(exempts(key, finding) for finding in current) else "nothing in the tree matches it any more"

    stale = allowlist.stale(allowlist.read(ALLOWLIST), still_needed)
    assert not stale, "\n".join(stale) + "\n" + allowlist.STALE_ADVICE


def test_the_shapes_catch_what_they_claim():
    assert HOME_DIR.search("/home/" + "someone/x") and TILDE_PATH.search("~/" + "work/x")
    assert not TILDE_PATH.search("~/" + ".config/x"), "a tool's own dotfile is not a leak"
    assert IPV4.search("ssh 10.0.0." + "5") and not _harmless("10.0.0." + "5")
    assert not IPV4.search("tool==1.7.12." + "24") and _harmless("127.0.0." + "1")
    assert not IPV4.search("§2.3.1." + "4") and not HOME_DIR.search("https://example.org/home/" + "Download")


def test_an_exemption_names_one_finding_a_whole_file_or_a_match_anywhere():
    finding = ("docs/a.md", "~/" + "src")
    assert all(exempts(key, finding) for key in ("docs/a.md ~/" + "src", "docs/a.md", "~/" + "src"))
    assert not exempts("docs/b.md", finding) and not exempts("~/" + "other", finding)
