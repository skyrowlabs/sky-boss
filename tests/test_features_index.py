"""The feature index in `docs/features/README.md` must match the docs.

An index is a copy, and a copy drifts — which is why `CLAUDE.md` refused to
build one for as long as `ls` was still an adequate answer. What makes this one
safe is not care, it is that **nothing maintains it by hand**: the table is
built from frontmatter, and this test fails when the file disagrees.

Regenerate rather than hand-edit:

    TB_WRITE_DOC_INDEX=1 .venv/bin/python -m pytest -k features_index

The generated block is delimited by markers. Everything around it in the README
is prose, written by a person, and this never touches it.
"""

from __future__ import annotations

import os

import yaml

from cli.helpers import PROJECT_ROOT

FEATURES = PROJECT_ROOT / "docs" / "features"
README = FEATURES / "README.md"

START = "<!-- index:start -->"
END = "<!-- index:end -->"

# Not features: orientation and the skeleton.
NOT_A_FEATURE = {"README.md", "_template.md"}

# Open work first, and within it the thing being worked on before the thing
# merely written down.
STATUS_ORDER = {"active": 0, "draft": 1, "complete": 2}


def _docs() -> list[dict]:
    found = []
    for path in sorted(FEATURES.rglob("*.md")):
        if path.name in NOT_A_FEATURE:
            continue
        text = path.read_text()
        if not text.startswith("---"):
            raise AssertionError(f"{path.name}: no frontmatter — every feature doc has it")
        front = yaml.safe_load(text.split("---", 2)[1])
        found.append(
            {
                "slug": front["slug"],
                "title": front["title"],
                "status": front["status"],
                "agent_value": front.get("agent_value"),
                "href": path.relative_to(FEATURES).as_posix(),
            }
        )
    return found


def _row(doc: dict) -> str:
    value = doc["agent_value"]
    return f"| [{doc['slug']}]({doc['href']}) | {doc['status']} | {value} | {doc['title']} |"


def _table(docs: list[dict]) -> list[str]:
    lines = ["| Doc | Status | Value | What it covers |", "|---|---|---|---|"]
    lines += [_row(doc) for doc in docs]
    return lines


def build_index() -> str:
    docs = _docs()
    open_docs = [d for d in docs if d["status"] != "complete"]
    done_docs = [d for d in docs if d["status"] == "complete"]

    open_docs.sort(key=lambda d: (STATUS_ORDER.get(d["status"], 9), d["slug"]))
    # Finished work sorts by how much a future session needs it, not by name.
    done_docs.sort(key=lambda d: (-(d["agent_value"] or 0), d["slug"]))

    lines = [START, ""]
    lines.append(f"### Open — {len(open_docs)}")
    lines.append("")
    lines += _table(open_docs) if open_docs else ["*Nothing open.*"]
    lines.append("")
    lines.append(f"### Done — {len(done_docs)}")
    lines.append("")
    lines += _table(done_docs) if done_docs else ["*Nothing finished yet.*"]
    lines.append("")
    lines.append(END)
    return "\n".join(lines)


def _split(text: str) -> tuple[str, str]:
    """The README either side of the generated block."""
    assert START in text, f"{README.name} has no {START} marker"
    assert END in text, f"{README.name} has no {END} marker"
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    return before, after


def test_the_index_matches_the_docs():
    text = README.read_text()
    before, after = _split(text)
    expected = before + build_index() + after

    if os.environ.get("TB_WRITE_DOC_INDEX"):
        README.write_text(expected)
        return

    assert text == expected, (
        "the feature index is out of date — regenerate it with\n"
        "  TB_WRITE_DOC_INDEX=1 .venv/bin/python -m pytest -k features_index"
    )


def test_every_feature_doc_is_in_the_index():
    """The check jam.sense's CI does, which is the half that actually bites: a
    doc nobody indexed is a doc nobody finds."""
    listed = README.read_text()
    missing = [doc["slug"] for doc in _docs() if f"]({doc['href']})" not in listed]
    assert not missing, f"not in the index: {missing}"


def test_the_index_links_resolve():
    """These are the only relative doc paths in the repo. They are safe *because*
    they are generated — a doc moving between `docs/features/` and `done/` fails
    the test above rather than leaving a dead link, which is exactly the failure
    jam.sense needed two link checkers and a CI ratchet to catch."""
    for doc in _docs():
        assert (FEATURES / doc["href"]).exists(), f"dead index link: {doc['href']}"


def test_a_docs_status_agrees_with_where_it_lives():
    """`done/` holds features with no open work, and the frontmatter is the
    truth the directory follows. The two disagreeing means one of them lied."""
    wrong = []
    for doc in _docs():
        in_done = doc["href"].startswith("done/")
        if in_done != (doc["status"] == "complete"):
            wrong.append(f"{doc['slug']}: status={doc['status']} but href={doc['href']}")
    assert not wrong, wrong


def test_every_feature_doc_declares_what_it_is_worth():
    """`agent_value` is the field a future session reads first, to decide
    whether to read the doc at all. A doc without one cannot be triaged."""
    missing = [d["slug"] for d in _docs() if d["agent_value"] not in (1, 2, 3)]
    assert not missing, f"no usable agent_value: {missing}"
