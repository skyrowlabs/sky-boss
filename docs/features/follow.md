---
status: active
created: 2026-08-21
updated: 2026-08-21
agent_value: 3
key_files: []
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
- [ ] **The canvas.** Stream frames for follow/run/read windows over the session stream; dead
      state + restart affordance; window close SIGTERMs the child — a test extends "a watcher
      dies with its window" to processes.

## Notes

### Round 1 — written as spec, from the constitution (2026-08-21)

The unification ("a Job is a stream that ends") was the operator's ratified answer to the
one-time / long-process / file-change taxonomy: one mechanism, shapes as policy, duration
discovered. The dead-streams rule (visible death, manual restart) predates this doc and is
inherited, not re-decided. `wrap`'s at-exit carve-out was almost re-litigated here and should not
be: a streamed JSON document is unparseable until its last byte, so "stream it anyway" has no
meaning — the running-since clock is the honest rendering of an in-flight data read.
