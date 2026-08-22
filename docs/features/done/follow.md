---
status: complete
created: 2026-08-21
updated: 2026-08-22
agent_value: 3
key_files:
  - cli/stream.py
  - cli/follow.py
  - cli/filefollow.py
  - cli/resident.py
  - cli/keys.py
  - cli/run.py
  - cli/read.py
  - cli/canvas/server.py
  - cli/canvas/static/app.js
  - tests/test_stream.py
  - tests/test_follow.py
  - tests/test_filefollow.py
  - tests/test_resident.py
  - tests/test_canvas_stream.py
---

# Following a command, and live output for everything

## Why

Two gaps, one substrate.

**The stream gap:** `journalctl -f`, `docker logs -f`, an agent session writing as it thinks —
commands whose whole point is that they never exit. tb has no way to hold one open. Every
existing command waits for exit before showing anything, and these never do.

**The black-box gap:** `tb run -- <ten-minute build>` shows nothing for ten minutes, then
everything. The constitution names the fix: *a Job is a stream that ends* — one execution
mechanism where output accrues as it happens and exit is just an event that stamps a status.
Duration is **discovered, never declared**: there is no "job" flag, a snapshot that turns out to
take eight minutes simply is one, and the surface shows it accruing either way.

The only operator assertion that remains is the one flag can't fake: choosing `follow` asserts
the process is *expected* not to exit, so the surface treats exit as an event to display rather
than a result to wait for.

This substrate is what the file cursor ([[file-follow]]) deliberately does not cover: **the
cursor owns files, the stream owns commands.** A file yields to `stat`; a process's only signal
is its output, so the liveness clock here reads "last line arrived", nothing deeper.

**One verb fronts both mechanisms.** This doc owns the `follow` command's registration and its
dispatch rule: a leading `--` means the process form (this doc), a bare path means the file form
([[file-follow]]), and there is no third shape. The name is the one Unix already taught —
`-f` is `--follow` in tail, journalctl, docker and kubectl alike.

## Shape

`tb follow -- <argv>` (with `--cwd`, like every runner here): spawn through `child_env()`
([[subprocess-env]]), read lines as they arrive, emit them into the ring. Exit — any exit — flips
the window to a plainly visible **dead** state carrying the exit code and time. Restart is the
operator's click, never the surface's initiative; that is the dead-streams decision from the
constitution, unchanged.

**Live accrual for `run` and `read`.** Both ride the same line-streaming runner: output shows
while the process runs, exit stamps the status. The `Result` envelope is untouched — under
`--json` the envelope is still emitted once, complete, at exit. Streaming is a *surface*
behavior; the contract stays byte-identical, and the stdout-purity tests keep proving it.
`data` stays report-at-exit — JSON parses only when complete — and shows a running-since clock
instead. That is its contract, not a limitation.

**Streams die with their window.** The subprocess rule [[canvas]] already enforces for snapshot
runs — a subprocess because a thread cannot be cancelled — extends to lifetime: closing a
follow's window SIGTERMs its process. Nothing survives the last window; this is what keeps a
follow a stream and not a service manager.

**stderr joins the stream**, tagged per-line as stderr rather than merged blind. Streaming tools
talk on stderr constantly; hiding it would make follow useless for half its targets, and the tag
is what lets a future Rule tint those lines without re-plumbing.

**Bounded.** Same ring as [[file-follow]] (default 200 lines, `--lines`). Liveness clock = last line
arrived. ANSI stripped per [[text-reads]].

**`q`, `Esc` and Ctrl-C all leave, and leaving kills** (round 2, amending round 1's "Ctrl-C
leaves (and kills)"). The frame is drawn inline below the prompt by default, keeping the
**tail** of the ring; `--screen` takes the alternate screen and shows the whole ring.

**Does not do:**

- **No terminal emulation.** Line streams, not a pty — follow is not tmux. A full-screen TUI run
  under follow prints what it prints; the answer for interactive tools is a terminal.
- **No cadence, no auto-restart.** Resident by nature, dead until clicked. `--refresh` does not
  exist here ([[refresh]] owns that flag, on snapshot reads only).
- **No shell.** Argv only, unchanged.
- **No change to `data`/`wrap`'s at-exit contract**, and no partial-JSON parsing ever.
- **Not a process manager.** One process per window, no detach, no reattach, no nohup. A process
  that must outlive the surface belongs to systemd.

## Phases

### Round 2 — leaving a stream, and what it leaves behind (2026-08-22)

[[refresh]] round 2 gave the resident *read* `q`, `Esc` and an inline redraw, on the operator's
report that the alternate screen took the terminal and could not be left. **`tb follow` has the
identical defect and did not get the fix**, deliberately: this doc records "Ctrl-C leaves (and
kills)" as a decision, and changing a recorded decision belongs in the doc that recorded it.
The operator asked for this round immediately after. Both follow forms are in scope — the
process stream here and the file cursor in [[file-follow]] — because they are one command with
one way out.

**1. `q` and `Esc` leave, alongside Ctrl-C.** The reader already exists as `cli/keys.py`,
written shared for exactly this: cbreak on a real terminal, polled by the `select` that is
already the loop's tick, drained so an arrow key cannot quit, and absent entirely when stdin is
not a terminal. Nothing new is designed here; it is applied.

**And leaving still kills.** This is the one place the two commands genuinely differ, and it is
worth stating rather than inheriting quietly: a resident *read* leaves a finished process
behind, while `q` on `tb follow -- journalctl -f` **terminates the child**, exactly as Ctrl-C
does today. Making the gentler-looking key do the same forceful thing is correct — the stream
*is* the window, and [[canvas]]'s rule that nothing survives the last window is the same rule —
but a reader should not have to infer it. `--help` says it.

**2. Inline redraw becomes the default here too, with one real difference.** Same argument as
[[refresh]]: leaving should leave what you were looking at, and today the tail of the log you
were watching vanishes the instant you press Ctrl-C. `--screen` keeps the alternate screen.

The difference is **which end gets clipped**, and it is not a detail:

> A snapshot's interesting end is the **top** — headers, the first rows. A stream's interesting
> end is the **bottom** — the newest lines. `clip` in `cli/resident.py` keeps the head and says
> how many it dropped, which is right for a table and exactly wrong for a log.

This is not an edge case for follow, it is the normal case: the ring holds 200 lines by default
and a terminal shows perhaps forty, so **every** inline follow frame is clipped. A follow that
kept the head would pin the oldest lines on screen and never show a new one — the feature
inverted. So the round adds a direction to the clip rather than reusing it as-is, and the
`N more lines` marker moves to the top of the body where the lines it counts actually went.

**Does not do:**

- **No detach, no background.** `q` closes and kills; it does not hand the process off to keep
  running unattended. That is the scheduler-not-daemon line, and a follow that survived its
  window would cross it.
- **No scrolling or paging.** Inherited unchanged from [[refresh]] round 2 — a resident view is
  a view. Scrollback and `less` already exist.
- **No change to dispatch, the ring, the chrome, or the canvas.** This round is how a terminal
  follow is left and where it draws. The canvas's follow windows are unaffected: they close by
  closing, which was never in doubt.

- [x] **Both forms take `q` and `Esc`.** `follow_process` and `follow_file` adopt `cli/keys.py`,
      replacing their `sleep(1)` with the same key-polling wait the resident loop uses; Ctrl-C
      unchanged, and leaving still kills a process child. Tested with the injected wait both
      loops already accept.
- [x] **Inline by default, `--screen` for the alternate screen.** `clip` grows a direction and
      both follow bodies ask for the tail; the dropped-lines marker leads the body instead of
      trailing it. A terminal-shaped end-to-end check through a pty, as [[refresh]] round 2's
      did, because the suite drives these loops with `screen=False` and never sees the real one.
- [x] **`--help` says how to leave, and that leaving kills.** The [[refresh]] help test enforces
      the example; this adds the sentence a reader would otherwise have to infer.
- [x] **The record.** [[file-follow]] gains a dated Notes entry — its loop changed, its "Ctrl-C
      ends it" line is amended, and the reason to read *this* doc for the leaving contract is
      stated there. The constitution needs nothing: it says `follow` is resident, which is
      still true.

### Round 1 — the streaming runner and the follow command (2026-08-21)

- [x] **The runner.** Async line-streaming subprocess execution (extending `cli/canvas/runner.py`
      or a shared module it and the CLI both use): bounded ring, stderr tagging, cancellation
      that kills the process. Tests: bounded waits only, a hung child is killable, the ring
      bounds memory, no real sleeps — drive with injected pipes.
- [x] **`tb follow` in the terminal.** Resident, ring + last-line clock, dead state with exit
      code, Ctrl-C leaves (and kills). Registered as an observe; keywords with
      `argv[0] == "follow"` inherit it. Full `--help` stating the contract with a runnable
      example — the [[refresh]] help test enforces it from birth. Clock, dead state and ring
      occupancy render through the [[chrome]] contract.
- [x] **Live accrual for `run` and `read` in the terminal.** Output streams during execution;
      exit renders exactly what renders today. Envelope under `--json` proven unchanged.
- [x] **The canvas.** Stream frames for follow/run/read windows over the session stream; dead
      state + restart affordance; window close SIGTERMs the child — a test extends "a watcher
      dies with its window" to processes. *(Follow windows stream; run/read canvas accrual
      deferred — see Notes.)*

## Notes

### Round 1 — written as spec, from the constitution (2026-08-21)

The unification ("a Job is a stream that ends") was the operator's ratified answer to the
one-time / long-process / file-change taxonomy: one mechanism, shapes as policy, duration
discovered. The dead-streams rule (visible death, manual restart) predates this doc and is
inherited, not re-decided. `wrap`'s at-exit carve-out was almost re-litigated here and should not
be: a streamed JSON document is unparseable until its last byte, so "stream it anyway" has no
meaning — the running-since clock is the honest rendering of an in-flight data read.

### Round 1 — executed (2026-08-21)

What the execution argued back:

- **"Exit renders exactly what renders today" was written before the streaming existed, and the
  executed form is better than the sentence.** In a terminal, `run` and `read` now stream each
  line to the stream it was printed on and stamp a chrome band on **stderr** at exit — the body
  is not re-rendered, because printing a ten-minute build's output twice was the alternative.
  What actually held, and is tested: stdout stays byte-pure for pipes (`tb read -- x | grep`
  sees exactly the tool's lines), and the `--json` envelope is still built once, complete, at
  exit, byte-identical.
- **The accrual queue is unbounded and the first cut proved why.** The first implementation fed
  `echo` through a bounded ring, and a two-line `printf` lost its first line to the race. Every
  line must reach the terminal exactly once; memory is bounded the same way the buffered path
  always bounded it, and only the *envelope's* copy is capped, cut declared.
- **The dispatch rule needed one refinement the spec's `--` couldn't give it.** Click consumes
  the `--` before the command sees it, so shape is judged on the argv alone: one argument that
  has a separator, exists, or answers to no executable is the file form. The ambiguity left —
  a bare word that is both an executable and a file — resolves to the executable, and `./name`
  means the file, exactly as a shell would read it.
- **The canvas resolves follow argvs server-side** (`resolve_follow`): a saved keyword's
  expansion lives on the Click tree, and the client keeping enough knowledge to strip
  `follow --` itself would be the start of a command table. Residency travels the same way
  `acts` does — `tb_resident` on the command object, through the catalog, inherited by
  keywords — and the loader refuses a `refresh` field on a follow loudly.
- **Dropped, deliberately: canvas accrual for `run`/`read` windows.** The canvas runs snapshots
  as `tb --json`, whose envelope is parseable only complete — streaming those windows means a
  second invocation mode for the runner and it earned its own round rather than a rushed
  corner of this one. Follow windows stream; snapshot windows still arrive whole.
- **The session's `finally` sends SIGTERM fire-and-forget** rather than waiting out the grace
  period: it runs inside `GeneratorExit`, where a blocking wait has nowhere to happen. The
  terminal form waits properly; a canvas child that ignores SIGTERM is reaped at server exit.

### Round 2 — drafted, awaiting the word (2026-08-22)

Asked for directly after [[refresh]] round 2 shipped, which is the cleanest possible provenance:
the operator hit the defect on `--refresh`, that round fixed it there and deliberately stopped at
the boundary this doc drew, and the flag raised at handover — *"follow still leaves only on
Ctrl-C"* — came back as "draft it".

**Nothing here is new mechanism.** `cli/keys.py` was written shared and is already proven against
a real pty; `--screen` and the inline default are [[refresh]] round 2's shape applied to a second
pair of loops. The round exists because the *decision* is this doc's, not because the code is
hard.

**The one genuine design finding is the clip direction**, and it only surfaced by asking what
inline means for a stream rather than assuming the read's answer generalised. `clip` keeps the
head, which is right for a table and inverts a log — and because a follow's ring is 200 lines
against a terminal's forty, it would have inverted *every* frame rather than an occasional one.
A shared helper that was correct for its first caller and silently wrong for its second is the
failure this project keeps finding in duplicated logic; here it would have been the same failure
in *shared* logic, which is worth noting as a caution against treating sharing as the safe
default.

**Recorded because it looks like an inconsistency and is not:** `q` on a follow kills the child,
while `q` on a resident read leaves nothing running. Both are "close the window"; the commands
differ in what a window owns, not in what the key means.

### Round 2 — executed (2026-08-22)

The round was right that nothing new had to be designed, and wrong about how little would move.
What the execution argued back:

- **The clip direction was the finding the draft predicted, and sharing went further than it
  planned.** Both follow loops, both frame assemblers and both clip calls collapsed into
  `cli/resident.py` — `hold`, `room`, `clip(..., tail=True)` and `stream_body`. The draft's
  caution ("a shared helper correct for its first caller and silently wrong for its second") is
  the reason to share *deliberately* rather than the reason not to: `clip` now takes a direction
  and both callers state which end they mean, which is exactly the failure made impossible
  instead of merely avoided. `stream_body` was already duplicated between the two forms before
  this round; one assembler is what the existing test *"both follow bodies tint through one
  `spans`"* was already asserting by hand.
- **`cli/resident.py` grew a charter rather than a helper.** It was written as "the terminal's
  rendering of the refresh rule"; it is now "the terminal's resident views — how they draw and
  how they are left", which is the honest description of a module that owns `q` for two commands
  that share nothing else. The alternative was a lazy cross-import between `follow.py` and
  `filefollow.py`, which would have put the leaving contract in whichever module happened to
  import first.
- **`tty.setcbreak` flushes the input queue, and only a real terminal shows it.** The pty
  end-to-end check pressed `q` before starting the residency and passed alone, passed in its own
  file, and hung for a hundred seconds inside the full suite — a race, not a failure, because
  `setcbreak` uses `TCSAFLUSH` and discards whatever is already queued. The key is now pressed
  after the reader is in cbreak. Two lessons, both already project rules: **bound every wait**
  (the bound was `ticks=100`, which is a hundred *seconds* when each tick is a real one-second
  select — a bound on frames is not a bound on time when the wait is real), and a test that only
  passes in isolation has not passed. The behaviour itself is correct and left alone: a key typed
  before the first frame appears is dropped.
- **`--screen` had to reach the file form too**, which the phase list implied and the dispatch
  did not: `follow` now passes it to both `follow_file` and `follow_process`, and the round's one
  test-shaped surprise was that the existing dispatch test asserted the *exact* call kwargs.
- **Verified against a real terminal, not only the suite.** A pty harness ran the actual `tb`
  through all three shapes — process inline, process `--screen`, file inline. Inline draws
  `room()` lines with the marker leading, `q` leaves, `--screen` hands the terminal back
  (`?1049l`), and the child is gone. The suite proves the mechanism; this proved the rendering,
  which is the half `screen=False` and an injected wait never see.

