"""The machine-neutrality rule, checked rather than remembered.

`CLAUDE.md` § What this repo is: *"A host name in a tracked file is a bug to
fix, not context to preserve."* That rule was enforced by a `grep` in the
operator's gitignored notes, run by hand before publishing — which works
exactly as long as the person publishing knows the grep exists. A contributor
does not, and neither does a future session that never reads that file.

**The names cannot move into this file, and that is the whole design.** The
operator's grep lists real hosts, a real tailnet and a real home directory; a
tracked test holding that list would publish the very strings it exists to keep
out. So the two halves split by what they can safely say:

- the operator's notes keep the **names**, and stay gitignored;
- this keeps the **shapes** — a home directory, a routable address — which
  identify no one and belong in the repo.

Neither half subsumes the other. The grep catches `archdesk`; this catches the
`/home/<someone>` that a name list has never heard of. Both were needed: this
file's patterns found five leaks on 2026-08-30 that four previous audits had
walked past, in prose that *argued the rule correctly while breaking it* —
`docs/features/done/state-root.md` called a baked-in workspace layout "the same
class of leak as a host name in a tracked file", two lines under one.
"""

import re
import subprocess

from cli.helpers import PROJECT_ROOT

# `/home/x/y/z.json` in a highlight fixture, `/home/you` in a bug quoted from
# the workbench. A placeholder is a shape standing in for a name; these are the
# names this repo has chosen for that job, and a new one is a deliberate act.
PLACEHOLDERS = {"you", "user", "me", "x"}

HOME_DIR = re.compile(r"/(?:home|Users)/([A-Za-z][\w.-]*)")
IPV4 = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")

# Loopback and the unspecified address are how a local server is spelled, and
# `127.0.0.1` appears in `cli/canvas/` by design. The rest are the ranges the
# RFCs reserve so that sample data cannot be mistaken for somebody's network:
# 192.0.2.0/24, 198.51.100.0/24 and 203.0.113.0/24 (RFC 5737).
SAFE_IPV4 = ("127.", "0.0.0.0", "255.255.255.255", "192.0.2.", "198.51.100.", "203.0.113.")

# `docs/design/sky-boss-demo.html` is the clickable mockup the canvas was built
# from, and its `10.0.0.x` fleet — pfsense, a synology, three reolink cameras —
# is invented furniture for a screenshot of a home-network dashboard. Nothing in
# it corresponds to a real machine. It is exempt as a whole rather than address
# by address because it is a frozen reference artifact: editing it to satisfy a
# test would change the record of what the canvas was built from. `Sky Boss
# Surface.dc.html` is a *render* of the same invented dataset, and is exempt for
# the reason `tests/test_theme.py` leaves `.html` alone — hand-editing a render
# is how a render stops matching its source.
#
# The exemption is *tested to still be needed*, the way `test_docs.py` tests its
# allowlist. An exemption nobody re-checks is how a rule quietly stops applying.
IP_EXEMPT = {"docs/design/sky-boss-demo.html", "docs/design/Sky Boss Surface.dc.html"}

# Generated, enormous, and full of hashes that are not addresses.
SKIP = {"package-lock.json", "shell/package-lock.json"}


def _tracked() -> list[tuple[str, str]]:
    """Every tracked text file, as (path, contents).

    Asked of git rather than walked, so `.venv`, `node_modules` and `tmp/` are
    excluded by the same declaration that decides what gets published — which
    is the only definition of "tracked" that cannot drift from the thing being
    tested.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")

    out = []
    for name in listed:
        if not name or name in SKIP:
            continue
        path = PROJECT_ROOT / name
        try:
            out.append((name, path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue  # a PNG is not prose
    return out


def test_the_listing_is_not_empty():
    """The guard every scan in this file needs. `git ls-files` returning
    nothing — a detached checkout, a renamed root — would make all three tests
    below pass while looking at zero bytes, which is *looked and saw nothing*
    wearing *could not see*'s clothes."""
    files = _tracked()
    assert len(files) > 50, f"only {len(files)} tracked text files — the scan is not seeing the tree"


def test_no_home_directory_in_a_tracked_file():
    """A home directory names the person who has one. `/home/jeston` shipped in
    a code comment and a feature doc for three days, both quoting a real
    workbench bug where two panes disagreed about a path — the evidence was
    *that they disagreed*, and never which path it was."""
    found = []
    for name, text in _tracked():
        if name == "tests/test_publication.py":
            continue  # this file names the shapes on purpose
        for match in HOME_DIR.finditer(text):
            if match.group(1) not in PLACEHOLDERS:
                line = text[: match.start()].count("\n") + 1
                found.append(f"{name}:{line}: {match.group(0)}")
    assert not found, "a home directory in a tracked file:\n  " + "\n  ".join(found)


def test_no_routable_address_in_a_tracked_file():
    """A LAN or tailnet address says where the operator's machines are. The
    2026-08-22 sweep missed one twice, in a test fixture and then in prose,
    which is why this reads every tracked file rather than the docs."""
    found = []
    for name, text in _tracked():
        if name in IP_EXEMPT or name == "tests/test_publication.py":
            continue
        for match in IPV4.finditer(text):
            address = match.group(1)
            if not address.startswith(SAFE_IPV4):
                line = text[: match.start()].count("\n") + 1
                found.append(f"{name}:{line}: {address}")
    assert not found, "a routable address in a tracked file:\n  " + "\n  ".join(found)


def test_the_mockup_exemption_is_still_needed():
    """Tested rather than trusted. If the mockup ever stops carrying invented
    addresses, the exemption becomes a hole nobody is watching — and the next
    real address added to that file would pass in silence."""
    for name in IP_EXEMPT:
        text = (PROJECT_ROOT / name).read_text(encoding="utf-8")
        hits = [m.group(1) for m in IPV4.finditer(text) if not m.group(1).startswith(SAFE_IPV4)]
        assert hits, f"{name} no longer needs its exemption — drop it from IP_EXEMPT"


def test_the_operators_notes_are_not_tracked():
    """`CLAUDE.local.md` is the other half of this rule and holds every string
    this file refuses to name. Committing it would publish the audit and its
    subject in one move."""
    listed = subprocess.run(
        ["git", "ls-files", "CLAUDE.local.md", ".env"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert not listed, f"tracked, and must not be: {listed}"
