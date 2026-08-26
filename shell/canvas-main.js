/* The other shell: one window, the canvas inside it.
 *
 * main.js gives every command an OS window. This one does not — it opens a
 * single window on the page tb already serves, which means the canvas stays
 * the canvas: panes are divs, the layout is yours rather than the window
 * manager's, and anything a pane wants to know about another pane is a lookup
 * in one JS heap instead of a message across a process boundary.
 *
 * It is deliberately tiny, and that is the argument it exists to make. There
 * is no preload and no bridge here, because there is nothing to bridge: the
 * window loads `ctx.url` and gets today's index.html, today's app.js, today's
 * render.js and today's token, exactly as the browser and pywebview shells do.
 * `api.js` keeps working because nothing about it changed.
 *
 * So this file is a like-for-like replacement for cli/canvas/shell.py, and the
 * only honest way to compare the two: same product, same frontend, different
 * host. What you are buying is a pinned Chromium instead of whatever WebKitGTK
 * the distro shipped, DevTools, and `backgroundThrottling`. What you are
 * paying is npm and ~300 MB. Run both; keep the one that earns it.
 */

const { app, BrowserWindow, shell: os } = require("electron");
const bridge = require("./bridge.js");

let ctx = null;
let win = null;

const FRAMELESS = process.env.TB_FRAME !== "1";

app.whenReady().then(async () => {
  app.setName("toolbox");
  bridge.reapOnSignal(() => ctx);

  try {
    ctx = await bridge.start({ tb: process.env.TB_BIN || "tb" });
  } catch (error) {
    console.error(`shell: ${error.message}`);
    app.exit(1);
    return;
  }

  win = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 640,
    minHeight: 400,
    frame: !FRAMELESS,
    backgroundColor: "#0d0f12",
    show: false,
    webPreferences: {
      // Nothing is injected into this page, so it needs no preload — and with
      // none, there is nothing for `contextIsolation` to isolate but the
      // page from Electron itself, which is exactly what is wanted.
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });

  /* The bar is already the title bar — app.js:172 says so, and calls
   * `window.pywebview.api.start_move` to make it one. That object does not
   * exist here, and the handler degrades to a no-op by its own design, so the
   * move is asked for in CSS instead. Injected rather than committed: the
   * frontend belongs to the canvas, not to whichever shell is hosting it, and
   * a `-webkit-app-region` in tb.css would be a line about Electron sitting in
   * a file that three other hosts also read.
   *
   * Whether this drag snaps and tiles the way Gtk.Window.begin_move_drag does
   * is the thing to verify. If it does not, that is the regression, and
   * TB_FRAME=1 is the way back. */
  win.webContents.on("dom-ready", () => {
    win.webContents.insertCSS(`
      .bar { -webkit-app-region: drag; }
      .bar button, .bar input, .bar .seg, .bar .barpal { -webkit-app-region: no-drag; }
    `);
  });

  win.once("ready-to-show", () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => {
    os.openExternal(url);
    return { action: "deny" };
  });

  // The surface's own close button posts /api/quit, which sets tb's `quitting`
  // latch and takes the server down. Nothing tells this process about that, so
  // it watches the child instead: tb going away is the session ending, whoever
  // asked for it.
  ctx.child.once("exit", () => app.exit(0));

  win.loadURL(ctx.url);
});

app.on("window-all-closed", () => app.quit());

app.on("before-quit", async (event) => {
  if (!ctx || ctx.child.exitCode !== null) return;
  event.preventDefault();
  await bridge.quit(ctx).catch(() => {});
  setTimeout(() => {
    ctx.child.kill("SIGTERM");
    app.exit(0);
  }, 1000);
});
