---
status: draft
created: 2026-08-21
updated: 2026-08-22
agent_value: 3
key_files:
  - cli/data.py
  - cli/read.py
  - cli/resident.py
  - cli/tools.py
  - tests/test_data.py
  - tests/test_resident.py
  - tests/test_help.py
---

# Refresh, spelled the same everywhere

## Why

The constitution (`docs/design/fundamentals.md`) decided that the terminal is a surface too: the
refresh rule — re-run a snapshot on a cadence — currently exists only as canvas machinery (the
`every` field, the window's cadence picker), while a CLI invocation always runs once and exits.
The operator's framing was exact: "a run without options is one time; we need a flag that doesn't
exit after one run and re-runs the command." One refresh concept, two renderings, the same shape
as the theme's two-renderings rule.

The same pass renamed two things that said the wrong word. `wrap` names a mechanism; **`data`**
names the contract — parsed data or a failed contract, never carried bytes — and the contract is
what matters. `every` and `--refresh` would be two spellings of one number; **`refresh`** is the
one word, flag and field. And JSON stops being an invisible assumption: it becomes the default
value of an explicit `--from`, so the next format is a value, not a redesign.

This doc owns that realignment round. [[table-views]] and [[text-reads]] are its history and stay
as written — they say `wrap` because it *was* `wrap`.

## Shape

**`--refresh <seconds>` on `read` and `data`.** Without it: run once, print, exit — unchanged.
With it: the invocation goes resident, `watch(1)`-style — re-run every N seconds, redraw in
place, Ctrl-C to leave. *(Round 2, 2026-08-22, revisits both halves of that last clause: the
redraw happens on the **alternate screen**, which the operator did not expect and could not
leave except by Ctrl-C. See Round 2 — inline becomes the default and `q`/`Esc` leave.)* On a
saved keyword, bare `--refresh` (no value) uses the keyword's
`refresh` field; in the terminal a keyword still runs **once** unless the flag is given — the
field is the *canvas* default cadence, and residency in a terminal is always asked for
explicitly.

**`run` never takes the flag.** The absence of `--refresh` in `run --help` is the act/observe
split made visible; a deploy re-running itself every 60 seconds is the exact failure the split
exists to prevent. Recorded as considered-and-rejected in the constitution. [[follow]] and
[[file-follow]] take no flag either — resident by nature.

**`--refresh` and `--json` refuse each other.** A resident redraw is a human rendering; under
`--json` it would mean an endless stream of envelopes on a pipe that expects one. A machine
consumer that wants a cadence is what the canvas API is for. Refused with a message that says so.

**`wrap` becomes `data`.** Module, command name, catalog, tests, prose. Hard rename, no alias —
one operator, one `tools.toml`, and an alias is a second name to test forever. A saved tool still
saying `wrap` fails to load *loudly by name* — `tb tools` already lists tools that failed to
load, which is the right surface for the migration message. Implementation note: `cli/data.py`
defining a command named `data` walks straight into the import-shadowing gotcha CLAUDE.md
records — import under an alias in `cli/__init__.py`, as `read` already must.

**`every` becomes `refresh`.** Same word as the flag, same hard-rename policy, same loud failure
through the tools-that-failed-to-load listing.

**`--from <format>` on `data`**, one option with enumerable values — `json` today, the only
value — defaulting to `json`. Never a flag per format, and `data` never grows its own `--json`:
the root owns that spelling for envelope output, and one flag meaning two things at two levels is
a confusion trap.

**Does not do:**

- **No `--refresh` on `run`, ever.** See above; not a future option, a rejected one.
- **No second format yet.** `--from` exists so csv/yaml can arrive as *values with their own
  parsing contracts*, one at a time, when something real needs them. Shipping speculative parsers
  is how "silently wrong" gets back in.
- **No back-compat aliases** for `wrap` or `every`.
- **No canvas changes.** The Python-side, connection-keyed refresh clock ([[canvas]]) is
  untouched; this round gives the *terminal* its rendering of the same rule. The two never share
  a scheduler — a terminal residency is owned by its process, a canvas cadence by its stream.

## Phases

### Round 2 — leaving, and staying in place (2026-08-22)

Two reports from the operator running `tb data --from json -- jam pr list --json --refresh`
in a real terminal: *"it took over the whole terminal screen — we need a flag to exit out,
like q or esc"*, and *"is there a way to have it render below the command line but not take
over the screen? Like it does when it's just printing once."*

**This round was already parked here.** Round 1's Notes end: *"The resident loop went on the
alternate screen (watch(1)/htop style) so hours of redraw leave the scrollback intact; inline
rendering was considered for small tmux panes and can be argued as its own round if wanted."*
It is now wanted, and for a better reason than tmux panes.

**Why the original argument does not survive contact.** It was *a resident invocation may
redraw for hours, and a terminal's history is the operator's* — protect the scrollback by
taking a screen that gets handed back intact. True, and it optimised for the wrong session.
What the operator actually does is run a read, look at it, and leave. In that session the
alternate screen costs the thing it was protecting: the output **vanishes on exit**, so the
one command you wanted to see leaves nothing behind, and `--refresh` stops being "the same
command, kept fresh" and becomes a different program with its own screen. The one-shot prints
below the prompt and stays there; the operator reasonably expected the resident form to be
that, plus redrawing.

**Two changes, and the second is the reversal:**

1. **`q` and `Esc` leave**, alongside Ctrl-C. Ctrl-C is the Unix answer and it stays, but it
   is the answer for *interrupting* something, and this is a view you are *closing* — every
   pager and full-screen tool the operator already uses takes `q`. Needs a key reader: raw
   `termios` on a real TTY, polled with `select` on the same one-second tick the loop already
   has, and restored on every exit path including an exception. **When stdin is not a TTY there
   is simply no key reader** and Ctrl-C remains the only way out — degrade, never fail.

2. **Inline redraw becomes the default; the alternate screen becomes `--screen`.** The frame
   is drawn below the prompt and redrawn in place, so leaving it leaves the last frame on
   screen exactly as the one-shot does. `--screen` keeps today's behaviour for the case the
   original argument was right about — a genuinely long residency where scrollback matters.

   *The honest cost, stated up front:* an inline redraw can only repaint what it can address,
   so a frame **taller than the terminal cannot redraw in place** — the top scrolls away and
   each tick appends rather than replaces. That is the case the alternate screen handles
   perfectly and inline cannot. Proposed answer: inline draws at most the height it has, the
   body is clipped to fit with the row-truncation line already used elsewhere saying so, and a
   result that wants more room is what `--screen` is for. This keeps the [[canvas]] rule that
   no single result renders unbounded, in the surface that rule came from.

**Does not do, this round:** no scrolling, no paging, no interaction beyond leaving — a
resident read is a view, not a pager, and the moment it grows a scroll position it owes the
operator a scrollbar and a search. No key bindings other than `q`, `Esc` and Ctrl-C.

- [ ] **The key reader.** A small TTY helper: cbreak on entry, restored on every exit path,
      `select` with a zero timeout on the loop's existing tick, `q`/`Esc` end the loop. Not a
      TTY → no reader, no error, Ctrl-C unchanged. Tested against a fake stdin rather than a
      real terminal, the way every other clock here is injected.
- [ ] **Inline residency.** `reside()` draws in place below the prompt; the body is clipped to
      the room available and says so. `--screen` restores the alternate screen. The chrome
      bands are unchanged — they already carry the countdown and the verdict.
- [ ] **The default flips, and the flag says so.** `--refresh`'s help gains the one line that
      matters — how to leave — since [[refresh]]'s own rule is that help is the doc. `--screen`
      documents what it is for (a long residency, scrollback preserved).
- [ ] **Docs.** Shape's "Ctrl-C to leave" is already amended above; CLAUDE.md's `data`/`read`
      rows gain nothing (they say "resident", which stays true).

### Round 1 — the realignment (2026-08-21)

- [x] **`wrap` → `data`, plus `--from`.** Rename module/command/tests/catalog references; add
      `--from json`; alias-import in `cli/__init__.py`; update CLAUDE.md's command table and the
      operator's `tools.toml` (one entry). The failed-to-load path proves the loud migration
      message.
- [x] **`every` → `refresh`** in the [[toolbox]] loader and its validation messages; docs.
- [x] **`--refresh` on `read` and `data`.** Resident terminal loop over an injectable clock
      (tests assert the mechanism, not five real seconds); redraw in place; Ctrl-C; bare-flag
      uses the keyword default; refused together with `--json`. The running-since clock and
      countdown render through the [[chrome]] contract rather than growing their own status
      line.
- [x] **Help is the doc.** A tree-walking test fails any command whose `--help` lacks a runnable
      example, and every existing command (`run`, `read`, `data`, `tools`, `ui`) is brought up to
      the standard — contract stated (acts/observes, once/resident), example included. Lands in
      this round so [[follow]] and [[file-follow]] are born covered. The palette inherits the same
      strings through the catalog; nothing is written twice.
- [x] **Docs sweep.** CLAUDE.md command table and § conventions say `data` and `refresh`;
      `docs/design/fundamentals.md` gains nothing (it already says all of this) — verify rather
      than edit. The done docs that predate the rename ([[table-views]], [[text-reads]],
      [[subprocess-env]]) are **dated, never scrubbed**: update their `key_files` paths (frontmatter
      is navigation, not history), and add one dated supersession line per doc — "`wrap` was
      renamed `data`, `every` renamed `refresh`, see [[refresh]]; this doc predates the rename" —
      leaving every argument and Notes entry exactly as written. Their prose says `wrap` because
      it *was* `wrap`; that is history being accurate.

## Notes

### Round 1 — written as spec, from the constitution (2026-08-21)

The rename question arrived as "cmd for foreign commands, data for wrap". Half survived: `data`
is the better name because it names the contract; `cmd` was rejected because a generic door for
foreign argvs cannot carry the act/observe assertion, and the keyword-inheritance rule leans on
`argv[0]` being a distinct entry point. The `--refresh`/`--json` mutual refusal was found while
speccing this doc, not in the constitution pass — an endless envelope stream on stdout has no
consumer and would break the one contract (`--json` purity) every consumer relies on.

### Round 1 — executed (2026-08-21)

What the execution argued back:

- **[[chrome]]'s first two phases were pulled ahead of the `--refresh` phase**, as its own doc
  ordered — the resident loop rendered through `status_lines` from birth and never grew a status
  line to migrate off. The interleave (rename → rename → chrome facts → residency) beat the
  strict doc order and cost nothing.
- **The field rename needed its own loud check, not just the argv one.** An unrecognised
  `every` field would have been silently ignored and the tool would load at cadence 0 — the
  pinned window that never refreshes, "wrong but looks right". `RENAMED` covers argv words;
  a separate check covers the field.
- **Bare `--refresh` on a keyword is Click's `flag_value` trick** (`is_flag=False,
  flag_value=0`), and the option is attached only to tools that observe — a tool that acts
  does not grow the flag at all, mirroring how `run` itself shows the split by absence.
- **Five done docs needed the supersession line, not three.** [[toolbox]] and [[canvas]] also
  predate the rename and say `wrap`/`every` throughout; the spec had named only the three the
  operator asked about. Same treatment: key_files re-pointed, one dated Notes entry, prose
  untouched.
- The resident loop went on the **alternate screen** (watch(1)/htop style) so hours of redraw
  leave the scrollback intact; inline rendering was considered for small tmux panes and can be
  argued as its own round if wanted.

### 2026-08-22 — the seam was used ([[capture]])

`--from` gained its first values beyond `json`, exactly as designed: a *name* resolving to a
kind or to an operator-declared format in `$TB_HOME/formats.toml` — the next format arrived as
a value with its own parsing contract, not a redesign. The Choice list became name resolution
in the process; the refusal still lists what would have worked.

### Round 2 — drafted, awaiting the word (2026-08-22)

Both halves came from the operator running the resident form for the first time in anger, which
is the only way this particular defect surfaces: every test in the suite drives `reside()` with
`screen=False` and a tick bound, so the suite has never once seen the alternate screen it
ships. Worth remembering — the injected-clock discipline that makes the loop testable is also
what kept the loop's most visible behaviour untested.

**The reversal is recorded in place above with Round 1's reasoning intact.** Scrollback
preservation was a real argument; it was simply an argument about a different session than the
one the operator has. Both sessions still exist, which is why `--screen` survives as a flag
rather than being deleted — the parked round asked for inline *as an option*, and what changed
is only which one is the default.

**Deliberately left out of scope:** scrolling and paging. A resident read is a view. The moment
it takes a scroll position it owes the operator a scrollbar, a search, and a decision about
what happens to the position when the next refresh lands — which is a pager, and `tb read |
less` is already a pager.
