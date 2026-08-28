# shell — the Electron window

Two shells, one bridge. Both spawn `sb ui --no-browser --port <free>` and
change nothing under `cli/`.

```bash
cd shell && npm install     # ~300 MB of prebuilt Chromium, once
npm run start:canvas        # canvas-main.js — one window, the canvas inside
npm start                   # main.js — one OS window per command
```

`sb` must be on PATH, or set `SB_BIN`.

Three environment variables, because Electron consumes argv before either entry
point sees it and there is no second CLI here to grow a flag on. A host takes
its configuration from the environment.

| | |
|---|---|
| `SB_BIN` | Which `sb` to spawn. Defaults to whatever is on PATH |
| `SB_FRAME=1` | Give the window its normal frame back. The default is frameless, which the window manager will still resize but gives you nothing visible to grab |
| `SB_SIZE` | `1600,1000` or `1600x1000` — spelled the way `sb ui --size` spells it, and defaulting to the same 1600×1000. An unparseable value warns and falls back: a typo in a window size should cost you a window the wrong size, not a surface that will not open |

**`canvas-main.js` is the one to look at.** ~100 lines, no preload and no IPC:
it opens a single window on `ctx.url` and gets **whatever page sky.boss is serving
today**, unchanged, token and all. Panes stay divs, the layout stays the
canvas's, and a pane reading another pane stays a lookup in one JS heap. It is
a like-for-like replacement for `cli/canvas/shell.py`, which makes it the only
honest way to compare the two: same product, same frontend, different host.

Deliberately not a list of files. It used to name `index.html`, `app.js`,
`render.js` and `sb.css`, and the workbench added a fifth on 2026-08-27 without
this file noticing — which is the point being made: **the shell gains a screen
by the server growing one.** [[workbench]] round 1 needed no change here at
all, and the frontend fix it did find — a panel that wrapped at 1100px — was
found *because* Electron's default window is narrower than a browser's.

**`main.js` is the road not taken**, kept because it is cheap to keep. Every
command becomes an OS window the window manager tiles and snaps. It works —
and it is a different product, in which the canvas does not exist.

## Canvas mode, in full

What it buys over pywebview: a pinned Chromium instead of whatever WebKitGTK
the distro shipped, DevTools, `backgroundThrottling: false`, and the option to
tear a single pane out into a real window later without rearchitecting for it.

What it costs: npm, and ~300 MB.

That is a thin margin against a shell that already works, and it should be
treated as one. Run both.

One thing it has to do by hand: `app.js:172` makes the bar the title bar by
calling `window.pywebview.api.start_move`, and degrades to a no-op when that
object is missing — which it is here. `canvas-main.js` injects
`-webkit-app-region` instead of committing it to `sb.css`, because the frontend
is read by four hosts and a line about Electron does not belong in it.

## The promise

`cli/canvas/shell.py` opens by saying its migration was "the launcher only —
the server, the frontend and every test are untouched." This shell makes the
same promise about `cli/`, and the smoke test above is what keeps it honest:
nothing here is imported by Python, and nothing in Python knows this exists.

The seam was already cut. `cli/canvas/static/api.js` says so in its own first
paragraph — "swapping the browser for a native webview later replaces this file
and nothing else." `bridge.js` and `preload.js` together *are* that file,
split across the process boundary.

## What is real

| | |
|---|---|
| `bridge.js` | Spawns sky.boss, waits for the bind, reads the token off `/`, speaks every route, and reaps the child on a signal. Verified against the live server |
| `canvas-main.js` | One window on the existing page. No preload, no IPC |
| `main.js` | Window registry, session lifetime, frame routing by `frame.window` |
| `preload.js` | `api.js`'s shape, minus `session` and `window` — the main process fills both in from the sender |

`preload.js` and `window.*` belong to `main.js` only; canvas mode needs none of
them.

## What is a stub

`window.js`, `window.html`, `window.css`. They exist so the pipe can be seen
working and are meant to be deleted.

The renderer that belongs here is `cli/canvas/static/render.js` — it already
knows how to draw the `view` envelope, and it carries the rule worth keeping
across every substrate this surface has had: **no single result may render
unbounded.** The terminal froze for that; then a browser tab died of it. A
window is not exempt. Port `render.js` before showing this to anything real.

## The one thing that got harder

`Session` in `cli/canvas/watch.py` is proud, correctly, that "the stream is the
lifetime — there is no unregister-on-close to forget." That holds because one
page means one stream, and it does not survive N windows. The session moves up
into `main.js`, outlives any individual window, and windows register and
unregister against it.

It is more reliable there than the thing it replaces: a tab that vanishes is
inferred from a dropped socket, while a window that vanishes tells the main
process directly, and a renderer that dies without saying goodbye still fires
`render-process-gone`. Both land on one `release`.

Still owed: a window whose renderer wedges without dying holds its watcher
forever. sky.boss's own heartbeat frame is the material for a liveness check.

## Verify first

1. **Drag.** `-webkit-app-region: drag` is a Cocoa and Windows story; its Linux
   behaviour is not the same thing, and it may not hand the move to the window
   manager the way `Gtk.Window.begin_move_drag` does. If it does not snap and
   tile, that is the one behaviour this shell regresses against `shell.py`.
   `SB_FRAME=1` restores a normal frame until it is fixed.
2. **Many small windows on your WM.** One window per command is excellent on a
   tiling WM and can be worse than the canvas on stock GNOME.
3. **`backgroundThrottling: false`** actually holding for an occluded window.
   sky.boss keeps its refresh clock in Python and does not depend on it — but the
   label clock and the progress bar reading it are cosmetic bugs today only
   because that is true.

## Found by running it

`before-quit` is Electron's own lifecycle and a signal does not enter it. A
`SIGTERM` to the main process therefore left `sb` running, reparented to init,
with its port still bound — and stopping the shell from the terminal that
started it is how a shell under development is stopped nearly every time.
`bridge.reapOnSignal` fixes it; both entries call it.

## Noticed while testing

`/api/quit` prints a `CancelledError` traceback from uvicorn's lifespan
teardown — `stop()` sets `force_exit`, which cancels it. Pre-existing and on
sky.boss's side of the line; visible here only because the shell keeps the child's
stderr instead of dropping it. Cosmetic, but "a working surface should not
narrate at them" is already the rule.

## Not done

- Frames rendered as anything but JSON (port `render.js`)
- The palette as a palette — filtering, keys, `cli/keys.py`'s bindings
- Cadence UI, which must read `acts` and refuse a write a refresh
- `follow` windows, which want a real terminal rather than a `<pre>`
- Window geometry across restarts, and stdio instead of the port
