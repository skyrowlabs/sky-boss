---
slug: surface-stall
title: The surface must not be able to freeze
status: draft
created: 2026-08-20
updated: 2026-08-20
agent_value: 3
key_files: []
---

# The surface must not be able to freeze

## Why

The surface can be locked up by a single command, and when it locks up there is no way out —
`Ctrl+D` does nothing, `Ctrl+C` does nothing, and the screen stays drawn showing stale state. It
looks like a hang with no cause, which is why it went unexplained for a while: the surface is
still *painted*, so nothing suggests the event loop is the thing that stopped.

The reported trigger was "after a code change", and that turns out to be a coincidence of
workflow rather than a mechanism. What follows a code change is a command dispatched to see
whether it worked, and after a bad edit that command returns an enormous amount of text — a
repeated traceback, a runaway warning loop, a log tail. **The size of the output is the trigger.
The code change is just what tends to produce it.**

`cli/tui/app.py` opens by declaring the one rule that cannot be relaxed: *a dispatch never runs
on the event loop.* That rule is honoured — `pump()` queues, `work()` is `@work(thread=True)`,
and the dispatch itself genuinely runs off-loop. But the **result** comes back through
`call_from_thread(self.finished, result)`, and `finished` writes the whole thing into the
`RichLog` in one call, on the loop. The expensive half of a large dispatch was never on the
thread at all.

Measured on this machine, one `RichLog.write()` of a single large `Text`:

| lines in one write | loop blocked |
|---|---|
| 20,000 | 0.42 s |
| 40,000 | 1.95 s |
| 80,000 | 7.69 s |
| 120,000 | 17.47 s |

The curve is superlinear — roughly quadratic — so it does not degrade gently. Extrapolated,
300,000 lines is about two minutes of frozen surface and a million is around twenty. That is
indistinguishable from a permanent hang, and it is reachable from one `tb auto log` on a chatty
job.

Two things were ruled out by measurement rather than by reading:

- **Not garbage collection.** The same write with `gc.disable()` costs 7.33 s against 7.62 s.
- **Not accumulation.** A transcript grown to 20,000 lines by 25 successive writes never blocks
  for more than 0.038 s. The cost is in the *size of a single write*, not in the size of the log.
  `RichLog` is nonetheless unbounded (`max_lines` is unset), which is a memory problem worth
  fixing at the same time even though it is not the freeze.

There is a **second, independent defect** underneath, which the existing comment at
`cli/tui/app.py:373` already half-knows about ("^Q is the unconditional way out, and the only one
that works if a thread wedges"). `@work(thread=True)` runs on asyncio's default
`ThreadPoolExecutor`. `App.exit()` calls `workers.cancel_all()`, but cancelling a *thread* worker
only cancels the awaiting task — the thread itself runs on. `asyncio.Runner.close()` then joins
it with `asyncio.constants.THREAD_JOIN_TIMEOUT`, which on Python 3.14 is **300 seconds**. So a
genuinely wedged dispatch — an internal task with no timeout by design, a subprocess that never
returns — costs five minutes of dead terminal after the UI has already gone. Fixing the freeze
does not fix this, and `^Q` does not either.

## Shape

**Bound the write, not the output.** The dispatch keeps producing whatever it produces; the
surface stops trying to render all of it in one turn.

**Chunk the transcript write and yield between chunks.** `write_body` is already the single path
everything reaches the transcript through — the docstring says so and means it — so there is
exactly one site to change. Split the incoming `Text` into slices of ~1,000 lines and write them
with an `await` between, so the loop gets a turn and the key bindings stay alive.

This is faster as well as more responsive, which is the surprise worth recording. Same 80,000
lines:

| | total | worst single block |
|---|---|---|
| one write | 7.62 s | 7.62 s |
| 1,000-line chunks | 1.48 s | 0.337 s |

Five times cheaper in total, and twenty-two times better at the thing that matters. Chunking is
not a trade here; the one-shot path was simply the bad one.

**Truncate what a single dispatch may put on screen.** Beyond a ceiling — 10,000 lines is far
above any real output and far below the pain threshold — stop writing and append a marker saying
how many lines were dropped and where the whole thing is. Nobody reads the 60,000th line of a
traceback in a scrollback pane; they re-run with `--json` or open the log. The envelopes are
already retained on `last_envelopes` for `inspect`, so nothing is actually lost.

**Bound the transcript.** Set `max_lines` on the `RichLog`. It is not the freeze, but an
unbounded log in a surface designed to be left open for days is a leak with no upper limit.

**Make exit unconditional.** `^Q` should not have to wait 300 seconds for a wedged thread. After
`App.exit()`, if a dispatch worker is still running past a short grace period, leave with
`os._exit()` rather than joining it. The surface holds no unflushed state of its own — the ledger
is written by the job process, history is appended on submit — so there is nothing that a clean
interpreter shutdown protects. A second `^Q` should take the short path immediately.

**A stall must be able to explain itself.** Add a watchdog: a daemon thread that a loop timer
heartbeats, which on a stall past a threshold dumps every thread's stack to
`$STATE_DIR/tui-stall.txt`. This diagnosis took a morning of reading and four measurement
harnesses; the next one should take reading one file. It is cheap, it is off the loop, and a
daemon thread cannot itself delay exit.

**Does not do:**

- **Does not put rendering back on a thread.** Textual widgets are not thread-safe and
  `call_from_thread` is the correct boundary. The fix is to make the on-loop work small and
  interruptible, not to move it.
- **Does not bound what a command may return.** A command's envelope is the contract
  ([[output-contract]]) and truncation belongs to the surface that is displaying it, never to the
  command producing it. `--json` must keep emitting the whole thing.
- **Does not add a pager or a scrollback search.** Truncation points at the log; reading a large
  log is `tb auto log`'s job and it already exists.
- **Does not add timeouts to internal tasks.** `cli/run.py` argues deliberately that an internal
  task must not be interrupted mid-write, and that argument still holds. This makes a wedged task
  survivable from the surface rather than making it impossible.
- **Does not touch reload.** Editing code while the surface is open is [[surface-reload]].

## Phases

### Phase 1 — Stop the freeze

- [ ] Chunk `write_body` into ~1,000-line slices with a yield between them
- [ ] Truncate a single dispatch's transcript output at a ceiling, with a marker naming the
      dropped line count and pointing at `inspect` / `tb auto log`
- [ ] Set `max_lines` on the `RichLog`
- [ ] Test: a 100,000-line dispatch result never blocks the loop for more than ~0.3 s, asserted
      with a heartbeat timer in `run_test()` rather than by eyeballing it
- [ ] Test: the truncation marker appears, and `last_envelopes` still holds the full envelope

### Phase 2 — Always be able to leave

- [ ] `^Q` exits without joining a running dispatch worker past a short grace period
- [ ] A second `^Q` exits immediately
- [ ] Record in the binding comment that this is deliberate, and why `cancel_all()` cannot do it
- [ ] Test: exit completes promptly with a worker thread deliberately parked

### Phase 3 — Make the next stall self-explaining

- [ ] Daemon watchdog thread, heartbeated by a loop timer, dumping all thread stacks to
      `$STATE_DIR/tui-stall.txt` on a stall past threshold
- [ ] Note the file's existence in `tb check` or the surface's own help, so it gets found
- [ ] Test: the dump is written when the loop is deliberately blocked

## Notes

The diagnosis is in **Why** rather than here because it was done before any code changed — the
measurement tables are the evidence for the design, not a record of surprises during
implementation. Implementation surprises go below.

The first three hypotheses were all wrong and each is worth not re-testing:

- **Not the thread-join at exit.** Real, confirmed, and a genuine second bug (Phase 2), but it
  produces "screen clears, shell never returns". The reported symptom was the surface still
  drawn, which is the loop, not shutdown.
- **Not `/proc` reads on the tick.** `lanes()` reads `/proc/locks` and `/proc/PID/cmdline` every
  second on the loop, which looked like a candidate, and `_describe` on a process in
  uninterruptible sleep genuinely can block. But it has no relationship to a code change and the
  measured numbers were nowhere near.
- **Not `Text.from_ansi`.** It parses 2.7 MB in 0.099 s. The parse was never the cost; the render
  into strips was.
