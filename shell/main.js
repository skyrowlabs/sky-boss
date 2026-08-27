/* The window — or rather, the windows.
 *
 * cli/canvas/shell.py exists because three things are impossible in a browser:
 * a frameless window that is still resizable, a page that moves its own
 * window, and no port exposed to any other tab. This shell inherits all three
 * and adds the one pywebview could not reasonably give: **a command is an OS
 * window.** Not a div the canvas draws and drags, but a window the window
 * manager tiles, snaps and moves like every other window on the desktop —
 * which is what "tiled and floating" was always trying to describe.
 *
 * The promise shell.py made, and kept, was that the migration was "the
 * launcher only": the server, the frontend and every test untouched. This one
 * makes the same promise about cli/. Nothing here is imported by Python and
 * nothing in Python knows this exists; `sb ui --no-browser` is the entire
 * interface, and it is a documented mode that already had to work.
 */

const { app, BrowserWindow, ipcMain, shell: os } = require("electron");
const path = require("node:path");

const bridge = require("./bridge.js");

/* The window registry.
 *
 * ---------------------------------------------------------------------------
 * This is the one place the multi-window model costs something real, and it is
 * worth stating plainly rather than discovering later.
 *
 * `Session` in cli/canvas/watch.py says:
 *
 *     The stream is the lifetime. There is no unregister-on-close to forget,
 *     because closing the stream drops the whole session.
 *
 * That holds because one page means one stream. It does not survive N windows:
 * a session scoped to whichever window happened to open the stream would take
 * everyone's watchers down when that window closed. So the session moves up
 * here, outlives any individual window, and windows register and unregister
 * against it — the unregister-on-close that docstring was glad not to have.
 *
 * The consolation is that it is *more* reliable here than the browser version
 * it replaces. A tab that vanishes is inferred from a dropped socket; a window
 * that vanishes tells this process directly, and a renderer that dies without
 * saying goodbye still fires `render-process-gone`. Both routes below land on
 * the same `release`, so the leak the old design avoided by construction is
 * avoided here by having exactly one exit.
 *
 * What is still owed: a window whose renderer wedges without dying holds its
 * watcher forever. sb's own heartbeat frame is the material for a liveness
 * check; this sketch does not spend it.
 * ---------------------------------------------------------------------------
 */
const windows = new Map(); // window_id → BrowserWindow

let ctx = null; // the running sb: url, token, child
let session = null; // learned from the `hello` frame
let endStream = null;
let quitting = false;

const FRAMELESS = process.env.SB_FRAME !== "1";

function create({ argv = null } = {}) {
  const win = new BrowserWindow({
    width: argv ? 720 : 900,
    height: argv ? 460 : 600,
    minWidth: 480,
    minHeight: 260,
    // The surface carries its own close button, guarded like every other
    // route, because the frame it would otherwise rely on may not be there.
    frame: !FRAMELESS,
    backgroundColor: "#0d0f12", // TODO: read cli/theme.py BG through the catalog
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // The clamping the README argues around: a browser timer in a hidden tab
      // is held to roughly one fire a minute. Chromium does the same to an
      // occluded window unless told not to. sb keeps its refresh clock in
      // Python and does not depend on this — but the *label* clock, and the
      // progress bar reading it, are cosmetic bugs today only because that is
      // true. Here they need not be bugs at all.
      backgroundThrottling: false,
    },
  });

  const id = String(win.id);
  windows.set(id, win);

  win.once("ready-to-show", () => win.show());
  win.webContents.once("did-finish-load", () => {
    win.webContents.send("sb:ready", { windowId: id, session, argv });
  });

  // Both deaths, one exit. See the registry note above.
  const release = () => {
    if (!windows.delete(id)) return;
    if (quitting || !ctx || !session) return;
    bridge.unwatch(ctx, session, id).catch(() => {});
    bridge.unfollow(ctx, session, id).catch(() => {});
  };
  win.on("closed", release);
  win.webContents.on("render-process-gone", release);

  // A link is a link. Anything a result wants to open belongs to the desktop's
  // browser, not to a window that is meant to be showing a command.
  win.webContents.setWindowOpenHandler(({ url }) => {
    os.openExternal(url);
    return { action: "deny" };
  });

  win.loadFile(path.join(__dirname, "window.html"));
  return win;
}

/* Frames, routed.
 *
 * A frame naming a window goes to that window and no other — `run` and
 * `stream` both carry one. Everything else is the session speaking about
 * itself, and every window wants it: `hello` (which is where `session` comes
 * from), `beat`, and `reload`. */
function dispatch(frame) {
  if (frame.type === "hello") {
    session = frame.session;
    for (const win of windows.values()) {
      win.webContents.send("sb:ready", { windowId: String(win.id), session });
    }
    return;
  }
  if (frame.window) {
    windows.get(String(frame.window))?.webContents.send("sb:frame", frame);
    return;
  }
  for (const win of windows.values()) win.webContents.send("sb:frame", frame);
}

function down(error) {
  if (quitting) return;
  for (const win of windows.values()) {
    win.webContents.send("sb:down", { error: error ? String(error) : null });
  }
}

/* Every call the renderer is allowed to make, and the session is supplied
 * here rather than accepted from there. A window may only ever speak about
 * itself: the id comes from the sender's own BrowserWindow, so a renderer
 * cannot stop a watcher belonging to a window it does not own. */
function wire() {
  const own = (event) => String(BrowserWindow.fromWebContents(event.sender)?.id);

  ipcMain.handle("sb:catalog", () => bridge.catalog(ctx));
  ipcMain.handle("sb:run", (_e, argv, timeout) => bridge.run(ctx, argv, timeout));
  ipcMain.handle("sb:watch", (e, argv, interval) =>
    bridge.watch(ctx, session, own(e), argv, interval)
  );
  ipcMain.handle("sb:unwatch", (e) => bridge.unwatch(ctx, session, own(e)));
  ipcMain.handle("sb:follow", (e, argv) => bridge.follow(ctx, session, own(e), argv));
  ipcMain.handle("sb:unfollow", (e) => bridge.unfollow(ctx, session, own(e)));

  // A command opens a window. This is the line the whole shell is for.
  ipcMain.handle("sb:open", (_e, argv) => String(create({ argv }).id));

  // Window management the page could never do in a browser, and the reason
  // shell.py had to reach for Gtk.Window.begin_move_drag. Here the frame is
  // Chromium's own, so a `-webkit-app-region: drag` bar asks the platform for
  // the same move — VERIFY THIS FIRST on your window manager. If the drag does
  // not snap and tile the way GTK's does, that is the one behaviour this shell
  // regresses, and `SB_FRAME=1` is the fallback until it is fixed.
  ipcMain.handle("sb:close", (e) => BrowserWindow.fromWebContents(e.sender)?.close());
  ipcMain.handle("sb:quit", () => app.quit());
}

app.whenReady().then(async () => {
  // A stable window class, so the desktop can tell these windows from every
  // other Chromium one — for the taskbar, and for a window-manager rule if the
  // operator wants one. shell.py sets the same string for the same reason, and
  // like that one, nothing here writes the rule itself.
  app.setName("sky.boss");
  bridge.reapOnSignal(() => ctx);

  try {
    ctx = await bridge.start({ sb: process.env.SB_BIN || "sb" });
  } catch (error) {
    // Not a blank window with no explanation. The launcher's failure belongs
    // in the terminal the operator launched from.
    console.error(`shell: ${error.message}`);
    app.exit(1);
    return;
  }

  wire();
  endStream = bridge.stream(ctx, dispatch, down);
  create();
});

app.on("window-all-closed", () => app.quit());

/* The session ends when this process does, which is the lifetime rule the old
 * one had, moved up exactly one level: there, the stream was the session's
 * life; here, the application is. sb is asked to quit rather than killed, so
 * its own teardown runs — every follower is a child process that would
 * otherwise be reparented rather than reaped. */
app.on("before-quit", async (event) => {
  if (quitting || !ctx) return;
  quitting = true;
  event.preventDefault();
  endStream?.();
  await bridge.quit(ctx).catch(() => {});
  // It was asked. If it has not gone in a second, it is not going politely.
  setTimeout(() => {
    ctx.child.kill("SIGTERM");
    app.exit(0);
  }, 1000);
  ctx.child.once("exit", () => app.exit(0));
});
