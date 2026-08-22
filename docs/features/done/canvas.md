---
status: complete
created: 2026-08-20
updated: 2026-08-21
agent_value: 3
key_files:
  - cli/canvas/server.py
  - cli/canvas/watch.py
  - cli/canvas/runner.py
  - cli/canvas/catalog.py
  - cli/canvas/__init__.py
  - cli/canvas/static/app.js
  - cli/canvas/static/render.js
  - cli/canvas/static/api.js
  - cli/canvas/static/tb.css
  - cli/data.py
  - cli/theme.py
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
- `POST /run` — run argv in a **subprocess** (`tb --json …`) and return the envelope. Not
  in-process; see the Notes entry for why that reversed.
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

**Live reload rides the stream that already exists.** The server fingerprints `static/` on a
half-second poll and pushes a `reload` frame when a file changes. A stylesheet edit is swapped in
place; anything else is a full reload. There is no watcher library and no second channel.

**Shell** — `tb ui` launches Chromium with `--app=`, which gives a window with no tab strip, no
address bar and no bookmarks bar, and its own taskbar entry. This is a launch flag rather than an architecture: swapping to pywebview later
touches the launcher and nothing else. The system libraries for that (`webkit2gtk-4.1`,
`python-gobject`) are already installed on workstation, though not visible from the venv.

**The wrapped-CLI contract is `--json`,** and `tb wrap` is the door it comes through. Chips
re-filter client-side, which means the frontend holds rows rather than a picture of rows.
`jam pr list --json` already exists, which is why it is the demo.

**`run` acts; `wrap` reads.** That split is what the canvas reads to decide whether a window may
be given a cadence, and it is why `wrap` had to exist — with `run` as the only command, nothing on
the canvas was pinnable and the whole watcher half was unreachable. `wrap` carries no raw output:
a tool that printed something other than JSON has failed its contract, and the envelope says so
rather than becoming a second `tb run`.

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
- **No ANSI-to-HTML fallback.** Rendering an ANSI table gives a picture of a table — no sorting, no
  chips, no resizing — and shipping it early would let it become the path everything takes. That
  half stands: ANSI is *stripped*, never interpreted.

  The other half — "a tool without `--json` is out of scope rather than half-supported" — was
  reversed by [[text-reads]] on 2026-08-20. See the correction in Notes.
- **No build step, no npm, no TypeScript** until something needs them. The cost is real and is
  named in the Notes: the frontend has no automated tests.
- **Not a terminal emulator and not a shell.** Argv only. No stdin, no interactive commands, no
  pipes.
- **The surface never writes a tool.** Round 5 renders the TOOLBOX sidebar and opens what is in it;
  it gains no route that creates or edits one. The server is remote code execution bound to a port,
  and a write route would turn a transient compromise into a persistent one. See [[toolbox]].
- **No indeterminate progress bar.** A bar that animates without measuring something is decoration
  that reads as information. Round 5 ships the bar only for the one quantity actually known.

## Phases

### Round 7 — the palette accepts a command that is not tb's (2026-08-21)

- [x] Anything typed whose first word is not a tb command is offered as a **raw command**, expanding
      to `tb read -- <argv>`. The expansion is the suggestion's description, so what will run is
      visible before Enter rather than discovered after.
- [x] Appended rather than shown only when nothing else matched. `list` matches `tools` by
      description, and a raw entry that hid behind a description match would be a palette that
      sometimes accepts a command and sometimes silently does not.
- [x] A raw window runs in `$HOME` by default, supplied by the server since the browser cannot know
      it, and carries an **editable directory field**. Its argv is rebuilt from that field rather
      than stored, so changing it re-points the watcher instead of leaving it on the old one.
- [x] Expanding to `read` rather than `run`: the whole point is a window that refreshes, and only a
      read may be given a cadence.

### Round 6 — the palette moves into the bar (2026-08-20)

- [x] The fixed palette becomes an input in the top bar, bounded at `80ch`. Most argvs are short,
      and a prompt spanning a 3000px monitor is harder to read rather than easier.
- [x] Suggestions appear **only while the input has focus**, as a dropdown floating over the canvas.
      A list that is always open is a menu; this is a prompt, and its suggestions answer something
      you started typing.
- [x] `Suggestions` and `paletteKeys` extracted, so the bar prompt and the `^K` overlay cannot drift
      on selection semantics.
- [x] The prompt stops the bar's window drag on mousedown, or clicking into it would move the
      window instead of placing a cursor.

### Round 5 — the wireframe's chrome, and the toolbox sidebar (2026-08-20)

`docs/design/Tackle Box Surface.dc.html` is a second mockup and a different kind of one: the
original demo is static HTML, this is **data-bound** — `sc-for`, `sc-if` and `{{ }}` over the same
window model the canvas already has. That makes it readable as a specification rather than a
picture, and reading it against the build shows most of it is already here.

Already built, confirmed against `app.js` — `win.num`, `win.tags` with `＋tag`, the pin and
interval controls, `⟳`, `✕`, palette fixed vs floating, tiled vs floating, the clock, and the
tasks / windows / watchers / attention counters. This round is the remainder.

- [x] **TOOLBOX sidebar.** 184px, header `TOOLBOX`, footer `tb <tool>`. Lists catalog entries where
      `tb_saved`; clicking one opens its window and takes its `every` as the starting interval.
      The data behind it is [[toolbox]]; the chrome is here. Shipped with [[toolbox]] Round 1, as a
      card *below* the top bar rather than a flush panel beside it — the bar is the window's title
      bar and calls `begin_move_drag`, so narrowing it would trade drag area for alignment with the
      mockup. Revisit here if the alignment turns out to matter more than the drag width.
- [x] **Window footer** — **already existed.** `app.js` has rendered `summarise()` on the left and
      `duration_s` on the right since Round 1; the claim that it was thrown away was written
      without checking. All this round did was dim the right half, as the mockup draws it.
- [x] **Refresh countdown as the progress bar.** The mockup carries `hasProgress` / `progress` /
      `progressLabel` and does not say what fills them. A running command cannot: a subprocess has
      no percentage and a bar that animates to look busy is decoration pretending to be
      information. **A watcher can** — `interval` and `last_run` are both known, so the bar is time
      until the next refresh and the label is `next in 12s`. Determinate, honest, and it answers
      the question a pinned window actually raises. Shown only when pinned with a non-zero
      interval; `hasProgress` is false otherwise.
- [x] **Label the chips row `LINKED`.** Cheap and it names something currently unnamed.
- [x] **Decide whether chips gate on `pinned`.** Resolved: they do not. The mockup wraps the row
      in `<sc-if value="{{ w.pinned }}">`, and following it would mean pinning a window you did not
      want pinned just to toggle a flag on it. The label ships; the gate does not.
- [x] More cushion between the frame and the panels — the shell is frameless, so the app's padding
      *is* the window margin and there is no border outside it to give the content room.

### Round 4 — a native window (2026-08-20)

- [x] The close button closes the window, not only the server.
- [x] The shell is a native webview; `--browser` and `--no-browser` keep the old paths.
- [x] The surface's own bar moves the window, through the window manager.
- [x] A stable `WM_CLASS`, so the desktop and any window rule can name it.
- [x] Default scale back to 1.

### Round 3 — the window itself (2026-08-20)

- [x] One scale factor drives every size on the surface; `tb ui --scale`, default 2.
- [x] Rounder corners, softer edges, and hairlines that scale with everything else.
- [x] A favicon generated from the palette, so the window is not a generic globe.
- [x] A close button in the surface, and `POST /api/quit` behind the same guards.
- [x] `--kiosk` for a wall display, `--size` for geometry. Windowed stays the default.

### Round 2 — live reload (2026-08-20)

- [x] Server fingerprints `static/` and pushes a `reload` frame on the session stream.
- [x] The page swaps the stylesheet in place for a CSS-only change, and reloads otherwise.
- [x] Static responses carry `cache-control: no-cache`, so a reload cannot serve a stale module.

### Round 1 — replace the TUI with the canvas (2026-08-20)

- [x] **Phase 1 — the API.** `cli/canvas/server.py`: loopback Starlette, per-launch token, strict
      `Origin` check. `GET /catalog` off the live Click tree, `POST /run` returning a `Result`.
      Lift the in-process dispatch out of `cli/tui/dispatch.py` before it is deleted. Tests cover
      the token, the origin rejection, and that the catalog cannot be a hardcoded table.
- [x] **Phase 2 — the watcher clock.** `GET /watch` as SSE, one scheduler per connection, cadence
      from `[0, 5, 30, 60, 300]`. Injectable clock, the way `cli/tui/watchdog.py` did it, so a
      cadence test costs milliseconds rather than five real seconds. Tests: a closed stream stops
      its watcher; an open one keeps firing.
- [x] **Phase 3 — the shell.** `tb ui` starts the server and opens the `--app` window. Vendored
      Preact/htm, the palette wired to `/catalog`, one window rendering one `Result`. **Delete
      `cli/tui/` and the textual dependency in this phase**, not before — the canvas has to be
      able to dispatch and show a result before the thing it replaces goes.
- [x] **Phase 4 — the demo.** `jam pr list --json` end to end: structured table, chips that re-run
      with flags, pin, cadence, manual refresh. Needs `cwd` pinned to `~/src/jam.sense` —
      jam's wrapper resolves its venv against cwd, so it is not runnable from anywhere despite
      being on PATH.
- [x] **Phase 5 — window management.** Tiled and floating modes, drag, z-order on focus, close,
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


### Round 1 — what actually got built (2026-08-20)

**Reversed before writing a line of it: commands run in a subprocess, not in-process.** Phase 1
said to lift `cli/tui/dispatch.py`. The original reasoning was sound for a terminal — the envelope
comes back directly, there is no interpreter to start, and `capture` already existed to collect it.
What it did not survive is that a watcher fires *unattended*. A thread cannot be cancelled, so
`jam pr list` hanging on a `git fetch` would strand its thread forever, and six windows on a bad
network would accumulate stuck threads until the server died. That is the 300-second thread-join
bug rebuilt on new ground. A subprocess makes `--timeout` a guarantee rather than a hope, and
`tb --json` already prints the envelope, so nothing parses human output. Introspection stayed
in-process because reading the tree runs nothing: **reads in, execution out.**

**`tb wrap` was added, which the doc did not call for.** Phase 4 asked for the `jam pr list` demo
with pin and cadence, and it could not be built: `run` is the only command, `run` acts, and an
acting command may not be given a cadence. So nothing was pinnable and Phase 2's entire mechanism
was unreachable from the UI. The mockup had already drawn this line — `wrap docker ps` carries
`watcher: true`, `run cam-health` carries `task: true` — and tb had no equivalent. `wrap` is not
the passthrough `CLAUDE.md` rejects: it does something the wrapped tool cannot express, which is
to hold itself open on a canvas and re-run itself, and it returns parsed data rather than bytes.

**Two bugs that were real rather than test artifacts.**

The session leaked when a window closed before its first tick. The `hello` yield sat outside the
`try`, and a `GeneratorExit` at a yield outside a `try` skips the `finally` — which is the only
thing that removes a session. Every fast open-and-close would have left one behind forever.

The palette filtered on the whole typed line, so `run -- df -h /` matched no command, the
suggestion list emptied, and Enter silently did nothing. Every command worth opening a window on
takes arguments, so that was the entire feature. A line now names a command once its name is
complete and a space follows; everything after is argv and narrows nothing.

**Three things that hung rather than failed, all worth remembering.** Starlette's `TestClient`
collects a whole response body before returning, so a stream that never ends cannot be opened
through it at all — the session loop had to be lifted out of the route to be testable, which was
the right shape anyway. Then a "stop after N frames" guard bounded how many frames were accepted
and not how long to wait for one, so a loop that yielded nothing blocked on the first pull. The
bound has to be a timeout. And a property about what *does not* happen is now tested against
`Session.due()` rather than the generator, because proving a negative by waiting is how a suite
gets slow.

**`request.is_disconnected()` is unusable here** for the same `TestClient` reason, so cleanup runs
through `GeneratorExit` and a dropped connection is noticed on the next write. That is what the
heartbeat is for.

**The frontend has no automated tests, and that is the round's real debt.** There is no JS test
runner, and adding one means npm, which the shape section rules out. Everything was verified by
rendering headless Chromium against the live server and reading the DOM back — which caught both
frontend bugs above, and is not the same as a suite. The pure parts (`unwrap`, `suggest`,
`roleFor`) are the parts worth testing and the parts a runner would be for. Worth revisiting if
the frontend grows.

**Deleted `TUI_STYLES`/`TUI_THEME`,** whose only consumer was the surface being replaced. The
concept survives as `cli/theme.css_variables`: the canvas paints `BG` itself, so it takes the
tokens undarkened, exactly as the TUI did, but it renders from the envelope's data rather than
from tb's bytes so it needs CSS custom properties rather than a Rich theme. The hex scan now
follows the surface rather than the language — `.css` and `.js` too, vendored code exempt — plus a
check for `rgba()` literals, which is the form the drift would actually take here given the mockup
is built out of them.

**`cli/output.capture` now has no consumer.** It was the mechanism the TUI rendered through, and
the canvas does not render tb's bytes at all. It is kept, tested and documented, but nothing in
the shipped surface calls it. It is a candidate for deletion the next time this area is opened.


### Round 2 — live reload (2026-08-20)

The first question ever asked of this project was whether the surface could take a live code edit
without dying. In the terminal the answer was no and deliberately so — widget classes were already
instantiated and timers held bound methods captured at mount, so a reload would have produced
wrong output that looked right. **In this medium the answer is yes for the half that matters.**

**It rides the stream rather than adding anything.** The session already pushes frames on a
half-second tick, so a fingerprint of `static/` costs nine `stat` calls per poll and a new frame
type. No watcher library, no second channel, no `--dev` flag to remember: the whole thing is about
forty lines because the hard part was built in Round 1 for another reason entirely.

**A stylesheet edit is swapped in place, and that is the whole point.** Every window keeps its
position, its pin, its chips and its last result while the CSS changes underneath it. Reloading
the page for a colour change would throw all of that away — the canvas has no persistence, so the
windows exist only in the tab. Anything that is not CSS is a full reload, which does lose every
window, and should: the module graph is already evaluated, and half-old, half-new JavaScript
holding live state is precisely the "wrong but looks right" failure the terminal version refused
to risk. The rule did not change; the medium made half of it cheap.

**`cache-control: no-cache` was needed and is not what it sounds like.** It means "revalidate
before use", not "do not store", so the ETag still answers 304 and nothing is re-sent. Without it
the browser applies heuristic freshness and can serve a module it fetched moments ago from memory
— which is exactly the window live reload operates in.

**Two checks failed before the code did, both worth recording.** A headless verification that
edited a file on disk and looked for the page reacting proved nothing, because
`--virtual-time-budget` fast-forwards page timers: the page took its "after" snapshot before the
edit happened in wall-clock time. And stubbing `location.reload` to observe a full reload throws
in a modern browser — `Location` will not be redefined. The fix for the second is better code
rather than a better test: `planReload` decides and `applyReload` acts, so the decision is
checkable without touching navigation at all.

**Cleared the state directory of everything the removed systems left**: `jobs/`, `tui-history`,
and 28 MB of `tui-stall.txt` from the freeze investigation. `browser-profile/` is the canvas's own
and stays.


### Round 3 — the window itself (2026-08-20)

**Every size on the surface is now one number.** `--tb-scale` is injected into the page from
`tb ui --scale`, and the stylesheet is written entirely in `rem` where `1rem` is four scaled
pixels — so a design pixel divided by four is its rem. The alternative was forty numbers that
drift apart the first time anyone adjusts one of them.

Two approaches were rejected on the way. **CSS `zoom` is a one-liner and breaks dragging**: the
drag maths compares `clientX`, which is in unzoomed viewport pixels, against `left`, which is in
zoomed ones, so a window would move at half the speed of the mouse. And
**`--force-device-scale-factor` overrides the display's own scaling rather than multiplying it**,
so on a HiDPI screen "2" would mean *no change* rather than *twice as big* — the flag pins a value
where the request was for a factor.

Hairlines scale too. A 1px border left literal turns into a thread at 2x: still technically
present, gone as far as the eye is concerned.

**There is no Chromium flag for a frameless window that is still resizable.** `--kiosk` removes
the frame by going full-screen, which is a different thing — it cannot be sized or moved, and was
briefly the default until that was tried and was obviously wrong. It remains available for a wall
display. Stripping the title bar while keeping the window sizable is the *window manager's* job:
on KDE a KWin rule matched on the window class, which is why `--class=tackle-box` is set here. A
rule is a change to the operator's own desktop and is theirs to make, so nothing here writes one.

**The close button exists because the frame may not.** It sets a latch the launcher waits on,
rather than calling `window.close()` — which is only reliably permitted on a window a script
opened, and neither a full-screen window nor an `--app` window is one. It is guarded by the same
token and origin checks as running a command: ending a session is a real effect, and a page you
did not open must not be able to cause it.

That latch was first watched only inside the browser thread, so with `--no-browser` — the mode you
develop in — pressing the button set it and nothing happened. It is watched in every mode now.

**Two bugs the screenshots caught that the tests could not.** The top bar's controls were shrinking
under flex's default, so `floating` rendered as `floatin` with the close button sitting on top of
it — invisible at 1x, obvious at 2x, and a class of fault no unit test here would have found. And
the theme suite failed on `--tb-scale`, correctly: it is injected by the server rather than owned
by the palette. The fix was to make the test state the real rule — **a token used with a fallback
is exempt, a bare one is not** — because `var(--tb-scale, 2)` carries a default precisely so a
failed substitution renders at normal size instead of collapsing the surface to zero.


### Round 4 — a native window (2026-08-20)

**The migration cost what it said it would.** Round 1 recorded pywebview as *deferred, not rejected*
and promised the change would be "the launcher only". It was: `cli/canvas/shell.py` is new, the
launcher chooses between it and Chromium, and the server, the frontend and all 106 tests were
untouched. Everything the page talks to is still HTTP, which is what made the swap cheap.

**GTK rather than Qt** because WebKitGTK 4.1 and python-gobject are already installed here, so the
backend downloads nothing where Qt would bundle a second Chromium at 244 MB. The price is
`include-system-site-packages` on `.venv`, since the bindings are system-owned. Venv packages still
take precedence — checked, because that is the failure that would matter.

**Three things that only appear when you run it.** WebKitGTK dies on a native Wayland session with
`Gdk-Message: Error 71 (Protocol error)` before any window appears and with no other diagnostic; a
bare GTK window realises fine on the same session, so it is WebKit's fault rather than GTK's, and
it runs under XWayland instead. The DMABUF renderer then narrates `Failed to create GBM buffer` at
the launching terminal on every resize. And pywebview probes Qt first on this install, reporting
`No module named 'qtpy'` — which sends you hunting a Python package when the backend you want is
present and working. All three are settled in `shell.py` rather than left to be rediscovered.

**The drag region is not what the documentation says.** `pywebview-drag-region` is a Cocoa and
Windows feature; **the GTK backend implements no drag regions at all**, offering only `easy_drag`,
which makes the whole page a handle — exactly wrong on a canvas of draggable windows, where it
would mean dragging a window inside the canvas also drags the canvas. So the bar asks for the move
itself and hands it to `Gtk.Window.begin_move_drag`, which is what a real title bar does: the
window manager takes over, so the drag snaps, tiles and crosses monitors instead of being
reimplemented in JavaScript. **Confirmed working with a real mouse.**

**`frameless=True` is requested and refused.** GTK reports `DECORATED = False` — verified against
our exact arguments and against the same call in isolation — and KWin draws a title bar anyway.
Confirmed on the operator's session, and confirmed to be the *native* window rather than a leftover
browser one: the closed window's envelope named the same ephemeral port as the screenshot showing
the frame. Removing it is therefore a window-manager rule matched on `WM_CLASS`, which is why the
shell sets one. KDE's right-click *No Border* does it for a single window and does not persist; the
durable form is in the README. **Nothing here writes that rule** — a desktop is the operator's, not
the tool's.

**Naming the window cost the shell its backend, once.** Importing `Gdk` without a version pins it
to a default, and pywebview's own `gi.require_version('Gtk', '3.0')` then raises — so it concluded
GTK was unavailable, fell through to Qt, and reported "You must have either QT or GTK with Python
extensions installed" on a machine where GTK was installed and working. The requirements come
first now, and the comment says why.


**The close button did not close the window.** Shutdown had one direction wired and not the other:
closing the *window* told the server to stop, and nothing told the *window* to stop when the server
was asked to. So the surface's own ✕ killed the server and left a dead window on screen with the
process still running.

Neither browser mode could have shown it. `--no-browser` has no window, and `--browser` terminates
a child process it can see — the native shell is the only mode where the window lives inside the
same process and has to be told. The test that existed proved the button *set the latch*; nothing
proved anything listened, which is the half that was missing.

Two things about measuring it are worth keeping. The fix looked slow — a `duration_s` of twenty
seconds — until the measurement was done properly: that field covers the whole session, so it was
counting the sleep before the button was pressed. Timed from the press, quit to exit is **0.31s**.
And `pgrep -f "m cli ui --port 8796"` matches the shell command *containing* that string, so a
liveness check written that way reports its own caller as the process it is looking for, and every
run says the process survived.

### Round 5 — reading the second mockup against the build (2026-08-20)

`Tackle Box Surface.dc.html` is data-bound rather than drawn — `sc-for`, `sc-if`
and `{{ }}` over the same window model this already has — which makes it
readable as a specification. Read against `app.js`, most of it turned out to be
built: `win.num`, tags, pin and interval, `⟳`, `✕`, palette fixed and floating,
tiled and floating, the clock, and all four counters.

**One planned item did not exist to build.** The round was written claiming the
window footer threw `summarise()` away. It does not, and never did —
`app.js` has rendered it on the left with `duration_s` on the right since Round
1. The claim was written from the mockup rather than from the file, which is the
exact failure `CLAUDE.md` opens by warning about. Only the dim on the hint half
was real work.

**The progress bar had to be given a meaning before it could be built.** The
mockup carries `hasProgress`, `progress` and `progressLabel` and never says what
fills them, and the obvious reading — a bar for a running command — is not
available: a subprocess has no percentage, and a bar that animates to look busy
is decoration that reads as information. A *watcher* has one, because `interval`
and `last_run` are both known. So the bar is time-to-next-refresh, shown only
while pinned with a cadence and not mid-run, and the title bar keeps saying
"running…" for the case with nothing to measure.

It reads the label clock, which is throttled in a hidden page. That is correct
and is what the Round 1 split bought: the *refresh* clock is in Python keyed to
the connection, so a throttled bar lags behind a refresh that still happened on
time. A stale bar is a cosmetic bug; a throttled scheduler would be a silent one.

**The mockup was overruled once.** It wraps the chips row in
`<sc-if value="{{ w.pinned }}">`. Following that would mean pinning a window you
did not want pinned in order to toggle a flag on it, which is a mockup
convenience rather than a rule. The `LINKED` label shipped; the gate did not.

**A bug only a screenshot would have found.** `.grid.shaped` sets flex rows, but
`.grid` was still `display: table`, and a table sizes to its content — so the
rows were measured against the widest row rather than against the window. The
columns clipped correctly *and* the table overflowed sideways, which reads as
broken clipping when the container is what is wrong. Reading the DOM back would
never have caught it: every element was present and every style was applied.
It took rendering the page and looking at it.

**Cushion.** The app's padding *is* the window's margin — the shell is frameless,
so there is no title bar or border outside it to give the content room. Widened,
along with the gaps between panels.

**Deferred.** The sidebar is a card below the top bar rather than a flush panel
beside it, where the mockup puts it. The bar is the window's title bar and calls
`begin_move_drag`; narrowing it to reach the top-left corner would trade drag
area for alignment. Worth revisiting only if the alignment turns out to matter
more than the drag width.

### Correction — a tool without `--json` is back in scope (2026-08-20)

Round 1's *Does not do* said "a tool without `--json` is out of scope rather than half-supported",
and the reasoning under it was about **ANSI**: rendering escape codes as colour gives you a picture
of a table, and a picture cannot be sorted or filtered.

That reasoning was right and is untouched — [[text-reads]] strips ANSI rather than interpreting it.
What the entry got wrong was the scope it drew from it. "Cannot be sorted" is a reason not to
*pretend* text is a table; it is not a reason to refuse to show text at all. The tool this repo
uses daily prints an aligned table with a legend under it that is better than anything rebuilt from
its own JSON, and refusing to display it was refusing the operator their own tool's design.

The real gap was never display in any case: `tb run` already carried the bytes. It was that `run`
acts, so the only command that carried text was the one command that must never be put on a timer.

### Round 7 — a palette that accepts what you actually typed (2026-08-21)

The request read as "stop making me call tb". What it turned out to mean is narrower and better:
*stop making me type tb's prefix*. tb still executes — through `tb read`, which is what gives the
window an envelope, a killable subprocess and a cadence. Only the typing changed.

**The interesting problem was the working directory, not the parsing.** A raw command has no place
to put `--cwd`, and the canvas inherits whatever directory `tb ui` was launched in — so a canvas
started inside this repo runs `jam pr list` with tackle-box's `cli/` package shadowing jam's own
and hands back tackle-box's error message. Defaulting to `$HOME` fixes it for a reason worth
writing down: a home directory has no `cli/` package to shadow anything. It is neutral rather than
merely conventional, and the same property makes it right for the next tool with the same bug.

The window carries that directory as an editable field, and **rebuilds its argv from it** rather
than storing the argv. Storing it would have left a watcher re-running the old directory after the
field changed — a window claiming to show something it is not, which is the failure this surface
keeps having to design against.

**Appended, not conditional.** The obvious rule is "offer a raw command when nothing else matched",
and it is wrong in a way that only shows up on particular input: `list` matches `tools` by its
description, so a conditional raw entry would vanish for some queries and appear for others with no
rule the operator could hold in their head. It is appended whenever the first word is not exactly a
tb command, which is a rule you can state in one sentence.

**And it expands to `read`, never `run`.** The whole point is a window that refreshes, and only a
read may be given a cadence. A raw command that wants to write is typed with `run --` in front of
it, which is the same explicit assertion `wrap` and `read` already ask for.

### 2026-08-21 — the words moved; the history stays (supersession)

`wrap` was renamed `data` and the `every` field renamed `refresh` — hard renames, no aliases;
see [[refresh]]. This doc predates the rename and its prose says `wrap` because it *was*
`wrap`; that is history being accurate, and nothing above has been scrubbed.
