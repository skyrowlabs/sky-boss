/* Everything the shell knows how to say to sb.
 *
 * The mirror of cli/canvas/static/api.js, one process up. That file opens by
 * promising the transport sits behind a seam so that "swapping the browser for
 * a native webview later replaces this file and nothing else" — this is that
 * swap, taken at its word. Every function here has a counterpart there, with
 * the same name and the same arguments, so a renderer ported from the canvas
 * changes its import and nothing else.
 *
 * What moved is who holds the secret. The token and the port now live in the
 * main process; the renderer never sees either, and reaches sky.boss only through
 * preload.js. That is the whole security gain of the shell: with N windows the
 * old arrangement would have had to write the token into N pages.
 *
 * sky.boss is spawned exactly as `--no-browser` documents, so nothing under cli/
 * changes to run this. `shell.py` made the same promise about pywebview and
 * kept it; there is no reason this shell should be allowed to be greedier.
 */

const { spawn } = require("node:child_process");
const net = require("node:net");

const TOKEN_HEADER = "x-sb-token";

/* A port the kernel just told us was free. The same race `_free_port` in
 * cli/canvas/__init__.py runs, and lost for the same reasons — which is to say
 * never, on a machine that is not also handing ports out in a loop. */
function freePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.unref();
    probe.on("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

/* The token, read out of the page sky.boss serves.
 *
 * `/` is not an API route and takes no header — server.py:117 says so, and
 * rests the token's secrecy on the same-origin policy instead. That is what
 * lets this shell start against an unmodified sky.boss: it fetches the page the way
 * a window would, and keeps the token instead of rendering it.
 *
 * The handshake worth building later is sky.boss printing `{"url":…,"token":…}` on
 * stdout once the bind is up. Not because scraping is fragile — the page is
 * ours — but because it would let this stop being HTTP at all. Note what is
 * *not* on the table either way: `--token X` on the command line, or the token
 * in the child's environment. Both /proc/PID/cmdline and /proc/PID/environ are
 * readable by every process this user runs.
 */
async function handshake(url, deadlineMs = 10_000) {
  // The window must not race the bind, or it lands on a refused connection and
  // shows an error page for a server that came up 40ms later. wait_for_bind()
  // in cli/canvas/__init__.py waits the same 10s for the same reason.
  const until = Date.now() + deadlineMs;
  for (;;) {
    try {
      const response = await fetch(url);
      const html = await response.text();
      const found = html.match(/window\.SB_TOKEN = "([^"]+)"/);
      if (found) return found[1];
      throw new Error("served a page with no token in it");
    } catch (error) {
      if (Date.now() > until) throw new Error(`sb never came up: ${error.message}`);
      await new Promise((r) => setTimeout(r, 50));
    }
  }
}

/* Start sky.boss and wait until it can be talked to. Resolves to the context every
 * other function here takes. */
async function start({ sb = "sb", scale = null } = {}) {
  const port = await freePort();
  const url = `http://127.0.0.1:${port}/`;

  const argv = ["ui", "--no-browser", "--port", String(port)];
  if (scale) argv.push("--scale", String(scale));

  const child = spawn(sb, argv, { stdio: ["ignore", "pipe", "pipe"] });

  // sky.boss's own diagnostics, kept rather than dropped. A shell that swallows the
  // stderr of the process it depends on turns every server-side failure into
  // an unexplained blank window.
  child.stderr.on("data", (b) => process.stderr.write(`[sb] ${b}`));
  child.stdout.on("data", (b) => process.stdout.write(`[sb] ${b}`));

  const died = new Promise((_, reject) =>
    child.once("exit", (code) => reject(new Error(`sb exited ${code} before it bound`)))
  );

  const token = await Promise.race([handshake(url), died]);
  return { child, url, port, token };
}

async function post(ctx, path, body) {
  const response = await fetch(new URL(path, ctx.url), {
    method: "POST",
    headers: { "content-type": "application/json", [TOKEN_HEADER]: ctx.token },
    body: JSON.stringify(body),
  });
  // 409 is an answer, not a failure — api.js lets it through for the same reason.
  if (!response.ok && response.status !== 409) {
    throw new Error(`${path} → ${response.status}`);
  }
  return response.json();
}

async function catalog(ctx) {
  const response = await fetch(new URL("/api/catalog", ctx.url), {
    headers: { [TOKEN_HEADER]: ctx.token },
  });
  if (!response.ok) throw new Error(`catalog → ${response.status}`);
  return response.json();
}

const run = (ctx, argv, timeout) => post(ctx, "/api/run", { argv, timeout });
const watch = (ctx, session, window, argv, interval) =>
  post(ctx, "/api/watch", { session, window, argv, interval });
const unwatch = (ctx, session, window) =>
  post(ctx, "/api/watch", { session, window, stop: true });
const follow = (ctx, session, window, argv) =>
  post(ctx, "/api/follow", { session, window, argv });
const unfollow = (ctx, session, window) =>
  post(ctx, "/api/follow", { session, window, stop: true });
const quit = (ctx) => post(ctx, "/api/quit", {});

/* The session, as newline-delimited JSON.
 *
 * One stream for the whole application, held here rather than in any window —
 * that is the change the multi-window model forces, and the one place the old
 * lifetime rule breaks. See the note above `windows` in main.js.
 *
 * The frame-per-line reading is api.js's, unchanged: a chunk boundary lands
 * mid-frame often enough that parsing per chunk is a bug that only shows up on
 * a large result.
 */
function stream(ctx, onFrame, onDown) {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(new URL("/api/stream", ctx.url), {
        headers: { [TOKEN_HEADER]: ctx.token },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`stream → ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let cut;
        while ((cut = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, cut).trim();
          buffer = buffer.slice(cut + 1);
          if (line) onFrame(JSON.parse(line));
        }
      }
      onDown();
    } catch (error) {
      if (error.name !== "AbortError") onDown(error);
    }
  })();

  return () => controller.abort();
}

/* Reap sky.boss when this process dies by signal.
 *
 * Electron's `before-quit` is Electron's own lifecycle and a signal does not
 * enter it: the main process goes, the child is reparented to init, and sky.boss
 * keeps running with its port bound. Found the ordinary way — by stopping the
 * shell from the terminal that started it, which is how a shell under
 * development is stopped nearly every time.
 *
 * `stop()` in cli/canvas/__init__.py is careful that the session ends when its
 * window does; this is the same promise kept from the other side.
 */
function reapOnSignal(getCtx) {
  const reap = () => {
    const ctx = getCtx();
    if (ctx && ctx.child.exitCode === null) ctx.child.kill("SIGTERM");
  };
  for (const signal of ["SIGTERM", "SIGINT", "SIGHUP"]) {
    process.on(signal, () => {
      reap();
      process.exit(0);
    });
  }
  process.on("exit", reap);
}

module.exports = {
  start,
  catalog,
  run,
  watch,
  unwatch,
  follow,
  unfollow,
  quit,
  stream,
  reapOnSignal,
};
