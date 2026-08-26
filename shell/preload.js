/* What a window is allowed to say, and the only thing it can reach.
 *
 * This is api.js's shape, deliberately: `catalog`, `run`, `watch`, `unwatch`,
 * `follow`, `unfollow`, `quit`, and a stream you subscribe to. A renderer
 * ported from cli/canvas/static/ swaps `import * as api from "./api.js"` for
 * `const api = window.tb` and should otherwise not notice.
 *
 * Two arguments are gone from every signature, and their absence is the point.
 * There is no `session`, and there is no `window` — the main process fills
 * both in from the sender, so a window can only ever speak about itself, and
 * neither the token nor the port is present in this context to leak.
 */

const { contextBridge, ipcRenderer } = require("electron");

const frameHandlers = new Set();
const downHandlers = new Set();

let identity = { windowId: null, session: null, argv: null };
const ready = new Promise((resolve) => {
  ipcRenderer.on("tb:ready", (_e, sent) => {
    identity = { ...identity, ...sent };
    resolve(identity);
  });
});

ipcRenderer.on("tb:frame", (_e, frame) => {
  for (const handler of frameHandlers) handler(frame);
});
ipcRenderer.on("tb:down", (_e, info) => {
  for (const handler of downHandlers) handler(info.error);
});

contextBridge.exposeInMainWorld("tb", {
  /* Who this window is. Resolves once the session has said hello — a window
   * opened before tb answers is a real ordering, not a hypothetical, because
   * the first window is created in the same tick as the stream. */
  ready: () => ready,
  identity: () => identity,

  catalog: () => ipcRenderer.invoke("tb:catalog"),
  run: (argv, timeout) => ipcRenderer.invoke("tb:run", argv, timeout),
  watch: (argv, interval) => ipcRenderer.invoke("tb:watch", argv, interval),
  unwatch: () => ipcRenderer.invoke("tb:unwatch"),
  follow: (argv) => ipcRenderer.invoke("tb:follow", argv),
  unfollow: () => ipcRenderer.invoke("tb:unfollow"),

  /* A command opens a window. In the canvas this made a div; here it asks the
   * desktop for a window, and the window manager decides where it goes. */
  open: (argv) => ipcRenderer.invoke("tb:open", argv),

  close: () => ipcRenderer.invoke("tb:close"),
  quit: () => ipcRenderer.invoke("tb:quit"),

  /* Frames for this window, plus the ones the session addresses to everybody.
   * Returns its own unsubscribe, as api.js's stream does. */
  onFrame: (handler) => {
    frameHandlers.add(handler);
    return () => frameHandlers.delete(handler);
  },
  onDown: (handler) => {
    downHandlers.add(handler);
    return () => downHandlers.delete(handler);
  },
});
