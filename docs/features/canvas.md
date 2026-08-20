---
status: draft
created: 2026-08-20
updated: 2026-08-20
agent_value: 3
key_files: []
---

# The canvas — a command palette over a window canvas

## Why

`tb tui` proved the output contract works with a second consumer, and then ran into the ceiling of
its medium. The design the operator actually wants is a **command palette that opens results as
windows** — tiled or floating, draggable, pinned, each re-running its command on a cadence. A
terminal cannot do that well. Free-form overlapping windows are the central metaphor here, and
every hour spent making Textual do them is an hour spent fighting the framework rather than
building the thing.

The mockup at `docs/design/tackle-box-demo.html` is the target, and it is clickable rather than
drawn, so the interactions are already settled: `Ctrl-K` for the palette, chips that re-run a
command with different flags, a per-window refresh interval, tags, and a status bar counting
tasks, windows, watchers and things wanting attention.

The demand this puts on tb is small, which is the point. **Commands already return a `Result` and
never print.** The TUI was the second consumer of that envelope; the canvas is the third, and the
command layer does not change to accommodate it. What changes is the shell around it.

## Shape

A loopback HTTP server in Python, a static frontend, and `tb ui` to start both and open a window.

**Backend** — Starlette on `127.0.0.1`, an ephemeral port, started by `tb ui` and dying with it.

- `GET /catalog` — the palette's suggestions, **derived from the live Click tree**, never a table.
  This is the TUI's hardest-won invariant and it carries over unchanged: a catalog written down
  twice is a catalog that drifts, and a palette that offers a command that does not exist is worse
  than no palette.
- `POST /run` — dispatch argv in-process, return the `Result` as JSON. Reuses `cli.output.capture`
  and the in-process dispatch lifted out of `cli/tui/dispatch.py`.
- `GET /watch` — an SSE stream per open window. **The refresh clock lives here, not in the
  browser.**

**The watcher clock is keyed to the connection, not to a timer.** A watcher runs while its stream
is open and stops when it closes. That is exactly "pauses when the window closes, continues when
the window is minimized" — minimizing does not drop a socket. Driving it from a JS `setInterval`
would not deliver that: a minimized window is a hidden page, and Chrome clamps hidden-page timers
to about one fire per minute, so a 5-second watcher would quietly become a 60-second one at the
moment you stopped watching. Server-side also means one clock rather than N drifting ones.

**Frontend** — Preact + htm as native ES modules, vendored, no build step and no `node_modules`.
The mockup's layout logic is already DOM math and transfers directly.

**Shell** — `tb ui` launches Chromium with `--app=`, which gives a chromeless window with its own
taskbar entry. This is a launch flag rather than an architecture: swapping to pywebview later
touches the launcher and nothing else. The system libraries for that (`webkit2gtk-4.1`,
`python-gobject`) are already installed on workstation, though not visible from the venv.

**The wrapped-CLI contract is `--json`.** Chips like `--sort rtt` re-sort client-side, which means
the frontend holds rows rather than a picture of rows. `jam pr list --json` already exists, which
is why it is the demo.

**Security.** A loopback port that executes argv is remote code execution bound to a port — any
page in any browser can POST to `127.0.0.1`. A capability token minted per launch and a strict
`Origin` check are in Phase 1, not bolted on later.

**Only reads get watchers.** The mockup already encodes this: every catalog entry carries
`watcher: true` except `run cam-health`, which is `task: true`. That is `tb run` is the single
command that acts, surviving into the new surface — auto-refreshing a read is a refresh,
auto-refreshing a write is a scheduler nobody asked for.

**Does not do:**

- **No daemon.** Nothing survives the last window closing. Deliberate, and the reason there is no
  scheduler, no state file, and no notion of a watcher that ran while you were away.
- **No remote, no multi-user.** Loopback only, one operator, one machine.
- **No credential handling.** Wrapped CLIs keep their own authentication; tb is never in the
  credential path. Unchanged from `CLAUDE.md`.
- **No ANSI-to-HTML fallback in Round 1.** A tool without `--json` is out of scope rather than
  half-supported. Rendering an ANSI table gives a picture of a table — no sorting, no chips, no
  resizing — and shipping it early would let it become the path everything takes.
- **No build step, no npm, no TypeScript** until something needs them.
- **Not a terminal emulator and not a shell.** Argv only. No stdin, no interactive commands, no
  pipes.

## Phases

### Round 1 — replace the TUI with the canvas (2026-08-20)

- [ ] **Phase 1 — the API.** `cli/canvas/server.py`: loopback Starlette, per-launch token, strict
      `Origin` check. `GET /catalog` off the live Click tree, `POST /run` returning a `Result`.
      Lift the in-process dispatch out of `cli/tui/dispatch.py` before it is deleted. Tests cover
      the token, the origin rejection, and that the catalog cannot be a hardcoded table.
- [ ] **Phase 2 — the watcher clock.** `GET /watch` as SSE, one scheduler per connection, cadence
      from `[0, 5, 30, 60, 300]`. Injectable clock, the way `cli/tui/watchdog.py` did it, so a
      cadence test costs milliseconds rather than five real seconds. Tests: a closed stream stops
      its watcher; an open one keeps firing.
- [ ] **Phase 3 — the shell.** `tb ui` starts the server and opens the `--app` window. Vendored
      Preact/htm, the palette wired to `/catalog`, one window rendering one `Result`. **Delete
      `cli/tui/` and the textual dependency in this phase**, not before — the canvas has to be
      able to dispatch and show a result before the thing it replaces goes.
- [ ] **Phase 4 — the demo.** `jam pr list --json` end to end: structured table, chips that re-run
      with flags, pin, cadence, manual refresh. Needs `cwd` pinned to `~/src/jam.sense` —
      jam's wrapper resolves its venv against cwd, so it is not runnable from anywhere despite
      being on PATH.
- [ ] **Phase 5 — window management.** Tiled and floating modes, drag, z-order on focus, close,
      tags, and the status bar counts.

## Notes

### Round 1 — choosing the medium (2026-08-20)

**Rejected: Qt/PySide6.** Native MDI windows and one language end to end, but it throws the
mockup away and rebuilds it in a layout system that fights this design, and the vendored Skyrow
design system is CSS that Qt only partly speaks.

**Rejected: Tauri.** The right answer if a Rust toolchain were already here. Two runtimes for one
operator on one machine is not.

**Rejected: Electron.** Bundles ~150MB of Chromium to duplicate the Chromium already installed.

**Deferred, not rejected: pywebview.** Removes the port entirely — the frontend talks over an IPC
bridge no web page can reach, which is a real security win given that the server executes argv.
Deferred because the venv sets `include-system-site-packages = false` and cannot see the system
`gi`, so the GTK backend needs either a venv change or a PySide6 install, and because DevTools
during the build is worth more right now. The migration is the launcher only, by construction.

**Rejected: a client-side refresh timer**, which is what the mockup does. It cannot express
"continue while minimized" — hidden pages have their timers clamped. This was the single most
useful thing to fall out of pinning down the watcher semantics before writing any code: the
requirement sounded like a UI detail and turned out to decide where the scheduler lives.

**What survives the TUI's deletion, and what dies with it.** Surviving: `cli/output.py` and its
thread-local capture, the in-process Click dispatch, and the rule that the catalog is derived
rather than written down. Dying: the watchdog, `os._exit` past a wedged worker, the bounded
`write_body`, and the chunked writes — all of them solutions to Textual-specific problems.

Their *lessons* survive even though the code does not. A 120k-line result will kill a DOM as dead
as it killed `RichLog`; the rule that no single result may be rendered unbounded has to be
rebuilt on the new substrate rather than assumed away by the change of medium.
