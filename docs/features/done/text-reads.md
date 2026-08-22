---
status: complete
created: 2026-08-20
updated: 2026-08-21
agent_value: 3
key_files:
  - cli/read.py
  - cli/__init__.py
  - cli/output.py
  - tests/test_read.py
---

# Reading a tool that has no `--json`

## Why

`tb wrap` requires the wrapped tool to speak JSON, and most tools do not. The one this repo uses
every day speaks both — but its human output is the better of the two to look at:

```
  PR    STATE  MERGE  BEHIND  CHECKS      MARKER    RAN  NEXT
  ─────────────────────────────────────────────────────────────────────
  #952  draft  CLEAN  6       1✓ passed   ✗ absent  —    run jam pr ready <n>
        fix(web-app): derive the banner card thumbnail key in one place

  MARKER = does a `jam pr ready` run vouch for this exact head?
```

That is a considered piece of design — an aligned table, a detail line per record, and a legend
explaining the two columns nobody remembers. Reproducing it from `--json` would mean reimplementing
someone else's judgement about their own domain, and getting it slightly wrong.

**tb can already show it, and cannot watch it.** `tb run -- jam pr list` carries the bytes today.
But `run` *acts*, and only a read may be given a refresh cadence, so that window can never be
pinned. The gap is not display. It is that **the only command that carries text is the one command
that must never be put on a timer.**

## Shape

`tb read -- <argv>`: like `tb run`, except it is declared a read.

```
tb read --cwd ~/skyrow.labs/jam.sense -- jam pr list
```

`data` is **the text itself** — a plain string, not an object wrapping one. That is the whole
implementation, because both renderers already do the right thing with a string: `_render_value`
echoes it verbatim, and `render.js` falls through to `<pre class="raw">`. A window shows exactly
what the tool printed, and re-shows it every thirty seconds.

**It is the second exception to "raw output must not reach `data`", and the rule it is an exception
to was drawn in the wrong place.** The rule exists because *a probe can print a token* — output tb
went and fetched on its own initiative must not reach stdout or a future MCP surface. `tb run` was
carved out as "the one exception", but the distinguishing property was never *run-ness*: it is that
the operator **named the argv**. `read` names it too. `CLAUDE.md` is corrected to say so rather
than growing a list of blessed commands.

**Choosing `read` is the operator's assertion that this argv is a read**, exactly as choosing
`wrap` over `run` already is. tb cannot tell a read from a write by inspecting an argv and does not
try — see `CLAUDE.md` § Scope. `tb read -- rm -rf /` is possible in the same way `tb wrap -- rm -rf /`
already is, and is refused for the same reason: it isn't.

**ANSI is stripped, never interpreted.** [[canvas]] rejected an ANSI-to-HTML fallback on the
grounds that rendering an ANSI table gives you a *picture* of a table — no sorting, no chips, no
resizing. That argument is untouched and this does not contradict it: `tb read` gives you a picture
and says so. What it does not do is leave `\e[32m` in the middle of a cell, which is what carrying
the bytes untouched would mean the first time a tool decides it is talking to a terminal.

**Bounded, like everything else here.** A 120k-line result kills a browser tab as dead as it killed
a `RichLog`. `read` truncates and says how much it dropped.

**Does not do:**

- **Does not parse.** No inferring columns from whitespace, no rows, no `--cols`, no sorting. Those
  need real data, and guessing at it from an aligned table is the "silently wrong" failure: jam's
  own output alone has continuation lines, a value containing a space (`1✓ passed`), and four lines
  of prose legend at the end. When structure is wanted, the tool has `--json` and [[table-views]]
  is already waiting for it.
- **Does not interpret ANSI.** Stripped, not rendered. See above.
- **Does not become the default path.** `wrap` stays the right answer for anything that speaks
  JSON, because a table you can sort and filter beats a picture of one. This is for tools that do
  not, which is most of them.
- **Does not run a shell.** Argv only, unchanged.

## Phases

### Round 1 — a read that carries text (2026-08-20)

- [x] `cli/read.py`: run an argv, strip ANSI, carry the text as `data`. Registered on the root
      group; the catalog gives it `acts: false` with no change, so a window may pin it.
- [x] Truncation with a warning naming how much was dropped.
- [x] `tests/test_read.py`: it is a read, it carries what the tool printed, it strips ANSI, it
      bounds a large result, and a failing tool still shows its output.
- [x] Fix `tb run`'s human rendering: stdout is currently folded into a key/value row, which wraps
      it and destroys the alignment. A block of text should render as a block.
- [x] Correct `CLAUDE.md`'s raw-output rule to be about *who named the argv* rather than a list of
      commands, and update [[canvas]]'s "no ANSI fallback" entry to point here.

## Notes

### Round 1 — the gap was cadence, not display (2026-08-20)

The request arrived as "render any format as it comes", which reads like the ANSI fallback
[[canvas]] rejected. Checking before describing changed the shape of the work twice.

**`tb run -- jam pr list` already carried the text.** The bytes were there, in `data.stdout`, and
the canvas already rendered them in a `<pre>`. So "tb cannot show this" was simply false. What is
true is that `run` **acts**, and only a read may be given a cadence — so the one command that
carried text was the one command that must never be put on a timer. The feature is four lines of
subprocess and a different `acts`.

**And jam emits no ANSI at all** when its stdout is not a terminal: zero escape sequences in 1083
bytes. The hard part everyone braces for was not there. Stripping is still implemented, because the
next tool will not be so well behaved, but it was a precaution rather than the work.

**`data` is the string itself, and that is the entire implementation.** Both renderers already
handle a plain string correctly — `_render_value` echoes it, `render.js` falls through to `<pre>`.
Every design that wrapped the text in an object would have needed a new branch in both.

**The rule about raw output was drawn around the wrong property.** `CLAUDE.md` said `tb run` is
"the one exception" to output never reaching `data`. But run-ness was never what made it safe: the
rule exists because *a probe can print a token*, and what distinguishes a probe is that tb chose to
run it. `read` runs an argv the operator typed, exactly as `run` does. Restated as **who named the
argv**, the rule stops needing a list of blessed commands and will not need amending for the next
one.

**A bug found on the way past.** `tb run`'s stdout was rendered as a value inside a key/value row,
so Rich folded it at the column edge and destroyed the alignment that was the reason to look at it.
Multi-line text is a block now. That had been wrong since `run` was written and nobody had looked at
a wide table through it.

**Not built, and the argument is unchanged:** no parsing. jam's own output in one screen has
continuation lines, a value containing a space (`1✓ passed`), and four lines of prose legend — a
column-inference heuristic would get some of that right and the rest silently wrong. A tool with
real structure has `--json`, and [[table-views]] is already waiting for it.

### 2026-08-21 — the words moved; the history stays (supersession)

`wrap` was renamed `data` and the `every` field renamed `refresh` — hard renames, no aliases;
see [[refresh]]. This doc predates the rename and its prose says `wrap` because it *was*
`wrap`; that is history being accurate, and nothing above has been scrubbed.
