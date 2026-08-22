"""Highlight — lexical tint for followed lines. See [[highlight]].

**Recognition for tinting only.** The text stays verbatim, nothing is
filtered, folded or reordered, and a missed match costs a color, not a fact.
That asymmetry is what let this through the boundary [[file-follow]] drew:
a tint that misfires is visibly cosmetic; a column that misfires is invisibly
wrong. Structure claims stay refused — marks tint characters, they never
become columns, fields or a `view`.

**Shape, not vocabulary.** A leading ISO timestamp, a job tag in brackets, a
URL — patterns a regex can name without an opinion. "This line is an error"
is a judgment, and judgments belong to the escalation ladder's Rule branch,
with the operator holding the pen, as a future round here.

**One rule set, applied everywhere a followed line renders.** The terminal
forms tint through `spans()`; the canvas receives each frame line's `marks`
beside its verbatim text and applies them dumbly — offsets into the text, so
the payload the window appends is provably the payload the file carried. The
frontend has no test runner, and two renderers holding their own opinions
would drift the week they were written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# (start, end, role) — offsets into the line, role names from cli/theme.py.
Mark = tuple[int, int, str]

# A leading ISO-8601 stamp, seconds required, fraction and zone optional. The
# least informative and most repeated thing on every line; dimming it is what
# makes everything else legible.
_TIMESTAMP = re.compile(
    r"\A\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)

# A [bracketed-tag]: short, no nesting, no inner whitespace-only. The job's
# name — the boundary the eye actually scans for in a multi-job log.
_TAG = re.compile(r"\[[^\[\]\s][^\[\]]{0,63}\]")

# A URL. Links are destinations; they should look like it.
_URL = re.compile(r"https?://[^\s<>\"]+")

# Punctuation a sentence hangs on a URL's end without meaning it.
_TRAILING = ".,;:!?'\")]}"

# ---------------------------------------------------------------- round 2
#
# The rest of the shapes an agent's log actually contains, each taking the
# role its *kind* already has in a table cell (`cli/output.py`'s `_cell`:
# numbers `tb.num`, path-like strings `tb.path`). One value vocabulary across
# both surfaces — a number that looked like a number in `tb data` and like
# prose in `tb follow` would be two palettes wearing one name. See [[highlight]].

# Inline code. Takes the *path* role rather than a hue of its own: a code span
# and a path are the same kind of thing — a literal, an identifier — and the
# design system has no third colour to spend on the distinction. A violet was
# prototyped, looked good, and is exactly how a second palette starts.
_CODE = re.compile(r"`[^`\n]{1,200}`")

# A path: absolute, or anything with an interior slash, or a dotted filename —
# each with an optional `:line`. The `:line` suffix is why this beats tinting
# the number separately: `report.py:75` is one location, not a file and a 75.
_PATH = re.compile(
    # A dotfile directory keeps its dot: `\b` cannot start a match at `.`, so
    # `.github/scripts/x.sh` used to tint from `github` and leave the dot bare.
    r"(?<![\w./-])(?:\.{1,2}/|\.?[\w@+-][\w.@+-]*/)[\w.@+-]+(?:/[\w.@+-]+)*(?::\d+)?"
    r"|(?:/[\w.@+-]+){2,}(?::\d+)?"
    r"|\b[\w@+-]+\.[a-z]{1,5}(?::\d+)\b"
)

# A date or a clock time *inside* the line. Deliberately the opposite job from
# the leading timestamp above: that one is the most repeated and least
# informative thing on every line, so it is dimmed; a date in the prose is a
# fact someone wrote down, so it reads as the value it is.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")

# `#925` — an issue or PR reference, and the single most scanned token in a
# queue-working log. It is a number; it gets the number's role.
_REF = re.compile(r"#\d+")

# A number, with an attached `%` or short unit — `8%`, `90m`, `10.2`, `20000`.
#
# **Attached only, and this is the rule that was got wrong first.** A version
# allowing a space before the unit tinted `8 issue`, `104 archive` and
# `50 candidate` — the numeral plus whatever English word happened to follow
# it. That is invisible in a unit test and unmissable in a rendered log, which
# is why the rules were prototyped against a real one before being written.
# The lookarounds are not decoration. `\b\d` happily matches the `7` inside the
# git SHA `7d9d878` and tints one character of an identifier, which looks like
# a rendering fault rather than a highlight; requiring plain text on both sides
# means a number is tinted only when it is a number.
_NUMBER = re.compile(r"(?<![\w-])\d[\d,_]*(?:\.\d+)?(?:%|[a-zA-Z]{1,3})?(?![\w-])")

# ---------------------------------------------------------------- round 4
#
# **A glyph that means one thing everywhere, and a word that *is* its own
# colour.** Both are still shape rather than judgment, which is the line this
# module has held since round 1 — but the reasoning is worth stating because
# they look like the vocabulary rules that are refused.
#
# A check mark is not tb deciding a line went well; it is tb reading a symbol
# whose meaning is not in dispute, and `tb data` already renders a true
# boolean as a green `✓` and a false one as a red `✗` (`_cell` in
# cli/output.py). One value vocabulary, two surfaces — a check is green in a
# table cell, so it is green in a log line.
#
# `red` is the same claim in its strongest form: the word denotes the colour.
# There is no inference between "the text says red" and "show it red", which
# is exactly what separates this from "the text says ERROR, so it is bad".
_OK_GLYPH = re.compile(r"[\u2713\u2714\u2705\u2611]\uFE0F?")
_FAIL_GLYPH = re.compile(r"[\u2716\u2717\u2718\u274C\u2612]\uFE0F?|\U0001F534")
_WARN_GLYPH = re.compile(r"[\u26A0\u26D4]\uFE0F?|\U0001F7E1")
_OK_EMOJI = re.compile(r"\U0001F7E2|\U0001F7E9")
_INFO_GLYPH = re.compile(r"\U0001F535|\U0001F7E6")

# A word that names a colour, in that colour. Standalone only — `\b` on both
# sides, so `reported` is not `red`.
_COLOUR_WORDS = {
    "red": "tb.fail",
    "green": "tb.ok",
    "yellow": "tb.warn",
    "amber": "tb.warn",
    "orange": "tb.warn",
    "blue": "tb.accent",
    "grey": "tb.muted",
    "gray": "tb.muted",
}
_COLOUR_WORD = re.compile(
    r"\b(?:" + "|".join(sorted(_COLOUR_WORDS)) + r")\b", re.IGNORECASE
)

# Markdown emphasis, which the agent prose in these logs leans on for its
# findings. **Bold is a weight, not a colour**, so it composes with whatever
# colour a mark already carries instead of competing for the same slot — the
# role becomes `bold tb.path`, which Rich reads directly and the canvas splits
# into two classes. The `**` markers stay on screen: marks tint characters and
# never alter them, and a renderer that hid them would be editing the log.
_BOLD = re.compile(r"\*\*(?=\S)[^\n]{1,300}?\*\*")
_HEADING = re.compile(r"\A#{1,6} +\S")

# What one line may carry. Every mark rides to the canvas inside the frame, and
# round 2 turned three rules into ten — a dense numeric line can now produce
# dozens where it used to produce three. The tail is dropped rather than the
# line, the same rule every surface here has had since the first unbounded
# render froze one.
MAX_MARKS = 64

# In priority order after the timestamp and tag, which are positional. First
# match wins and nothing nests, so a number inside a code span or a `:75`
# inside a path is claimed once, by the outer shape.
_RULES: tuple[tuple[re.Pattern, str, bool], ...] = (
    (_CODE, "tb.path", False),
    (_URL, "tb.path", True),
    (_OK_GLYPH, "tb.ok", False),
    (_OK_EMOJI, "tb.ok", False),
    (_FAIL_GLYPH, "tb.fail", False),
    (_WARN_GLYPH, "tb.warn", False),
    (_INFO_GLYPH, "tb.accent", False),
    (_PATH, "tb.path", True),
    (_DATE, "tb.num", False),
    (_TIME, "tb.num", False),
    (_REF, "tb.num", False),
    (_NUMBER, "tb.num", True),
)


def marks(text: str, ruleset: "Ruleset | None" = None) -> list[Mark]:
    """The line's lexical marks: sorted, non-overlapping, first match wins.

    Pure, and bounded: every rule is a linear scan and the result is capped at
    `MAX_MARKS`. The text is never altered — a caller holding the marks and
    the line holds everything.

    A `ruleset` is the operator's declared vocabulary ([[highlight]] round 3).
    **It runs last and claims only text no built-in rule claimed**, so a
    timestamp stays muted and a tag stays a tag whatever the operator writes.
    Letting a declaration win would make every built-in rule conditional on a
    file tb does not ship, and the first surprising log would be
    unexplainable.
    """
    found: list[Mark] = []

    stamp = _TIMESTAMP.match(text)
    if stamp:
        found.append((0, stamp.end(), "tb.muted"))

    # The tag rule is positional: immediately after the timestamp (spaces
    # allowed) or at line start — a bracket mid-prose is prose.
    at = stamp.end() if stamp else 0
    while at < len(text) and text[at] == " ":
        at += 1
    tag = _TAG.match(text, at)
    if tag:
        found.append((tag.start(), tag.end(), "tb.accent"))

    for pattern, role, trim in _RULES:
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            if trim:
                # Punctuation a sentence hangs on the end without meaning it.
                while end > start and text[end - 1] in _TRAILING:
                    end -= 1
            if end <= start:
                continue
            if any(start < e and s < end for s, e, _ in found):
                continue  # first match wins, no nesting
            found.append((start, end, role))

    # A colour word takes the colour it names. Its role comes from the word
    # itself rather than from the rule, which is why it cannot ride `_RULES`.
    for match in _COLOUR_WORD.finditer(text):
        start, end = match.start(), match.end()
        if any(start < e and s < end for s, e, _ in found):
            continue
        found.append((start, end, _COLOUR_WORDS[match.group(0).lower()]))

    if ruleset is not None:
        for pattern, role in ruleset.rules:
            for match in pattern.finditer(text):
                start, end = match.start(), match.end()
                if end <= start:
                    continue  # a zero-width pattern marks nothing
                if any(start < e and s < end for s, e, _ in found):
                    continue
                found.append((start, end, role))
                if len(found) >= MAX_MARKS:
                    break

    return _emphasise(text, sorted(found))[:MAX_MARKS]


def _emphasise(text: str, coloured: list[Mark]) -> list[Mark]:
    """Fold markdown emphasis into the colour marks as a *weight*.

    Bold is the one attribute here that is not a colour, so it does not
    compete for the slot: a mark inside an emphasised range keeps its role and
    gains `bold`, and the stretches with no colour of their own become bold on
    their own. Rich reads `"bold tb.path"` directly; the canvas splits it into
    two classes. Nothing overlaps and the list stays flat, which is what lets
    the frontend keep applying marks dumbly.
    """
    ranges = [(m.start(), m.end()) for m in _BOLD.finditer(text)]
    if _HEADING.match(text):
        ranges.append((0, len(text)))
    if not ranges:
        return coloured

    out: list[Mark] = []
    for start, end, role in coloured:
        inside = any(s <= start and end <= e for s, e in ranges)
        out.append((start, end, f"bold {role}" if inside else role))

    # The stretches an emphasised range covers that no colour mark claimed.
    for start, end in ranges:
        cursor = start
        for s, e, _ in sorted(out):
            if e <= cursor or s >= end:
                continue
            if s > cursor:
                out.append((cursor, s, "bold"))
            cursor = max(cursor, e)
        if cursor < end:
            out.append((cursor, end, "bold"))

    return sorted(out)


def spans(text: str, ruleset: "Ruleset | None" = None) -> list[tuple[str, str | None]]:
    """The line as (chunk, role) spans — the same shape the chrome bands use,
    so both terminal forms tint through the same assembler and untinted text
    rides through with role None."""
    out: list[tuple[str, str | None]] = []
    cursor = 0
    for start, end, role in marks(text, ruleset):
        if start > cursor:
            out.append((text[cursor:start], None))
        out.append((text[start:end], role))
        cursor = end
    if cursor < len(text) or not out:
        out.append((text[cursor:], None))
    return out


# ============================================================================
# Declared rules — the operator's own words. See [[highlight]] round 3.
# ============================================================================
#
# **Shape is tb's; vocabulary is the operator's.** `ESCALATE`, `Done.`,
# `handing to 'claude'` — the words that matter in one operator's log and mean
# nothing in anyone else's. tb cannot know them and must not guess, for exactly
# the reason it does not guess columns ([[capture]]): a word list is a judgment
# wearing a regex's clothes. So it is declared, in the file that already holds
# declarations about output, and named on the command that follows the stream.

# Longer than this is not a pattern, it is a program. The cap is a guard
# against a pasted mistake, not against an adversary — this is the operator's
# own file on their own machine, at `tools.toml`'s trust level.
MAX_PATTERN = 200

# What a declared rule may ask for: the palette's role names, minus the `tb.`
# prefix the operator should not have to type. A role the theme does not
# define is refused by name — nothing operator-authored gets near a colour.
def _roles() -> dict[str, str]:
    from cli.theme import STYLES

    return {name.removeprefix("tb."): name for name in STYLES}


@dataclass(frozen=True)
class Ruleset:
    """One named set of operator patterns, already compiled and validated."""

    name: str
    description: str = ""
    rules: tuple[tuple[re.Pattern, str], ...] = ()


def parse_rulesets(raw: dict) -> tuple[list[Ruleset], list[str]]:
    """Validate `[highlight.<name>]` declarations. Pure — reads no file.

    One bad ruleset must not cost the operator the other nine, and one bad
    *rule* must not cost the ruleset: both are skipped and named, the way a
    malformed format and a malformed tool already are.
    """
    if "__error__" in raw:
        return [], [raw["__error__"]]

    roles = _roles()
    found: list[Ruleset] = []
    problems: list[str] = []

    for name, body in (raw.get("highlight") or {}).items():
        if not isinstance(body, dict):
            problems.append(f"highlight {name!r}: not a table")
            continue
        declared = body.get("rules")
        if not isinstance(declared, list) or not declared:
            problems.append(f"highlight {name!r}: rules must be a non-empty list")
            continue

        compiled: list[tuple[re.Pattern, str]] = []
        for index, rule in enumerate(declared):
            problem = _check_rule(rule, roles)
            if problem:
                problems.append(f"highlight {name!r} rule {index + 1}: {problem}")
                continue
            compiled.append((re.compile(rule["pattern"]), roles[rule["role"]]))

        if compiled:
            found.append(
                Ruleset(
                    name=name,
                    description=str(body.get("description", "")),
                    rules=tuple(compiled),
                )
            )

    return found, problems


def _check_rule(rule, roles: dict[str, str]) -> str | None:
    """The reason this rule is unusable, or None."""
    if not isinstance(rule, dict):
        return "not a table"
    pattern = rule.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return "pattern must be a non-empty string"
    if len(pattern) > MAX_PATTERN:
        return f"pattern is longer than {MAX_PATTERN} characters"
    role = rule.get("role")
    if role not in roles:
        # Names the alternatives rather than just refusing: the mistake this
        # catches is someone writing a colour, and the fix is to say which
        # words the palette answers to.
        return f"role must be one of {', '.join(sorted(roles))} — not {role!r}"
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"pattern does not compile: {exc}"
    return None


def load_rulesets(home: Path | None = None) -> tuple[list[Ruleset], list[str]]:
    """Every declared ruleset, and every reason one was skipped.

    Read at use rather than cached, like the formats beside them: editing the
    file under a pinned window is the REPL.
    """
    from cli import capture as capture_

    return parse_rulesets(capture_.read(home))


def resolve(name: str, home: Path | None = None) -> tuple[Ruleset | None, str | None]:
    """`--highlight <name>` down to a ruleset, or the reason it is not one."""
    found, problems = load_rulesets(home)
    for ruleset in found:
        if ruleset.name == name:
            return ruleset, None
    mine = [p for p in problems if p.startswith(f"highlight {name!r}")]
    if mine:
        return None, mine[0]
    known = ", ".join(sorted(r.name for r in found)) or "none declared"
    return None, f"no highlight named {name!r} — declared: {known}"
