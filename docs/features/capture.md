---
status: draft
created: 2026-08-22
updated: 2026-08-22
agent_value: 2
key_files: []
---

# Capture — a declared parser for a tool with no --json

## Why

The question arrived as "a `--pretty` flag that completely reformats the text." The inference
version of that flag is the one idea this design has rejected by name since the beginning —
CLAUDE.md: *inferring columns from whitespace is the "silently wrong" failure* — and the
asymmetry that let [[highlight]] through cuts against it: a tint that misfires costs a color,
a reformat that misfires **alters facts while looking finished**. So the flag is refused and
the want behind it is built instead, on the doctrine every other decision here already stands
on: **tb never guesses; the operator asserts.** Choosing `data` over `run` asserts read-ness;
`key = "number"` asserts the delta identity; a capture pattern asserts the format.

The mechanism is one line of operator-written regex:

    tb data --from 'lines:(?P<pr>#\d+)\s+(?P<state>\w+)\s+(?P<title>.+)' -- sometool status

Named groups become fields, matched lines become rows — and then **everything downstream is
already built**: the [[table-views]] shaping, `--cols`/`--drop`, the column budget, the canvas
table, `--refresh` residency, and saving the whole thing as a keyword in `tools.toml`. That
last one is the real prize: a foreign tool with no `--json` becomes a pinned, refreshing table
on the canvas, and this spec adds no new command, no new flag — only a new **value** for
`--from`, which [[refresh]] created for exactly this moment: *the next format is a value with
its own parsing contract, not a redesign.*

`data`'s contract does not move: parsed data or a failed contract, never carried bytes. A
declared pattern that matches nothing is a failed contract exactly as non-JSON is today.

## Shape

**`--from lines:<pattern>`** on `data`, beside `--from json`. The pattern is a Python regex
with at least one named group — zero named groups is a usage error at parse time, before
anything runs, because a capture that captures nothing is a typo, not a request.

**The deciding half is pure.** `cli/capture.py`: `capture(text, pattern) -> Captured` — rows,
the unmatched count, and one sample unmatched line. `data` maps that onto its envelope; the
regex is applied per line, never across lines.

**The rules, each one earning its place:**

- **A matched line is a row; its named groups are the fields**, in group order. `re.search`
  semantics, so a pattern need not anchor the whole line to be useful.
- **A value shaped like a number becomes one** — digits (with optional sign, optional decimal
  point) convert to int or float. This is shape, not judgment, and it is what makes numeric
  columns right-align and a `*_bytes` group humanize through the existing convention for
  free. Anything else stays the string the tool printed.
- **Unmatched lines are never silently dropped.** Blank lines are ignored; every other
  unmatched line is counted, and the count arrives as a warning that carries one sample:
  `14 of 60 lines did not match — first: "…"`. A capture that misses is then *visible*, which
  is the whole difference between a declared parser and a guessed one.
- **Nothing matching is a failed contract, not an empty table.** Same envelope shape as
  non-JSON today, with an error that names both recourses: fix the pattern, or use `tb read`
  to see what the tool actually printed. An empty table would read as "the tool reports
  nothing", which is the exact lie this command exists to never tell.
- **Rows flow into the standard view shaping** — hidden-column warnings, `--cols` overrides,
  `--no-shape` — with no capture-specific carve-outs. One shaping contract, not two.

**Keywords and the canvas ride free, and a test says so.** The pattern lives inside a saved
tool's argv like any other option; `acts` inherits from `data` as always; the canvas runs
`tb --json data --from lines:… -- …` through the runner unchanged. No canvas code moves.

**Does not do:**

- **No inference, ever.** No pattern, no table. `--pretty` remains rejected; this doc is the
  built form of the want behind it.
- **No multi-line records.** A record is one line. Tools whose records span lines need a
  declared record separator, which is a different contract — a future round here, argued when
  a real tool demands it, not shipped speculatively.
- **No typed columns beyond number shape.** Dates, durations, enums stay strings; declaring
  column types is machinery without a driving case.
- **No capture on `read`.** `read` shows verbatim and says that is what it is doing; `data`
  is the one door for parsing contracts. Two doors would blur the assertion each one makes.
- **Unmatched lines do not reach `data`.** The envelope carries rows or a failed contract.
  The warning carries the count and sample; the file of record for the full text is `tb read`.
- **No regex timeout machinery.** A catastrophic pattern is the operator's own foot, on their
  own machine, inside the `--timeout` the subprocess already has. Noted, not defended against.

## Phases

### Round 1 — the lines contract (2026-08-22)

- [ ] **The capture, pure.** `cli/capture.py` and `tests/test_capture.py`: matching, group
      naming, number shaping, blank-line skip, unmatched counting with sample, the
      nothing-matched verdict. No subprocess anywhere in the tests.
- [ ] **`--from lines:` on `data`.** Validation at parse time (known contract, ≥1 named
      group); the envelope mapping; the failed-contract error naming both recourses; `--help`
      gains the runnable example — the [[refresh]] help test enforces it.
- [ ] **The free rides, proven.** A saved tool declaring a capture loads and lands on the
      canvas as a refreshing table with zero canvas changes — asserted by test, because "no
      code needed" is a claim that rots silently.
- [ ] **Docs.** CLAUDE.md's rejected-list entry for parsing human output gains its dated
      narrowing: *declared* capture is in, inference stays out. [[refresh]]'s Notes gain one
      line pointing here as the first `--from` value to arrive after `json`.

## Notes

### Round 1 — drafted, awaiting the word (2026-08-22)

Drafted from the operator's `--pretty` question. The inference flag was refused in
conversation before this doc existed; what survived is the assertion form, which is the same
shape as every safety decision in the codebase. Two alternatives noted and kept out of scope:
`jc` (a CLI converting ~200 classic tools' output to JSON) already makes `tb data -- jc df`
work today with zero code, for tools it knows; and display kinds beyond tables (sparkline,
gauge, key-value card) are a `view.kind` seam on [[table-views]], parked until a first real
non-table display has a driving case.
