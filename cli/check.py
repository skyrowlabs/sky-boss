"""``dev check`` — every gate, runnable locally.

The organising rule: **anything CI blocks on must be runnable here, with the same
invocation.** A gate you can only observe by pushing costs a round trip per fix,
and the fix rate then depends on how patient you are rather than on how wrong
the code is.
"""

from __future__ import annotations

import sys

import click

from scripts.paths import TMP_DIR

from .helpers import PROJECT_ROOT, fail, module, ok, run, script, summarize


@click.group()
def check() -> None:
    """Validation gates — lint, docs, types, and the pre-push bundle."""


@check.command()
def lint() -> None:
    """The blocking lint set for this project's languages."""
    sys.exit(_lint())


#: language -> (what declares it is here, the configs `_lint()` needs before it
#: will read that language at all). Globs anchored at the project root, so the
#: walk never reaches `.venv` or `node_modules` where the answer is always yes
#: and never about this tree.
#:
#: Declaration rather than a bare "any file of this type" on purpose: a single
#: vendored `.js` beside no eslint config is not a project that forgot its
#: linter, and a check that cannot tell those apart goes red in somebody else's
#: repository over a file they did not write. Python is declared by the roots
#: this project owns, and node by its manifest.
#:
#: **These used to be the same names `pyrightconfig.json` lists in `include`,
#: and in this tree they are not.** The product moved to `skyboss/` when
#: skeletor's shell took `cli/`, and only the pyright config followed it — this
#: literal is parsed by `bin/skeletor-verify` to ask a question about the
#: *generator's* configurations, so an adopter's own package name does not
#: belong in it. Nothing is lost: this asks only *is python here*, `cli/` is
#: still full of it, and flake8 scans the whole tree regardless. Said out loud
#: because the sentence that used to be here asserted a correspondence that had
#: quietly stopped holding, which is how the type checker came to be reading an
#: empty package for a whole branch.
#:
#: The gates below run a linter only when its config exists, which was written
#: as tolerance and reads as a claim. A missing config makes the source it
#: governs *invisible*, and invisible renders as green: a `--language node`
#: tree shipped 52 python files with no `.flake8` and no `pyrightconfig.json`,
#: ran eslint alone, and printed `all 1 gates passed`. Nothing in that line is
#: false and nothing in it is the answer. Absence is two questions — *is this
#: language here* and *is anything checking it* — and they are asked separately
#: now.
#:
#: Kept as plain data because two readers need it. `bin/skeletor-verify` parses
#: this literal to ask the question no single tree can: whether every
#: CONFIGURATION the generator can produce ships the linter for the source it
#: ships. A tree only ever knows its own.
LANGUAGE_CONFIGS = (
    ("python", ("cli/**/*.py", "scripts/**/*.py", "tests/**/*.py"), (".flake8", "pyrightconfig.json")),
    ("node", ("package.json",), ("eslint.config.js",)),
)


def _unlinted() -> list[str]:
    """Languages this tree holds source for that no configured linter reads."""
    gaps = []
    for language, declares, configs in LANGUAGE_CONFIGS:
        if not any(next(PROJECT_ROOT.glob(pattern), None) for pattern in declares):
            continue
        for config in configs:
            if not (PROJECT_ROOT / config).exists():
                gaps.append(f"{language}: {config} is missing, so nothing here lints it")
    return gaps


def _lint() -> int:
    gaps = _unlinted()
    if gaps:
        fail(
            "source is present that no gate reads:\n  "
            + "\n  ".join(gaps)
            + "\nRestore the config, or delete the source it was meant to govern."
        )
        return 1

    results = []
    if (PROJECT_ROOT / ".flake8").exists():
        results.append(
            ("flake8 (errors)", run(["flake8", ".", "--select=E9,F63,F7,F82,F401", "--show-source"]).returncode)
        )
        results.append(("isort", run(["isort", "--check-only", "--diff", "."]).returncode))
        results.append(("black", run(["black", "--check", "."]).returncode))
    if (PROJECT_ROOT / "pyrightconfig.json").exists():
        results.append(("pyright", run(["pyright", "--project", "pyrightconfig.json"]).returncode))
    if (PROJECT_ROOT / "eslint.config.js").exists():
        results.append(("eslint", run(["npm", "run", "lint:check"]).returncode))
    if not results:
        fail("no linters configured — add .flake8 / pyrightconfig.json / eslint.config.js")
        return 1
    return summarize(results)


@check.command(name="docs")
def docs_cmd() -> None:
    """Every documentation gate: indexes, tables, links, refs, report anchors."""
    sys.exit(_docs())


def _docs() -> int:
    return summarize(
        [
            ("generated indexes", script("scripts/docs/regen.py", "--check")),
            ("doc index tables", script("scripts/check_doc_tables.py")),
            ("doc links", script("scripts/check_doc_links.py")),
            ("source → doc refs", script("scripts/check_source_doc_refs.py")),
            ("report anchors", script("scripts/docs/release_window.py", "--check")),
        ]
    )


@check.command(name="doc-links")
@click.option("--fix", is_flag=True, help="repoint fragments with exactly one matching heading")
def doc_links(fix: bool) -> None:
    """Relative markdown links between docs, and their `#fragments`."""
    sys.exit(script("scripts/check_doc_links.py", *(["--fix"] if fix else [])))


@check.command(name="doc-refs")
def doc_refs() -> None:
    """`docs/*` paths cited from source comments — the direction nothing else checks."""
    sys.exit(script("scripts/check_source_doc_refs.py"))


@check.command()
def reports() -> None:
    """Every in-flight report carries a valid, consistent release anchor."""
    sys.exit(script("scripts/docs/release_window.py", "--check"))


@check.command(name="output")
def output_cmd() -> None:
    """Does every emission go through `scripts/output.py`?

    Status lines and streams are picked in one module so a `--json` payload and
    the ❌ lines explaining it never share a stream. Full rules in
    `docs/rules/output.md`.
    """
    sys.exit(script("scripts/check_output_discipline.py"))


@check.command(name="merge-drivers")
def merge_drivers() -> None:
    """Are the generated-docs merge drivers installed in this checkout?

    The driver definition lives in `.git/config`, which is not version
    controlled — so a fresh clone has `.gitattributes` pointing at a driver that
    does not exist, and git silently falls back to a three-way text merge of a
    100k-line generated JSON. That resolution is never correct.
    """
    sys.exit(script("scripts/git/install_merge_drivers.py", "--check"))


@check.command(name="pre-push")
@click.option("--quick", is_flag=True, help="lint and docs only — skip the test suites")
def pre_push(quick: bool) -> None:
    """Every gate CI blocks on that can run on this host, in fail-fastest order.

    Lint first because it is seconds and catches most of what CI would reject;
    tests last because they are the expensive half. Every gate still runs even
    after one fails — one fix per round trip is the thing this exists to avoid.

    **The sentence used to be "everything CI blocks on", and it was false.** It
    omitted `check_skip_budget.py` and `check_commit_subjects.py` — both of
    which CI blocks on and both of which run fine here — so a reader got a
    completeness claim from a command that had not run two of the gates about to
    fail. proto.pilot ran it four times across four upgrades, watched it pass,
    pushed, and CI went red on the skip budget. **A command that claims a
    coverage it does not have is worse than one that stays quiet**, because the
    sentence is doing active work to stop somebody looking.

    Both are here now. The junit report is why `pytest` grew `--junitxml`: the
    ratchet reads a report rather than a process, and *"I could not measure" is
    not "the budget is respected"* — it refuses a missing one.

    What is still missing is named rather than implied: **the integration
    suite**, which CI blocks on and which needs a stack this host does not have.
    That is the whole of the difference, and `tests/test_pre_push_covers_ci.py`
    is what keeps this paragraph true — it recomputes the two sets from
    `ci.yml` and from this function, and fails when a gate is in neither.
    """
    results = [
        ("lint", _lint()),
        ("output discipline", script("scripts/check_output_discipline.py")),
        ("docs", _docs()),
        # No `--range`, which now means everything not yet on the upstream —
        # the set this push will send, and therefore the set CI will check.
        # It used to mean HEAD alone, so a push of three commits was validated
        # here one commit deep and there three: same gate, same name, two sets,
        # and the bigger one runs after the push. The script prints the range
        # it chose, because two ranges that print alike is the whole defect.
        # Self-guarding: with no release automation in the tree there is no
        # contract to check and it says so.
        ("commit subjects", script("scripts/check_commit_subjects.py")),
    ]
    if not quick:
        junit = TMP_DIR / "junit-unit.xml"
        junit.parent.mkdir(parents=True, exist_ok=True)
        results.append(("unit tests", module("pytest", "tests/", "-m", "unit", "-q", f"--junitxml={junit}")))
        results.append(
            ("skip budget", script("scripts/check_skip_budget.py", "--suite", "unit", "--junit", str(junit)))
        )
    sys.exit(summarize(results))


@check.command()
def health() -> None:
    """Is the local stack up and answering?"""
    # SCAFFOLD: replace with this project's real health probes.
    ok("nothing to probe yet — wire this to the project's services")
