---
slug: rich-output
title: Rich human rendering
status: complete
created: 2026-08-18
updated: 2026-08-18
agent_value: 2
key_files:
  - cli/output.py
  - cli/__init__.py
  - cli/doctor.py
  - cli/assets.py
  - tests/test_output.py
---

# Rich human rendering

## Why

The human renderer is deliberate but plain: `click.echo` with manual column padding. Tables have
no borders, nothing is colorized beyond bold headers and yellow warnings, and there are no
headings or visual grouping. For a CLI meant to be read at a glance — `tb brief`, `tb assets
status`, `tb doctor` — that is harder to scan than it needs to be.

This is cheap to do now precisely because of [[output-contract]]: commands return data and never
print, so all rendering lives in `cli/output.py`. Prettiness is a change to one file, and no
command changes at all.

## Shape

Add `rich` (15.x — pure Python, no compiled extensions, installs clean on this box's 3.14).

Two consoles in `cli/output.py`: one for stdout, one constructed with `stderr=True`. Rich
auto-detects a TTY and drops color when piped, and respects `NO_COLOR`, so no manual detection.

Rendering upgrades, all inside `_render_human`:

- **Tables** — `rich.table.Table` with a box border, the dotted command name as the title,
  automatic column widths, numeric columns right-aligned.
- **Semantic cell styling** — `yes` green, `no` red, `-` dimmed. Derived from the *value type*
  in the renderer.
- **Mappings** — a two-column table rather than manual padding.
- **Status markers** — `partial` and hard failure become rich panels on stderr instead of a
  bare `~`/`✗` prefix.

Optionally `rich-click` so `--help` matches. Cosmetic and independent; last phase, droppable.

**Does not do:**

- **`--json` output does not change, at all.** No color, no wrapping, no box characters. It is
  structurally separate and must stay byte-identical — the test asserting stdout parses as JSON
  is the guard.
- **Commands never style anything.** They return `True`, `None`, `"not installed"`; the renderer
  decides how that looks. A command that embeds a color has broken the contract, and the MCP
  surface would inherit terminal formatting.
- No progress bars, spinners, or live displays. Jobs log; they do not animate.
- No user-configurable themes.

## Phases

### Phase 1 — Console plumbing

- [x] Add `rich` to `requirements.txt`
- [x] Module-level stdout and stderr `Console` objects in `cli/output.py`
- [x] Warnings and status markers move to the stderr console
- [x] Confirm `--json` output is unchanged (existing tests must pass untouched)

### Phase 2 — Tables and mappings

- [x] `_render_table` uses `rich.table.Table`, titled with the command name
- [x] Semantic cell styling: booleans green/red, `EMPTY` dimmed, numbers right-aligned
- [x] `_render_mapping` becomes a two-column table
- [x] Update the human-rendering tests to assert on *content*, not exact layout

### Phase 3 — Status-list redesign and palette

Chosen direction: **status list**, not tables. Borders read as dated; modern CLIs (bun, vite,
biome, the charm suite) use whitespace, glyphs, dim secondary text and one accent. Plus a
**rich truecolor palette** — hues per section and values coloured by type.

- [x] A `rich.theme.Theme` holding the whole palette, attached to both consoles, so colour is
      defined in exactly one object
- [x] Header line: accent `●` + dotted command name + dim item count
- [x] **Convention: a row containing an `ok` field renders as a status line.** `ok` drives the
      glyph, the first string field is the label, `detail` is the dim suffix. This is a data
      convention, not styling in commands — commands still never choose a colour
- [x] Rows without `ok` fall back to borderless aligned columns with a dim header
- [x] Mappings: dim labels, values coloured by type, accent section headings, no borders
- [x] Values typed by the renderer: numbers, paths, booleans, absent
- [x] Dim footer summary — counts of ok/failed
- [x] `doctor` gains an `ok` field alongside `installed`/`authenticated`, so machine consumers
      keep the distinction while the renderer gets one status to draw
- [x] Verify piped output stays plain and `NO_COLOR` is honoured

### Phase 4 — Help text (optional, droppable)

- [x] `rich-click` for `--help`
- [x] Confirm usage errors still exit 2 and still come from Click

## Notes

The existing human-rendering tests assert exact plain-text layout
(`lines[0].split() == ["a", "b"]`). Borders break that by design. They should be rewritten to
assert content and presence rather than column positions — which is the better test regardless,
since layout is exactly the thing this feature is changing.

**Phase 1 (2026-08-18).** Two consoles; the JSON path deliberately bypasses rich entirely, since
a `Console` would soft-wrap to terminal width and `--json` must stay byte-identical. All 51
existing tests passed untouched, which was the phase's acceptance condition.

**Phase 2 (2026-08-18).** Cells are `rich.text.Text`, **not markup strings**. A value containing
square brackets — `[bold]`, a desktop-file name, an error message — would otherwise be parsed as
rich markup and either vanish or raise. `test_bracketed_value_is_not_parsed_as_rich_markup`
guards it.

Nested mappings render as one titled table per section, titled with the dotted path
(`fleet.describe · apps · handlers`), which is how `tb assets describe` became readable.

Only one test broke — the layout-coupled one, as predicted. It now extracts cells on the row
separator and asserts content, which is the right level: layout is exactly what this feature is
free to change.

Verified: piped human output contains no escape codes, and `--json` is unaffected by any of it.

**Phase 3 (2026-08-18).** Direction chosen by comparing rendered mockups rather than describing
them — borderless columns, status list, left rail. Status list won, with a truecolour palette.

The whole palette is one `rich.theme.Theme`. Hex mid-tones rather than the eight ANSI names,
which are unreadable on one background or the other depending on the terminal.

**The `ok` convention is the key design decision.** A row containing an `ok` field renders as a
status line; `ok` drives the glyph, the first string field is the label, `detail` is the dim
suffix. Rows without `ok` fall back to borderless aligned columns. This keeps the rule that
commands never choose a colour — `ok` is a fact about the data, not a presentation directive.

`doctor` gained `ok` alongside `installed`/`authenticated`, so machine consumers keep the
distinction while the renderer has a single status to draw.

**Mappings render through a borderless `Table`, not hand-assembled `Text` lines.** A long value —
PATH, the shell list — must wrap *inside its column*. Printing Text directly wraps to column zero
and destroys the indent, which is exactly what the first attempt did.

Verified: `NO_COLOR` honoured, piped output free of escape codes, `--json` unchanged.

**Phase 4 (2026-08-18).** `rich-click` 1.9 dropped the module-global `STYLE_*` knobs the docs
still show; configuration is now a `RichHelpConfiguration` dataclass with lowercase fields,
attached to the root group via `@rich_config` and inherited by every subcommand. It also does
not expose `RichHelpConfiguration` through module attribute access — `from rich_click import ...`
is required.

`style_*_box=""` raises: rich-click resolves box names with `getattr(rich.box, name)`. It ships
its own **`"BLANK"`** box, which is what makes help borderless and consistent with the
status-list output. The error panel deliberately keeps its box — an error should break the
visual rhythm.

`--section` uses `metavar="NAME"` with the valid sections listed in the help text. The inline
choice list `[apps|identity|os|settings|shell]` contains no spaces, so at 80 columns rich-click
broke it mid-word.

Usage errors still exit 2 and are still raised by Click, which was the phase's acceptance
condition.
