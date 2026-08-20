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
export function suggest(commands, query) {
  const q = query.trim().toLowerCase();
  if (!q) return commands;

  const named = commands
    .filter((c) => q === c.name || q.startsWith(c.name + " "))
    .sort((a, b) => b.name.length - a.name.length);
  if (named.length) return named;

  const head = q.split(/\s+/)[0];
  return commands.filter(
    (c) => c.name.startsWith(q) || (c.summary || "").toLowerCase().includes(head)
  );
}

/* argv for a window: its command, plus whichever chips are on. */
function argvOf(win) {
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

// --------------------------------------------------------------------- palette

function Palette({ commands, query, setQuery, selected, setSelected, open, floating, close }) {
  const input = useRef(null);
  useEffect(() => {
    if (floating && input.current) input.current.focus();
  }, [floating]);

  const shown = suggest(commands, query).slice(0, 8);

  function onKey(event) {
    if (event.key === "Enter" && shown.length) {
      open(shown[Math.min(selected, shown.length - 1)], query);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelected(Math.min(selected + 1, shown.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelected(Math.max(selected - 1, 0));
    } else if (event.key === "Escape" && floating) {
      close();
    }
  }

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
      html`
        <div class="suggestions">
          ${shown.map(
            (c, i) => html`
              <div
                key=${c.name}
                class=${`suggestion ${i === selected ? "sel" : ""}`}
                onMouseDown=${() => open(c, query)}
              >
                <span class="mark">${i === selected ? "▸" : ""}</span>
                <span class="name">${c.name}</span>
                <span class="desc">${c.summary}</span>
                <span class="meta">${c.acts ? "acts" : "opens a window"}</span>
              </div>
            `
          )}
        </div>
      `}
    </div>
  `;
}

// --------------------------------------------------------------------- window

function Window({ win, now, layout, focused, actions, intervals }) {
  const age = win.ranAt ? Math.round((now - win.ranAt) / 1000) : null;
  const failed = win.result && (win.result.error || win.result.ok === false);

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
          ${win.running ? "running…" : age === null ? "" : `${age}s ago`}
        </span>
        <div class="spacer"></div>
        ${win.tags.map(
          (tag) => html`<span class="tag" key=${tag} onClick=${() => actions.untag(win.id, tag)}>
            #${tag}
          </span>`
        )}
        <span class="addtag" onClick=${() => actions.tag(win.id)}>＋tag</span>
        ${!win.acts &&
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

      ${win.chips.length > 0 &&
      html`
        <div class="chips">
          <span class="label">FLAGS</span>
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

      <div class="body"><${Body} result=${win.result} /></div>

      <div class="foot">
        <span>${summarise(win.result)}</span>
        <div class="spacer"></div>
        <span>
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
          }
        } else if (frame.type === "reload") {
          applyReload(frame.files);
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

  function execute(id, argv) {
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

  function open(entry, typed) {
    /* Anything typed past the command name is argv. `run -- jam pr list --json`
     * has to reach the server whole; splitting it here would be a second
     * parser, and tb's own is the one that decides what an argv means. */
    const words = typed.trim().split(/\s+/).filter(Boolean);
    const extra = words.slice(entry.argv.length);
    const id = newId();
    const count = windowsRef.current.length;

    const win = {
      id,
      num: count + 1,
      argv: [...entry.argv, ...extra],
      label: [...entry.argv, ...extra].join(" "),
      acts: entry.acts,
      chips: (entry.options || [])
        .filter((o) => o.is_flag)
        .map((o) => ({ flag: o.flag, help: o.help, on: false })),
      tags: [],
      pinned: false,
      interval: 0,
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
    execute(id, argvOf(win));
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
      if (sessionRef.current) api.unwatch(sessionRef.current, id);
      setWindows((all) => all.filter((w) => w.id !== id));
    },
    refresh: (id) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (win) execute(id, argvOf(win));
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
      <div class="bar">
        <span class="brand">TACKLEBOX</span>
        <span class="host">${location.host}</span>
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
      </div>

      ${!floating &&
      html`<${Palette}
        commands=${commands}
        query=${query}
        setQuery=${setQuery}
        selected=${selected}
        setSelected=${setSelected}
        open=${open}
        floating=${false}
      />`}
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
          floating=${true}
          close=${() => setFloating(false)}
        />
      `}

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
