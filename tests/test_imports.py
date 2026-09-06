"""No module imports a name it never uses.

## Why this exists

`scripts/paths.py` carried an `import os` with no `os.` anywhere in it for a
day, left behind when the `state_dir` block was trimmed out of the copy taken
from skeletor. It was found by reading the file, which is the only instrument
this tree had.

That gap is a property of **how** these files were adopted, not a mistake in
them. A scaffolded tree receives skeletor's `ci.yml` along with its scripts, and
that workflow runs `flake8 --select=E9,F63,F7,F82,F401` — `F401` being exactly
this rule. sky.boss is a *component consumer*: it took seven Python files one at
a time and no workflow, because a workflow is the least portable thing in a
template and this repo already has its own. **The artifact arrived; the check
that kept it honest upstream did not.**

Adoption granularity and safety granularity are different. A file is adoptable;
the invariant that made it correct may not be.

## Why a test rather than a linter

The alternative was adding flake8 to `requirements-dev.txt` and a step to CI.
This tree has no Python linter, no `pyproject.toml` and no pre-commit, on the
stated rule that none of them arrives until something needs them — and twelve
dead imports is thin grounds for a dependency. A stdlib AST walk rides the suite
that already runs. It is the same shape as `test_theme.py` forbidding a hex
outside the palette and `test_naming.py` masking code before it greps prose: a
structural gate, written here, run here.

It is deliberately **not** a CI job of its own. A required check is *named* in
branch protection rather than discovered, so a new job means editing protection
on `develop` and `main` in the same sitting, and a context no job reports blocks
every pull request for ever.

## Why it is scope-aware, which the first version was not

The obvious implementation unions every name loaded anywhere in the file and
flags imports outside that set. It reported **10** where flake8 reported 12, and
the two it missed are the interesting ones:

- `test_canvas_stream.py:25` imports `pytest` at module level. Four functions
  further down load `pytest` — each having imported it again for itself. The
  union sees the name used and clears a binding nothing reads.
- `test_stream.py:202` is a function-local `import time` in a function that
  never says `time`, while two sibling functions import and use their own.

Counting bindings per name instead — "bound twice, so one is redundant" —
reported **302**, because two functions importing `pytest` separately is not a
duplicate, it is ordinary Python. A rule needing 290 exceptions is describing
the wrong shape.

So the walk carries scope. A binding of `n` in scope `S` is used if `n` is
loaded directly in `S`, or in a nested scope that does **not** rebind `n` — the
rebinding is what severs a nested use from an outer binding, and it is the whole
of what the union missed. Class bodies and comprehensions are deliberately
approximated toward *used*: this gate may miss a dead import, and must never
invent one.

Validated against the tool it replaces rather than against my reasoning about
it: on the tree as it stood, this reported **exactly** the twelve `F401` hits
`flake8 --select=F401` did — same files, same lines, same names.

## What it does not do

Only unused imports. Not undefined names, not shadowing, not any of the rest of
`F`. Those were measured at zero when this landed, and a gate that grew to cover
them would be a linter written by hand — at which point take the dependency
instead and be honest about it.

The escape hatch is `# noqa: F401` on the import line, spelled the way flake8
spells it — and that spelling was already in this tree before this gate was,
which is the finding in miniature. `cli/canvas/shell.py` annotates two imports
it makes purely to see whether they *work*, and annotates them for a linter that
has never run here. The notation crossed over from the wider Python world by
habit; the check it addresses did not.

The suppressions are enumerated below rather than merely permitted, and that
test fails in **both** directions: a new one has to be written down, and one
that stops being needed has to be removed. It is not an allowlist standing in
for a predicate — the predicate is the walk and it covers every file. It is a
record of where a human overrode it, which is the part worth making loud.
"""

from __future__ import annotations

import ast
from pathlib import Path

from skyboss.helpers import PROJECT_ROOT

SKIPPED_DIRS = {".git", ".venv", "vendor", "node_modules", "__pycache__", "dist", "tmp"}

#: `from __future__ import ...` binds a name nothing reads. It is a compiler
#: directive wearing an import's clothes.
FUTURE = "__future__"

#: Spelled as flake8 spells it, so the annotation survives ever taking that
#: dependency. A bare `# noqa` is deliberately not honoured: silencing every
#: future rule to quiet this one is not a trade anybody meant to make.
SUPPRESSION = "noqa: F401"

#: What starts a new namespace for an import. Lambdas and comprehensions cannot
#: contain one, so their loads are counted against the enclosing scope.
SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

#: Every override, and why. An import that exists to be *attempted* binds a name
#: nothing reads on purpose: `shell.available()` asks whether this machine has a
#: webview behind `pywebview` at all, and the answer is whether the import raised.
SUPPRESSED = {
    "skyboss/canvas/shell.py:74",  # gi.repository.WebKit2 — probed, never called
    "skyboss/canvas/shell.py:76",  # webview — probed, never called
}


def _python_files() -> list[Path]:
    return sorted(
        p for p in PROJECT_ROOT.rglob("*.py") if p.is_file() and not SKIPPED_DIRS & set(p.parts)
    )


def _label(path: Path) -> str:
    """Repo-relative where that means anything. The controls below parse a file
    in a tmp dir, and a checker that raises on its own fixture is not one whose
    null anybody can trust."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return path.name


class _Scope:
    """One namespace: what it binds, what it reads, what nests inside it."""

    def __init__(self) -> None:
        self.imports: list[tuple[str, int, str]] = []  # local name, line, what was written
        self.binds: set[str] = set()
        self.loads: set[str] = set()
        self.children: list[_Scope] = []

    def sees(self, name: str) -> bool:
        """Is `name` read here, or anywhere nested that has not rebound it?

        The rebinding is the whole point. A function that imports `pytest` for
        itself is not a reader of the module's `pytest`, which is how a
        module-level import can be dead in a file that says the name forty times.
        """
        return name in self.loads or any(
            child.sees(name) for child in self.children if name not in child.binds
        )


def _walk(node: ast.AST, scope: _Scope) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, SCOPES):
            nested = _Scope()
            scope.children.append(nested)
            scope.binds.add(getattr(child, "name", ""))
            _walk(child, nested)
            continue
        if isinstance(child, ast.Import):
            for alias in child.names:
                local = alias.asname or alias.name.split(".")[0]
                scope.imports.append((local, child.lineno, alias.name))
                scope.binds.add(local)
        elif isinstance(child, ast.ImportFrom) and child.module != FUTURE:
            for alias in child.names:
                if alias.name == "*":
                    continue  # unknowable; pyflakes gives up here too
                local = alias.asname or alias.name
                scope.imports.append((local, child.lineno, alias.name))
                scope.binds.add(local)
        elif isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Load):
                scope.loads.add(child.id)
            else:
                scope.binds.add(child.id)
        _walk(child, scope)


def _report(scope: _Scope, path: Path, lines: list[str], out: list[str]) -> None:
    for local, line, written in scope.imports:
        if SUPPRESSION in lines[line - 1] or scope.sees(local):
            continue
        out.append(f"{_label(path)}:{line}: {written} imported but unused")
    for child in scope.children:
        _report(child, path, lines, out)


def _unused(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    module = _Scope()
    _walk(ast.parse("\n".join(lines), filename=str(path)), module)
    out: list[str] = []
    _report(module, path, lines, out)
    return sorted(out)


def test_no_module_imports_a_name_it_never_uses():
    """The gate the component copies arrived without."""
    found = [problem for path in _python_files() for problem in _unused(path)]
    assert not found, "unused imports:\n  " + "\n  ".join(found)


def test_every_suppression_is_the_declared_set():
    """Both directions: a new override written down, a stale one removed."""
    using = set()
    for path in _python_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        module = _Scope()
        _walk(ast.parse("\n".join(lines), filename=str(path)), module)

        def collect(scope: _Scope) -> None:
            for _, line, _ in scope.imports:
                if SUPPRESSION in lines[line - 1]:
                    using.add(f"{_label(path)}:{line}")
            for child in scope.children:
                collect(child)

        collect(module)
    assert using == SUPPRESSED, (
        f"suppressions changed — added {sorted(using - SUPPRESSED)}, "
        f"stale {sorted(SUPPRESSED - using)}"
    )


def _check(tmp_path: Path, source: str) -> list[str]:
    sample = tmp_path / "sample.py"
    sample.write_text(source, encoding="utf-8")
    return _unused(sample)


def test_the_checker_sees_an_unused_import(tmp_path):
    """A positive control. A checker reporting nothing is indistinguishable from
    one that cannot see, and this suite has been caught by that before."""
    found = _check(tmp_path, "import os\nimport sys\n\nprint(sys.argv)\n")
    assert len(found) == 1 and "os imported but unused" in found[0], found


def test_the_checker_sees_a_binding_a_nested_scope_shadows(tmp_path):
    """The case a whole-file usage scan clears wrongly, and the reason for scopes.

    `pytest` is loaded twice below and the module-level import is still dead:
    both readers imported their own.
    """
    found = _check(
        tmp_path,
        "import pytest\n\n\ndef a():\n    import pytest\n\n    return pytest.raises\n",
    )
    assert len(found) == 1 and found[0].endswith("sample.py:1: pytest imported but unused"), found


def test_the_checker_sees_a_function_local_import_its_function_ignores(tmp_path):
    """A sibling function using its own `time` must not vouch for this one."""
    found = _check(
        tmp_path,
        "def a():\n    import time\n\n    return 1\n\n\ndef b():\n    import time\n\n    return time.monotonic()\n",
    )
    assert len(found) == 1 and found[0].endswith("sample.py:2: time imported but unused"), found


def test_the_checker_does_not_flag_two_functions_importing_the_same_name(tmp_path):
    """The 302-hit false positive that killed the duplicate-binding rule."""
    assert (
        _check(
            tmp_path,
            "def a():\n    import time\n\n    return time.monotonic()\n\n\n"
            "def b():\n    import time\n\n    return time.monotonic()\n",
        )
        == []
    )


def test_the_checker_counts_a_use_from_a_nested_scope(tmp_path):
    """A module import read only inside a function is used."""
    assert _check(tmp_path, "import os\n\n\ndef a():\n    return os.sep\n") == []


def test_the_checker_honours_the_suppression(tmp_path):
    assert _check(tmp_path, f"import os  # {SUPPRESSION}\n") == []


def test_the_checker_does_not_flag_a_dotted_or_renamed_import(tmp_path):
    """`import a.b` binds `a`, and `import a.b as c` binds `c`."""
    assert _check(tmp_path, "import os.path\nimport os.path as p\n\nprint(os.sep, p.sep)\n") == []


def test_the_checker_counts_a_name_used_only_in_an_annotation(tmp_path):
    """Postponed annotations are unevaluated, not unparsed."""
    assert (
        _check(
            tmp_path,
            "from __future__ import annotations\n\nfrom pathlib import Path\n\n\ndef f(p: Path) -> None: ...\n",
        )
        == []
    )
