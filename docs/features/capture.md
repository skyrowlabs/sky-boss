---
status: draft
created: 2026-08-22
updated: 2026-08-22
agent_value: 2
key_files: []
---

# Capture — named formats for tools with no --json

## Why

The question arrived as "a `--pretty` flag that completely reformats the text." The inference
version of that flag is the one idea this design has rejected by name since the beginning —
CLAUDE.md: *inferring columns from whitespace is the "silently wrong" failure* — and the
asymmetry that let [[highlight]] through cuts against it: a tint that misfires costs a color,
a reformat that misfires **alters facts while looking finished**. So the flag is refused and
the want behind it is built instead, on the doctrine every other decision here already stands
on: **tb never guesses; the operator asserts.**

The first draft put the assertion inline — a raw regex on the command line — and the operator
refused it on review: **commands must stay simple to execute.** What survived is the same
two-level shape the toolbox already proved: complexity lives in a named, operator-authored
declaration, written once in an editor; the command line only says the name.

    tb data --from jam-status -- sometool status

And then **everything downstream is already built**: the [[table-views]] shaping,
`--cols`/`--drop`, the column budget, the canvas table, `--refresh` residency, and saving the
whole invocation as a keyword — a foreign tool with no `--json` becomes a pinned, refreshing
table on the canvas. No new command, no new flag: only new **values** for `--from`, which
[[refresh]] created for exactly this moment — *the next format is a value with its own parsing
contract, not a redesign.*

`data`'s contract does not move: parsed data or a failed contract, never carried bytes.

## Shape

**Two levels: kinds are code, formats are declarations.**

- A **kind** is a parsing contract tb ships and tests: `json` today; `lines` (a per-line
  pattern with named groups) is this round's addition. Later kinds — `csv`, aligned-`table`,
  multi-line records — arrive one at a time when something real needs them, exactly as
  [[refresh]] ruled for formats generally.
- A **format** is an operator-declared, named parameterization of a kind, in
  **`$TB_HOME/formats.toml`** — operator content, outside the repo, `$EDITOR`-authored, and
  tb reads it and never writes it, all inherited from the [[toolbox]] rules:

      [format.jam-status]
      description = "sometool status — PR, state, title"
      kind = "lines"
      pattern = '(?P<pr>#\d+)\s+(?P<state>\w+)\s+(?P<title>.+)'

**`--from` resolves a name**: a kind that needs no parameters (`json`) or a declared format.
Anything else is a usage error that lists what would have worked. Builtin kinds always win a
name collision, same rule as commands; a format declaring an unknown kind, a pattern with no
named group, or a pattern that does not compile **fails loudly by name and does not load** —
one bad format must not cost the operator the other nine.

**`tb tools` reports formats too.** It is already the one place the operator looks for "what
did I declare, and what was refused" — a second listing command would split that. Declared
formats appear with their kind and description; load failures land in the same problems list
the toolbox uses.

**The deciding half is pure.** `cli/capture.py`: `capture(text, format) -> Captured` — rows,
the unmatched count, one sample unmatched line. The `lines` kind's rules, each earning its
place:

- **A matched line is a row; its named groups are the fields**, in group order. `re.search`
  semantics, so a pattern need not anchor the whole line to be useful.
- **A value shaped like a number becomes one** — digits (optional sign, optional decimal)
  convert to int or float. Shape, not judgment; it is what makes numeric columns right-align
  and a `*_bytes` group humanize through the existing convention for free. Everything else
  stays the string the tool printed.
- **Unmatched lines are never silently dropped.** Blank lines are ignored; every other
  unmatched line is counted, and the count arrives as a warning carrying one sample:
  `14 of 60 lines did not match jam-status — first: "…"`. A capture that misses is *visible*,
  which is the whole difference between a declared parser and a guessed one.
- **Nothing matching is a failed contract, not an empty table.** Same envelope shape as
  non-JSON today, with an error naming both recourses: fix the format, or `tb read` to see
  what the tool actually printed. An empty table would read as "the tool reports nothing" —
  the exact lie this command exists to never tell.
- **Rows flow into the standard view shaping** with no capture-specific carve-outs. One
  shaping contract, not two.

**Keywords and the canvas ride free, and a test says so.** `--from jam-status` sits inside a
saved tool's argv like any other option; `acts` inherits from `data` as always; the canvas
runs `tb --json data --from … -- …` through the runner unchanged. No canvas code moves.

**Does not do:**

- **No inference, ever.** No format, no table. `--pretty` remains rejected; this doc is the
  built form of the want behind it.
- **No inline regex on the command line.** Refused by the operator on the first draft:
  commands stay simple to execute, and a pattern worth typing is a pattern worth naming.
  If a future one-off case genuinely earns an escape hatch, argue it as its own round.
- **No multi-line records.** A record is one line. A declared record separator is a future
  kind, argued when a real tool demands it.
- **No typed columns beyond number shape.** Dates, durations, enums stay strings.
- **No capture on `read`.** `read` shows verbatim and says so; `data` is the one door for
  parsing contracts. Two doors would blur the assertion each one makes.
- **Unmatched lines do not reach `data`.** Rows or a failed contract; the warning carries the
  count and sample; the record of the full text is `tb read`.
- **tb never writes `formats.toml`.** Creation is `$EDITOR`, the same boundary the toolbox
  drew and for the same reason.
- **No regex timeout machinery.** A catastrophic pattern is the operator's own foot, on their
  own machine, inside the `--timeout` the subprocess already has. Noted, not defended against.

## Phases

### Round 1 — the lines kind and the formats file (2026-08-22)

- [ ] **The capture, pure.** `cli/capture.py` and `tests/test_capture.py`: matching, group
      naming, number shaping, blank-line skip, unmatched counting with sample, the
      nothing-matched verdict. No subprocess, no file I/O in the mechanism tests.
- [ ] **`formats.toml`.** Loader beside the toolbox's, sharing its degrade-gracefully rules:
      validation (known kind, compilable pattern, ≥1 named group, builtin names win), loud
      per-format failures, absent file degrades to nothing declared. `tb tools` lists
      declared formats and their failures.
- [ ] **`--from <name>` resolution on `data`.** Kinds needing no parameters plus declared
      formats; unknown names are usage errors listing what would have worked; the envelope
      mapping; the failed-contract error naming both recourses; `--help` gains the runnable
      example — the [[refresh]] help test enforces it.
- [ ] **The free rides, proven.** A saved tool whose argv says `--from <format>` loads and
      lands on the canvas as a refreshing table with zero canvas changes — asserted by test,
      because "no code needed" is a claim that rots silently. The suite redirects `TB_HOME`,
      so declared formats in tests never touch the operator's file.
- [ ] **Docs.** CLAUDE.md: the rejected-list entry for parsing human output gains its dated
      narrowing (*declared* capture in, inference still out); the "Where things live" table
      gains `formats.toml`; [[refresh]]'s Notes gain one line pointing here as the first
      `--from` addition after `json`.

## Notes

### Round 1 — drafted, awaiting the word (2026-08-22)

Drafted from the operator's `--pretty` question; the inference flag was refused in
conversation before this doc existed. **Reshaped once before execution, on operator review:**
the first draft's inline `--from lines:<regex>` violated their stated plan — commands simple
to execute — and was replaced by named formats in `$TB_HOME/formats.toml`, which is the
toolbox's own two-level shape applied to parsing: declarations carry the complexity, commands
carry a name. The inline form moved from the Shape to the Does-not-do, with its door left
ajar only as a future argued round.

Kept out of scope with reasons: `jc` (a CLI converting ~200 classic tools' output to JSON)
already makes `tb data -- jc df` work today with zero code, for tools it knows; display kinds
beyond tables (sparkline, gauge, key-value card) are a `view.kind` seam on [[table-views]],
parked until a first real non-table display has a driving case.
