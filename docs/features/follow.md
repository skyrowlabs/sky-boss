---
status: active
created: 2026-08-21
updated: 2026-08-28
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
  - cli/canvas/runner.py
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
commands whose whole point is that they never exit. sky.boss has no way to hold one open. Every
existing command waits for exit before showing anything, and these never do.

**The black-box gap:** `sb run -- <ten-minute build>` shows nothing for ten minutes, then
everything. The constitution names the fix: *a Job is a stream that ends* — one execution
mechanism where output accrues as it happens and exit is just an event that stamps a status.
Duration is **discovered, never declared**: there is no "job" flag, a snapshot that turns out to
take eight minutes simply is one, and the surface shows it accruing either way.

The only operator assertion that remains is the one flag can't fake: choosing `follow` asserts
the process is *expected* not to exit, so the surface treats exit as an event to display rather
than a result to wait for.

**The black-box gap was closed in the terminal and left open on the canvas** — round 1 deferred
that half by name. Round 4 closes it, and the deferral turned out to have grown a second, worse
symptom in the meantime: a canvas run is not merely silent while it works, it is *killed at sixty
seconds* by a ceiling that exists for a different reason. See Round 4.

This substrate is what the file cursor ([[file-follow]]) deliberately does not cover: **the
cursor owns files, the stream owns commands.** A file yields to `stat`; a process's only signal
is its output, so the liveness clock here reads "last line arrived", nothing deeper.

**One verb fronts both mechanisms.** This doc owns the `follow` command's registration and its
dispatch rule: a leading `--` means the process form (this doc), a bare path means the file form
([[file-follow]]), and there is no third shape. The name is the one Unix already taught —
`-f` is `--follow` in tail, journalctl, docker and kubectl alike.

## Shape

`sb follow -- <argv>` (with `--cwd`, like every runner here): spawn through `child_env()`
([[subprocess-env]]), read lines as they arrive, emit them into the ring. Exit — any exit — flips
the window to a plainly visible **dead** state carrying the exit code and time. Restart is the
operator's click, never the surface's initiative; that is the dead-streams decision from the
constitution, unchanged.

**Live accrual for `run` and `read`, on both surfaces.** Both ride the same line-streaming
runner: output shows while the process runs, exit stamps the status. *(Round 1 shipped this in
the terminal only and said so; the sentence read as though it covered the canvas, and round 4 is
what makes it true. See Notes.)* The `Result` envelope is untouched — under
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

### Round 4 — the canvas accrues too (2026-08-28)

The round round 1 named. *"Dropped, deliberately: canvas accrual for `run`/`read` windows … it
earned its own round rather than a rushed corner of this one."* This is that round, opened when
the operator went to watch a real two-hour agentic job — `sb run -- jam report agent-task
--budget 120` — on the canvas and found there was nothing to watch.

**The deferral grew a second symptom while it sat.** A canvas run window is not just silent for
two hours; it dies after sixty. `/api/run` is `subprocess.run` in a thread against
`runner.DEFAULT_TIMEOUT = 60`, and the page never passes a timeout (`api.run(argv)`, one
argument). Worse, `--timeout` *inside* the argv is honoured by `sb` and then overridden by the
ceiling around it — so the operator can write a bound, watch it be ignored, and read a hang where
a job was.

**The ceiling is not wrong, it is in the wrong place.** Its comment says what it is for: *"so a
watcher can never wedge on a command with no opinion about how long it should take."* That is the
refresh clock's problem — an unattended re-run, firing while nobody looks. An accruing window is
the opposite case by construction: it is being watched, it dies with its window ([[canvas]]'s rule,
already enforced for follows), and its output is arriving the whole time. So the ceiling stays on
the watcher path and on `/api/trial`, and an accruing window has no default bound; `--timeout` in
the argv is the operator's, honoured.

### What separates an accruing window from a resident one

The frontend currently spells these as one thing — `stream: Boolean(entry.resident)` — and round 4
is where that stops being adequate, because a run accrues and is emphatically not resident. They
are two different questions:

| | Accruing | Resident |
|---|---|---|
| What it says | lines arrive **while it runs** | it is **not expected to exit** |
| Who decides | the transport | the operator, by choosing `follow` |
| Exit means | a verdict — the act is stamped | a death, drawn plainly |
| Ends with | `chrome.act` / `chrome.snapshot` | `chrome.stream`, `dead` |

Every follow is accruing. Not every accruing window is a follow, and the one that is not is the
one this round adds. **Exit is where they genuinely differ**, which is why this cannot be "let
`/api/follow` take a `run` argv": that route's whole rendering treats exit 0 as a death, and for
an act exit 0 is the answer.

**Only an unpinned window accrues.** A pinned one is a watcher, its argv is a read by definition,
and the watcher path already delivers a complete envelope on a cadence — which is also where the
ceiling belongs. So the split is exactly the existing one, drawn once more: a cadence gets the
snapshot path, a single invocation gets the stream.

**The envelope construction moves to one place, deliberately.** `_accrued` in `cli/run.py` already
turns an `Outcome` into a `Result` — ok from the exit code, the `wrote to stderr` warning, the
timed-out shape — and the canvas must not re-decide any of that beside it. Round 2's caution about
a shared helper being *"correct for its first caller and silently wrong for its second"* is the
argument for sharing **on purpose** rather than against sharing, exactly as `clip`'s direction was.

**And a streamed body is not in the envelope.** The terminal already sets `result.data = None`
because the lines reached the terminal on the streams they arrived on; the canvas does the same
because they reached the window. That is what keeps this round cheap — nothing is delivered twice,
and `--json` from a pipe is untouched, still one complete envelope built at exit.

**Does not do:**

- **No detach, and nothing outlives the session.** A two-hour job in a canvas window still dies
  when the window closes. That is the scheduler-not-daemon line and round 4 does not go near it;
  job identity that outlives a window is [[open]] item 6, and folding it in here would turn
  sky.boss into a daemon inside a feature about drawing output. `--help` already says a command
  that must outlive its window wants systemd, and it stays true.
- **No cadence on an act.** The ⟳ on an accruing run window means *again* — the operator's click,
  never the surface's initiative, the same word round 1 used for restarting a dead follow. `run`
  still refuses `--refresh`, the pin control is still hidden for an act, and nothing here weakens
  the § Scope split.
- **No `data` accrual, ever.** Unchanged and not re-litigated: a JSON document parses only when
  complete, and the running-since clock is the honest rendering of an in-flight data read.
- **No `--delay` on the canvas.** A pending act is a countdown, not a stream — nothing is arriving
  during it. [[delay]] owns that state and `chrome.pending` already draws it; a canvas rendering is
  that doc's round if it wants one.
- **No structure inferred from an accruing run's output.** The lines are verbatim, tinted by shape
  and by the operator's declared words ([[highlight]]) and nothing else. [[capture]]'s rule is
  unchanged: declared structure in, inference out.
- **No auto-restart on exit**, for either kind.

- [x] **`resolve_run`, beside `resolve_follow`.** An `sb`-level argv down to the foreign one it
      would run: `run`/`read`, `--cwd`, `--timeout`, and a saved tool's expansion off the Click
      tree. Server-side for the reason round 1 gave — a client that could strip `run --` itself is
      the start of a command table. Raises on an argv that is not one, like its sibling. Pure,
      tested against the tree.
- [x] **One `Outcome` → `Result`.** Extract `_accrued`'s tail in `cli/run.py` into a function both
      surfaces call, so ok, the stderr warning and the timed-out envelope are decided once. The
      terminal path must come out byte-identical; the existing `--json` purity tests are the proof.
- [ ] **An act that is running.** `chrome.act` gains `running_since` the way `chrome.resident`
      already has it — attention `running` while the subprocess lives, the verdict at exit. Still
      no `interval` and still no countdown on the act shape: the absence is the split made visible,
      and that sentence stays in the docstring.
- [ ] **`/api/run` accrues an unpinned window.** A `Follower` over the resolved foreign argv,
      frames on the session stream that already exists, the act band at exit. No second transport,
      no `text/event-stream` — the preflight rule is why. A pinned window keeps the snapshot path.
- [ ] **The ceiling moves to where it is for.** `DEFAULT_TIMEOUT` stays on the watcher and on
      `/api/trial`; an accruing window has no default bound and honours `--timeout` from the argv.
      A test asserts a run window is not killed at sixty seconds.
- [ ] **The frontend splits accruing from resident.** `win.stream` stops meaning `entry.resident`;
      a window knows which it is, and an accruing run ends with an act band rather than a dead one.
      Closing still SIGTERMs the child either way.
- [ ] **Verified by rendering.** There is no JS runner, so the check is the one this repo already
      uses: headless Chromium against a live server, a run window watched from first line to act
      band, and the DOM read back. Bounded waits only.

### Round 3 — a follow you can look back through (2026-08-23)

From the ideas list: *"build in embedded scrolling for follow."*

**The inherited rejection does not survive being read carefully.** [[refresh]] round 2 rejected
scrolling with *"a resident read is a view, not a pager, and the moment it grows a scroll position
it owes the operator a scrollbar and a search"*, and added *"scrollback and `less` already exist."*
That last sentence is true of a refreshing read drawing inline: each frame is printed, so the
terminal's history holds what went by.

**It is false of a follow.** The ring holds 200 lines; the frame shows the ones that fit. A line
pushed out of the visible frame **was never printed** — it lives in sky.boss's memory and nowhere
else, so there is no scrollback holding it and no file for `less` to open. Under `--screen` the
terminal's history is untouched by design. The one escape hatch the rejection named does not exist
here, which is what makes this a reversal rather than a re-litigation.

**The scrollbar debt is real and is already paid.** The chrome band says `showing last 200` today.
A parked view says `showing 41–60 of 200`, which is a scrollbar written out — position and extent,
in the band that exists to carry exactly this. [[chrome]] built the slot; this fills it.

**The search debt is real and stays unpaid, deliberately.** The original bundled two obligations and
only one of them belongs to a scroll position. *Where am I* is owed by scrolling. *Find me a line*
is owed by a **pager**, and this does not become one: there is no file to open, no `/`, no `n`, no
match count. A bounded ring is the wrong place to search — the answer for a file is `grep` or lnav
on the file, and for a stream it is [[highlight]], which already tints the operator's declared words
as they arrive. Round 3 adds a viewport, not a query.

### Parked, and what happens to the lines that keep coming

Scrolling up **parks** the view: the ring keeps filling, the frame holds still, and the band says
so. `End` resumes following and jumps to the newest line. This is the only behaviour that makes
scrolling worth having — a view that snapped back to the tail on every arriving line would be
unusable on exactly the busy log you scrolled up to read.

**The ring still evicts while you are parked, and the band tells the truth about it.** Holding a
line on screen forever would mean an unbounded ring, which is the rule [[canvas]] set and this doc
inherited. So the viewport is anchored to an absolute line number, clamped to the oldest line still
held; when eviction catches up with you the numbers walk to `showing 1–20 of 200` and stay there.
Nothing is invented to explain it because the band already reads correctly.

**Does not do:**

- **No search, no `/`, no `n`.** Argued above. It is the difference between a viewport and a pager.
- **No selection, no copy, no mouse.** The terminal owns those and does them better.
- **No unbounded ring.** Parking does not make sky.boss keep more than it kept before.
- **Not the refreshing read**, this round. A follow scrolls a *ring*; `--refresh` re-renders a
  *snapshot*, where holding a position across a redraw asks a question this round does not have to
  answer — did the content move under you, and is line 40 still the same line 40. Different
  mechanism, different doc, and [[refresh]] can have it if it earns it.

- [x] **The key reader decodes instead of draining.** `_drain` swallows an arrow key's bytes today
      so a bare Esc still means leave; it becomes `_sequence`, returning a name — `up`, `down`,
      `pgup`, `pgdn`, `home`, `end` — while a truly bare Esc still leaves by the same
      nothing-followed test that already distinguishes them. Pure, against a fake stream, since
      there is no terminal in the suite.
- [x] **A viewport, pure.** Offset arithmetic over a ring in one place: park, move, clamp to the
      oldest line still held, and resume. Injected everything, no I/O, so the eviction case is a
      test rather than a wait.
- [x] **Both follow forms scroll**, process and cursor alike, through the frame each already
      builds. A view with nothing above it is not parked by pressing `up` at the top.
- [x] **The band becomes the scrollbar.** `showing 41–60 of 200 · parked` from the chrome facts,
      in both renderings — the canvas scrolls natively, so it takes the *facts* and keeps its own
      scrollbar.
- [x] **Help says how.** The keys, and that `End` resumes following, because [[refresh]]'s own rule
      is that help is the doc.

### Round 2 — leaving a stream, and what it leaves behind (2026-08-22)

[[refresh]] round 2 gave the resident *read* `q`, `Esc` and an inline redraw, on the operator's
report that the alternate screen took the terminal and could not be left. **`sb follow` has the
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
behind, while `q` on `sb follow -- journalctl -f` **terminates the child**, exactly as Ctrl-C
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

  *Reversed in round 3 (2026-08-23), and only half of it was ever true here. The argument was
  written for a refreshing **read**, where the terminal's own scrollback does hold the frames that
  scrolled past. A **follow redraws a ring in place**, so a line that leaves the visible frame was
  never printed to the terminal at all — `less` cannot reach it and neither can scrollback, because
  it exists only in sky.boss's memory. The rejection was inherited without noticing that the thing
  it relied on is absent in the form that inherited it. See Round 3.*
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
- [x] **`sb follow` in the terminal.** Resident, ring + last-line clock, dead state with exit
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
  What actually held, and is tested: stdout stays byte-pure for pipes (`sb read -- x | grep`
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
  `acts` does — `sb_resident` on the command object, through the catalog, inherited by
  keywords — and the loader refuses a `refresh` field on a follow loudly.
- **Dropped, deliberately: canvas accrual for `run`/`read` windows.** The canvas runs snapshots
  as `sb --json`, whose envelope is parseable only complete — streaming those windows means a
  second invocation mode for the runner and it earned its own round rather than a rushed
  corner of this one. Follow windows stream; snapshot windows still arrive whole.
- **The session's `finally` sends SIGTERM fire-and-forget** rather than waiting out the grace
  period: it runs inside `GeneratorExit`, where a blocking wait has nowhere to happen. The
  terminal form waits properly; a canvas child that ignores SIGTERM is reaped at server exit.

### Round 3 — shipped, and the band absorbed a marker (2026-08-23)

The reversal held under building. The one thing the spec did not see coming is that scrolling
**found an existing lie** rather than only adding a capability.

**`showing last 200` was wrong whenever the terminal was smaller than the ring** — which is every
inline follow, since the ring holds 200 against a terminal's forty. The band said 200 and forty
were drawn; a separate `N more lines not shown` marker from `clip()` admitted that something was
missing. Two places each telling half the truth, and neither telling it alone. The viewport made
the exact answer available, so the band now says `showing 33–40 of 40` while *following* too, and
the marker is gone. `showing last N` survives for the one case where it was never lying: everything
held is on screen.

**Slicing moved before rendering.** Round 2 rendered the whole ring and clipped the rendered text.
That is fine for a tail and wrong for a window — the lines drawn would not be the lines
[[highlight]] tinted, and the band's numbers would describe a different set than the one on screen.
Lines are sliced first now, which also means a parked view does no work on the 160 lines it is not
showing.

**The anchor is absolute and that is the whole eviction story.** An offset counted from the oldest
*held* line slides under the operator every time a line arrives — you would scroll to the top and
drift downward while standing still. Counting from the first line the stream ever produced and
clamping to what is still held makes the view walk to the top and stop, which is correct and also
what it looks like. Two lines of arithmetic; the alternative would have needed a rule.

**`_drain` became `_sequence`, which is the same test with the answer kept.** Round 2 already had to
distinguish a bare Esc from an arrow key's first byte, and already did it by asking whether anything
followed. It threw the sequence away. Decoding it required no new mechanism, and the risk it
guarded — Up quitting the window — is now covered by a test that presses Up twice.

**`select` on a fake stream polls the real stdin**, which cost a confused minute reading correct
code as broken. `_sequence` takes its readiness check for the same reason every clock here is
injected, and the suite's fake now answers from the buffer it is actually reading.

**Both stream kinds grew a `dropped` property** so no caller reaches through `.ring`. The first
attempt put it on `Ring`, which already had one — worth recording only because the duplicate was
silent and the error surfaced two layers away as `ChildStream has no attribute dropped`.

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
- **Verified against a real terminal, not only the suite.** A pty harness ran the actual `sb`
  through all three shapes — process inline, process `--screen`, file inline. Inline draws
  `room()` lines with the marker leading, `q` leaves, `--screen` hands the terminal back
  (`?1049l`), and the child is gone. The suite proves the mechanism; this proved the rendering,
  which is the half `screen=False` and an injected wait never see.


### Round 4 — drafted, from a real job that had nothing to watch (2026-08-28)

Provenance as clean as round 2's: the operator went to run `jam report agent-task --limit 2
--budget 120` on the canvas to exercise the surface, and the answer had to be *don't — it will be
killed at sixty seconds and show you nothing until then*. The workaround offered instead was to
launch it from a terminal and watch `cron.log` in a follow window, which works and is a fair
description of the hole.

**Round 1's deferral was right and its sentence was not.** The decision — that canvas accrual
"earned its own round" — held up completely; a rushed corner of round 1 would have had to invent
`resolve_run`, split the ceiling and re-decide the envelope in one sitting. What did not hold up is
Shape's line **"Live accrual for `run` and `read`. Both ride the same line-streaming runner"**,
which reads as a property of the feature and was only ever true of the terminal. The phase box
carried the qualifier and the Shape section did not, so the doc's summary and its checklist
disagreed for seven days. Amended in place, with this note as the record. **A deferral belongs in
Shape as well as in Phases** — Shape is what a reader checks, and a caveat that lives only in a
checked box is a caveat nobody reads.

**The 60s ceiling is the round's actual finding, and it is not a missing feature.** It is a correct
bound applied one layer too high. `DEFAULT_TIMEOUT` was written for the watcher — *"so a watcher can
never wedge on a command with no opinion about how long it should take"* — and `/api/run` serves
both the watcher and the operator's single click, so the watcher's bound silently became everyone's.
The compounding part is that `sb run --timeout` is honoured *inside* the subprocess and then
overridden by the ceiling outside it, which is the "wrong but looks right" failure this project keeps
naming: the operator writes a bound, sees it accepted, and gets a different one.

**`stream: Boolean(entry.resident)` is the same conflation in the frontend**, and it has been
harmless only because every streaming window so far *was* a follow. Writing the table in this round
was what made it legible: accruing is a property of the transport, resident is the operator's
assertion, and they happen to have coincided. The distinction that matters is exit — a follow's
exit 0 is a death and an act's exit 0 is the answer — which is also the reason this round cannot
be spelled as "let `/api/follow` accept a `run` argv", which was the first shape considered and is
the cheap wrong one.

**What this round deliberately does not fix**, recorded because it is the obvious next question and
answering it here would be the mistake: a two-hour job still dies with the session. [[open]] item 6
(job identity that outlives a window) owns that, and [[open]] item 10 owns whether the
scheduler/daemon line moves at all. Round 4 makes the two hours *visible*; it does not make them
survivable, and `--help`'s "a command that must outlive this window wants systemd" is still the
honest answer.

**One item this round supplies evidence for rather than closing.** [[open]] item 8 asks whether the
budget should move to `run`; the job that opened this round carries `--budget 120` belonging to
*jam*, not to sky.boss, which is the mockup's own resolution — sky.boss follows a foreign supervisor
that owns the budget — arriving as a real case rather than an argument. And [[open]] item 1, the
failure screen, is marked *blocked on evidence*; an accruing two-hour agent run is the first thing
here likely to produce some.
