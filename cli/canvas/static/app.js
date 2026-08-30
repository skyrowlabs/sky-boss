/* The canvas: a command palette over a window canvas.
 *
 * Three rules this file exists to keep, all inherited from the surface it
 * replaces rather than invented here:
 *
 * 1. **Nothing keeps a command table.** The palette comes from /api/catalog,
 *    which reads the live Click tree. A palette offering a command that does
 *    not exist is worse than no palette, because it has already told you it
 *    does.
 * 2. **Only a read may be given a cadence.** An entry with `acts` is `sb run`,
 *    and re-running a write on a timer is a scheduler nobody asked for. The
 *    pin control is simply not offered on one.
 * 3. **No single result may render unbounded.** See render.js. The terminal
 *    surface froze for exactly this and the medium change does not repeal it.
 *
 * The refresh clock is not here. It is in Python, keyed to the stream, because
 * "keeps running while minimized" is not something a browser timer can promise
 * — a hidden page has its timers clamped. See cli/canvas/watch.py.
 */

import { html, useEffect, useRef, useState } from "./vendor/htm-preact.js";
import * as api from "./api.js";
import { Body, markedLine, summarise } from "./render.js";
import { BENCH_WINDOW, Bench, RESIDENT, compose, tagPool } from "./bench.js";
import { Plan } from "./schedule.js";

const TILE = "tile";
const FLOAT = "float";

/* Three screens as of [[schedule]] round 4. The design pass drew four —
 * workbench, flight plan, control tower — and the rule here used to be that a
 * nav offering a screen that is not there is the palette's own failure wearing
 * different clothes: it has already told you the thing exists.
 *
 * **The rule stands; its condition changed.** The objection was to *offering*
 * something absent, so the schedule screen answers it by existing rather than
 * by overriding it — and it is called `schedule`, not `plan`, because the rest
 * of the drawn flight plan still needs job identity, a claim vocabulary and a
 * clock source. A nav entry reading `plan` above a table of fire times would
 * be the same over-promise in a smaller font. The control tower is still not
 * offered. See [[workbench]] and docs/open.md.
 */
const CANVAS = "canvas";

/* How many columns the tile grid gets: a function of how many windows there
 * are, not of a fixed minimum width. One fills the canvas, two split it, four
 * quarter it. `auto-fill` used to build every track that fitted whether or not
 * anything occupied it. See [[canvas]] round 8. */
function tileColumns(count) {
  return Math.max(1, Math.ceil(Math.sqrt(count)));
}
const WORKBENCH = "workbench";
const SCHEDULE = "schedule";

/* The view flags a saved tool may carry in its argv, and the draft field each
 * belongs in. Named here rather than in the loop so adding a fourth is one
 * line and cannot be half-done. See [[highlight]] round 5. */
const VIEW_FLAGS = { "--highlight": "highlight", "--from": "from", "--due": "due" };

/* What the bench opens on. Decided before the screen existed rather than
 * after, which is what round 1 asked for.
 *
 * **No contract is selected.** The mockup pre-selected `data`, and that is the
 * one thing the bench must not do: the selector *is* the operator asserting
 * the bit no parser can infer, and answering it for them on arrival is the
 * inference with a friendlier face. It also gives the empty state something
 * true to say instead of a blank pane.
 *
 * `cwd` fills in from the server's `home` once the catalog lands — the same
 * neutral directory a raw palette command runs in, and for the same reason.
 */
const EMPTY_DRAFT = {
  contract: null,
  cwd: "",
  /* [[subprocess-env]] round 4. A tool that gates its output on isatty()
   * says less into a pipe, and only its author knows which variable turns
   * that back on — so the operator declares it. */
  env: "",
  argv: "",
  result: null,
  chrome: null,
  lines: [],
  running: false,
  error: null,

  /* Round 2 — the view controls. Every one of these composes into the argv,
   * and two of them also re-shape what is already drawn.
   *
   * `offered` is the checklist, and it comes from the server shaping the same
   * payload with *nothing* asked of it. It cannot be read off the drawn view:
   * with `--cols` in force `shape` returns exactly what was named and `hidden`
   * is empty, so a checklist built from that would lose a column the moment
   * you unticked it and offer no way back. */
  cols: [],
  offered: [],
  /* `shaped` is null both before a shaping has been asked for and when one
   * came back saying there are no rows here — two different states that must
   * not render the same, so the fact of having an answer is tracked
   * separately rather than inferred from the answer being empty. */
  hasShaped: false,
  shaped: null,
  shapeWarnings: [],
  rows: "",
  from: "",
  due: "",
  highlight: "",
  /* [[table-views]] round 6. `--cols` says *which* columns; these two say
   * *how many* — everything, or everything minus these. `noShape` wins over
   * `cols` in `compose`, because the two disagree by construction. */
  noShape: false,
  drop: "",

  /* Round 3 — the job strip. The name is the *last* control and it is checked
   * before it is used, because `--save` writes before it runs: a refusal found
   * after the write is found too late, under a name that then cannot be
   * reused. `checks` is what an act gets instead of a trial run. */
  save: "",
  describe: "",
  group: "",
  /* Space-separated while being typed, split on save. A text box rather than a
   * chip editor because a tag has a name's shape — no spaces are legal inside
   * one, so the separator can never be ambiguous. See [[tools]] round 8. */
  tags: "",
  checks: [],
  nameProblem: null,
  /* What this tool is *already called*, when the bench was opened from the
   * rail's ✎. Null for a fresh draft. Changing `save` away from it is a
   * rename, and without this the bench could not tell one from a new tool —
   * so every rename was a copy. See [[workbench]] round 5. */
  was: null,
  /* What saving would overwrite, rendered. Not a problem: a taken name is a
   * replace, which is [[tools]] round 4's whole point. */
  replaces: null,
  block: null,
  saving: false,
  saved: null,
};


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
 * never stored: `tools jam-pr-list` is the address since [[tools]] round 2,
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

/* Anything typed that is not a sky.boss command is offered as one anyway, run
 * through `sb read` so it can be pinned and refreshed.
 *
 * Appended rather than shown only when nothing else matched: `list` matches
 * `tools` by description, and a raw entry that hid behind a description match
 * would be a palette that sometimes accepts a command and sometimes silently
 * does not. Suppressed only when the first word is exactly a sky.boss command, where
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
    summary: `sb read -- ${words.join(" ")}`,
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

/* The tools: the operator's saved commands, down the left.
 *
 * It is not a second list of commands. These come from the same /api/catalog
 * every other surface reads, filtered on `saved` — a property the *command*
 * carries, so a tool that stops existing stops appearing here with no code
 * involved. See [[tools]].
 */
/* Sections, in the order the *server* gives them.
 *
 * Round 5 sorted here. That was one copy too many the moment a group could be
 * *declared* as well as named, because an empty group appears in no command's
 * `group` field and the rail would have had to know about a file it never
 * reads. `/api/catalog` now ships `groups` already ordered and counted, from
 * `cli.tools.sections`, and this only buckets. Within a group nothing sorts
 * here either: the catalog walks `sorted(command.commands)`.
 *
 * The ungrouped are appended last and are deliberately *not* a server-side
 * group — they are a bucket, and a bucket cannot be deleted.
 *
 * `dragging` forces that bucket to exist. Without it, a rail where every
 * command is in a group draws no ungrouped section — and then there is nowhere
 * to drop one to take it *out* of a group, which found itself the first time
 * the drag was tested end to end. The empty bucket appears only while
 * something is being dragged, so it costs nothing the rest of the time. */
/* What kind of window a tool opens — [[tools]] round 8.
 *
 * **Derived, never declared.** `expansion[0]` *is* the contract, so a `type`
 * field in `tools.toml` would be a second opinion about something the argv
 * already settles — the mistake round 4 fixed for `acts`.
 *
 * `run` is deliberately absent: it already has `!`, which is a *warning* and
 * not a label, and doubling it would dilute the one marker that stops
 * something ([[canvas]] round 11). So this speaks only for the three reads,
 * which is exactly what the `!` could not tell you apart. */
export function kindOf(entry) {
  /* `.length`, not `||`: an **empty array is truthy**, so `expansion || argv`
   * never once fell back — a catalog entry with `expansion: []` came out with
   * no kind at all instead of reading its argv. Latent today, because the rail
   * only draws saved commands and those always carry an expansion; found in the
   * first minute of having a test runner, which is the argument for having one.
   * See [[canvas]] round 12. */
  const words = entry.expansion?.length ? entry.expansion : entry.argv || [];
  const contract = words[0];
  return contract === "run" ? "" : contract || "";
}

/* Does this tool match what was typed in the rail's filter?
 *
 * One text box over name, description, expansion and tags rather than a type
 * selector. Type has four values and three of them are reads, so filtering by
 * it barely narrows anything; a text box expresses those four *and* everything
 * else — typing `follow` matches the expansion, `release` matches a tag — and
 * adds no vocabulary the operator has to learn. See [[tools]] round 8.
 *
 * Every term must match, so terms narrow rather than widen: `jam release` is
 * the jam tools about releases, which is what a second word is for. */
export function matches(entry, query) {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const hay = [
    entry.name,
    shortOf(entry),
    entry.summary || "",
    entry.group || "",
    (entry.tags || []).join(" "),
    (entry.expansion || []).join(" "),
  ]
    .join(" ")
    .toLowerCase();
  return terms.every((term) => hay.includes(term));
}

function sectionsOf(saved, groups, dragging) {
  const by = new Map();
  for (const c of saved) {
    const key = c.group || "";
    if (!by.has(key)) by.set(key, []);
    by.get(key).push(c);
  }
  const sections = groups.map((g) => [g.name, by.get(g.name) || [], g]);
  if (by.has("") || dragging) sections.push(["", by.get("") || [], null]);
  return sections;
}

/* The rail's width, in `rem`, and the drag that sets it. See [[tools]] round 7.
 *
 * **Rem rather than pixels, and the conversion is read rather than recomputed.**
 * The stylesheet is measured in `rem` where `1rem = 4px x --sb-scale`, so a
 * width stored in pixels would mean a different rail at every scale. The
 * px-per-rem comes from the root's computed `font-size` instead of a second
 * copy of that formula — one place to be wrong instead of two. This is the
 * `clientX`-is-not-CSS-units mismatch that got `zoom` rejected in [[canvas]]
 * round 4, met head-on.
 *
 * Written on release, not per move: one file write per drag rather than one
 * per pixel. */
const RAIL_DEFAULT = 46;
const RAIL_MIN = 18;
const RAIL_MAX = 160;

function pxPerRem() {
  const size = parseFloat(getComputedStyle(document.documentElement).fontSize);
  return size > 0 ? size : 4;
}

function useRailWidth() {
  const [rail, setRail] = useState(null);
  const dragging = useRef(null);

  const onPointerDown = (event) => {
    event.preventDefault();
    const start = event.clientX;
    const from = rail === null ? RAIL_DEFAULT : rail;
    dragging.current = { start, from, unit: pxPerRem() };
    event.target.setPointerCapture(event.pointerId);
    document.body.classList.add("rail-dragging");
  };

  const onPointerMove = (event) => {
    const state = dragging.current;
    if (!state) return;
    const moved = (event.clientX - state.start) / state.unit;
    const next = Math.round(state.from + moved);
    state.value = Math.min(RAIL_MAX, Math.max(RAIL_MIN, next));
    setRail(state.value);
  };

  /* The width to save comes off the drag state, **not** out of `rail`.
   *
   * `setState` is batched, so a pointerup arriving in the same task as the
   * last pointermove sees the `rail` this handler closed over at its last
   * render — `null` on a first drag, which the guard below then read as
   * "nothing to save". A real mouse renders between the two events and hid
   * it; a synthetic drag dispatched in one tick did not, which is what the
   * headless render pass is for. See [[tools]] round 7. */
  const onPointerUp = (event) => {
    const state = dragging.current;
    if (!state) return;
    dragging.current = null;
    document.body.classList.remove("rail-dragging");
    if (event.target.hasPointerCapture?.(event.pointerId)) {
      event.target.releasePointerCapture(event.pointerId);
    }
    if (state.value !== undefined) api.savePrefs({ rail: state.value });
  };

  return { rail, setRail, onPointerDown, onPointerMove, onPointerUp };
}

/* Which groups are folded. Held in `$SB_STATE` on the server rather than in
 * `localStorage`, because `sb ui` binds an ephemeral port every launch and
 * browser storage is keyed by origin — a fold written under one launch's
 * origin is simply not there under the next. Never `tools.toml` either: that
 * is the operator's file, and a chevron click has no business writing it or
 * spending one of round 4's backups on it. See [[tools]] round 5.
 *
 * Read once on mount and written on every toggle. Both directions swallow
 * their failure in `api.js`, so an unreachable preference costs the fold and
 * never the rail — everything open is the honest degradation. */
/* Dragging a command into a group.
 *
 * HTML5 drag and drop rather than pointer events, because the browser already
 * does the hard half — the drag image, the cursor, the escape key, the drop
 * outside — and reimplementing that with `pointermove` is how a rail ends up
 * with its own broken window manager.
 *
 * What crosses is the command's **name**, and nothing else. The drop handler
 * sends a regroup, which splices one line server-side; it does not restate the
 * command, because the rail knows a command's `summary` and not its
 * `description` and cannot see a `highlight` at all. See [[tools]] round 6. */
const DRAG_TYPE = "application/x-sb-tool";

function Tools({ commands, groups, open, edit, drop, addGroup, dropGroup, move }) {
  const [filter, setFilter] = useState("");
  const all = commands.filter((c) => c.saved);
  const saved = all.filter((c) => matches(c, filter));
  /* Whether something is in flight, so the ungrouped bucket can exist as a
   * target even when nothing is in it. */
  const [dragging, setDragging] = useState(false);
  /* Filtering *before* sectioning, so a group with no match disappears rather
   * than sitting there empty — an empty section under a filter reads as "this
   * group has nothing in it", which is a different and false statement. The
   * ungrouped bucket still appears while dragging, because it is a drop target
   * and not a result. */
  const sections = sectionsOf(saved, groups, dragging).filter(
    ([, entries]) => !filter.trim() || entries.length > 0
  );
  const [folded, setFolded] = useState(() => new Set());
  const grip = useRailWidth();
  /* The name being typed, or null when the control is closed. An empty string
   * is the open-and-blank state and has to be distinguishable from it. */
  const [naming, setNaming] = useState(null);
  /* The section the pointer is over, so it can say so. `null` is "not
   * dragging"; `""` is the ungrouped bucket, which is a real target. */
  const [over, setOver] = useState(null);
  useEffect(() => {
    let live = true;
    api.prefs().then((stored) => {
      if (!live) return;
      if (Array.isArray(stored.folded)) setFolded(new Set(stored.folded));
      if (Number.isFinite(stored.rail)) grip.setRail(stored.rail);
    });
    return () => {
      live = false;
    };
  }, []);
  const toggle = (group) => {
    const next = new Set(folded);
    if (!next.delete(group)) next.add(group);
    setFolded(next);
    /* Written back against the groups that currently exist, so one the
     * operator renamed or emptied stops being remembered rather than sitting
     * in the file forever matching nothing. */
    const groups = new Set(sections.map(([g]) => g).filter(Boolean));
    api.savePrefs({ folded: [...next].filter((g) => groups.has(g)) });
  };
  return html`
    <div
      class="tools"
      style=${grip.rail === null ? "" : `--sb-rail: ${grip.rail}rem`}
    >
      <div
        class="tools-grip"
        onPointerDown=${grip.onPointerDown}
        onPointerMove=${grip.onPointerMove}
        onPointerUp=${grip.onPointerUp}
        onPointerCancel=${grip.onPointerUp}
        title="drag to resize"
      ></div>
      <div class="tools-head">
        <span>TOOLS</span>
        ${all.length > 0 &&
        html`<input
          class="tools-filter"
          value=${filter}
          placeholder="filter"
          title="name, description, tag or expansion — every word must match"
          onInput=${(e) => setFilter(e.target.value)}
        />`}
      </div>
      <div class="tools-list">
        ${all.length === 0 &&
        html`<div class="tools-empty">
          nothing saved yet — declare a tool in tools.toml
        </div>`}
        ${/* An empty *result* is a different sentence from an empty rail, and
             saying the wrong one is how a filter reads as a tool that vanished.
             See [[tools]] round 8. */
        all.length > 0 &&
        saved.length === 0 &&
        html`<div class="tools-empty">
          no tool matches “${filter}” — ${all.length} hidden
        </div>`}
        ${sections.map(
          ([group, items]) => html`
          <div
            key=${group || "\u0000"}
            class=${`tool-section${over === group ? " over" : ""}`}
            onDragOver=${(e) => {
              if (!e.dataTransfer.types.includes(DRAG_TYPE)) return;
              /* Preventing the default is what makes an element a drop target
               * at all — without it the browser refuses the drop and there is
               * nothing to debug. */
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
              if (over !== group) setOver(group);
            }}
            onDragLeave=${(e) => {
              /* Only when the pointer has actually left the section, not when
               * it crosses one of the rows inside it. */
              if (!e.currentTarget.contains(e.relatedTarget)) setOver(null);
            }}
            onDrop=${(e) => {
              e.preventDefault();
              setOver(null);
              setDragging(false);
              const name = e.dataTransfer.getData(DRAG_TYPE);
              if (name) move(name, group);
            }}
          >
            ${group
              ? html`<div class="tool-group-row">
                  <button
                    class="tool-group"
                    aria-expanded=${!folded.has(group)}
                    title=${folded.has(group) ? "show these" : "fold these away"}
                    onClick=${() => toggle(group)}
                  >
                    <span class="tool-chevron">${folded.has(group) ? "▸" : "▾"}</span>
                    <span class="tool-group-name">${group}</span>
                    ${(folded.has(group) || items.length === 0) &&
                    html`<span class="tool-count">${items.length}</span>`}
                  </button>
                  ${/* A sibling, not a child — a button inside a button is not
                       valid and the row is the pattern `.tool-row` already
                       uses. Only on an empty group, and the server refuses a
                       non-empty one regardless: hiding a control is not
                       refusing. See [[tools]] round 6. */
                  items.length === 0 &&
                  html`<button
                    class="tool-group-drop"
                    title="delete this empty group"
                    onClick=${() => dropGroup(group)}
                  >
                    ✕
                  </button>`}
                </div>`
              : sections.length > 1 &&
                html`<div class="tool-rule">
                  ${dragging && items.length === 0
                    ? html`<span class="tool-rule-label">ungrouped</span>`
                    : ""}
                </div>`}
        ${(group && folded.has(group) ? [] : items).map(
          (c) => html`
            <div
              key=${c.name}
              class="tool-row"
              draggable=${true}
              onDragStart=${(e) => {
                e.dataTransfer.setData(DRAG_TYPE, shortOf(c));
                e.dataTransfer.effectAllowed = "move";
                setDragging(true);
              }}
              onDragEnd=${() => {
                setOver(null);
                setDragging(false);
              }}
            >
              <button
                class="tool"
                title=${c.summary || c.name}
                onClick=${() => open(c, shortOf(c), { interval: c.refresh })}
              >
                <span class="tool-name">${shortOf(c)}</span>
                ${c.refresh > 0 && html`<span class="tool-refresh">${c.refresh}s</span>`}
                ${/* What shape of window this opens — a table, verbatim text,
                     a live stream. A marker rather than a column, because the
                     rail is a narrow list where the *name* is the thing that
                     clips (see open.md item 19) and a column would compete
                     with it. Absent for a `run`, which has `!`. */
                kindOf(c) &&
                html`<span class="tool-kind" title=${`opens ${kindOf(c)}`}>
                  ${kindOf(c)}
                </span>`}
                ${c.acts && html`<span class="tool-acts" title="acts — never refreshed">!</span>`}
              </button>
              <button
                class="tool-edit"
                title="open this tool in the workbench"
                onClick=${() => edit(c)}
              >
                ✎
              </button>
              <button
                class="tool-drop"
                title="delete this tool"
                onClick=${() => drop(c)}
              >
                ✕
              </button>
            </div>
          `
        )}
          </div>
        `
        )}
      </div>
      ${naming === null
        ? html`<button class="tools-add" onClick=${() => setNaming("")}>
            + group
          </button>`
        : html`<form
            class="tools-add-form"
            onSubmit=${(e) => {
              e.preventDefault();
              const name = naming.trim();
              setNaming(null);
              if (name) addGroup(name);
            }}
          >
            <input
              class="tools-add-name"
              autofocus
              value=${naming}
              placeholder="group name"
              onInput=${(e) => setNaming(e.target.value)}
              onKeyDown=${(e) => e.key === "Escape" && setNaming(null)}
              onBlur=${() => setNaming(null)}
            />
          </form>`}
      <!-- An expression, not markup: htm does not decode HTML entities, so a
           literal &lt; here renders as the four characters "&lt;" on screen.
           Angle brackets inside a template have to arrive as a string. -->
      <div class="tools-foot">${"sb -t <tool>"}</div>
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
      <span class="chev">sb ▸</span>
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
        <span class="chev">sb ▸</span>
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
 * and this only chooses the friendlier spelling of two of them.
 *
 * **A lost session outranks every one of them, and that is [[canvas]] round 10.**
 * Those words are all claims about the *file*, earned by a stat that just
 * happened. With the session gone nothing is being stated, so the last one to
 * arrive is not stale information, it is a false claim — a window reading
 * `quiet` over a dead stream says the log is fine. The replacement names what
 * is actually wrong, and names the surface rather than the file so it cannot be
 * read as another verdict about the log. */
function streamLabel(win, down) {
  if (down) return "no session";
  const c = win.chrome;
  if (!c) return win.streamLines.length ? "live" : "starting…";
  if (c.attention === "dead") return `dead · exited ${c.exit_code}`;
  if (c.attention === "running") return "live";
  return c.attention;
}

function StreamBody({ win, actions }) {
  const bodyRef = useRef(null);
  useEffect(() => {
    const node = bodyRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [win.streamLines]);
  /* Only a follow dies. An accruing run reaching exit 0 has *succeeded*, and
   * offering to restart it there would read as recovery from a failure that
   * did not happen — its ⟳ is in the title bar like every other run's. */
  const dead = win.resident && win.chrome && win.chrome.attention === "dead";
  return html`
    <div class="body" ref=${bodyRef}>
      <pre class=${`raw stream ${win.wrap ? "wrap" : ""}`}>
${win.streamLines.map((l) => markedLine(l))}</pre
      >
      ${dead &&
      html`<div class="dead-band">
        exited ${win.chrome.exit_code}
        <button class="sbtn" onClick=${() => actions.refresh(win.id)}>restart</button>
      </div>`}
    </div>
  `;
}

/* A window's own view controls ([[table-views]] round 6).
 *
 * The same question the bench answers, asked of a payload that keeps being
 * replaced. Round 3 established that `hidden` is a property of the *run* —
 * an empty column, an opaque sha — and true at any width, so no window is ever
 * big enough to reveal one. Overruling that is the operator's to do, and until
 * this round the only way was to edit the saved tool.
 *
 * Folded by default: most windows are looked at, not configured, and a control
 * strip on every table would cost every window three lines to serve the few
 * where the question comes up.
 */
function ViewControls({ win, actions }) {
  /* The view lives on the *envelope*, not on the run result — `win.result` is
   * `{ok, envelope, …}` and `render.js` reads `envelope.view`. Reading one
   * level too shallow renders nothing at all and looks exactly like a window
   * whose contract returns no rows. */
  const envelope = win.result && win.result.envelope;
  const view = envelope && envelope.view;
  const offered = win.viewOffered || [];
  /* **Not gated on the view existing**, and that is the whole of "reverting is
   * a control, not a memory game". Choosing *everything* removes the view —
   * that is what `--no-shape` means — so controls that needed one disappeared
   * the moment you used them, taking the way back with them. `offered` is the
   * durable fact: once a shaping has answered for this window, it stays
   * answerable. */
  if (!offered.length && !(view && view.columns)) return null;
  const chosen = win.viewCols || [];
  const everything = Boolean(win.viewEvery);
  /* With no view every column is drawn, which is what having no view means. */
  const drawn = view
    ? new Set([
        ...(view.columns || []).map((c) => c.key),
        ...(view.details || []).map((c) => c.key),
      ])
    : new Set(offered);

  if (!win.viewOpen) {
    const hidden = ((view && view.hidden) || []).length;
    return html`
      <button class="vw-open" onClick=${() => actions.viewToggle(win.id)}>
        columns${hidden ? ` · ${hidden} hidden by rule` : ""}
      </button>
    `;
  }

  return html`
    <div class="vw">
      <div class="vw-chips">
        ${offered.map(
          (key) => html`<button
            key=${key}
            class=${`vc-chip ${drawn.has(key) ? "on" : ""}`}
            onClick=${() => actions.viewCol(win.id, key)}
          >
            ${key}
          </button>`
        )}
      </div>
      <div class="vw-row">
        <button
          class=${`vc-every ${everything ? "on" : ""}`}
          onClick=${() => actions.viewEvery(win.id)}
          title="every column, in the order found"
        >
          ${everything ? "✓ everything" : "everything"}
        </button>
        <button
          class="vw-clear"
          disabled=${!chosen.length && !everything}
          onClick=${() => actions.viewClear(win.id)}
        >
          clear
        </button>
        <span class="vw-note">
          ${everything
            ? "every column, in the order found."
            : chosen.length
              ? `${chosen.length} named — every column drawn is one you chose.`
              : "the lit ones are the shaping's own choices. A column a rule hid is still one you may name."}
        </span>
        <div class="spacer"></div>
        <button class="vw-open" onClick=${() => actions.viewToggle(win.id)}>close</button>
      </div>
    </div>
  `;
}

/* The confirmation for an act. See [[canvas]] round 11.
 *
 * **Run is never the focused default and never answers to Enter.** Enter is
 * how a palette row launches, so a dialog that focused Run would be dismissed
 * by a second Enter — held, repeated, or typed ahead — before anything had been
 * read, and a guard defeated by the gesture it exists to catch is worse than
 * none. Cancel takes focus; Run costs a deliberate click.
 *
 * It shows the argv it will actually run, expanded, because "make sure it was
 * not accidental" is a question about *what*, not merely whether — a saved
 * tool is a short name in the rail and the argv is the thing that happens. */
function ConfirmAct({ pending, onConfirm, onCancel }) {
  const cancelRef = useRef(null);
  useEffect(() => {
    if (cancelRef.current) cancelRef.current.focus();
  }, []);
  return html`
    <div class="scrim confirm-scrim" onMouseDown=${onCancel}></div>
    <div class="confirm" role="dialog" aria-modal="true">
      <div class="confirm-head"><span class="acts-mark">!</span> ${pending.head}</div>
      <div class="confirm-note">${pending.note}</div>
      <pre class="confirm-argv">${pending.body}</pre>
      ${(pending.under || []).map((line) => html`<div class="confirm-cwd" key=${line}>${line}</div>`)}
      <div class="confirm-buttons">
        <button class="sbtn" ref=${cancelRef} onClick=${onCancel}>cancel</button>
        <button class="sbtn danger" onClick=${onConfirm}>${pending.confirm}</button>
      </div>
    </div>
  `;
}

function Window({ win, now, layout, focused, actions, intervals, down }) {
  const age = win.ranAt ? Math.round((now - win.ranAt) / 1000) : null;
  const chrome = (win.result && win.result.chrome) || win.chrome;
  const failed = chrome
    ? chrome.attention === "failed" || chrome.attention === "dead"
    : win.result && (win.result.error || win.result.ok === false);
  /* The bar measures time to the next refresh. With the session down there is
   * no next refresh, so an animating bar is the countdown lying in exactly the
   * way `quiet` was — worse, because a bar reaching zero and resetting looks
   * like a refresh happening. See [[canvas]] round 10. */
  const countdown = down ? null : progressOf(win, now);

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
        <span class=${`age ${failed ? "bad" : ""} ${down ? "stale" : ""}`}>
          ${win.resident
            ? streamLabel(win, down)
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
        !win.resident &&
        html`
          <button class=${`sbtn ${win.pinned ? "on" : ""}`} onClick=${() => actions.pin(win.id)}>
            ${win.pinned ? "PINNED" : "PIN"}
          </button>
          ${win.pinned &&
          html`<button class="sbtn plain" onClick=${() => actions.cycle(win.id, intervals)}>
            ${intervalLabel(win.interval)}
          </button>`}
        `}
        ${win.stream &&
        html`<button
          class=${`sbtn ${win.wrap ? "on" : ""}`}
          title="wrap long lines to the window, indented under the timestamp"
          onClick=${() => actions.wrap(win.id)}
        >
          WRAP
        </button>`}
        <button class="sbtn plain" title="refresh now" onClick=${() => actions.refresh(win.id)}>⟳</button>
        <button class="sbtn plain" title="close" onClick=${() => actions.close(win.id)}>✕</button>
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

      ${!win.stream && html`<${ViewControls} win=${win} actions=${actions} />`}

      ${win.stream
        ? html`<${StreamBody} win=${win} actions=${actions} />`
        : html`<div class="body">
            <${Body} result=${win.result} warnings=${win.viewWarnings} />
          </div>`}

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
  /* Every group that exists — declared, named, or both — ordered and counted
   * by the server. See [[tools]] round 6. */
  const [groups, setGroups] = useState([]);
  const [intervals, setIntervals] = useState([0, 5, 30, 60, 300]);
  /* Where a raw command runs unless the window says otherwise. Supplied by the
   * server rather than assumed, since the browser cannot know it. */
  const [home, setHome] = useState("");
  const [windows, setWindows] = useState([]);
  const [layout, setLayout] = useState(TILE);
  const [screen, setScreen] = useState(CANVAS);
  /* The schedule screen's own reading, and when it was taken.
   *
   * Kept beside the screen rather than as a window: it is not draggable, not
   * pinnable and not closeable, so giving it a window id would put it in every
   * loop that iterates windows for reasons none of which apply to it. */
  const [plan, setPlan] = useState(null);
  const [planAt, setPlanAt] = useState(0);
  /* Where each project's rows come from — the declaration, not the data.
   * Fetched beside the reading rather than folded into it, because it is true
   * whether or not the command has run and its envelope is a bare list that
   * stays one. See [[schedule]] round 5. */
  const [planSources, setPlanSources] = useState([]);
  /* Which project, which view, which span. One object so a new control is one
   * key rather than a fourth `useState` and a fourth setter to forget. */
  const [planUi, setPlanUi] = useState({ mode: "table", projects: [], span: "24h" });
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const [floating, setFloating] = useState(false);
  const [focus, setFocus] = useState(null);
  const [session, setSession] = useState(null);
  const [down, setDown] = useState(false);
  /* The act awaiting a yes. Null when nothing is being asked. See [[canvas]]
   * round 11 — this is the only thing on the surface that reads `acts` to stop
   * an action rather than to label one. */
  const [pending, setPending] = useState(null);
  /* What the operator declared about output. Null until the bench is opened
   * for the first time — the canvas never needs it, since the palette *runs*
   * saved tools and only the bench *authors* one. */
  const [vocab, setVocab] = useState(null);
  const now = useNow();

  const zTop = useRef(1);
  const canvas = useRef(null);
  /* The stream handler is installed once and must not close over a stale
   * `windows`. A ref is the escape hatch: the effect reads through it. */
  const windowsRef = useRef(windows);
  windowsRef.current = windows;
  const sessionRef = useRef(null);
  /* Read by handlers that must not fire behind an open dialog — the palette's
   * Enter above all. A ref rather than a closure over `pending`, for the same
   * reason `windowsRef` exists: those handlers are registered once. */
  const pendingRef = useRef(null);
  pendingRef.current = pending;
  /* The catalog, for handlers registered once — the tag vocabulary is read out
   * of it and must not be a stale closure. Same escape hatch as `windowsRef`. */
  const commandsRef = useRef([]);
  commandsRef.current = commands;
  /* Same escape hatch as `windowsRef`, and needed for the same reason: the
   * stream handler is installed once, and a follow trial's frames arrive on it
   * long after this closure was made. */
  const draftRef = useRef(draft);
  draftRef.current = draft;

  /* Re-read after any write. Three callers had this inline and a fourth was
   * about to; the catalog is derived per request, so refreshing it is the only
   * way the surface learns what it just changed. */
  const refreshCatalog = () =>
    api.catalog().then((c) => {
      setCommands(c.commands);
      setGroups(c.groups || []);
    });

  /* Re-fetched every time the bench opens, not once at boot. The rulesets
   * and formats are read at use rather than cached server-side, precisely so
   * that editing `formats.toml` under a running surface is the REPL; a
   * fetch-once here would put that back and the operator would be looking at
   * a list from an hour ago while the stream tinted by the new one. */
  useEffect(() => {
    if (screen !== WORKBENCH) return;
    api.vocabulary().then(setVocab).catch(() => {});
  }, [screen]);

  useEffect(() => {
    api.catalog().then((body) => {
      setCommands(body.commands);
      setGroups(body.groups || []);
      setIntervals(body.intervals);
      setHome(body.home || "");
      /* Only into a draft nobody has touched. Overwriting a typed `--cwd`
       * because the catalog answered late would be the surface arguing with
       * the operator over a field they had already filled in. */
      setDraft((d) => (d.cwd ? d : { ...d, cwd: body.home || "" }));
    });
  }, []);

  useEffect(() => {
    const stop = api.stream(
      (frame) => {
        if (frame.type === "hello") {
          /* A second hello is a reconnect, not a launch — [[canvas]] round 10.
           * The distinction has to be drawn here because everything below is
           * *recovery*, and doing it on the first hello would announce a gap
           * that never happened. */
          const resumed = sessionRef.current !== null && sessionRef.current !== frame.session;
          sessionRef.current = frame.session;
          setSession(frame.session);
          setDown(false);
          /* A resident window is cleared and resumed from the tail, and says so.
           *
           * A fresh cursor backfills on open, so a silent re-follow would
           * re-push lines the window is already showing; keeping the old lines
           * and appending the backfill duplicates them, and dropping the
           * backfill hides that anything was missed. Both are the failure this
           * round exists to fix, arriving through the fix. So: clear, resume,
           * and mark the seam in the stream's own voice — the channel the
           * cursor already uses to announce a rotation, for the same reason.
           *
           * `stderr` as well as `voice`, because that pair is what `markedLine`
           * reads to draw the cursor's own announcements rather than the file's. */
          if (resumed) {
            setWindows((all) =>
              all.map((w) =>
                w.resident
                  ? {
                      ...w,
                      streamLines: [
                        {
                          text: "— session dropped; reconnected and resumed from the tail —",
                          stderr: true,
                          voice: true,
                        },
                      ],
                      chrome: null,
                    }
                  : w
              )
            );
          }
          /* Re-register everything. A reconnect after a dropped stream would
           * otherwise leave every pinned window silently unwatched — still
           * saying PINNED, never refreshing again. */
          for (const win of windowsRef.current) {
            if (win.pinned) api.watch(frame.session, win.id, argvOf(win), win.interval);
            /* A follow window's child died with the old session; a reconnect
             * spawns a fresh one, which is the honest reading of "nothing
             * survives the last window".
             *
             * An accruing window is deliberately *not* respawned. Its child
             * died with the session too, but re-running it would be a second
             * write nobody asked for — the ⟳ is the operator's click, and a
             * reconnect is not one. It is left holding what it had. */
            if (win.resident) api.follow(frame.session, win.id, argvOf(win));
          }
          /* The bench's own stream died with the old session too. Re-opened
           * from the draft rather than remembered separately — the draft is
           * what the trial was made of. */
          const d = draftRef.current;
          if (d.contract === RESIDENT && d.lines.length) {
            const argv = compose(d);
            if (argv) api.follow(frame.session, BENCH_WINDOW, argv);
          }
        } else if (frame.type === "reload") {
          applyReload(frame.files);
        } else if (frame.type === "stream" && frame.window === BENCH_WINDOW) {
          /* A follow trial. The bench is a pseudo-window on the session, so its
           * stream arrives exactly like every other one and needs no second
           * transport — only a second place to land. */
          setDraft((d) => {
            const limit = (frame.chrome && frame.chrome.ring_limit) || 200;
            return {
              ...d,
              lines: [...d.lines, ...frame.lines].slice(-limit),
              chrome: frame.chrome,
              running: false,
            };
          });
        } else if (frame.type === "stream") {
          setWindows((all) =>
            all.map((w) => {
              if (w.id !== frame.window) return w;
              const limit = (frame.chrome && frame.chrome.ring_limit) || 200;
              const lines = [...(w.streamLines || []), ...frame.lines].slice(-limit);
              /* `result` rides only the frame that announces an accruing
               * window's exit, shaped exactly like `/api/run`'s payload so the
               * page has one way to read a verdict. Until it arrives the
               * window is still working — which is not true of a follow, where
               * every frame means the same thing. */
              const done = Boolean(frame.result);
              return {
                ...w,
                streamLines: lines,
                chrome: frame.chrome,
                running: w.resident ? false : !done && w.running,
                result: done ? frame.result : w.result,
                ranAt: done ? Date.now() : w.ranAt,
              };
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
      /* Three states, not two. `retry` is a blip the surface is working on;
       * `stale` is a launch that ended, which no amount of retrying fixes and
       * which the operator has to act on. Collapsing them would leave the
       * second looking like the first forever — the same failure one level up.
       * See [[canvas]] round 10. */
      (info) => setDown(info && info.stale ? "stale" : "retry")
    );
    return stop;
  }, []);

  useEffect(() => {
    function onKey(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setFloating((f) => !f);
      } else if (event.key === "Escape") {
        /* The dialog first: Escape is the cheap way out of a confirmation, and
         * making the cancel cheap is what keeps the guard from being routed
         * around. See [[canvas]] round 11. */
        setPending(null);
        setFloating(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  /* The one gate in front of the one funnel. See [[canvas]] round 11.
   *
   * Every launch converges on `execute` — a palette entry, a click in the
   * tools rail, a window's ⟳, `chdir`'s re-run — so asking here is exhaustive
   * by construction rather than by remembering the call sites. It takes the
   * *window object* rather than an id because `open()` has not landed its
   * window in `windowsRef` yet, and `acts` is the whole question.
   *
   * Not a security control: a page past the guard POSTs /api/run and never
   * sees this. It stops the operator's own stray Enter, which is what was
   * asked for. */
  function launch(win, argv) {
    if (!win.acts) {
      execute(win.id, argv, win.resident);
      return;
    }
    const under = [];
    if (win.expansion) under.push(`saved as ${["sb", ...argv].join(" ")}`);
    if (win.cwd) under.push(`in ${win.cwd}`);
    setPending({
      head: "this command acts",
      note: "It changes something. Nothing has run yet.",
      body: ["sb", ...(win.expansion || argv)].join(" "),
      under,
      confirm: "run it",
      go: () => execute(win.id, argv, win.resident),
    });
  }

  function execute(id, argv, resident = null) {
    /* `resident` is passed explicitly from open(), because the state update
     * that adds the window has not landed in windowsRef yet on the very
     * first execute. Everywhere else the window is looked up. */
    const win = windowsRef.current.find((w) => w.id === id);
    if (resident === null) resident = Boolean(win && win.resident);
    if (resident) {
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
    /* An unpinned run or read accrues: its lines arrive while it works and its
     * exit is the verdict. A *pinned* one does not — a pinned window is a
     * watcher, the server re-runs it on a cadence and delivers whole
     * envelopes, which is also the one place the timeout ceiling belongs.
     *
     * Whether this particular argv can accrue is the server's call, not a rule
     * copied here: `resolve_run` refuses anything it cannot fully account for,
     * because accrual spawns the foreign command directly and a dropped
     * `--save` would not save. A refusal falls back to `run`. */
    if (sessionRef.current && !win?.pinned) {
      setWindows((all) =>
        all.map((w) =>
          w.id === id ? { ...w, streamLines: [], chrome: null, result: null, running: true } : w
        )
      );
      api
        .accrue(sessionRef.current, id, argv)
        .then((answer) => {
          if (answer && answer.accruing) {
            patch(id, () => ({ stream: true }));
            return;
          }
          patch(id, () => ({ stream: false }));
          return snapshotRun(id, argv);
        })
        .catch(() => snapshotRun(id, argv));
      return;
    }
    snapshotRun(id, argv);
  }

  function snapshotRun(id, argv) {
    setWindows((all) => all.map((w) => (w.id === id ? { ...w, running: true } : w)));
    return api
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
    /* One question at a time. Without this a second stray Enter opens a window
     * *behind* the dialog, answering for the first. See [[canvas]] round 11. */
    if (pendingRef.current) return;
    /* Anything typed past the command name is argv. `run -- jam pr list --json`
     * has to reach the server whole; splitting it here would be a second
     * parser, and sky.boss's own is the one that decides what an argv means. */
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
      /* Two facts, not one. `resident` is the operator's assertion that this
       * is not expected to exit — inherited from the catalog, so a saved
       * keyword wrapping follow is one too. `stream` is only whether the body
       * is a list of lines, which a `run` or `read` becomes the moment the
       * server agrees to accrue it. They coincided until [[follow]] round 4
       * and reading one as the other is why an act could not be watched. */
      resident: Boolean(entry.resident),
      stream: Boolean(entry.resident),
      streamLines: [],
      chrome: null,
      /* What a saved name actually expands to, kept so the confirmation can
       * show the command rather than the nickname. The rail draws a short name
       * and `sb tools jam-release-train` is not what happens — see [[canvas]]
       * round 11. Null for anything that is already its own expansion. */
      expansion: entry.expansion || null,
      raw: Boolean(entry.raw),
      rawWords: entry.rawWords || null,
      cwd: entry.cwd || null,
      chips: (entry.options || [])
        .filter((o) => o.is_flag)
        .map((o) => ({ flag: o.flag, help: o.help, on: false })),
      /* Inherited from the tool, which is what makes a chip in the title bar
       * mean something. Round 8 gave tags a home in `tools.toml`; before it
       * these were five hardcoded words with no source. A tag added by hand
       * still dies with the window — a window is transient by design, and
       * *nothing survives the last window* is the rule that says so. */
      tags: [...(entry.tags || [])],
      /* A tool may declare the cadence it opens on. Pinning it here rather
       * than leaving it to a click is the whole point of saving it: the
       * window you wanted is the window you get. Only a read can carry one —
       * `refresh` is refused at load on a tool that acts. */
      /* Per window, not per surface: a table wants the sideways scroll it
       * was given and a prose log wants the wrap, and both can be open on one
       * canvas.
       *
       * **A follow opens wrapped and everything else does not** ([[wrap]]
       * round 2). A follow is a log by contract, which is the case wrapping
       * was built for and the one the operator tested. `read` is *verbatim by
       * contract* — sky.boss will not infer whether that output has structure,
       * which is why it refuses to make columns out of it, and defaulting it
       * to wrap would be the same inference arriving through the rendering.
       * The palette's raw-command fallback makes this concrete rather than
       * theoretical: anything typed that is not a sky.boss command opens as
       * `sb read`, so `git log --graph` and `docker ps` are the common case,
       * and reflowing either destroys the only structure they have.
       *
       * `resident` rather than `stream` for the same reason the two exist
       * separately: `stream` is not true yet for a run or a read at the moment
       * a window opens, and it becomes true later without meaning the output
       * turned into prose. */
      wrap: Boolean(entry.resident),
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
    launch(win, argvOf(win));
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

  /* Re-shape a window's table when the operator has chosen columns, and again
   * every time the payload underneath is replaced.
   *
   * **The difference between a window and the bench.** On the bench a shaping
   * is a one-shot against a frozen trial payload; here the payload is replaced
   * on every watcher tick, every manual refresh and every re-run. A choice that
   * did not survive that would be undone by a 30-second watcher while the
   * operator watched it happen — worse than offering no control. So the choice
   * lives on the *window* and is re-applied to each new result, keyed on the
   * result object rather than on a tick count.
   *
   * Runs nothing: `/api/shape` is a pure function of rows the page already
   * holds. See [[table-views]] round 6.
   */
  useEffect(() => {
    for (const win of windows) {
      const result = win.result;
      const envelope = result && result.envelope;
      const view = envelope && envelope.view;
      /* **Not `if (!view) continue`.** Choosing *everything* removes the view,
       * which is what `--no-shape` means — and a guard that skipped a window
       * without one meant the effect could never put the shaping back. Clear
       * became a no-op, and every later chip read its columns off a view that
       * was not there. Once a window has been shaped it stays shapeable, and
       * `viewOffered` is the record of that. */
      const shapeable = (view && view.columns) || (win.viewOffered || []).length > 0;
      if (win.stream || !envelope || !shapeable) continue;
      if (win.viewFor === result) continue;

      const cols = win.viewCols || [];
      /* The authored view, remembered the first time it arrives.
       *
       * Two things need it. The shaping route has to be *told* the view is
       * authored, and after the first pass `envelope.view` is whatever came
       * back rather than what the command sent. And clearing a choice has to
       * restore the authored columns — inference cannot rebuild them, so
       * without this, unticking everything would silently widen the table
       * from five columns to seven and look like it had worked. */
      const authored = win.viewAuthored || (view && view.authored ? view : null);
      /* The rows path is remembered too, for the same reason: it lives on the
       * view, and the view is a thing the operator can remove. */
      const rowsPath = (view && view.rows) || win.viewRows;
      api
        .shape(envelope.data, { cols, rows: rowsPath, view: authored })
        .then((body) =>
          patch(win.id, (w) => {
            /* `everything` needs no view at all: with none, the renderer
             * derives its own columns from the rows in the order found, which
             * is exactly what `--no-shape` means. The call still happens
             * because `offered` — the checklist — comes from a shaping with
             * *nothing* asked of it, and a checklist built from the filtered
             * view would lose a column the moment you unticked it. */
            /* Three states, one of which used to be "leave it alone" and was
             * wrong. Clearing after *everything* has to put the shaping's own
             * view back, and there is nothing to put back from — choosing
             * everything destroyed it. `body.view` is a shaping of this same
             * payload with whatever is currently asked, which for no choice is
             * the shaping's own answer. So the no-choice branch installs it
             * rather than preserving whatever the last choice left behind. */
            const next = {
              ...w.result,
              envelope: {
                ...w.result.envelope,
                view: w.viewEvery ? null : body.view,
              },
            };
            /* Stamped with the object this loop is about to *install*, not the
             * one it read. Stamping the old one leaves `viewFor !== result` on
             * the very next render, so the effect re-fires against its own
             * output — a shaping loop that hits the server forever and looks
             * like nothing at all, because the view it computes is identical
             * every time. */
            return {
              result: next,
              viewAuthored: authored,
              viewOffered: body.offered || [],
              viewRows: (body.view && body.view.rows) || w.viewRows,
              /* The banner is about *this* shaping, not the one the run came
               * back with. Left on the envelope's own warnings it kept saying
               * "2 columns hidden: head" with `head` drawn above it — a
               * warning that is wrong is worse than no warning. */
              viewWarnings: w.viewEvery ? [] : body.warnings || [],
              viewFor: next,
            };
          })
        )
        .catch(() => patch(win.id, (w) => ({ viewFor: w.result })));
    }
  }, [windows]);

  /* Re-read the schedule. One funnel, like everything else that runs: this is
   * `/api/run` with the same argv the palette would send, not a private route.
   *
   * **Read on entering the screen, and on demand — never on a browser timer.**
   * A hidden page has its timers clamped to about one fire a minute, so a
   * cadence here would silently become a different cadence exactly when you
   * stopped being able to see it. The screen states its own age instead, which
   * is honest at any rate including none. See [[canvas]] on the refresh clock. */
  const readPlan = () => {
    /* Two calls, deliberately not chained: the provenance is introspection and
     * cannot fail because a foreign CLI did, so a schedule that comes back
     * partial still gets its sources drawn beside it. */
    api
      .projects()
      .then((body) => setPlanSources(body.projects || []))
      .catch(() => setPlanSources([]));
    api
      .run(["schedule"])
      .then((body) => {
        setPlan(body);
        setPlanAt(Date.now());
      })
      .catch((error) => {
        setPlan({ error: String(error) });
        setPlanAt(Date.now());
      });
  };

  useEffect(() => {
    if (screen !== SCHEDULE) return;
    readPlan();
  }, [screen]);

  const actions = {
    focus: (id) => {
      setFocus(id);
      if (layout === FLOAT) patch(id, () => ({ z: ++zTop.current }));
    },
    /* Fold the strip. Most windows are looked at, not configured. */
    viewToggle: (id) => patch(id, (w) => ({ viewOpen: !w.viewOpen })),

    /* Tick or untick one column. Naming any column puts `--cols` in force, and
     * from then on every column drawn is one the operator chose — which is why
     * the first tick has to seed from what is currently *drawn* rather than
     * from nothing, or ticking one column would hide the other nine. */
    viewCol: (id, key) =>
      patch(id, (w) => {
        const view = w.result && w.result.envelope && w.result.envelope.view;
        const current =
          (w.viewCols || []).length > 0
            ? w.viewCols
            : [
                ...((view && view.columns) || []).map((c) => c.key),
                ...((view && view.details) || []).map((c) => c.key),
              ];
        const next = current.includes(key)
          ? current.filter((c) => c !== key)
          : (w.viewOffered || []).filter((c) => c === key || current.includes(c));
        return { viewCols: next, viewEvery: false, viewFor: null };
      }),

    /* Every column, in the order found. Exclusive with a column list, because
     * the two say different things about the same question. */
    viewEvery: (id) =>
      patch(id, (w) => ({ viewEvery: !w.viewEvery, viewCols: [], viewFor: null })),

    /* Back to the shaping's own choices. There has to be a way back: with
     * `--cols` in force the shaping returns only what was named, so without
     * this the operator's first tick would be one-way. */
    viewClear: (id) => patch(id, () => ({ viewCols: [], viewEvery: false, viewFor: null })),

    close: (id) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (sessionRef.current) {
        api.unwatch(sessionRef.current, id);
        /* Closing the window SIGTERMs its child — a stream dies with its
         * window, which is what keeps a follow a stream and not a service
         * manager, and an accruing act a run and not a daemon. */
        if (win && win.resident) api.unfollow(sessionRef.current, id);
        else if (win && win.stream) api.unaccrue(sessionRef.current, id);
      }
      setWindows((all) => all.filter((w) => w.id !== id));
    },
    refresh: (id) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (win) launch(win, argvOf(win));
    },
    /* Re-runs at once. A directory that changed but left the old output on
     * screen is a window claiming to show something it is not. */
    chdir: (id, cwd) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (!win || !win.raw || !cwd || cwd === win.cwd) return;
      const next = { ...win, cwd };
      patch(id, () => ({ cwd }));
      reWatch(next);
      launch(next, argvOf(next));
    },
    pin: (id) => {
      const win = windowsRef.current.find((w) => w.id === id);
      if (!win || win.acts) return;
      const next = { ...win, pinned: !win.pinned, interval: win.pinned ? 0 : 30 };
      patch(id, () => ({ pinned: next.pinned, interval: next.interval }));
      reWatch(next);
    },
    /* Nothing to re-run and nothing to re-watch: wrapping is a decision about
     * the box the lines are drawn in, and the lines are unchanged. That is the
     * whole reason it can be a per-window toggle rather than a flag on the
     * argv — see [[wrap]]. */
    wrap: (id) => patch(id, (win) => ({ wrap: !win.wrap })),
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
    /* Add a tag by typing it. Until [[tools]] round 8 this cycled a hardcoded
     * pool of five words and did nothing once they were used — there was no
     * vocabulary anywhere for it to draw on, because a tool could not carry a
     * tag. Now it can, so the suggestion list is every tag any tool declares.
     *
     * `prompt()` rather than an inline editor, and the trade is deliberate: a
     * browser prompt blocks every later event, which `sb.css` already warns
     * about for the `cwd` field, so it is wrong for anything the surface must
     * stay live through. A title-bar tag is a one-shot on a window the operator
     * is looking at, and building an inline chip editor is a larger change than
     * this round is. Left as the cheap version on purpose, noted rather than
     * hidden. */
    tag: (id) => {
      const known = tagPool(commandsRef.current);
      const hint = known.length ? ` (${known.join(", ")})` : "";
      const typed = window.prompt(`tag this window${hint}`, "");
      const tag = (typed || "").trim().toLowerCase();
      if (!tag) return;
      patch(id, (w) => (w.tags.includes(tag) ? {} : { tags: [...w.tags, tag] }));
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

  /* ------------------------------------------------------------ the bench */

  /* Re-draw what is already in hand. Runs nothing: `/api/shape` is a pure
   * function of the payload the trial run returned, so a chip click costs one
   * loopback round trip rather than another execution of a foreign command —
   * and every chip compares against the same rows, which is the comparison the
   * checklist exists to let you make. */
  function reshape(next) {
    const data = next.result && next.result.envelope && next.result.envelope.data;
    if (data === undefined) return;
    api
      .shape(data, { cols: next.cols, rows: next.rows || undefined })
      .then((body) =>
        setDraft((d) => ({
          ...d,
          hasShaped: true,
          shaped: body.view,
          shapeWarnings: body.warnings || [],
          /* Only ever from a shaping with nothing asked of it — the server
           * computes it that way, so this is safe to take on every reply and
           * the checklist never shrinks to what is currently ticked. */
          offered: body.offered || [],
        }))
      )
      .catch(() => {
        /* A failed re-shape leaves the last good drawing alone. The rows have
         * not changed and neither has the answer; only the presentation
         * request went unanswered. */
      });
  }

  /* Ask the server what it can say without running: the act's checks, whether
   * the name is free, and the block `run` cannot save by example. Fired on
   * every change to the argv or the name, which is cheap because it runs
   * nothing — the same reason `/api/catalog` is derived per request. */
  function preflight(next) {
    const argv = compose(next);
    if (!argv) {
      setDraft((d) => ({ ...d, checks: [], nameProblem: null, block: null }));
      return;
    }
    api
      .preflight(argv, { name: next.save })
      .then((body) =>
        setDraft((d) => ({
          ...d,
          checks: body.checks || [],
          nameProblem: body.name && !body.name.ok ? body.name.reason : null,
          replaces: (body.name && body.name.replaces) || null,
          block: body.block || null,
        }))
      )
      .catch(() => {});
  }

  /* One effect owns the preflight, rather than each setter firing its own.
   *
   * Firing from the setters raced: `setCwd` then `setArgv` in the same tick
   * both read `draftRef.current`, which the first `setDraft` has not updated
   * yet, so the second request carried the *old* cwd and the checks described
   * a line nobody had typed. An effect keyed on the fields that matter sees
   * the merged state by construction. Measured — the pane reported `--cwd
   * /home/jeston` while the block beside it said `/tmp`. */
  useEffect(() => {
    preflight(draftRef.current);
  }, [draft.contract, draft.cwd, draft.argv, draft.save, draft.rows, draft.from, draft.due, draft.highlight, draft.cols]);

  const benchActions = {
    /* **Swaps the draft rather than clearing it.** The `--cwd` and the argv are
     * what you have been getting right; the contract is what you are still
     * deciding, and losing the line every time you change your mind about which
     * renderer it goes through is the bench being an obstacle.
     *
     * The *result* does not carry over, because it belongs to the contract that
     * produced it: a shaped table left standing under `read` would be claiming a
     * shape that contract cannot return. */
    pick: (contract) => {
      const before = draftRef.current;
      if (before.contract === RESIDENT && sessionRef.current) {
        api.unfollow(sessionRef.current, BENCH_WINDOW);
      }
      setDraft((d) => ({
        ...d,
        contract,
        result: null,
        chrome: null,
        lines: [],
        running: false,
        error: null,
        /* The view controls go with the result, for the same reason it does:
         * they describe a shaping of rows this contract may not even return.
         * `--cols` under `read` is a control for a table that cannot exist. */
        cols: [],
        offered: [],
        hasShaped: false,
        shaped: null,
        shapeWarnings: [],
        rows: "",
        /* The name goes with the result too. It named a tool wrapping a
         * contract that is no longer selected, and `--save` on `run` is not a
         * flag at all — it saves by example, and the example ran. */
        noShape: false,
        drop: "",
        save: "",
        describe: "",
        group: "",
        nameProblem: null,
        block: null,
        saved: null,
      }));

    },
    setCwd: (cwd) => setDraft((d) => ({ ...d, cwd })),
    setEnv: (env) => setDraft((d) => ({ ...d, env })),
    setArgv: (argv) => setDraft((d) => ({ ...d, argv })),

    /* The name. Judged by `cli.tools.name_problem` rather than here — a page
     * holding a copy of the rule would disagree the day the rule changed. */
    setSave: (save) => setDraft((d) => ({ ...d, save, saved: null })),
    /* What the tool is *for*. `--save` could never ask — it saves by example
     * and an example is an argv — so every tool saved before [[tools]] round 4
     * has no description and a list of them is a list of argvs to decipher. */
    setDescribe: (describe) => setDraft((d) => ({ ...d, describe })),
    /* Where the rail sorts it. Declared, never inferred — the bench does not
     * read a prefix off the name and guess, for the reason the contract is not
     * read off a trailing `--json`. Blank is ungrouped and writes no line at
     * all, so clearing it here removes the field from the block. */
    setGroup: (group) => setDraft((d) => ({ ...d, group })),
    setTags: (tags) => setDraft((d) => ({ ...d, tags })),

    /* Open an existing tool in the bench, decomposed back into the fields that
     * compose it. The inverse of `compose`, and deliberately partial: it reads
     * the flags the bench itself can draw and leaves anything else in the argv
     * text, where it is visible and editable rather than silently dropped on
     * the next save. See [[tools]] round 4. */
    edit: (tool) => {
      /* `expansion`, not `argv`: the latter is the path you type to run it —
       * `tools drainer` — which is no answer at all when the question is what
       * the tool *is*. See [[tools]] round 4. */
      const argv = [...(tool.expansion || [])];
      const contract = argv[0] || null;
      const rest = argv.slice(1);
      const fields = { cwd: "", env: "", highlight: "", from: "", due: "" };
      let i = 0;
      for (; i < rest.length; i++) {
        if (rest[i] === "--") { i += 1; break; }
        if (rest[i] === "--cwd" && rest[i + 1] !== undefined) { fields.cwd = rest[++i]; continue; }
        if (rest[i] === "--env" && rest[i + 1] !== undefined) {
          fields.env = (fields.env ? fields.env + " " : "") + rest[++i];
          continue;
        }
        /* The view flags, lifted out of the argv into the controls that own
         * them. Without this the panel said `none` while the line beside it
         * said `--highlight jam` — the surface disagreeing with itself about
         * one flag, and the exact tool the operator actually saved, since
         * `--save` writes the flag into the argv rather than into a field.
         * `compose` puts each back, so the round trip is unchanged. A flag
         * after the argv still stays in the argv, as it always has. */
        if (VIEW_FLAGS[rest[i]] && rest[i + 1] !== undefined) {
          fields[VIEW_FLAGS[rest[i]]] = rest[++i];
          continue;
        }
        break;
      }
      setScreen(WORKBENCH);
      setDraft(() => ({
        ...EMPTY_DRAFT,
        contract,
        cwd: fields.cwd,
        env: fields.env,
        argv: rest.slice(i).join(" "),
        save: shortOf(tool),
        was: shortOf(tool),
        describe: tool.summary || "",
        group: tool.group || "",
        tags: (tool.tags || []).join(" "),
        /* Seeded from the *field*, because the argv of a tool declaring
         * `highlight = "jam"` carries no `--highlight` to decompose — and
         * without this the bench opens with the control blank, composes a line
         * without it, and the save drops the ruleset. Measured in [[tools]]
         * round 6: the tint just stopped, with nothing to read anywhere. It
         * lands back in the argv rather than the field, which is a change of
         * representation the operator can see in the line the bench shows
         * before it saves. */
        /* The argv wins when it carries one, because that is what will run;
         * the declared field is the fallback for a tool that has no
         * `--highlight` to decompose. */
        highlight: fields.highlight || tool.highlight || "",
        from: fields.from,
        due: fields.due,
      }));
    },

    /* Delete, with one confirmation and the backup path in the answer. A
     * delete is not undoable from here — the backup is the undo.
     *
     * On the surface's own dialog as of [[canvas]] round 13, having been
     * `window.confirm()` since round 4 of [[tools]]. The reason that gave —
     * "this surface has no modal and inventing one to ask a yes/no question is
     * the larger change" — expired the moment round 11 built one. A browser
     * confirm also blocks every later event, which `sb.css` already warns about
     * for the `cwd` field, and it cannot show the argv you are about to lose. */
    forget: (tool) => {
      const name = shortOf(tool);
      setPending({
        head: "this deletes a saved command",
        note: "tools.toml is copied into $SB_HOME/backups/ first — the backup is the undo.",
        body: ["sb", ...(tool.expansion || tool.argv || [])].join(" "),
        under: [`declared as ${name}`],
        confirm: "delete it",
        /* `benchActions`, not `actions` — `forget` lives in the *second* of the
         * two action objects, and the first one exists, so writing `actions`
         * here resolved to a real object with no such method and failed only at
         * click time. See [[canvas]] round 13. */
        go: () => benchActions.dropNow(name),
      });
    },

    /* The half `forget` used to do inline, split out so the confirmation can
     * hand it to the dialog as a thunk. See [[canvas]] round 13. */
    dropNow: (name) => {
      api
        .deleteTool(name)
        .then((result) => {
          if (result.error) {
            window.alert(`Could not delete ${name}: ${result.error}`);
            return;
          }
          refreshCatalog();
        })
        .catch((error) => window.alert(`Could not delete ${name}: ${error}`));
    },

    /* Make a group. It has nothing in it, which is the whole reason a group
     * can be declared at all — round 5's group was a label on a command, so
     * an empty one had nowhere to exist. See [[tools]] round 6. */
    addGroup: (name) => {
      api
        .writeGroup({ name })
        .then((result) => {
          if (result.error) {
            window.alert(`Could not add "${name}": ${result.error}`);
            return;
          }
          refreshCatalog();
        })
        .catch((error) => window.alert(`Could not add "${name}": ${error}`));
    },

    /* Unmake one. The rail only offers this on a group with nothing in it, and
     * the server refuses a non-empty one regardless — a surface that declines
     * to draw a button has not refused anything. Deleting a group never
     * deletes a command; the refusal names what is still in it. */
    dropGroup: (name) => {
      if (!window.confirm(`Delete the group "${name}"? Its file is backed up first.`)) return;
      api
        .deleteGroup(name)
        .then((result) => {
          if (result.error) {
            window.alert(`Could not delete "${name}": ${result.error}`);
            return;
          }
          refreshCatalog();
        })
        .catch((error) => window.alert(`Could not delete "${name}": ${error}`));
    },

    /* Move a command into a group, or out of every group by dropping it in the
     * ungrouped bucket. A regroup, not a save: it changes the one line, so a
     * field the rail cannot see is not a field the rail can lose. */
    move: (name, group) => {
      api
        .regroupTool(name, group)
        .then((result) => {
          if (result.error) {
            window.alert(`Could not move ${name}: ${result.error}`);
            return;
          }
          refreshCatalog();
        })
        .catch((error) => window.alert(`Could not move ${name}: ${error}`));
    },

    /* The act's one button. Down `/api/run`, which is the route that runs
     * things — `/api/trial` refuses an act on purpose and asking it twice
     * would not change its mind. Labelled for what it does: there is no dry
     * run to fall back to, and the pane says so beside the button. */
    runForReal: () => {
      const d = draftRef.current;
      const argv = compose(d);
      if (!argv || d.running) return;
      setDraft((prev) => ({ ...prev, running: true, error: null, result: null, chrome: null }));
      api
        .run(argv)
        .then((result) =>
          setDraft((prev) => ({
            ...prev,
            running: false,
            result,
            chrome: result.chrome || null,
          }))
        )
        .catch((error) =>
          setDraft((prev) => ({ ...prev, running: false, error: String(error) }))
        );
    },

    /* **A second run, because it is one.** Save does not confirm the trial
     * run's output; it repeats the work with `--save` in the line, and
     * `--save` writes before that run produces anything. Down `/api/run`
     * rather than `/api/trial` for the same reason — this is not a trial, and
     * a route called trial that writes would be lying about itself.
     *
     * Since [[tools]] round 4 this writes through `/api/tools` rather than by
     * running the argv again with `--save` in it. Two things change and both
     * are the point: **saving no longer runs the command** — it was a second
     * execution of a foreign tool to record a line of text, which for an
     * observe was merely wasteful and was never available for a `run` at all —
     * and a name that already exists is now a *replace* rather than a refusal,
     * because `--save` saves by example and editing is not an example. */
    save: () => {
      const d = draftRef.current;
      if (!d.save || d.saving) return;
      const argv = compose({ ...d, saving: true });
      if (!argv) return;
      setDraft((prev) => ({ ...prev, saving: true, saved: null }));
      api
        .writeTool({
          name: d.save,
          argv,
          refresh: 0,
          description: d.describe || "",
          group: d.group || "",
          /* Sent only when the bench was opened on an existing tool. The
           * server removes the old block after the new one lands, so a
           * changed name renames instead of copying. */
          was: d.was || "",
          /* Split here rather than in the input, so what the operator is
           * typing stays exactly what they typed until they save. */
          tags: (d.tags || "").split(/\s+/).filter(Boolean),
        })
        .then((result) => {
          const ok = !result.error;
          setDraft((prev) => ({
            ...prev,
            saving: false,
            /* `saved` is its own envelope key, beside `data` rather than
             * inside it — omitted entirely when a command saved nothing, the
             * same rule `view` follows. `runs` is the half worth showing: it
             * is the operator's one chance to notice the saved line is not the
             * line they meant. */
            saved: {
              ok,
              action: result.renamed_from ? `renamed from ${result.renamed_from}` : result.action || null,
              backup: result.backup || null,
              runs: result.runs || null,
              error: ok ? null : result.error || "save failed",
            },
            /* The tool is now called this. Without the update a second save
             * would send the *old* `was` and delete a block that is no longer
             * there — or worse, one the operator has since recreated under
             * that name. See [[workbench]] round 5. */
            was: ok ? d.save : prev.was,
          }));
          /* Two things go stale the instant a save lands: the tools rail,
           * and the name — which is now taken, and taken because the file says
           * so. Both are re-asked rather than patched here, because both
           * answers are the server's. Without the second, the button stayed
           * enabled on a name that would now be refused. */
          if (ok) {
            refreshCatalog();
            preflight(draftRef.current);
          }
        })
        .catch((error) =>
          setDraft((prev) => ({
            ...prev,
            saving: false,
            saved: { ok: false, error: String(error) },
          }))
        );
    },

    /* `--from`, `--due` and `--highlight` change how the tool is *read* or how
     * a stream is *opened*, so they only compose into the argv and take effect
     * on the next trial run. Nothing is re-shaped here, and the panel says so
     * rather than leaving it to be discovered by clicking. */
    set: (key, value) => setDraft((d) => ({ ...d, [key]: value })),

    /* A chip. The chosen set is rebuilt in the checklist's own order rather
     * than in click order, so the same set of columns produces the same table
     * however you arrived at it — `--cols` sets column order, and making that
     * depend on the sequence of clicks would be a table that quietly differs
     * from an identical-looking one. */
    toggle: (key) => {
      const d = draftRef.current;
      const cols = d.cols.includes(key)
        ? d.cols.filter((c) => c !== key)
        : d.offered.filter((c) => c === key || d.cols.includes(c));
      setDraft((prev) => ({ ...prev, cols }));
      reshape({ ...d, cols });
    },

    setRows: (rows) => {
      const d = draftRef.current;
      setDraft((prev) => ({ ...prev, rows }));
      reshape({ ...d, rows });
    },
    trial: () => {
      const current = draftRef.current;
      const argv = compose(current);
      if (!argv || current.running) return;
      setDraft((d) => ({
        ...d,
        running: true,
        error: null,
        result: null,
        chrome: null,
        lines: [],
        hasShaped: false,
        shaped: null,
        shapeWarnings: [],
      }));

      /* A stream is held open, not run to completion. It goes down the same
       * `/api/follow` every window's stream does — `/api/trial` refuses a
       * resident argv rather than sitting on it until the timeout. */
      if (current.contract === RESIDENT) {
        if (!sessionRef.current) {
          setDraft((d) => ({
            ...d,
            running: false,
            error: "stream down — a follow trial needs the session",
          }));
          return;
        }
        api
          .follow(sessionRef.current, BENCH_WINDOW, argv)
          .then((body) => {
            if (body && body.error) {
              setDraft((d) => ({ ...d, running: false, error: body.error }));
            }
          })
          .catch((error) =>
            setDraft((d) => ({ ...d, running: false, error: String(error) }))
          );
        return;
      }

      /* A refusal comes back as a body with an `error` in it, and that body is
       * handed to the same renderer a result is. `Body` already draws
       * `result.error`, so the reason the server gave is what the pane shows —
       * rather than a status code translated into a sentence here. */
      api
        .trial(argv)
        .then((result) => {
          setDraft((d) => ({
            ...d,
            running: false,
            result,
            chrome: result.chrome || null,
          }));
          /* One shaping call after every trial, whether or not `--cols` was in
           * force. It is what supplies `offered`, which the envelope cannot:
           * a run that carried `--cols` came back with a view describing only
           * the named columns. */
          if (current.contract === "data") reshape({ ...current, result });
        })
        .catch((error) =>
          setDraft((d) => ({ ...d, running: false, error: String(error) }))
        );
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
        <span class="brand">SKY.BOSS</span>
        <span class="host">${location.host}</span>
        <div class="seg nav">
          <button
            class=${screen === CANVAS ? "on" : ""}
            onClick=${() => setScreen(CANVAS)}
          >
            canvas
          </button>
          <button
            class=${screen === WORKBENCH ? "on" : ""}
            onClick=${() => setScreen(WORKBENCH)}
          >
            workbench
          </button>
          <button
            class=${screen === SCHEDULE ? "on" : ""}
            onClick=${() => setScreen(SCHEDULE)}
          >
            schedule
          </button>
        </div>
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
        ${screen === CANVAS &&
        html`
          <div class="seg">
            <button class=${layout === TILE ? "on" : ""} onClick=${() => setLayout(TILE)}>
              tiled
            </button>
            <button class=${layout === FLOAT ? "on" : ""} onClick=${() => setLayout(FLOAT)}>
              floating
            </button>
          </div>
        `}
        <button class="quit" title="close sky.boss" onClick=${() => api.quit()}>✕</button>
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

      ${screen === SCHEDULE
        ? html`<${Plan}
            result=${plan}
            projects=${planSources}
            readAt=${planAt}
            now=${now}
            onRefresh=${readPlan}
            ui=${planUi}
            setUi=${(patch) => setPlanUi((u) => ({ ...u, ...patch }))}
          />`
        : screen === WORKBENCH
        ? html`<${Bench}
            commands=${commands}
            groups=${groups}
            draft=${draft}
            actions=${benchActions}
            vocab=${vocab}
          />`
        : html`
            <div class="stage">
              <${Tools}
                commands=${commands}
                groups=${groups}
                addGroup=${benchActions.addGroup}
                dropGroup=${benchActions.dropGroup}
                move=${benchActions.move}
                open=${open}
                edit=${benchActions.edit}
                drop=${benchActions.forget}
              />
              <div
                class=${`canvas ${layout}`}
                ref=${canvas}
                style=${`--sb-cols: ${tileColumns(windows.length)}`}
              >
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
                    down=${down}
                  />`
                )}
              </div>
            </div>
          `}

      ${pending &&
      html`<${ConfirmAct}
        pending=${pending}
        onCancel=${() => setPending(null)}
        onConfirm=${() => {
          const ask = pending;
          setPending(null);
          ask.go();
        }}
      />`}

      <div class="foot-bar">
        ${screen === SCHEDULE
          ? html`
              <span>⟳ re-read</span>
              <span>one mark per job — never a recurrence</span>
            `
          : screen === WORKBENCH
          ? html`
              <span>⏎ trial run</span>
              <span>the contract is the assertion</span>
            `
          : html`
              <span>⏎ open window</span>
              <span>^K palette</span>
              <span>⟳ refresh</span>
            `}
        <div class="spacer"></div>
        ${down === "stale"
          ? html`<span class="disconnected">session ended — reload to reconnect</span>`
          : down
            ? html`<span class="disconnected">stream down — reconnecting…</span>`
            : html`<span>session ${session ? session.slice(0, 8) : "…"}</span>`}
      </div>
    </div>
  `;
}

/* The mount lives in `main.js`, not here — [[canvas]] round 12.
 *
 * One line, and it was the only thing in the whole frontend that could not be
 * imported outside a browser: it touches `document` at module scope, so any
 * `import` of this file threw `ReferenceError` before reaching a single
 * function. Moving it made `matches`, `kindOf` and `shortOf` testable and cost
 * nothing else. Anything that runs on import belongs there for the same reason.
 */
export { App };
