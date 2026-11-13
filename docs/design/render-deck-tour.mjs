#!/usr/bin/env node
/**
 * Record the README's deck clip: a real three-tab deck running /deck-tour.
 *
 *     node docs/design/render-deck-tour.mjs [--keep]
 *
 * The agents are real `claude` sessions, so a take costs tokens and no two
 * takes match; re-run until one reads well. Everything else is sandboxed: its
 * own tmux socket, `$SB_HOME`, `$SB_STATE`, and three throwaway repos under a
 * fixed `/tmp/sb-tour`, because those paths are drawn in the picture.
 *
 * ttyd serves the deck to headless Chromium, which is photographed over CDP
 * (no new dependency, as in render-canvas.mjs). The one human act, the click
 * on a decision and the key that rules it, goes through the same xterm the
 * camera sees. Idle stretches play fast and pane changes play slow, then
 * ffmpeg writes `readme-deck-tour.webp`, starting only once the panes hide
 * every session outside the sandbox. `--keep` leaves the frames in /tmp.
 */

import { spawn, execFileSync } from "node:child_process";
import { createServer } from "node:net";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const OUT = join(HERE, "readme-deck-tour.webp");
const KEEP = process.argv.includes("--keep");

const WIDTH = 1600;
const HEIGHT = 900;
const SESSION = "tour";
const REPOS = "/tmp/sb-tour";
const AGENTS = {
  planner: "coordinates the other two tabs",
  api: "the service's backend",
  web: "the service's front end",
};
const MODEL = "sonnet";
const FRAME_MS = 400; // one photograph per this many real milliseconds
const PLAY_FPS = 5;
const HOLD_S = 4; // the last frame stays this long before the loop
const LIVELY_S = 3; // frames this close to a pane change play at full rate
const DULL_EVERY = 10; // otherwise keep one frame in this many
const DEADLINE_S = 600;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

/** A CDP session over the debugger websocket; see render-canvas.mjs. */
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

  async evaluate(expression) {
    const out = await this.send("Runtime.evaluate", { expression, returnByValue: true });
    if (out.exceptionDetails) throw new Error(out.exceptionDetails.exception?.description ?? "page threw");
    return out.result.value;
  }

  async click(x, y) {
    for (const type of ["mousePressed", "mouseReleased"]) {
      await this.send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 });
      await sleep(80);
    }
  }
}

function sandbox() {
  rmSync(REPOS, { recursive: true, force: true });
  const git = (cwd, ...args) =>
    execFileSync("git", ["-c", "user.name=demo", "-c", "user.email=demo@example.com", ...args], { cwd });
  for (const name of Object.keys(AGENTS)) {
    const dir = join(REPOS, name);
    mkdirSync(join(dir, "src"), { recursive: true });
    git(dir, "init", "-q", "-b", "main");
    writeFileSync(join(dir, "README.md"), `# ${name}\n`);
    writeFileSync(join(dir, "src", "main.py"), "print('hello')\n");
    git(dir, "add", "-A");
    git(dir, "commit", "-q", "-m", "chore: start the repo");
    writeFileSync(join(dir, "src", "util.py"), "def add(a, b):\n    return a + b\n");
    git(dir, "add", "-A");
    git(dir, "commit", "-q", "-m", `feat(${name}): add the first helper`);
  }
  const home = mkdtempSync("/tmp/sbt-home-");
  const state = mkdtempSync("/tmp/sbt-state-");
  // Short: a Unix socket path is limited to about a hundred bytes.
  const sockets = mkdtempSync("/tmp/sbt-");
  const args = ["--model", MODEL, "--allowedTools", "Bash(sb:*)", "Bash(git:*)", "Bash(wc:*)"];
  const toml = [`session = "${SESSION}"`, "themes = true", ""];
  for (const [name, role] of Object.entries(AGENTS)) {
    toml.push(`[agent.${name}]`, `cwd = "${join(REPOS, name)}"`, `role = "${role}"`, `args = ${JSON.stringify(args)}`, "");
  }
  const [primary, ...tabs] = Object.keys(AGENTS);
  toml.push("[profile.tour]", `primary = "${primary}"`, `tabs = ${JSON.stringify(tabs)}`, `session = "${SESSION}"`, "");
  writeFileSync(join(home, "deck.toml"), toml.join("\n"));
  return { home, state, sockets };
}

async function main() {
  const box = sandbox();
  const frames = mkdtempSync("/tmp/sbt-frames-");
  const env = { ...process.env, TMUX_TMPDIR: box.sockets, SB_HOME: box.home, SB_STATE: box.state };
  delete env.TMUX;
  delete env.TMUX_PANE;
  delete env.SB_DECK;
  const tmux = (...args) => execFileSync("tmux", args, { env, encoding: "utf8" });
  const sb = (...args) => execFileSync(join(ROOT, "sb"), args, { env, encoding: "utf8" });
  let ttyd;
  let browser;

  try {
    const ttydPort = await freePort();
    const cdpPort = await freePort();
    ttyd = spawn(
      "ttyd",
      ["-p", String(ttydPort), "-W", "-i", "127.0.0.1", "-t", "fontSize=13", "-t", "disableLeaveAlert=true",
        "-t", "titleFixed=sky.boss deck", join(ROOT, "sb"), "deck", "--profile", "tour"],
      { env, stdio: ["ignore", "pipe", "pipe"] },
    );
    browser = spawn(
      "chromium",
      ["--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        `--remote-debugging-port=${cdpPort}`, `--window-size=${WIDTH},${HEIGHT}`, "about:blank"],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    const cdp = await Devtools.open(cdpPort);
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await sleep(800);
    await cdp.send("Page.navigate", { url: `http://127.0.0.1:${ttydPort}/` });
    for (let i = 0; i < 80 && !(await cdp.evaluate("typeof term === 'object' && !!document.querySelector('.xterm-screen')").catch(() => false)); i++) {
      await sleep(250);
    }

    // The camera: one frame per FRAME_MS, each tagged with a hash of the right
    // column, so the edit can tell a pane changing from a spinner turning.
    const shots = [];
    let rolling = true;
    const panes = () => {
      try {
        const rows = tmux("list-panes", "-t", `=${SESSION}`, "-F", "#{pane_id} #{pane_start_command}");
        return rows.split("\n").filter((r) => / deck (messages|todo|decide)/.test(r)).map((r) => r.split(" ")[0]);
      } catch {
        return [];
      }
    };
    const camera = (async () => {
      const t0 = Date.now();
      while (rolling) {
        const at = Date.now();
        const shot = await cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 85 }).catch(() => null);
        if (!shot) {
          await sleep(FRAME_MS);
          continue;
        }
        const file = join(frames, `f${String(shots.length).padStart(5, "0")}.jpg`);
        writeFileSync(file, Buffer.from(shot.data, "base64"));
        let text = "";
        for (const id of panes()) {
          try { text += tmux("capture-pane", "-p", "-t", id); } catch { /* pane gone */ }
        }
        shots.push({ file, t: (at - t0) / 1000, hash: createHash("sha1").update(text).digest("hex") });
        await sleep(Math.max(0, FRAME_MS - (Date.now() - at)));
      }
    })();

    const deadline = Date.now() + DEADLINE_S * 1000;
    const until = async (what, test, every = 1500) => {
      while (Date.now() < deadline) {
        try { if (await test()) return; } catch { /* not yet */ }
        await sleep(every);
      }
      throw new Error(`timed out waiting for ${what}`);
    };

    // Every tab's claude at its prompt: its pane shows the input box.
    const tab = (name) => `=${SESSION}-agents:${name}`;
    await until("three tabs", () => Object.keys(AGENTS).every((n) => tmux("capture-pane", "-p", "-t", tab(n)).includes("❯")));
    // M-h's switch: rows from sessions outside this deck (the operator's own) stay out of frame.
    // The clip starts once the list says so, so no frame before it carries another session's path.
    tmux("set-option", "-t", `=${SESSION}:`, "@sb-hide-outside", "1");
    await until("outside rows hidden", () => locate(tmux, "outside hidden"));
    await sleep(1500);
    const first = shots.length;

    tmux("send-keys", "-t", tab("planner"), "-l", "/sky-boss:deck-tour");
    await sleep(1200);
    tmux("send-keys", "-t", tab("planner"), "Enter");

    // The peer's decision, then a click on it, the way an operator rules. Found by
    // owner and state rather than wording: an agent words its row its own way.
    const rows = () => JSON.parse(sb("--json", "deck", "decide", "list", "--all")).data;
    let asked = null;
    await until("the decision", () => {
      asked = rows().find((r) => r.kind === "item" && r.agent !== "planner" && r.ask === "choice" && !r.done);
      return asked;
    });
    await sleep(2500);
    const where = locate(tmux, asked.text.slice(0, 24));
    if (!where) throw new Error(`the decision is not drawn in any pane: ${asked.text}`);
    const cell = await cdp.evaluate(`(() => {
      const s = document.querySelector('.xterm-screen').getBoundingClientRect();
      return { x: s.left, y: s.top, w: s.width / term.cols, h: s.height / term.rows };
    })()`);
    await cdp.click(cell.x + (where.col + 0.5) * cell.w, cell.y + (where.row + 0.5) * cell.h);
    await sleep(2500);
    await cdp.send("Input.insertText", { text: "2" });

    await until("the tour's close", () => rows().some((r) => r.agent === "planner" && /tour/i.test(r.text)), 2000);
    await sleep(6000);
    rolling = false;
    await camera;
    encode(shots.slice(first), frames);
  } finally {
    browser?.kill();
    ttyd?.kill();
    try { execFileSync("tmux", ["kill-server"], { env, stdio: "ignore" }); } catch { /* none */ }
    for (const dir of [box.home, box.state, box.sockets]) rmSync(dir, { recursive: true, force: true });
    if (!KEEP) rmSync(frames, { recursive: true, force: true });
    else console.log(`frames kept in ${frames}`);
  }
}

/** The outer cell where `text` starts, in the first of the deck's panes that draws it. */
function locate(tmux, text) {
  const rows = tmux("list-panes", "-t", `=${SESSION}`, "-F", "#{pane_id} #{pane_left} #{pane_top}");
  for (const row of rows.trim().split("\n")) {
    const [id, left, top] = row.split(" ");
    const lines = tmux("capture-pane", "-p", "-t", id).split("\n");
    const i = lines.findIndex((line) => line.includes(text));
    if (i >= 0) return { col: Number(left) + lines[i].indexOf(text), row: Number(top) + i };
  }
  return null;
}

/** Keep every frame near a pane change and one in DULL_EVERY elsewhere, then encode. */
function encode(shots, frames) {
  const changes = shots.filter((s, i) => i > 0 && s.hash !== shots[i - 1].hash).map((s) => s.t);
  const lively = (t) => changes.some((c) => Math.abs(c - t) <= LIVELY_S);
  const kept = shots.filter((s, i) => lively(s.t) || i % DULL_EVERY === 0);
  const list = join(frames, "list.txt");
  const step = 1 / PLAY_FPS;
  const durations = kept.map((s, i) => (i === kept.length - 1 ? HOLD_S : step));
  writeFileSync(list, kept.map((s, i) => `file '${s.file}'\nduration ${durations[i]}`).join("\n") + `\nfile '${kept.at(-1).file}'\n`);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list,
    "-vf", `fps=${PLAY_FPS},scale=1280:-1:flags=lanczos`, "-c:v", "libwebp_anim", "-lossless", "0",
    "-q:v", "70", "-loop", "0", OUT]);
  const seconds = (kept.length / PLAY_FPS + HOLD_S).toFixed(1);
  const mb = (statSync(OUT).size / 1e6).toFixed(1);
  console.log(`${shots.length} frames shot, ${kept.length} kept: ${seconds}s, ${mb} MB → ${relative(ROOT, OUT)}`);
}

await main();
