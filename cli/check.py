"""``dev check`` — every gate, runnable locally.

The organising rule: **anything CI blocks on must be runnable here, with the same
invocation.** A gate you can only observe by pushing costs a round trip per fix,
and the fix rate then depends on how patient you are rather than on how wrong
the code is.
"""

from __future__ import annotations

import json
import re
import sys

import click

from scripts.gates import DOCS_GATES, PRE_PUSH_GATES, Gate
from scripts.git.green_stamp import clean_tree, record
from scripts.output import EXIT_NO_SUBJECT, EXIT_REFUSED
from scripts.paths import TMP_DIR
from scripts.yaml_text import read_uncommented

from .helpers import PROJECT_ROOT, Declared, detail, fail, module, no_subject, run, script, summarize, warn

#: tests/test_cli_smoke.py runs this module's argument-less commands for real.
SMOKE_EXECUTES = True


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


#: The python lint gates, as (label, argv) with the paths to check appended.
#: A command that lints a subset of paths runs this same list over them, so a
#: tree that changes its linters here (ruff, say) changes the commands that read
#: this list. `.pre-commit-config.yaml` and `ci.yml` name their own and stay as they were.
PYTHON_LINTERS = (
    ("flake8 (errors)", ("flake8", "--select=E9,F63,F7,F82,F401", "--show-source")),
    ("isort", ("isort", "--check-only", "--diff")),
    ("black", ("black", "--check")),
)


def typecheck() -> tuple[str, int] | None:
    """The whole-project type check, or None when this tree configures none."""
    if not (PROJECT_ROOT / "pyrightconfig.json").exists():
        return None
    # The wrapper, not pyright directly — the same entry the pre-commit hook
    # runs. It pre-flights the interpreter pyright would resolve, because a
    # bare one reports an environment fault as errors in files this run never
    # touched (`reportMissingImports` is `none`). scripts/lint_pyright_gate.py.
    return ("pyright", script("scripts/lint_pyright_gate.py", "--project", "pyrightconfig.json"))


def workflow_lint() -> tuple[str, int] | None:
    """actionlint over `.github/workflows/`, as the commit hook runs it, or None without that hook.

    Through pre-commit so the hook's `rev:` stays the one version. Only the hook ran
    it before, so a workflow edited without a commit (a hand-merge, an upgrade)
    passed this and pre-push and failed at the commit (sky.boss).
    """
    config = PROJECT_ROOT / ".pre-commit-config.yaml"
    if not config.exists() or not re.search(r"^\s*-\s*id:\s*actionlint\s*$", read_uncommented(config), re.M):
        return None
    return ("actionlint", module("pre_commit", "run", "actionlint", "--all-files"))


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
        results += [(label, run([*argv, "."]).returncode) for label, argv in PYTHON_LINTERS]
    typed = typecheck()
    if typed:
        results.append(typed)
    workflows = workflow_lint()
    if workflows:
        results.append(workflows)
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
            # The other generated artifact, and it sits here for the same
            # reason: `.vscode/settings.json`'s query region is rendered from
            # `scripts/lanes.py`, so adding a lane without regenerating leaves
            # a queue that `dev bug`/`dev task` file into and no view
            # shows. A write-only queue looks exactly like an empty one.
            ("editor queries", script("scripts/gen_vscode_queries.py", "--check")),
            ("doc index tables", script("scripts/check_doc_tables.py")),
            ("doc links", script("scripts/check_doc_links.py")),
            ("source → doc refs", script("scripts/check_source_doc_refs.py")),
            ("report anchors", script("scripts/docs/release_window.py", "--check")),
            *_product(DOCS_GATES),
        ]
    )


#: The product scripts a node tree is gated on by name. The template ships none of
#: them, because it does not pick a test runner.
NODE_PRODUCT_SCRIPTS = ("typecheck", "test", "build")


def _node_products() -> list:
    """`package.json`'s product scripts, plus prettier, which CI runs and this did not.

    A script present runs. One declared in `skeletor.requiredScripts` and missing is
    refused, because deleting a gate must not pass; undeclared and missing has no
    subject. `.github/scripts/node-gate.cjs` is the same rule in the job with no python.
    """
    manifest = PROJECT_ROOT / "package.json"
    if not manifest.exists():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except ValueError as error:
        fail(f"package.json cannot be read: {error}")
        return [("package.json", EXIT_REFUSED)]
    scripts = data.get("scripts") or {}
    required = (data.get("skeletor") or {}).get("requiredScripts") or []
    rows: list = []
    if "format:check" in scripts:
        rows.append(("prettier", run(["npm", "run", "format:check"]).returncode))
    for name in NODE_PRODUCT_SCRIPTS:
        if name in scripts:
            rows.append((f"npm {name}", run(["npm", "run", name]).returncode))
        elif name in required:
            fail(f"package.json requires the `{name}` script and has none: a deleted gate does not pass")
            rows.append((f"npm {name}", EXIT_REFUSED))
        else:
            no_subject(f"npm {name}: no such script in package.json")
            rows.append((f"npm {name}", Declared(EXIT_NO_SUBJECT)))
    return rows


def _product(gates: list[Gate]) -> list:
    """Your gates from `scripts/gates.py`, run after the template's own."""
    results = [(gate, script(gate.script, *gate.args)) for gate in gates]
    return [(gate.label, Declared(code) if gate.no_subject else code) for gate, code in results]


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


@check.command()
@click.option("--plan", is_flag=True, help="print what would run, run nothing")
@click.option("--workflow", "workflows", multiple=True, help="one workflow file name; repeatable")
@click.option("--keep", is_flag=True, help="leave the worktree and venv behind")
def scheduled(plan: bool, workflows: tuple, keep: bool) -> None:
    """Rehearse each scheduled workflow here: the working tree, a clean venv.

    No pull request runs a scheduled job, so this is the only way to see one
    pass before its first night. Exits 3, no subject, when nothing could be rehearsed.
    scripts/rehearse_scheduled.py says what it can and cannot stand in for.
    """
    args = ["--plan"] * plan + ["--keep"] * keep
    for name in workflows:
        args += ["--workflow", name]
    sys.exit(script("scripts/rehearse_scheduled.py", *args))


@check.command(name="pre-push")
@click.option("--quick", is_flag=True, help="lint and docs only — skip the test suites, and write no green stamp")
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
    _say_if_interpreter_differs()
    tree = clean_tree()
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
        # With no Release Please config the contract is the commit-msg hook.
        ("commit subjects", script("scripts/check_commit_subjects.py")),
        # A clone fact, so CI cannot hold it and `tests/test_pre_push_covers_ci.py`
        # cannot require it: the merge driver and commit template live in
        # .git/config, which every second clone starts without.
        ("clone-local config", script("scripts/git/install_merge_drivers.py", "--check")),
        *_product(PRE_PUSH_GATES),
    ]
    if not quick:
        junit = TMP_DIR / "junit-unit.xml"
        junit.parent.mkdir(parents=True, exist_ok=True)
        results.append(("unit tests", module("pytest", "tests/", "-m", "unit", "-q", f"--junitxml={junit}")))
        results.append(
            ("skip budget", script("scripts/check_skip_budget.py", "--suite", "unit", "--junit", str(junit)))
        )
        results += _node_products()
    code = summarize(results)
    # What scripts/hooks/pre-push reads: a push to a protected branch needs this.
    if code == 0 and not quick:
        record(tree)
    sys.exit(code)


#: The python this project was rendered for — what `ci.yml`'s single-version
#: jobs install, and what `pyproject.toml` and `pyrightconfig.json` target.
TARGET_PYTHON = "3.12"


def _ci_pythons() -> list:
    """Every version `ci.yml`'s test matrix runs, read from `ci.yml`.

    **Read, not rendered, and it was rendered for a day.** Rendering the matrix
    into this file made `--python-ceiling` reach a second file, so every tree that
    has edited this one — two of six, at the round that added it — would conflict
    here whenever the ceiling moved, and a tree that declined `ci.yml` could no
    longer record a ceiling without touching this. The workflow is where the
    matrix lives and what CI actually runs; a copy of it here is one more home
    for the value. A tree without the workflow falls back to `TARGET_PYTHON`.
    """
    workflow = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    if workflow.exists():
        found = re.search(r"^\s*python:\s*\[([^\]]*)\]", read_uncommented(workflow), re.MULTILINE)
        if found:
            versions = [v.strip().strip("'\"") for v in found.group(1).split(",") if v.strip()]
            if versions:
                return versions
    return [TARGET_PYTHON]


def _say_if_interpreter_differs() -> None:
    """Name the interpreter every gate below runs on, when CI runs no job on it.

    Every gate here runs on `sys.executable` — the `.venv` the wrapper found —
    and nothing pins what that venv was built from: the setup block, the
    wrapper's own hint and the worktree command all say `python -m venv`.
    stash.flow's gates ran on 3.14 against a recorded 3.12 and nothing said so.
    Whether any verdict changes is unmeasured — their words, *"nothing would
    notice if it did"* is the claim — so this says it rather than failing: red
    on every machine without that exact minor would be a gate that is red for a
    reason that is not a defect.

    **Against the whole matrix, and v0.31.0 compared the floor alone.** On a tree
    with a `--python-ceiling`, a venv on the ceiling is a version CI tests, and
    "CI runs 3.12, rebuild with python3.12" pointed away from it — sky.boss filed
    it, proto.pilot saw it independently. So this fires only outside the matrix,
    and when it does it says which jobs run what rather than naming one version as
    the answer. It names no command either: whether the right interpreter is
    installed is a fact about the host, and a hint here cannot know it. (This
    shipped for a release citing one adopter's host as lacking it; that was a
    relayed claim nobody had run, and it was false.)

    The README's setup block stays `python -m venv` on purpose. Pinning it there
    makes line one of the quick start fail on every host that lacks that exact
    minor — most of them — which is the red-on-arrival this template refuses.
    """
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    matrix = _ci_pythons()
    if running in matrix:
        return
    warn(f"these gates run on python {running}, which no CI job runs")
    detail(f"  CI's test matrix runs {', '.join(matrix)}; its lint and type jobs run {TARGET_PYTHON}.")
    detail("  A result here can differ from CI's. A .venv built from one of those, if this host has one,")
    detail("  makes the two agree.")


@check.command()
def health() -> None:
    """Is the local stack up and answering?"""
    # SCAFFOLD: replace with this project's real health probes.
    no_subject("nothing to probe yet — wire this to the project's services")
    sys.exit(EXIT_NO_SUBJECT)
