"""The wordmark in prose, the command in code spans.

The project is **sky.boss**. `sb` is what you type — the binary, the argv's
first word, the window class. They are not interchangeable, and this repo
spent its first week proving it: the CLI was `tb` until 2026-08-27, and the
rename that made it `sb` was a find-and-replace over text that had already
been through one. What that leaves behind is a document describing *the
command* where it means *the project* — 368 of them when this check was
written, 195 in Markdown and 173 in docstrings and comments, and the
fingerprint was `a sb command`, which appeared fifteen times. Nobody writing
that fresh writes `a sb`.

The sibling repos never had the problem: jam-sense's and breeze-brain's
`CLAUDE.md` between them name their own binary in prose exactly once. They say
`jam.sense` and `breeze.brain`, because a wordmark is what the naming canon
(`skyrow-workspace/strategy/naming.md`) reserves for prose.

So the rule, and it is the whole rule:

    Outside code, the project is sky.boss. `sb` appears only inside
    backticks, and only as the literal thing being typed.

That is testable rather than remembered, which is the point — the same strip
that finds a violation is the one that defines it. Fences, indented blocks,
inline spans and HTML tags come out; whatever still says the command is prose
that means the project.

**The mask preserves length.** Every strip substitutes spaces rather than
deleting, so an offset into the mask is an offset into the file. That is what
lets a failure name a real line — and it is why the one-off sweep that closed
those 368 cases could edit at exactly the positions this check reports,
rather than running a find-and-replace of its own. A third one of those is the
thing this file exists to prevent.

**What is deliberately not scanned.** `.html` is out for the reason it is out
of `tests/test_theme.py`: `docs/design/*.dc.html` are design artboards, drawn
elsewhere and carried here as renders, and editing one by hand is how a render
stops matching its source. Identifiers are out by construction — `$SB_HOME`,
`SB_STATE`, `sb.fish` and `readme-banner.png`'s alt text all fail the word
boundary or live inside a tag, so nothing has to name them. And a dated record
of the old spelling stays: the sentences saying the CLI *was* `tb` are facts
about the past, and they are already in backticks, where the rule leaves them.
"""

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

from cli.helpers import PROJECT_ROOT

# The command as a standalone word. The lookarounds are what exempt every
# identifier that merely starts with the letters: `$SB_HOME`, `sb.fish`.
BARE = re.compile(r"(?<![\w./$-])sb(?![\w./-])")

FENCE = re.compile(r"^\s*```")
INDENTED = re.compile(r"^(?: {4,}|\t)\S")
# A run of backticks opens a span and an equal run closes it, which is what
# lets `` ``sky.boss`` `` (the reStructuredText spelling, used in docstrings) sit
# beside the one-backtick form. A *backslashed* backtick is neither: CLAUDE.md
# writes ``html\` `` for the template-literal opener, and reading that as a
# delimiter desynchronised every span in the file after it — which showed up
# as this check reporting `` `sb` is installed on PATH `` as prose.
ESCAPED_TICK = re.compile(r"\\`")
CODE_SPAN = re.compile(r"(`+)[\s\S]*?\1")
HTML_TAG = re.compile(r"<[^>]*>", re.DOTALL)

SKIPPED_DIRS = {".git", ".venv", "vendor", "node_modules", "__pycache__", "dist"}
# Gitignored; the operator's half, and not published prose.
SKIPPED_FILES = {"CLAUDE.local.md"}

_JS_STRING = re.compile(
    r"""(?<!\\)(?:'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`)""", re.DOTALL
)
_JS_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)


def _spans_blanked(text: str) -> str:
    """Every code span replaced by spaces, escaped backticks left out of it."""
    neutral = ESCAPED_TICK.sub(r"\\x", text)
    out = list(text)
    for match in CODE_SPAN.finditer(neutral):
        out[match.start() : match.end()] = list(_blank(match.group(0)))
    return "".join(out)


def _blank(text: str) -> str:
    """Same shape, no content — newlines survive so line numbers do."""
    return "".join("\n" if c == "\n" else " " for c in text)


def tracked(suffix: str) -> list[Path]:
    return sorted(
        p
        for p in PROJECT_ROOT.rglob(f"*{suffix}")
        if p.is_file() and not SKIPPED_DIRS & set(p.parts) and p.name not in SKIPPED_FILES
    )


def _markdown_mask(text: str) -> str:
    kept: list[str] = []
    fenced = False
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\n")
        if FENCE.match(body):
            fenced = not fenced
            kept.append(_blank(line))
            continue
        kept.append(_blank(line) if fenced or INDENTED.match(body) else line)
    mask = "".join(kept)
    mask = _spans_blanked(mask)
    return HTML_TAG.sub(lambda m: _blank(m.group(0)), mask)


def _block_mask(block: str) -> str:
    """A comment or docstring, masked like the Markdown it is written in.

    Indentation is measured *relative to the block*, because a docstring
    nested in a function is already indented and its worked examples are
    indented again from there. Without this a `sb data --refresh 30` shown
    under **Examples** would read as prose and the rule would forbid the one
    place the command genuinely belongs.
    """
    lines = block.splitlines(keepends=True)
    bodies = [ln.rstrip("\n") for ln in lines[1:] if ln.strip()]
    base = min((len(b) - len(b.lstrip()) for b in bodies), default=0)
    kept: list[str] = []
    fenced = False
    for i, line in enumerate(lines):
        body = line.rstrip("\n")
        if FENCE.match(body):
            fenced = not fenced
            kept.append(_blank(line))
        elif fenced or (i and INDENTED.match(body[base:])):
            kept.append(_blank(line))
        else:
            kept.append(line)
    return _spans_blanked("".join(kept))


def _python_mask(text: str) -> str:
    """Comments and docstrings — the two places a `.py` file holds prose."""
    lines = text.splitlines(keepends=True)
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line)
    mask = list(_blank(text))

    def reveal(start: int, end: int) -> None:
        mask[start:end] = list(_block_mask(text[start:end]))

    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            reveal(
                starts[token.start[0] - 1] + token.start[1],
                starts[token.end[0] - 1] + token.end[1],
            )
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
            continue
        if isinstance(first.value.value, str):
            reveal(
                starts[first.lineno - 1] + first.col_offset,
                starts[first.end_lineno - 1] + first.end_col_offset,
            )
    return "".join(mask)


def _javascript_mask(text: str) -> str:
    """Comments only. Strings are blanked first, because a URL's `//` does not
    start one and a template literal may hold a whole page."""
    without_strings = _JS_STRING.sub(lambda m: _blank(m.group(0)), text)
    mask = list(_blank(text))
    for match in _JS_COMMENT.finditer(without_strings):
        mask[match.start() : match.end()] = list(_block_mask(text[match.start() : match.end()]))
    return "".join(mask)


MASKS = {
    ".md": lambda p: _markdown_mask(p.read_text()),
    ".py": lambda p: _python_mask(p.read_text()),
    ".js": lambda p: _javascript_mask(p.read_text()),
}


def offences(path: Path) -> list[int]:
    """Every offset into `path` where the command stands in for the project."""
    return [m.start() for m in BARE.finditer(MASKS[path.suffix](path))]


def _report(path: Path, mask: str, hits: list[int]) -> str:
    rel = path.relative_to(PROJECT_ROOT)
    # The newline is bound outside the f-string on purpose. A backslash *inside*
    # an f-string expression is PEP 701, which lands in 3.12, and `README.md`
    # promises 3.11 — so this file failed to import there and took the whole
    # suite's collection with it. Found by the CI matrix on its first run.
    newline = "\n"
    return ", ".join(f"{rel}:{mask.count(newline, 0, at) + 1}" for at in hits)


@pytest.mark.parametrize(
    "path",
    [p for suffix in MASKS for p in tracked(suffix)],
    ids=lambda p: str(p.relative_to(PROJECT_ROOT)),
)
def test_prose_says_sky_boss(path: Path):
    """`sb` outside a code span is the binary standing in for the project."""
    mask = MASKS[path.suffix](path)
    hits = [m.start() for m in BARE.finditer(mask)]
    assert not hits, (
        f"the bare command in prose at {_report(path, mask, hits)} — the project is "
        "sky.boss; `sb` belongs in backticks, naming what is typed"
    )


def test_the_check_can_still_see_a_violation():
    """A mask this aggressive could pass by blanking everything. Each exempt
    form is exercised beside the prose it must not swallow."""
    exempt = (
        "`sb run`, $SB_HOME, sb.fish, <img alt='sb --help'>\n"
        "\n```\nsb data -- x\n```\n"
        "\n    sb read -- y\n"
    )
    assert not BARE.findall(_markdown_mask(exempt))
    assert len(BARE.findall(_markdown_mask("sb never guesses; sb's rule.\n"))) == 2
    assert BARE.findall(_python_mask("# sb never guesses\nx = 'sb'\n"))
    assert not BARE.findall(_python_mask("# `sb run` never guesses\nrun('sb', 'x')\n"))
    spans = 'r' + r'"""A human, ``sb``, and `html\`` after it."""' + "\n"
    assert not BARE.findall(_python_mask(spans))
    assert BARE.findall(_python_mask('"""sb never guesses."""\n'))
    example = 'def f():\n    """Examples.\n\n        sb data -- x\n    """\n'
    assert not BARE.findall(_python_mask(example))
    assert BARE.findall(_javascript_mask("// sb never guesses\nconst a = 'sb'\n"))
    assert not BARE.findall(_javascript_mask("// see https://x/y\nconst a = 'sb ui'\n"))


def test_the_mask_is_the_same_length_as_the_file():
    """Offsets are the whole contract: a failure names a line by counting
    newlines in the mask, so a strip that shortened it would point at the
    wrong one — and silently, which is the only kind of wrong that matters."""
    for suffix, mask_of in MASKS.items():
        for path in tracked(suffix)[:8]:
            assert len(mask_of(path)) == len(path.read_text()), path
