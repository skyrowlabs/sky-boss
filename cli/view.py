"""Shaping a foreign CLI's rows into a table worth reading.

**A view is not the data.** Nothing here edits a row. `shape` returns a
*description* of how to present them — which columns, in what order, at what
relative width — and the envelope carries it beside `data` rather than instead
of it. `tb --json data | jq` keeps every field, and so does any future MCP
consumer; dropping a column to make a table prettier would be trading a machine
contract for a human one.

**Why this is Python and not JavaScript.** The frontend has no test runner and
adding one means npm. Putting the decisions here makes the interesting half the
tested half, and leaves `render.js` doing something dumb enough to be obviously
correct — *render these columns in this order*. It also means there is exactly
one opinion about column selection; two renderers holding their own would drift
the week after they were written.

Only `data` calls this. tb's own commands return fields a person chose
deliberately, and auto-dropping one of those would be a bug wearing a feature's
clothes. See [[table-views]].
"""

from __future__ import annotations

import re

# There is no column budget here. There was — a fixed count of eight — and it
# hid the same two columns whether the window had room for them or not, because
# a *count* cannot answer a question about *width* and nothing in this module
# knows a width. Fitting is now each renderer's, against the width only it
# knows; this module decides which columns are worth showing and in what order.
# See [[table-views]] round 3.

# A string column wider than this is prose — something you read once you have
# found the row, not something you scan across rows.
PROSE_WIDTH = 40

# A value this wide or wider, all hex, uniform length, is an opaque identifier.
# 32 admits an md5 and a git sha and excludes a hex colour or a short id.
OPAQUE_MIN = 32

# Width per unit of flex. Derived from the shape of real output rather than
# chosen: it puts a 3-character number at 1 and a 78-character title at the cap.
FLEX_UNIT = 12
FLEX_MAX = 5

# No column narrower than its own header, up to this. A truncated *value* is a
# readable table with a detail elided; a truncated *header* is a column you
# cannot identify at all, which is strictly worse. Capped so that one
# pathologically long key cannot squeeze every other column out.
LABEL_CAP = 14

# No inline column wider than this, however long its values. Prose leaves the
# row entirely now, so anything still claiming forty characters is a value that
# will read just as well clipped.
NATURAL_CAP = 40

_HEX = re.compile(r"\A[0-9a-fA-F]+\Z")

# Values that count as nothing. `0` and `False` are absent from this on
# purpose — a count of zero is an answer, and "0 failed" is often the answer
# you opened the window for.
_EMPTY = (None, "", [], {})


def resolve(row: dict, key: str):
    """Look a dotted path up in a row: `checks.failed` reaches inside `checks`.

    Only `--cols` produces dotted keys. The heuristic never invents one, because
    flattening a nested dict turns one column into six and makes the crowding
    worse — the thing we are here to fix. See `summarise_mapping`.
    """
    current = row
    for part in key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def summarise_mapping(value: dict) -> str:
    """A nested dict as one cell: `passed=2 skipped=7`.

    Zero and null members are dropped, which is what makes this fit — jam's
    `checks` carries six counters of which two are ever interesting. The
    exception is a dict where *everything* is zero, which summarises to nothing
    at all and would render as an empty cell that looks like a bug; it gets the
    empty marker instead, and the caller styles it dim.
    """
    parts = [f"{k}={v}" for k, v in value.items() if v not in _EMPTY and v != 0]
    return " ".join(parts) if parts else "—"


def _cell_width(value) -> int:
    """How wide this value renders. Estimation only — each renderer keeps its
    own text, and this exists to weight a column rather than to draw one."""
    if value is None:
        return 1
    if isinstance(value, bool):
        return 3
    if isinstance(value, dict):
        return len(summarise_mapping(value))
    if isinstance(value, (list, tuple)):
        return len(", ".join(str(v) for v in value)) if value else 1
    return len(str(value))


def _values(rows: list[dict], key: str) -> list:
    return [row.get(key) for row in rows]


def _all_empty(values: list) -> bool:
    """Rule 1 — a column that has never once carried a value is pure width."""
    return all(v in _EMPTY for v in values)


def _is_opaque(values: list) -> bool:
    """Rule 2 — an identifier you would never read: a sha, a digest.

    Matched on the *values*, never on the name. `head` is a sha and `head_ref`
    is a branch, they differ by four characters, and the next tool will call its
    sha something else entirely. Uniform length is what separates a digest from
    a column that merely happens to be hex-ish.
    """
    present = [v for v in values if v not in _EMPTY]
    if not present or not all(isinstance(v, str) for v in present):
        return False
    lengths = {len(v) for v in present}
    if len(lengths) != 1 or lengths.pop() < OPAQUE_MIN:
        return False
    return all(_HEX.match(v) for v in present)


def _is_mapping(values: list) -> bool:
    """Rule 3 — every present value is a nested dict, so it can be summarised."""
    present = [v for v in values if v is not None]
    return bool(present) and all(isinstance(v, dict) for v in present)


def _is_numeric(values: list) -> bool:
    present = [v for v in values if v is not None]
    return bool(present) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in present
    )


def _flex(width: int) -> int:
    """A proportional width, not a character count.

    A character count is not portable: the canvas renders into a *draggable*
    window that has no fixed width to count against, and gets its clipping from
    CSS at whatever width the window happens to be. A weight maps onto `flex`
    there and onto a column `ratio` in Rich. One primitive, two renderings.
    """
    return min(FLEX_MAX, max(1, round(width / FLEX_UNIT)))


def columns_of(rows: list[dict]) -> list[str]:
    """Every key, in first-seen order across every row rather than from the
    first row alone. A row carrying a field the others lack would otherwise
    drop it silently, which for a table about what is wrong is exactly the
    wrong thing to lose."""
    seen: list[str] = []
    for row in rows:
        for key in row:
            if key not in seen:
                seen.append(key)
    return seen


def is_rows(data) -> bool:
    """A non-empty list of plain objects — the only thing there is to shape."""
    return (
        isinstance(data, list)
        and bool(data)
        and all(isinstance(row, dict) for row in data)
    )


def _describe(key: str, rows: list[dict], *, dotted: bool = False) -> dict:
    """One column, measured against every row."""
    values = [resolve(row, key) for row in rows] if dotted else _values(rows, key)
    mapping = _is_mapping(values)
    width = max([_cell_width(v) for v in values] + [len(key)])
    label = key.upper()
    column = {
        "key": key,
        "label": label,
        "flex": _flex(width),
        # A floor, not a width. Both renderers apply it — because the reason
        # for it is the same in both and a second opinion would drift.
        "min": min(len(label), LABEL_CAP),
        # And the width it would take if nothing were competing. Since prose
        # left the row, every remaining column is one you *scan*, and none of
        # them wants to be wider than its own content — spreading spare width
        # across four scan columns just puts eighteen spaces inside `NUMBER`.
        "max": min(max(width, len(label)), NATURAL_CAP),
    }
    if mapping:
        column["summarise"] = True
    if _is_numeric(values):
        column["align"] = "right"
    return column


def _is_prose(rows: list[dict], key: str) -> bool:
    """Is this column something you read rather than something you scan?

    Matched on the values, like every other rule here — a string column whose
    longest value runs past `PROSE_WIDTH`. Deliberately *not* a list of blessed
    names like `title` or `description`: the next tool calls it `subject`, or
    `Command`, or `message`, and a name list goes stale the first time one does.
    A column of one-word statuses called `title` stays inline, which is right.
    """
    present = [v for v in _values(rows, key) if v not in _EMPTY]
    if not present or not all(isinstance(v, str) for v in present):
        return False
    return max(len(v) for v in present) > PROSE_WIDTH


def shape(
    data,
    *,
    cols: list[str] | None = None,
    drop: list[str] | None = None,
    enabled: bool = True,
) -> dict | None:
    """Describe how to present these rows, or None if there is nothing to say.

    None means *render as you always did* — the data is not a table, or shaping
    was declined with `--no-shape`. The envelope omits the key entirely in that
    case, so an unshaped result is byte-identical to one from before this
    existed.

    Every column worth showing is returned. **`hidden` means hidden by rule** —
    empty in every row, an opaque identifier, or explicitly dropped — which is
    a property of the *run*, true at any width and worth an envelope warning.
    A column that does not fit is a property of the *drawing*, and each
    renderer reports its own. See [[table-views]] round 3.
    """
    if not is_rows(data):
        return None

    rows = data

    # An explicit column list defeats every rule. The operator looked at the
    # table and said what they wanted; a heuristic that argued would be a bug.
    # An explicit list chooses *which* columns and in what order. It does not
    # choose their layout: a 90-character title asked for by name is still a
    # 90-character title, and clipping it into a share of the width would be
    # obeying the letter of the request while destroying what was asked for.
    if cols:
        chosen = [_describe(key, rows, dotted="." in key) for key in cols]
        inline = [c for c in chosen if not _is_prose(rows, c["key"])]
        details = [c for c in chosen if _is_prose(rows, c["key"])]
        return {"columns": inline, "details": details, "hidden": []}

    if not enabled:
        return None

    keys = columns_of(rows)
    dropped = set(drop or [])
    hidden: list[str] = [k for k in keys if k in dropped]

    kept = []
    for key in keys:
        if key in dropped:
            continue
        values = _values(rows, key)
        if _all_empty(values) or _is_opaque(values):
            hidden.append(key)
            continue
        kept.append(key)

    # Rule 5 — prose leaves the row rather than being placed within it. A
    # column you *read* gets the full width on its own line beneath the record;
    # the columns you *scan* stay narrow and aligned above it.
    #
    # This replaces Round 1's ordering rule, which tried to solve the same
    # problem by moving prose to the end of the row. See Notes: the honest
    # version of "a title does not fit in a share of the width" is not to put
    # it somewhere else in the row, it is to stop giving it a share.
    details = [_describe(key, rows) for key in kept if _is_prose(rows, key)]
    columns = [_describe(key, rows) for key in kept if not _is_prose(rows, key)]

    return {"columns": columns, "details": details, "hidden": hidden}
