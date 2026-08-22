/* The canvas: a command palette over a window canvas.
 *
 * Three rules this file exists to keep, all inherited from the surface it
 * replaces rather than invented here:
 *
 * 1. **Nothing keeps a command table.** The palette comes from /api/catalog,
 *    which reads the live Click tree. A palette offering a command that does
 *    not exist is worse than no palette, because it has already told you it
 *    does.
 * 2. **Only a read may be given a cadence.** An entry with `acts` is `tb run`,
 *    and re-running a write on a timer is a scheduler nobody asked for. The
 *    pin control is simply not offered on one.
 * 3. **No single result may render unbounded.** See render.js. The terminal
 *    surface froze for exactly this and the medium change does not repeal it.
 *
 * The refresh clock is not here. It is in Python, keyed to the stream, because
 * "keeps running while minimized" is not something a browser timer can promise
 * — a hidden page has its timers clamped. See cli/canvas/watch.py.
 */

import { html, render, useEffect, useRef, useState } from "./vendor/htm-preact.js";
import * as api from "./api.js";
import { Body, summarise } from "./render.js";

const TILE = "tile";
const FLOAT = "float";

let nextId = 0;
const newId = () => `w${++nextId}`;

function intervalLabel(seconds) {
  if (!seconds) return "⟳ manual";
  return seconds >= 60 ? `⟳ ${seconds / 60}m` : `⟳ ${seconds}s`;
}

/* Which commands a typed line is offering.
 *
 * The first version filtered on the whole line, which works right up until you
 * type an argument: `run -- df -h /` matches no command name, the suggestion
 * list empties, and Enter silently does nothing. Every command worth opening a
 * window on takes arguments, so that was the whole feature.
 *
 * A line names a command once its name is complete and a space follows. From
 * then on the rest is argv and must not narrow anything — the palette is
 * choosing a command, not searching the argv.
 *
 * Longest name first, so `auto log ...` resolves to `auto log` rather than to
 * `auto` when both exist.
 */
/* A saved command's own name — the last word of its catalog path. Derived,
 * never stored: `tools jam-pr-list` is the address since [[toolbox]] round 2,
 * `jam-pr-list` is the name the operator gave it, and the sidebar and the
 * palette show the name. Typing either form finds it. */
export function shortOf(entry) {
  return entry.name.split(" ").pop();
}

function namesEntry(q, c) {
  if (q === c.name || q.startsWith(c.name + " ")) return true;
  return Boolean(c.saved) && (q === shortOf(c) || q.startsWith(shortOf(c) + " "));
}

export function suggest(commands, query) {
  const q = query.trim().toLowerCase();
  if (!q) return commands;

  const named = commands
    .filter((c) => namesEntry(q, c))
    .sort((a, b) => b.name.length - a.name.length);
  if (named.length) return named;

  /* A name match always outranks a description match, and the two are never
   * interleaved. Typing `w` used to select `run`, because its summary contains
   * "what it printed" — and the first suggestion is what Enter fires, so a
   * prefix of one command's name would silently run a different one.
   */
  const head = q.split(/\s+/)[0];
  const prefixed = (c) => c.name.startsWith(q) || (c.saved && shortOf(c).startsWith(q));
  const byName = commands.filter(prefixed);
  const byText = commands.filter(
    (c) => !prefixed(c) && (c.summary || "").toLowerCase().includes(head)
  );
  return [...byName, ...byText];
}

/* Anything typed that is not a tb command is offered as one anyway, run
 * through `tb read` so it can be pinned and refreshed.
 *
 * Appended rather than shown only when nothing else matched: `list` matches
 * `tools` by description, and a raw entry that hid behind a description match
 * would be a palette that sometimes accepts a command and sometimes silently
 * does not. Suppressed only when the first word is exactly a tb command, where
 * the operator is plainly reaching for that command.
 *
 * The expansion goes in `summary`, so what will actually run is visible before
 * Enter rather than discovered afterwards.
 */
export function rawEntry(query, home) {
  const words = query.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  return {
    name: words.join(" "),
    raw: true,
    rawWords: words,
    cwd: home,
    argv: ["read", "--cwd", home, "--", ...words],
    summary: `tb read -- ${words.join(" ")}`,
    options: [],
    acts: false,
    saved: false,
    refresh: 0,
  };
}

export function withRaw(commands, query, home) {
  const shown = suggest(commands, query);
  const words = query.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return shown;
  if (commands.some((c) => c.name === words[0] || (c.saved && shortOf(c) === words[0])))
    return shown;
  const raw = rawEntry(query, home);
  return raw ? [...shown, raw] : shown;
}

/* argv for a window: its command, plus whichever chips are on. */
function argvOf(win) {
  /* A raw window owns an editable working directory, so its argv is rebuilt
   * rather than stored — otherwise changing the directory would leave the
   * watcher re-running the old one. */
  if (win.raw) return ["read", "--cwd", win.cwd, "--", ...win.rawWords];
  const flags = [];
  for (const chip of win.chips) if (chip.on) flags.push(chip.flag);
  return [...win.argv, ...flags];
}

/* Live reload, driven by the server rather than by a timer here.
 *
 * A stylesheet edit is swapped in place, which is the difference between live
 * reload and merely refreshing: every window keeps its position, its pin, its
 * chips and its last result while you adjust the CSS. Reloading the page for a
 * colour change would throw all of that away, and the canvas has no persistence
 * — the windows exist only in this tab.
 *
 * Anything else is a full reload, because the module graph is already evaluated
 * and there is no honest way to re-run it in place. That *does* lose every
 * window, and it should: half-old, half-new JS holding live state is exactly
 * the kind of wrongness that looks right.
 */
export function planReload(files) {
  const onlyStyles = files.length > 0 && files.every((f) => f.endsWith(".css"));
  return onlyStyles ? "styles" : "full";
}

export function applyReload(files) {
  /* The decision is split from the act so it can be checked without stubbing
   * navigation — `location.reload` cannot be redefined in a modern browser, and
   * the attempt throws, which is how the first version of that check failed. */
  if (planReload(files) === "full") {
    location.reload();
    return "full";
  }
  for (const link of document.querySelectorAll('link[rel="stylesheet"]')) {
    const url = new URL(link.href, location.href);
    // A changing query is what defeats the cache; the browser has no other
    // reason to believe a file it fetched a second ago is different.
    url.searchParams.set("v", String(Date.now()));
    link.setAttribute("href", url.pathname + url.search);
  }
  return "styles";
}

/* The bar behaves as the window's title bar.
 *
 * Only under the native shell, and only on the bar's own background — a
 * mousedown on a button or the mode switch must press it, not drag the window.
 * In a browser there is simply no API for this, so the handler is a no-op and
 * the frame the browser drew is what you move by.
 */
function barDrag(event) {
  if (event.button !== 0) return;
  if (event.target.closest("button, input, .seg")) return;
  const api = window.pywebview && window.pywebview.api;
  if (api && api.start_move) api.start_move();
}

function useNow() {
  /* Drives the "12s ago" labels only. Distinct from the refresh clock in every
   * way that matters: this one may be throttled to a crawl in a hidden page
   * without anything being wrong, because a label nobody can see is not late. */
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  return Date.now();
}

/* The toolbox: the operator's saved commands, down the left.
 *
 * It is not a second list of commands. These come from the same /api/catalog
 * every other surface reads, filtered on `saved` — a property the *command*
 * carries, so a tool that stops existing stops appearing here with no code
 * involved. See [[toolbox]].
 */
function Toolbox({ commands, open }) {
  const saved = commands.filter((c) => c.saved);
  return html`
    <div class="toolbox">
      <div class="toolbox-head">TOOLBOX</div>
      <div class="toolbox-list">
        ${saved.length === 0 &&
        html`<div class="toolbox-empty">
          nothing saved yet — declare a tool in tools.toml
        </div>`}
        ${saved.map(
          (c) => html`
            <button
              key=${c.name}
              class="tool"
              title=${c.summary || c.name}
              onClick=${() => open(c, shortOf(c), { interval: c.refresh })}
            >
              <span class="tool-name">${shortOf(c)}</span>
              ${c.refresh > 0 && html`<span class="tool-refresh">${c.refresh}s</span>`}
              ${c.acts && html`<span class="tool-acts" title="acts — never refreshed">!</span>`}
            </button>
          `
        )}
      </div>
      <!-- An expression, not markup: htm does not decode HTML entities, so a
           literal &lt; here renders as the four characters "&lt;" on screen.
           Angle brackets inside a template have to arrive as a string. -->
      <div class="toolbox-foot">${"tb -t <tool>"}</div>
    </div>
  `;
}

// --------------------------------------------------------------------- palette

/* The suggestion list, shared. Extracted when the palette moved into the top
 * bar: the overlay shows it inline and the bar shows it as a dropdown, and two
 * copies of a list whose selection semantics matter would drift. */
function Suggestions({ shown, selected, open, query }) {
  /* `onMouseDown` rather than `onClick`: it fires before the input's blur, so
   * choosing a suggestion does not race the dropdown closing. */
  return html`
    <div class="suggestions">
      ${shown.map(
        (c, i) => html`
          <div
            key=${c.name}
            class=${`suggestion ${i === selected ? "sel" : ""}`}
            onMouseDown=${() => open(c, query)}
          >
            <span class="mark">${i === selected ? "▸" : ""}</span>
            <span class="name">${c.saved ? shortOf(c) : c.name}</span>
            ${c.saved && html`<span class="saved-badge">saved</span>`}
            <span class="desc">${c.summary}</span>
            <span class="meta">${c.acts ? "acts" : "opens a window"}</span>
          </div>
        `
      )}
    </div>
  `;
}

/* Keyboard behaviour is identical wherever the palette is drawn. */
function paletteKeys({ shown, selected, setSelected, open, query, onEscape }) {
  return (event) => {
    if (event.key === "Enter" && shown.length) {
      open(shown[Math.min(selected, shown.length - 1)], query);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelected(Math.min(selected + 1, shown.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelected(Math.max(selected - 1, 0));
    } else if (event.key === "Escape" && onEscape) {
      onEscape();
    }
  };
}

/* The palette in the top bar.
 *
 * Bounded rather than full width: an argv long enough to need more than eighty
 * characters is one you would rather save as a tool anyway, and a prompt
 * stretched across a 3000px monitor is harder to read, not easier.
 *
 * The list appears only while the input has focus. A palette that permanently
 * lists every command is a menu, and this is a prompt — the suggestions are an
 * answer to something you started typing, so they belong to the moment you are
 * typing it.
 */
function BarPalette({ commands, query, setQuery, selected, setSelected, open, home }) {
  const input = useRef(null);
  const [focused, setFocused] = useState(false);
  const shown = withRaw(commands, query, home).slice(0, 8);

  const onKey = paletteKeys({
    shown, selected, setSelected, open, query,
    onEscape: () => input.current && input.current.blur(),
  });

  /* The bar is the window's title bar and starts a window drag on mousedown.
   * Without this, clicking into the prompt moves the window instead of placing
   * a cursor.
   *
   * Declared here rather than inline in the template: htm is a template-literal
   * parser with no notion of comments, so a `/* … *\/` inside a tag is parsed
   * as attribute text and silently mangles the element's children. That is how
   * this input came to be missing from the DOM entirely. */
  const stopDrag = (event) => event.stopPropagation();

  return html`
    <div class="barpal" onMouseDown=${stopDrag}>
      <span class="chev">tb ▸</span>
      <input
        ref=${input}
        value=${query}
        placeholder="type a command"
        onFocus=${() => setFocused(true)}
        onBlur=${() => setFocused(false)}
        onInput=${(e) => {
          setQuery(e.target.value);
          setSelected(0);
        }}
        onKeyDown=${onKey}
      />
      ${focused && shown.length > 0 &&
      html`<div class="drop">
        <${Suggestions} shown=${shown} selected=${selected} open=${open} query=${query} />
      </div>`}
    </div>
  `;
}

function Palette({ commands, query, setQuery, selected, setSelected, open, floating, close, home }) {
  const input = useRef(null);
  useEffect(() => {
    if (floating && input.current) input.current.focus();
  }, [floating]);

  const shown = withRaw(commands, query, home).slice(0, 8);
  const onKey = paletteKeys({
    shown, selected, setSelected, open, query,
    onEscape: floating ? close : null,
  });

  return html`
    <div class=${`palette ${floating ? "overlay" : ""}`}>
      <div class="prompt">
        <span class="chev">tb ▸</span>
        <input
          ref=${input}
          value=${query}
          placeholder="type a command — run -- jam pr list --json"
          onInput=${(e) => {
            setQuery(e.target.value);
            setSelected(0);
          }}
          onKeyDown=${onKey}
        />
        <span class="hint">⏎ open window · ^K palette</span>
      </div>
      ${shown.length > 0 &&
      html`<${Suggestions} shown=${shown} selected=${selected} open=${open} query=${query} />`}
    </div>
  `;
}

// --------------------------------------------------------------------- window

/* How far through this window's refresh interval we are.
 *
 * The mockup carries `hasProgress` / `progress` / `progressLabel` and does not
 * say what fills them. A *running command* cannot: a subprocess has no
 * percentage, and a bar that animates to look busy is decoration pretending to
 * be information. A *watcher* can — the interval and the last run are both
 * known — so this is the one quantity a bar here can honestly show.
 *
 * null when there is nothing measurable: unpinned, no cadence, never run, or a
 * run in flight. The title bar already says "running…".
 *
 * This reads `now`, which is the label clock and may be throttled to a crawl in
 * a hidden page. That is fine and is the point of the split: the *refresh*
 * clock lives in Python keyed to the connection, so a throttled bar lags behind
 * a refresh that still happened on time. A stale bar is a cosmetic bug; a
 * throttled scheduler would be a silent one.
 */
function progressOf(win, now) {
  /* Re-pointed at the chrome contract's last_run (epoch seconds, stamped at
   * result time in Python) when a result has one; the local stamp remains the
   * fallback for a window that has not heard from the server yet. Same
   * numbers, same behavior — the deciding half just lives where pytest is. */
  const chrome = win.result && win.result.chrome;
  const since = chrome && chrome.last_run ? chrome.last_run * 1000 : win.ranAt;
  if (!win.pinned || !win.interval || !since || win.running) return null;
  const elapsed = (now - since) / 1000;
  const remaining = Math.max(0, Math.ceil(win.interval - elapsed));
  const percent = Math.min(100, Math.max(0, (elapsed / win.interval) * 100));
  return { remaining, percent };
}

/* The tail of a held-open stream. Newest lines stay in view — a live log
 * window showing anything but its tail is broken — and stderr lines carry
 * the tag as a style, which is the tint a Rule will drive later. */
/* The title label for a held-open stream. The attention word is the chrome's
 * verdict — quiet, absent and rotated come from a stat, dead from an exit —
 * and this only chooses the friendlier spelling of two of them. */
function streamLabel(win) {
  const c = win.chrome;
  if (!c) return win.streamLines.length ? "live" : "starting…";
  if (c.attention === "dead") return `dead · exited ${c.exit_code}`;
  if (c.attention === "running") return "live";
  return c.attention;
}

/* One followed line, marks applied dumbly. The rules live in Python and the
 * offsets arrive beside the verbatim text ([[highlight]]); this only slices
 * and wraps — a page holding its own opinion about what a timestamp looks
 * like is the drift the one-rule-set design exists to prevent. A stderr line
 * never carries marks and keeps its warn tint. */
function markedLine(l) {
  if (l.stderr || !l.marks || !l.marks.length)
    return html`<span class=${l.stderr ? "err" : ""}>${l.text + "\n"}</span>`;
  const parts = [];
  let cursor = 0;
  for (const [start, end, role] of l.marks) {
    if (start > cursor) parts.push(l.text.slice(cursor, start));
    parts.push(
      html`<span class=${"mk-" + role.replace("tb.", "")}>${l.text.slice(start, end)}</span>`
    );
    cursor = end;
  }
  parts.push(l.text.slice(cursor) + "\n");
  return html`<span>${parts}</span>`;
}

function StreamBody({ win, actions }) {
  const bodyRef = useRef(null);
  useEffect(() => {
    const node = bodyRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [win.streamLines]);
  const dead = win.chrome && win.chrome.attention === "dead";
  return html`
    <div class="body" ref=${bodyRef}>
      <pre class="raw stream">
${win.streamLines.map(markedLine)}</pre
      >
      ${dead &&
      html`<div class="dead-band">
        exited ${win.chrome.exit_code}
        <button class="tbtn" onClick=${() => actions.refresh(win.id)}>restart</button>
      </div>`}
    </div>
  `;
}

function Window({ win, now, layout, focused, actions, intervals }) {
  const age = win.ranAt ? Math.round((now - win.ranAt) / 1000) : null;
  const chrome = (win.result && win.result.chrome) || win.chrome;
  const failed = chrome
    ? chrome.attention === "failed" || chrome.attention === "dead"
    : win.result && (win.result.error || win.result.ok === false);
  const countdown = progressOf(win, now);

  const style =
    layout === FLOAT
      ? { left: `${win.x}px`, top: `${win.y}px`, width: `${win.w}px`, height: `${win.h}px`, zIndex: win.z }
      : {};

  return html`
    <div
      class=${`win ${focused ? "focus" : ""} ${win.wide ? "wide" : ""}`}
      style=${style}
      onMouseDown=${() => actions.focus(win.id)}
    >
      <div class="title" onMouseDown=${(e) => layout === FLOAT && actions.drag(win.id, e)}>
        <span class=${`dot ${failed ? "bad" : win.running ? "task" : ""}`}></span>
        <span class="num">#${win.num}</span>
        <span class="cmd">${win.label}</span>
        <span class=${`age ${failed ? "bad" : ""}`}>
          ${win.stream
            ? streamLabel(win)
            : win.running
              ? "running…"
              : age === null
                ? ""
                : `${age}s ago`}
        </span>
        <div class="spacer"></div>
        ${win.tags.map(
          (tag) => html`<span class="tag" key=${tag} onClick=${() => actions.untag(win.id, tag)}>
            #${tag}
          </span>`
        )}
        <span class="addtag" onClick=${() => actions.tag(win.id)}>＋tag</span>
        ${!win.acts &&
        !win.stream &&
        html`
          <button class=${`tbtn ${win.pinned ? "on" : ""}`} onClick=${() => actions.pin(win.id)}>
            ${win.pinned ? "PINNED" : "PIN"}
          </button>
          ${win.pinned &&
          html`<button class="tbtn plain" onClick=${() => actions.cycle(win.id, intervals)}>
            ${intervalLabel(win.interval)}
          </button>`}
        `}
        <button class="tbtn plain" title="refresh now" onClick=${() => actions.refresh(win.id)}>⟳</button>
        <button class="tbtn plain" title="close" onClick=${() => actions.close(win.id)}>✕</button>
      </div>

      ${win.raw &&
      html`
        <div class="chips">
          <span class="label">DIR</span>
          <input
            class="cwd"
            value=${win.cwd}
            title="where this command runs"
            onChange=${(e) => actions.chdir(win.id, e.target.value)}
          />
        </div>
      `}
      ${win.chips.length > 0 &&
      html`
        <div class="chips">
          <span class="label">LINKED</span>
          ${win.chips.map(
            (chip) => html`
              <button
                key=${chip.flag}
                class=${`chip ${chip.on ? "on" : ""}`}
                title=${chip.help}
                onClick=${() => actions.toggle(win.id, chip.flag)}
              >
                ${chip.flag}
              </button>
            `
          )}
        </div>
      `}

      ${countdown !== null &&
      html`
        <div class="progress">
          <div class="track"><div class="fill" style=${`width:${countdown.percent}%`}></div></div>
          <span class="until">next in ${countdown.remaining}s</span>
        </div>
      `}

      ${win.stream
        ? html`<${StreamBody} win=${win} actions=${actions} />`
        : html`<div class="body"><${Body} result=${win.result} /></div>`}

      <div class="foot">
        <span>
          ${win.stream
            ? `showing last ${win.streamLines.length}`
            : summarise(win.result)}
        </span>
        ${chrome && chrome.warnings > 0 &&
        html`<span class="foot-warn">
          ${chrome.warnings} warning${chrome.warnings === 1 ? "" : "s"}
        </span>`}
        <div class="spacer"></div>
        <span class="hint">
          ${chrome && chrome.attention ? `${chrome.attention} · ` : ""}
          ${win.result && win.result.duration_s !== undefined ? `${win.result.duration_s}s` : ""}
        </span>
      </div>
      ${layout === FLOAT &&
      html`<div class="resize" onMouseDown=${(e) => actions.resize(win.id, e)}></div>`}
    </div>
  `;
}

// ------------------------------------------------------------------------ app

function App() {
  const [commands, setCommands] = useState([]);
  const [intervals, setIntervals] = useState([0, 5, 30, 60, 300]);
  /* Where a raw command runs unless the window says otherwise. Supplied by the
   * server rather than assumed, since the browser cannot know it. */
  const [home, setHome] = useState("");
  const [windows, setWindows] = useState([]);
  const [layout, setLayout] = useState(TILE);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [floating, setFloating] = useState(false);
  const [focus, setFocus] = useState(null);
  const [session, setSession] = useState(null);
  const [down, setDown] = useState(false);
  const now = useNow();

  const zTop = useRef(1);
  const canvas = useRef(null);
  /* The stream handler is installed once and must not close over a stale
   * `windows`. A ref is the escape hatch: the effect reads through it. */
  const windowsRef = useRef(windows);
  windowsRef.current = windows;
  const sessionRef = useRef(null);

  useEffect(() => {
    api.catalog().then((body) => {
      setCommands(body.commands);
      setIntervals(body.intervals);
      setHome(body.home || "");
    });
  }, []);

  useEffect(() => {
    const stop = api.stream(
      (frame) => {
        if (frame.type === "hello") {
          sessionRef.current = frame.session;
          setSession(frame.session);
          setDown(false);
          /* Re-register everything. A reconnect after a dropped stream would
           * otherwise leave every pinned window silently unwatched — still
           * saying PINNED, never refreshing again. */
          for (const win of windowsRef.current) {
            if (win.pinned) api.watch(frame.session, win.id, argvOf(win), win.interval);
            /* A follow window's child died with the old session; a reconnect
             * spawns a fresh one, which is the honest reading of "nothing
             * survives the last window". */
            if (win.stream) api.follow(frame.session, win.id, argvOf(win));
          }
        } else if (frame.type === "reload") {
          applyReload(frame.files);
        } else if (frame.type === "stream") {
          setWindows((all) =>
            all.map((w) => {
              if (w.id !== frame.window) return w;
              const limit = (frame.chrome && frame.chrome.ring_limit) || 200;
              const lines = [...(w.streamLines || []), ...frame.lines].slice(-limit);
              return { ...w, streamLines: lines, chrome: frame.chrome, running: false };
            })
          );
        } else if (frame.type === "run") {
          setWindows((all) =>
            all.map((w) =>
              w.id === frame.window
                ? { ...w, result: frame.result, ranAt: Date.now(), running: false }
                : w
            )
          );
        }
      },
      () => setDown(true)
    );
    return stop;
  }, []);

  useEffect(() => {
    function onKey(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setFloating((f) => !f);
      } else if (event.key === "Escape") {
        setFloating(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  function execute(id, argv, stream = null) {
    /* `stream` is passed explicitly from open(), because the state update
     * that adds the window has not landed in windowsRef yet on the very
     * first execute. Everywhere else the window is looked up. */
    const win = windowsRef.current.find((w) => w.id === id);
    if (stream === null) stream = Boolean(win && win.stream);
    if (stream) {
      /* Streams are held open by the server, not run to completion. This is
       * also the restart affordance: re-POSTing kills the corpse and spawns
       * fresh, so the ⟳ button means "again" for a stream too. */
      setWindows((all) =>
        all.map((w) => (w.id === id ? { ...w, streamLines: [], running: true } : w))
      );
      if (sessionRef.current) {
        api.follow(sessionRef.current, id, argv).catch((error) =>
          setWindows((all) =>
            all.map((w) =>
              w.id === id ? { ...w, result: { error: String(error) }, running: false } : w
            )
          )
        );
      }
      return;
    }
    setWindows((all) => all.map((w) => (w.id === id ? { ...w, running: true } : w)));
    api
      .run(argv)
      .then((result) =>
        setWindows((all) =>
          all.map((w) =>
            w.id === id ? { ...w, result, ranAt: Date.now(), running: false } : w
          )
        )
      )
      .catch((error) =>
        setWindows((all) =>
          all.map((w) =>
            w.id === id
              ? { ...w, result: { error: String(error) }, ranAt: Date.now(), running: false }
              : w
          )
        )
      );
  }

  function open(entry, typed, initial) {
    /* Anything typed past the command name is argv. `run -- jam pr list --json`
     * has to reach the server whole; splitting it here would be a second
     * parser, and tb's own is the one that decides what an argv means. */
    const words = typed.trim().split(/\s+/).filter(Boolean);
    /* A raw entry was built from the query itself, so every word is already in
     * its argv. Slicing by command length here would append them a second
     * time.
     *
     * For anything else, drop however many words the typed text spent *naming*
     * the entry — which is not always the argv's length, because a saved
     * command answers to its short name: `prs` names the two-word argv
     * `tools prs`. Counting argv words there would eat the first argument
     * typed after the name, silently. */
    const q = typed.trim().toLowerCase();
    const named =
      q === entry.name || q.startsWith(entry.name + " ")
        ? entry.name.split(" ").length
        : entry.saved && (q === shortOf(entry) || q.startsWith(shortOf(entry) + " "))
          ? 1
          : entry.argv.length;
    const extra = entry.raw ? [] : words.slice(named);
    const id = newId();
    const count = windowsRef.current.length;

    const win = {
      id,
      num: count + 1,
      argv: [...entry.argv, ...extra],
      label: entry.raw ? entry.rawWords.join(" ") : [...entry.argv, ...extra].join(" "),
      acts: entry.acts,
      /* Resident by nature — a stream is held open, not run. Inherited from
       * the catalog, so a saved keyword wrapping follow is one too. */
      stream: Boolean(entry.resident),
      streamLines: [],
      chrome: null,
      raw: Boolean(entry.raw),
      rawWords: entry.rawWords || null,
      cwd: entry.cwd || null,
      chips: (entry.options || [])
        .filter((o) => o.is_flag)
        .map((o) => ({ flag: o.flag, help: o.help, on: false })),
      tags: [],
      /* A tool may declare the cadence it opens on. Pinning it here rather
       * than leaving it to a click is the whole point of saving it: the
       * window you wanted is the window you get. Only a read can carry one —
       * `refresh` is refused at load on a tool that acts. */
      pinned: Boolean(initial && initial.interval),
      interval: (initial && initial.interval) || 0,
      result: null,
      running: false,
      ranAt: null,
      wide: false,
      x: 24 + (count % 3) * 40,
      y: 24 + (count % 3) * 40,
      w: 620,
      h: 320,
      z: ++zTop.current,
    };

    setWindows((all) => [...all, win]);
    setQuery("");
    setSelected(0);
    setFloating(false);
    setFocus(id);
    execute(id, argvOf(win), win.stream);
    /* Registered now rather than on the next session frame, so a tool that
     * opens pinned starts its clock immediately instead of on the next tick. */
    if (win.pinned) reWatch(win);
  }

  function patch(id, change) {
    setWindows((all) => all.map((w) => (w.id === id ? { ...w, ...change(w) } : w)));
  }

  function reWatch(win) {
    if (!sessionRef.current) return;
    if (win.pinned) api.watch(sessionRef.current, win.id, argvOf(win), win.interval);
    else api.unwatch(sessionRef.current, win.id);
  }

  const actions = {
    focus: (id) => {
      setFocus(id);
      if (layout === FLOAT) patch(id, () => ({ z: ++zTop.current }));
    },
    close: (id) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (sessionRef.current) {
        api.unwatch(sessionRef.current, id);
        /* Closing a follow's window SIGTERMs its process — streams die with
         * their window, which is what keeps a follow a stream and not a
         * service manager. */
        if (win && win.stream) api.unfollow(sessionRef.current, id);
      }
      setWindows((all) => all.filter((w) => w.id !== id));
    },
    refresh: (id) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (win) execute(id, argvOf(win));
    },
    /* Re-runs at once. A directory that changed but left the old output on
     * screen is a window claiming to show something it is not. */
    chdir: (id, cwd) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (!win || !win.raw || !cwd || cwd === win.cwd) return;
      const next = { ...win, cwd };
      patch(id, () => ({ cwd }));
      reWatch(next);
      execute(id, argvOf(next));
    },
    pin: (id) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (!win || win.acts) return;
      const next = { ...win, pinned: !win.pinned, interval: win.pinned ? 0 : 30 };
      patch(id, () => ({ pinned: next.pinned, interval: next.interval }));
      reWatch(next);
    },
    cycle: (id, list) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (!win) return;
      const interval = list[(list.indexOf(win.interval) + 1) % list.length];
      patch(id, () => ({ interval }));
      reWatch({ ...win, interval });
    },
    toggle: (id, flag) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (!win) return;
      const chips = win.chips.map((c) => (c.flag === flag ? { ...c, on: !c.on } : c));
      const next = { ...win, chips };
      patch(id, () => ({ chips }));
      /* Re-run at once. A chip that changed the argv but left the old rows on
       * screen would be showing an answer to a question nobody asked. */
      execute(id, argvOf(next));
      reWatch(next);
    },
    tag: (id) => {
      const pool = ["jam", "review", "net", "ops", "release"];
      patch(id, (w) => {
        const next = pool.find((t) => !w.tags.includes(t));
        return next ? { tags: [...w.tags, next] } : {};
      });
    },
    untag: (id, tag) => patch(id, (w) => ({ tags: w.tags.filter((t) => t !== tag) })),
    drag: (id, event) => {
      if (event.target.closest("button, .tag, .addtag")) return;
      event.preventDefault();
      const win = windowsRef.current.find((w) => w.id === id);
      const sx = event.clientX;
      const sy = event.clientY;
      const ox = win.x;
      const oy = win.y;
      const move = (e) =>
        patch(id, () => ({
          x: Math.max(0, ox + e.clientX - sx),
          y: Math.max(0, oy + e.clientY - sy),
        }));
      const up = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
      };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
      actions.focus(id);
    },
    resize: (id, event) => {
      event.preventDefault();
      event.stopPropagation();
      const win = windowsRef.current.find((w) => w.id === id);
      const sx = event.clientX;
      const sy = event.clientY;
      const ow = win.w;
      const oh = win.h;
      const move = (e) =>
        patch(id, () => ({
          w: Math.max(280, ow + e.clientX - sx),
          h: Math.max(140, oh + e.clientY - sy),
        }));
      const up = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
      };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
    },
  };

  const watchers = windows.filter((w) => w.pinned).length;
  const running = windows.filter((w) => w.running).length;
  const attention = windows.filter(
    (w) => w.result && (w.result.error || w.result.ok === false)
  ).length;

  return html`
    <div class="app">
      <div class="bar" onMouseDown=${barDrag}>
        <span class="brand">TACKLEBOX</span>
        <span class="host">${location.host}</span>
        <${BarPalette}
          commands=${commands}
          query=${query}
          setQuery=${setQuery}
          selected=${selected}
          setSelected=${setSelected}
          open=${open}
          home=${home}
        />
        <div class="spacer"></div>
        <span class=${`stat ${running ? "live" : ""}`}>TASKS<b>${running}</b></span>
        <span class="stat">WINDOWS<b>${windows.length}</b></span>
        <span class=${`stat ${watchers ? "live" : ""}`}>WATCHERS<b>${watchers}</b></span>
        <span class=${`stat ${attention ? "alert" : ""}`}>ATTENTION<b>${attention}</b></span>
        <div class="seg">
          <button class=${layout === TILE ? "on" : ""} onClick=${() => setLayout(TILE)}>
            tiled
          </button>
          <button class=${layout === FLOAT ? "on" : ""} onClick=${() => setLayout(FLOAT)}>
            floating
          </button>
        </div>
        <button class="quit" title="close tackle-box" onClick=${() => api.quit()}>✕</button>
      </div>

      ${floating &&
      html`
        <div class="scrim" onMouseDown=${() => setFloating(false)}></div>
        <${Palette}
          commands=${commands}
          query=${query}
          setQuery=${setQuery}
          selected=${selected}
          setSelected=${setSelected}
          open=${open}
          home=${home}
          floating=${true}
          close=${() => setFloating(false)}
        />
      `}

      <div class="stage">
      <${Toolbox} commands=${commands} open=${open} />
      <div class=${`canvas ${layout}`} ref=${canvas}>
        ${windows.length === 0 &&
        html`<div class="empty">no windows open — run a command to open one</div>`}
        ${windows.map(
          (win) => html`<${Window}
            key=${win.id}
            win=${win}
            now=${now}
            layout=${layout}
            focused=${focus === win.id}
            actions=${actions}
            intervals=${intervals}
          />`
        )}
      </div>
      </div>

      <div class="foot-bar">
        <span>⏎ open window</span>
        <span>^K palette</span>
        <span>⟳ refresh</span>
        <div class="spacer"></div>
        ${down
          ? html`<span class="disconnected">stream down — watchers paused</span>`
          : html`<span>session ${session ? session.slice(0, 8) : "…"}</span>`}
      </div>
    </div>
  `;
}

render(html`<${App} />`, document.getElementById("root"));
