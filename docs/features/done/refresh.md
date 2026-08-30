---
status: complete
created: 2026-08-21
updated: 2026-08-30
agent_value: 3
key_files:
  - cli/data.py
  - cli/keys.py
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
saying `wrap` fails to load *loudly by name* — `sb tools` already lists tools that failed to
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

### Round 4 — a cadence off a terminal streams NDJSON (2026-08-30)

**This reverses round 3 for `data`, on the operator's ruling**, relayed through the
skyrow-workspace session out of the morning review. Round 3 refused `sb data --refresh` down a pipe
and under `--json`; the owner was shown that diagnosis and the argument for refusing and chose
against it.

```
$ sb data --from jsonl --refresh 2 runs.jsonl | jq -c .
{"tick":1,"at":"2026-08-30T14:02:21+00:00","ok":true,"data":[…],"warnings":[],"view":{…}}
{"tick":2,"at":"2026-08-30T14:02:23+00:00","ok":true,"data":[…],"warnings":[],"view":{…}}
```

**The objection round 3 raised is answered by the form rather than dismissed.** It held that a
resident render has no *single* envelope, which is true — and a **stream** of envelopes is not a
single envelope. It is the thing `sb follow` already legitimises. [[jsonl-reads]] round 2 settled
that every tick is a whole read that stands alone, so a tick is exactly the unit already known to be
safe to emit by itself. The two alternatives were rejected on this repo's own stated grounds:
render-once-and-ignore-`--refresh` is the *wrong but looks right* failure, and repeating a whole
table into a pipe is not a document.

**Each line is the single-shot envelope plus `tick` and `at`,** rather than a slimmer per-tick
record. That is the choice that costs nothing to consume: every reader of `sb --json data` reads one
of these lines unchanged, where a second shape would be a second data contract to keep in step. `at`
is ISO 8601 UTC, not the band's `08:50:02` — a band is drawn for a human reading one screen, and a
machine consumer needs an unambiguous instant.

**`--json --refresh` takes the same path rather than staying refused**, which is the half round 3
left to this round's judgement. `--json` is the flag that *means* machine output, so under the old
rule it was the one thing that could not have a cadence. One path, not two.

**`read` keeps both refusals and that is deliberate.** Its contract is verbatim text; it has no
envelope worth streaming, and the owner ruled on `data`. `follow` is untouched — its own ruling
(degrade to verbatim lines) already covers the same ground for a stream.

**Warnings ride the line and are not reprinted on stderr.** A one-shot prints them both places
because a human may be reading either; a stream would reprint the same warning every tick forever,
and nothing is lost — `warnings` is a field on every line.

- [x] `data --refresh` emits one NDJSON line per tick off a terminal, or under `--json`.
- [x] Each line is the single-shot envelope plus `tick` and `at`, flushed per line.
- [x] `read` still refuses; `follow` untouched.
- [x] A consumer that leaves ends the stream without reporting a failure.
- [x] Tests bounded by `ticks` with an injected clock — never by running the endless loop.

### Round 3 — a cadence needs a screen (2026-08-29)

**The defect.** `sb data --refresh 2 … | cat` renders **0 bytes and never exits**. The same command
under `script` renders 14,237. `rich.Live` owns a cursor, a pipe has none, so every frame is
suppressed while the loop runs perfectly — and because residency is by nature endless, the caller
does not get a wrong answer, it *hangs*.

This is [[follow]]'s bug, found on 2026-08-29 by the skyrow-workspace session driving `sb` against a
live job, one day after the follow half was fixed. The fix missed it for a structural reason worth
recording: the `emit` spill went onto `resident.hold`, the *streaming* path, and `resident.reside`
is a different function that `data --refresh` and `read --refresh` both use.

**The answer is not follow's.** A follow's content *is* a stream of lines, so verbatim was the
obvious degrade. A refreshing table has no sensible pipe reading — repeating a whole table every N
seconds is not a document — and rendering once while silently ignoring `--refresh` is the
wrong-but-looks-right failure this repo names by hand.

**So: refuse, at the door.** The precedent is already in the code and needs no new argument.
`refuse_resident_json` turns down `--json --refresh` because *a resident redraw is a human rendering*
and under `--json` it would be an endless stream of envelopes on a pipe expecting one. Off a
terminal there is no human rendering to do at all. Same rule, one step further.

The consumer's version of the argument is the stronger one and it is why this is a refusal rather
than a degrade: **a refusal is a sentence where a hang is not.** See `CLAUDE.md` § *Worked fine,
told nobody*, of which this is one of five instances.

- [x] `refuse_resident_pipe(refresh)` in `cli/output.py`, beside `refuse_resident_json` and raised
      in the same two places in each command — at the door before `--save` writes, and again inside
      `_reside` for any future path that reaches residency another way.
- [x] The message names the fix: drop `--refresh` for a single read.
- [x] `--screen` does not exempt it. The alternate screen is *more* of a terminal requirement, not
      less.
- [x] A test that a piped `--refresh` is a usage error rather than a silence, for `data` and `read`.

### Round 2 — leaving, and staying in place (2026-08-22)

Two reports from the operator running `sb data --from json -- jam pr list --json --refresh`
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

- [x] **The key reader.** A small TTY helper: cbreak on entry, restored on every exit path,
      `select` with a zero timeout on the loop's existing tick, `q`/`Esc` end the loop. Not a
      TTY → no reader, no error, Ctrl-C unchanged. Tested against a fake stdin rather than a
      real terminal, the way every other clock here is injected.
- [x] **Inline residency.** `reside()` draws in place below the prompt; the body is clipped to
      the room available and says so. `--screen` restores the alternate screen. The chrome
      bands are unchanged — they already carry the countdown and the verdict.
- [x] **The default flips, and the flag says so.** `--refresh`'s help gains the one line that
      matters — how to leave — since [[refresh]]'s own rule is that help is the doc. `--screen`
      documents what it is for (a long residency, scrollback preserved).
- [x] **Docs.** Shape's "Ctrl-C to leave" is already amended above; CLAUDE.md's `data`/`read`
      rows gain nothing (they say "resident", which stays true).

### Round 1 — the realignment (2026-08-21)

- [x] **`wrap` → `data`, plus `--from`.** Rename module/command/tests/catalog references; add
      `--from json`; alias-import in `cli/__init__.py`; update CLAUDE.md's command table and the
      operator's `tools.toml` (one entry). The failed-to-load path proves the loud migration
      message.
- [x] **`every` → `refresh`** in the [[tools]] loader and its validation messages; docs.
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
- **Five done docs needed the supersession line, not three.** [[tools]] and [[canvas]] also
  predate the rename and say `wrap`/`every` throughout; the spec had named only the three the
  operator asked about. Same treatment: key_files re-pointed, one dated Notes entry, prose
  untouched.
- The resident loop went on the **alternate screen** (watch(1)/htop style) so hours of redraw
  leave the scrollback intact; inline rendering was considered for small tmux panes and can be
  argued as its own round if wanted.

### 2026-08-22 — the seam was used ([[capture]])

`--from` gained its first values beyond `json`, exactly as designed: a *name* resolving to a
kind or to an operator-declared format in `$SB_HOME/formats.toml` — the next format arrived as
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
what happens to the position when the next refresh lands — which is a pager, and `sb read |
less` is already a pager.

### Round 2 — shipped (2026-08-22)

Both halves landed as drafted, and the honest cost stayed the size it was advertised at.

**The tick and the key poll became one primitive, which is why `q` is instant.** The loop used
to `sleep(1)`; it now waits up to a second *for a key* through `select`, so a keypress ends the
frame it arrives in rather than up to a second later. `loop`'s parameter was renamed `sleep` →
`wait`, and because a sleep that returns None is a valid `wait`, the suite's injected clock kept
working untouched — the pure layer needed no new concept to absorb this.

**An arrow key nearly quit the view.** Esc arrives as the first byte of `Esc [ A`, so reading one
byte and comparing it to the leave set makes Up close the window — and leaves `[` and `A` in the
buffer for the shell that gets the terminal back. `_drain` swallows the rest of the sequence.
Found by writing the test for it rather than by pressing it, which is the only reason it was
found before the operator did.

**The suite still cannot see the thing that shipped, and that is now recorded rather than
merely true.** Every resident test drives `reside()` with `screen=False` and an injected wait,
so the alternate screen shipped for a day untested and unseen. The new tests use a real `pty`
where the behaviour is genuinely terminal-shaped — cbreak restored on an exception, a keypress
read back, an escape sequence drained — and the end-to-end check (`q`, `Esc`, Ctrl-C, `--screen`)
was driven through a pty outside the suite.

**Ctrl-C looked broken and was not.** Driven through a bare pty it kept running, because a child
that is not the terminal's foreground process group receives `\x03` as a *byte* rather than as
SIGINT — the harness was wrong, not the loop. Re-driven with `setsid` and `TIOCSCTTY` it exits 0
and leaves the frame on screen. Worth remembering the next time a signal appears not to arrive
in a test: check who owns the terminal before changing the code.

**Left alone deliberately:** [[follow]] and [[file-follow]] still take the alternate screen and
still leave only on Ctrl-C. The same `q`/`Esc` argument applies to them and the module was
written to be shared, but their docs record "Ctrl-C leaves" as a decision, and changing a
recorded decision is a round in *their* docs rather than a quiet extension of this one.

### 2026-08-29 — round 3, and the fixture that had to say so out loud

**Five existing tests broke on the new refusal, and they were right to.** They drive `--refresh`
through `CliRunner` — which never has a terminal — with `resident.reside` stubbed, to assert that
`--screen` reaches the loop and that `--save` writes before residency. Legitimate properties, and
the tests were standing in for an operator at a terminal without ever saying so; the absence of a
check was what let them.

They now take an `at_a_terminal` fixture that forces `cli.output.console` to report one. It renders
nothing extra — `reside` is still stubbed — it only gets them through the door, and it makes the
claim they were already making visible in the signature.

**The check is on stdout specifically**, through `_out()` rather than a fresh `Console`. `reside`
renders to stdout, so a terminal on stderr is no help, and asking through `_out()` is what lets the
suite's redirection be the thing that answers.

**One boundary worth naming:** the refusal is about the *cadence*, not about the pipe. Every read
without `--refresh` works off a terminal exactly as before, which is why this is a usage error on
one flag rather than a mode. There is a test for that, because it is the regression a careless
version of this fix would ship.


### 2026-08-30 — round 4, and the refusal that was load-bearing for a *test*

**Removing the refusal hung the suite twice**, and both hangs were the rule `CLAUDE.md` states as
*bound every wait*, arriving from the product side rather than the test side. Four tests invoked
`sb data --refresh` through `CliRunner` expecting exit 2; with the refusal gone they entered an
endless stream and the suite stopped rather than failed. The fix is the one the repo already uses
for `reside`: **assert the mechanism by intercepting it, never by running it.** A residency that a
test can enter is a test that can only hang.

**One of those tests was guarding something real, and the reversal retired it rather than weakening
it.** `test_a_refused_cadence_writes_nothing` exists because `--save` writes *before* it runs, so a
refusal raised further down fired after the append — a tool on disk under a name that could not be
reused, then exit 2. With `data` no longer refusing, there is no refusal to fire late: the hazard is
gone for that command rather than untested. Retargeted at `read`, which still refuses and where the
ordering can still go wrong.

**`✗ data failed` on a broken pipe was this repo's usual bug inverted.** `… --refresh 2 | head -3`
is a normal way to use the feature, and the consumer leaving is how it ends — but the unhandled
`BrokenPipeError` reported a failure that had not happened. Telling the operator something broke
when nothing did is the mirror of *worked fine, told nobody*, and no less wrong. Caught by running
the real thing down a real pipe, which is the only way it shows: the clean case has empty stderr and
the suite never opened a pipe at all.
