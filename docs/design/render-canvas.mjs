#!/usr/bin/env node
/**
 * Screenshot the canvas for the README, from a real running `sb ui`.
 *
 *     node docs/design/render-canvas.mjs
 *
 * **The operator's own tools must never reach this image.** The first draft of
 * this script did not redirect `$SB_HOME`, and the capture came back with the
 * real `~/.sky-boss/tools.toml` drawn down the left — a private checkout's job
 * names, in a picture headed for a public README. This is the same obligation
 * `tests/conftest.py` carries and for the same reason it states: a tool is an
 * argv sky.boss will *run*, so anything reading the real home is reading the
 * operator. It seeds an isolated home from `tools.example.toml`, which is the
 * one tools file in the repo that a test already keeps generic.
 *
 * **No new dependency.** Node 22 ships a global `WebSocket`, so the Chrome
 * DevTools Protocol is reachable with nothing installed — the same argument
 * that made `node --test` free in `package.json`. A screenshot needs CDP rather
 * than `chromium --screenshot` because an empty canvas is a picture of nothing:
 * the windows have to be opened by typing into the palette, which is also the
 * honest way to photograph a surface whose whole point is that you type at it.
 *
 * **The sample data lives in `sample/`, and is copied to a neutral temporary
 * directory before use.** One home for it, so this and `render-mark.py`
 * photograph the same thing instead of drifting; copied rather than read in
 * place because the path is *drawn in the window title*, and the path to a
 * checkout names whoever's home it sits in — `tests/test_publication.py`'s rule
 * arriving somewhere no test can look, which is inside a PNG.
 */

import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { mkdtemp, copyFile, rm, mkdir } from "node:fs/promises";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");

// Wide enough that a tiled pair of windows is not two slivers, and short enough
// that the README does not scroll past it. Doubled by the device scale factor.
const WIDTH = 1280;
const HEIGHT = 760;
const SCALE = 2;

// What gets typed into the palette, in order. Each opens one window.
//
// Both read a *file*, so neither needs a tool that might not be installed on
// whoever's machine re-runs this — and between them they show the two things
// the surface does that a terminal cannot: a stream held open and tinted, and a
// record file shaped into a table.
const TYPED = [
  "follow {DATA}/agent.log",
  "data --from jsonl {DATA}/runs.jsonl",
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** A port nothing is listening on. Asked of the kernel rather than guessed. */
function freePort() {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

/** Wait for a line matching `re` on a child's stdout, or throw with what it said. */
function awaitLine(child, re, what, ms = 20000) {
  return new Promise((resolve, reject) => {
    let seen = "";
    const timer = setTimeout(
      () => reject(new Error(`${what} never printed ${re}. It said:\n${seen}`)),
      ms,
    );
    const read = (buf) => {
      seen += buf.toString();
      const hit = seen.match(re);
      if (hit) {
        clearTimeout(timer);
        resolve(hit);
      }
    };
    child.stdout.on("data", read);
    child.stderr.on("data", read);
  });
}

/** A CDP session over the debugger websocket. */
class Devtools {
  constructor(ws) {
    this.ws = ws;
    this.next = 1;
    this.pending = new Map();
    ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      const waiting = this.pending.get(msg.id);
      if (!waiting) return;
      this.pending.delete(msg.id);
      msg.error ? waiting.reject(new Error(JSON.stringify(msg.error))) : waiting.resolve(msg.result);
    });
  }

  static async open(port) {
    // The browser needs a moment before it answers /json; poll rather than
    // sleep a guessed amount, so a slow machine is slow and not broken.
    for (let attempt = 0; attempt < 60; attempt++) {
      try {
        const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then((r) => r.json());
        const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
        if (page) {
          const ws = new WebSocket(page.webSocketDebuggerUrl);
          await new Promise((ok, no) => {
            ws.addEventListener("open", ok, { once: true });
            ws.addEventListener("error", no, { once: true });
          });
          return new Devtools(ws);
        }
      } catch {
        /* not up yet */
      }
      await sleep(250);
    }
    throw new Error("chromium never offered a page target on the debugging port");
  }

  send(method, params = {}) {
    const id = this.next++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }

  /** Evaluate in the page and return the value. Throws what the page threw. */
  async evaluate(expression) {
    const out = await this.send("Runtime.evaluate", { expression, returnByValue: true });
    if (out.exceptionDetails) {
      throw new Error(out.exceptionDetails.exception?.description ?? "page threw");
    }
    return out.result.value;
  }

  async type(text) {
    await this.send("Input.insertText", { text });
  }

  async enter() {
    for (const type of ["keyDown", "keyUp"]) {
      await this.send("Input.dispatchKeyEvent", {
        type,
        key: "Enter",
        code: "Enter",
        windowsVirtualKeyCode: 13,
        nativeVirtualKeyCode: 13,
      });
    }
  }
}

async function main() {
  const out = join(HERE, "readme-canvas.png");
  const home = await mkdtemp(join(tmpdir(), "sb-shot-home-"));
  const state = await mkdtemp(join(tmpdir(), "sb-shot-state-"));
  // Fixed rather than random: this path is *drawn in the window title*, and
  // an mkdtemp suffix there is six characters of noise in the first picture
  // anyone sees. Removed first, so a previous run cannot seed this one.
  const data = join(tmpdir(), "sb-demo");
  let ui;
  let browser;

  try {
    // The isolated home. `tools.example.toml` is the repo's own tools file and
    // a test keeps it generic, so the rail draws something real without
    // drawing anybody's real thing.
    await rm(data, { recursive: true, force: true });
    await mkdir(data, { recursive: true });
    await copyFile(join(ROOT, "tools.example.toml"), join(home, "tools.toml"));
    for (const name of ["agent.log", "runs.jsonl"]) {
      await copyFile(join(HERE, "sample", name), join(data, name));
    }

    const uiPort = await freePort();
    const cdpPort = await freePort();

    ui = spawn(join(ROOT, "sb"), ["ui", "--no-browser", "--port", String(uiPort)], {
      env: { ...process.env, SB_HOME: home, SB_STATE: state, NO_COLOR: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const [url] = await awaitLine(ui, /http:\/\/127\.0\.0\.1:\d+\//, "sb ui");
    console.log(`serving ${url}`);

    browser = spawn(
      "chromium",
      [
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        `--remote-debugging-port=${cdpPort}`,
        `--window-size=${WIDTH},${HEIGHT}`,
        `--force-device-scale-factor=${SCALE}`,
        "about:blank",
      ],
      { stdio: ["ignore", "pipe", "pipe"] },
    );

    const cdp = await Devtools.open(cdpPort);
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("Page.navigate", { url });
    await sleep(2500);

    // Fail loudly if the surface did not come up. A blank page screenshots
    // perfectly well, and a green run that wrote a picture of nothing is this
    // repo's own favourite failure.
    const palette = await cdp.evaluate("!!document.querySelector('.barpal input')");
    if (!palette) throw new Error("no palette on the page — the canvas did not render");

    for (const template of TYPED) {
      const line = template.replaceAll("{DATA}", data);
      await cdp.evaluate("document.querySelector('.barpal input').focus()");
      await cdp.type(line);
      await sleep(400);
      await cdp.enter();
      await sleep(1800);
    }

    // Close the palette before the shutter. Typing leaves it focused with its
    // suggestion list open, and in the first render that list covered most of
    // the second window — a picture of the palette hiding what it just opened.
    await cdp.evaluate("document.querySelector('.barpal input').blur()");

    // Let the follow window accrue its lines and the table settle.
    await sleep(2500);

    const windows = await cdp.evaluate("document.querySelectorAll('.win').length");
    if (!windows) throw new Error("no windows opened — the palette did not launch anything");
    console.log(`${windows} windows open`);

    const shot = await cdp.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(out, Buffer.from(shot.data, "base64"));
    console.log(`wrote ${relative(ROOT, out)} ${WIDTH * SCALE}x${HEIGHT * SCALE}`);
  } finally {
    browser?.kill();
    ui?.kill();
    await rm(home, { recursive: true, force: true });
    await rm(state, { recursive: true, force: true });
    await rm(data, { recursive: true, force: true });
  }
}

await main();
