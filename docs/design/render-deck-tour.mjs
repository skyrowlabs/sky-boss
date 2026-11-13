#!/usr/bin/env node
/**
 * Record the README's deck clip: a real six-tab deck running /deck-tour.
 *
 *     node docs/design/render-deck-tour.mjs [--keep]
 *
 * The agents are real `claude` sessions, so a take costs tokens and no two
 * takes match; re-run until one reads well. Everything else is sandboxed: its
 * own tmux socket, `$SB_HOME`, `$SB_STATE`, and a throwaway repo per agent under
 * a fixed `/tmp/sb-tour`, because those paths are drawn in the picture.
 *
 * Six agents, each in a product's hue; the terminal takes the operator's Konsole
 * scheme (`--colorscheme=PATH`, else SkyrowLabs in Konsole's data directory).
 * ttyd serves the deck to headless Chromium, which is photographed over CDP
 * (no new dependency, as in render-canvas.mjs). The human acts, a click on
 * each decision and the key that rules it, go through the same xterm the
 * camera sees. Idle stretches play fast and pane changes play slow, then
 * ffmpeg writes `readme-deck-tour.webp`, starting only once the panes hide
 * every session outside the sandbox. `--keep` leaves the frames in /tmp.
 */

import { spawn, execFileSync } from "node:child_process";
import { createServer } from "node:net";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, statSync, readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { createHash } from "node:crypto";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const OUT = join(HERE, "readme-deck-tour.webp");
const KEEP = process.argv.includes("--keep");

const WIDTH = 1800;
const HEIGHT = 1000;
const OUT_WIDTH = 1440;
const SESSION = "tour";
const REPOS = "/tmp/sb-tour";
// Names no live tab carries, since SendMessage reaches a session by name; each
// wears a product's hue so the tab row reads like the real deck's.
const AGENTS = {
  coordinator: { role: "hands out work and collects the answers", colour: "brand", commits: 6 },
  audio: { role: "chord detection service", colour: "js", commits: 4 },
  gpu: { role: "rented GPU fleet", colour: "bb", commits: 7 },
  streams: { role: "personal data streams", colour: "sf", commits: 3 },
  brain: { role: "self-hosted model memory", colour: "mh", commits: 5 },
  scaffold: { role: "project-shell generator", colour: "sk", commits: 2 },
};
const PRIMARY = Object.keys(AGENTS)[0];
// The terminal's colours: a Konsole scheme when one is given or found, else xterm's own.
const SCHEME =
  process.argv.find((a) => a.startsWith("--colorscheme="))?.slice(14) ??
  join(process.env.XDG_DATA_HOME ?? join(homedir(), ".local", "share"), "konsole", "SkyrowLabs.colorscheme");
const FONT = "MesloLGS Nerd Font Mono";
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
  const subjects = ["chore: start the repo", "feat: add the first helper", "test: cover the helper",
    "fix: handle an empty input", "docs: say what it does", "refactor: split the module", "feat: read the config"];
  for (const [name, agent] of Object.entries(AGENTS)) {
    const dir = join(REPOS, name);
    mkdirSync(join(dir, "src"), { recursive: true });
    git(dir, "init", "-q", "-b", "main");
    writeFileSync(join(dir, "README.md"), `# ${name}\n`);
    for (let i = 0; i < agent.commits; i++) {
      writeFileSync(join(dir, "src", `part${i}.py`), `STEP = ${i}\n`);
      git(dir, "add", "-A");
      git(dir, "commit", "-q", "-m", subjects[i].replace(": ", `(${name}): `));
    }
  }
  const home = mkdtempSync("/tmp/sbt-home-");
  const state = mkdtempSync("/tmp/sbt-state-");
  // Short: a Unix socket path is limited to about a hundred bytes.
  const sockets = mkdtempSync("/tmp/sbt-");
  const args = ["--model", MODEL, "--allowedTools", "Bash(sb:*)", "Bash(git:*)", "Bash(wc:*)"];
  const toml = [`session = "${SESSION}"`, "themes = true", ""];
  for (const [name, { role, colour }] of Object.entries(AGENTS)) {
    toml.push(`[agent.${name}]`, `cwd = "${join(REPOS, name)}"`, `role = "${role}"`, `colour = "${colour}"`,
      `args = ${JSON.stringify(args)}`, "");
  }
  const [primary, ...tabs] = Object.keys(AGENTS);
  toml.push("[profile.tour]", `primary = "${primary}"`, `tabs = ${JSON.stringify(tabs)}`, `session = "${SESSION}"`,
    // Two panes a column, so six agents' todos and decisions have the height to be drawn.
    'columns = [["queue", "messages"], ["todos", "decisions"]]', "");
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
        "-t", `fontFamily=${FONT}`, ...xtermTheme(),
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
    await until("every tab", () => Object.keys(AGENTS).every((n) => tmux("capture-pane", "-p", "-t", tab(n)).includes("❯")));
    // M-h's switch: rows from sessions outside this deck (the operator's own) stay out of frame.
    // The clip starts once the list says so, so no frame before it carries another session's path.
    sb("deck", "layout", "grid");
    tmux("set-option", "-t", `=${SESSION}:`, "@sb-hide-outside", "1");
    await until("outside rows hidden", () => locate(tmux, "outside hidden"));
    await sleep(1500);
    const first = shots.length;

    tmux("send-keys", "-t", tab(PRIMARY), "-l", "/sky-boss:deck-tour");
    await sleep(1200);
    tmux("send-keys", "-t", tab(PRIMARY), "Enter");

    // Each peer's decision, clicked as it is drawn, the way an operator rules. Found by
    // owner and state rather than wording: an agent words its row its own way.
    const rows = () => JSON.parse(sb("--json", "deck", "decide", "list", "--all")).data;
    const cell = await cdp.evaluate(`(() => {
      const s = document.querySelector('.xterm-screen').getBoundingClientRect();
      return { x: s.left, y: s.top, w: s.width / term.cols, h: s.height / term.rows };
    })()`);
    const ruled = new Set();
    await until("the tour's close", async () => {
      const all = rows();
      if (all.some((r) => r.agent === PRIMARY && /tour/i.test(r.text))) return true;
      const asked = all.find((r) => r.kind === "item" && r.agent !== PRIMARY && r.ask === "choice" && !r.done
        && !ruled.has(`${r.agent}#${r.n}`));
      if (!asked) return false;
      await sleep(2500);
      const where = locate(tmux, asked.text.slice(0, 24));
      if (!where) return false;
      await cdp.click(cell.x + (where.col + 0.5) * cell.w, cell.y + (where.row + 0.5) * cell.h);
      await sleep(2500);
      await cdp.send("Input.insertText", { text: "2" });
      ruled.add(`${asked.agent}#${asked.n}`);
      return false;
    }, 2000);
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

/** ttyd's `-t theme=…`, built from a Konsole colour scheme; nothing when there is none. */
function xtermTheme() {
  if (!existsSync(SCHEME)) {
    console.log(`no colour scheme at ${SCHEME}: xterm's own colours`);
    return [];
  }
  const colours = {};
  let section = "";
  for (const line of readFileSync(SCHEME, "utf8").split("\n")) {
    const head = line.match(/^\[(.+)\]$/);
    if (head) section = head[1];
    const rgb = line.match(/^Color=(\d+),(\d+),(\d+)/);
    if (rgb) colours[section] = "#" + rgb.slice(1).map((v) => Number(v).toString(16).padStart(2, "0")).join("");
  }
  const names = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"];
  const theme = { background: colours.Background, foreground: colours.Foreground, cursor: colours.Color4 };
  names.forEach((name, i) => {
    theme[name] = colours[`Color${i}`];
    theme[`bright${name[0].toUpperCase()}${name.slice(1)}`] = colours[`Color${i}Intense`];
  });
  return ["-t", `theme=${JSON.stringify(theme)}`];
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
    "-vf", `fps=${PLAY_FPS},scale=${OUT_WIDTH}:-1:flags=lanczos`, "-c:v", "libwebp_anim", "-lossless", "0",
    "-q:v", "70", "-loop", "0", OUT]);
  const seconds = (kept.length / PLAY_FPS + HOLD_S).toFixed(1);
  const mb = (statSync(OUT).size / 1e6).toFixed(1);
  console.log(`${shots.length} frames shot, ${kept.length} kept: ${seconds}s, ${mb} MB → ${relative(ROOT, OUT)}`);
}

await main();
