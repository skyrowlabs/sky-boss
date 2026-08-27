/* The workbench: where a command gets made.
 *
 * The palette is a one-line composer, which is the right shape for invoking
 * something you already trust and the wrong shape for authoring something you
 * do not. This is the screen with room for the knobs that make an invocation
 * correct — and, before any of them, room for the assertion they all hang off.
 *
 * Three rules this file keeps, all of them the canvas's rather than its own:
 *
 * 1. **The contract is asserted, never inferred.** Nothing here reads a
 *    trailing `--json` and decides you meant `data`. A bench that guessed
 *    would be the act/observe split undone by a heuristic, and that split is
 *    what the whole surface turns on.
 * 2. **The result is drawn in the renderer it will really use** — `Body` from
 *    render.js, unchanged, so `MAX_ROWS` and `MAX_CHARS` apply here exactly as
 *    they do in a window. A bench that drew its own preview would be showing
 *    you a picture of the thing rather than the thing.
 * 3. **Nothing keeps a command table.** The reference rail is the same
 *    /api/catalog the palette reads, so the help that serves `--help` in a
 *    terminal serves the bench with no second copy to drift.
 *
 * See [[workbench]].
 */

import { html, useEffect, useRef } from "./vendor/htm-preact.js";
import { Body, summarise } from "./render.js";

/* The four entry points, split by the one bit that matters. Named here rather
 * than filtered out of the catalog by a property, because this list is not
 * "every command" — it is the set of contracts a command may be *authored*
 * against, and `roll-call` being a read does not make it one of them.
 *
 * The split is drawn, not just ordered: a rail that listed `run` beside `data`
 * with no visual difference would lose the bit the design turns on. */
export const OBSERVES = ["data", "read", "follow"];
export const ACTS = ["run"];
export const CONTRACTS = [...OBSERVES, ...ACTS];

/* A stream is held open rather than run to completion, so its trial goes down
 * the follow route and its frames arrive on the session like any other. */
export const RESIDENT = "follow";

/* The bench's pseudo-window. A follow trial is a held-open stream, and every
 * held-open stream on this surface is keyed to a window id — so the bench has
 * one, and closing the screen drops it exactly as closing a window would. */
export const BENCH_WINDOW = "bench";

export function words(text) {
  return (text || "").trim().split(/\s+/).filter(Boolean);
}

/* The sb-level argv the bench is about to run.
 *
 * `--` goes in unless the operator typed one. Every contract here takes its
 * foreign argv after a `--`, and follow's file-versus-command dispatch reads
 * what comes *after* it — `sb follow -- build.log` is still the file form —
 * so supplying one chooses nothing on the operator's behalf.
 *
 * Splitting on whitespace is the palette's limitation carried over rather than
 * a new one: a foreign argument containing a space cannot be typed here yet.
 * The composed line is shown before it runs, so it is a visible limitation
 * instead of a silent one.
 *
 * null when there is not yet a command — no contract, or no argv. The trial
 * button reads that as "nothing to run" rather than each caller re-deciding.
 */
export function compose({ contract, cwd, argv }) {
  if (!contract) return null;
  const tail = words(argv);
  if (!tail.length) return null;
  const out = [contract];
  if ((cwd || "").trim()) out.push("--cwd", cwd.trim());
  if (tail[0] !== "--") out.push("--");
  return [...out, ...tail];
}

/* ------------------------------------------------------------------- chrome */

function stamp(seconds) {
  if (!seconds) return "";
  return new Date(seconds * 1000).toLocaleTimeString();
}

/* The [[chrome]] band, top and bottom — the same facts a canvas window wears,
 * given the room the bench has and a tile does not. One contract drawn twice:
 * nothing here derives a verdict, it only spells the one Python sent. */
function Band({ chrome, where, result, running, contract }) {
  const attention = chrome && chrome.attention;
  const refused = Boolean(result && result.error);
  const bad = attention === "failed" || attention === "dead" || refused;

  if (where === "top") {
    const right = running
      ? "running…"
      : chrome
        ? attention
        : refused
          ? "refused"
          : contract === "run"
            ? "not run"
            : "no trial yet";
    return html`
      <div class="band top">
        <span class="band-src">${(chrome && chrome.source) || ""}</span>
        <div class="spacer"></div>
        <span class=${`band-att ${bad ? "bad" : ""}`}>${right}</span>
      </div>
    `;
  }

  /* A stream has no result and never will — it is held open rather than run —
   * so its foot reads the ring and the stat instead of an envelope. Same two
   * facts the canvas window's foot carries, drawn from the same chrome. */
  const streaming = chrome && (chrome.shape === "stream" || chrome.shape === "cursor");

  return html`
    <div class="band foot">
      <span>
        ${streaming
          ? `showing last ${chrome.ring_shown || 0} of ${chrome.ring_limit || 0}`
          : result
            ? summarise(result)
            : ""}
      </span>
      ${chrome &&
      chrome.warnings > 0 &&
      html`<span class="band-warn">
        ${chrome.warnings} warning${chrome.warnings === 1 ? "" : "s"}
      </span>`}
      <div class="spacer"></div>
      <span class="band-hint">${streaming ? streamFoot(chrome) : ranFoot(result, chrome)}</span>
    </div>
  `;
}

function ranFoot(result, chrome) {
  const took = result && result.duration_s !== undefined ? `${result.duration_s}s` : "";
  const ran = chrome && chrome.ran_at ? `ran ${stamp(chrome.ran_at)}` : "";
  return [took, ran].filter(Boolean).join(" · ");
}

/* Where the stream last was. `size_bytes` and `last_write_at` are the file
 * cursor's; `last_line_at` and `exit_code` are a process's. Only the fields
 * that shape carries are set, so this reads whichever arrived. */
function streamFoot(chrome) {
  const parts = [];
  if (chrome.size_bytes) parts.push(`${Math.round(chrome.size_bytes / 1024)} KB`);
  if (chrome.last_write_at) parts.push(`last write ${stamp(chrome.last_write_at)}`);
  else if (chrome.last_line_at) parts.push(`last line ${stamp(chrome.last_line_at)}`);
  if (chrome.exit_code !== undefined) parts.push(`exited ${chrome.exit_code}`);
  return parts.join(" · ");
}

/* ------------------------------------------------------------------ results */

/* A follow trial's tail. Deliberately plainer than the canvas's `StreamBody`:
 * the marks, the parked ring and the restart band belong to a window that is
 * living with a stream, and this one is being drafted. What it must show is
 * that the file cursor and the stream are real renderers, which they are. */
function Tail({ lines }) {
  /* Newest lines stay in view. A live log showing anything but its tail is
   * broken, and the bench is no more exempt from that than a window is. */
  const ref = useRef(null);
  useEffect(() => {
    const node = ref.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [lines]);
  return html`<pre class="raw stream" ref=${ref}>
${lines.map((l) => (l.stderr ? html`<span class="err">${l.text + "\n"}</span>` : l.text + "\n"))}</pre
  >`;
}

/* Why there is nothing to draw yet, said in the pane that would draw it.
 *
 * A blank result pane is the failure this replaces: it looks identical whether
 * the bench is waiting for you, waiting for a command, or broken. */
function Blank({ contract, composed }) {
  if (contract === "run") {
    return html`
      <div class="bench-blank">
        <b>an act has no trial run.</b>${" "}sb will not execute a write to show
        you what it would print. Every other contract on this bench is drafted by
        running it and looking; this one is drafted by reading it and meaning it.
      </div>
    `;
  }
  if (!composed) {
    return html`
      <div class="bench-blank">
        type an argv. An observe is drafted by running it — the flags that make
        it right are the ones you get wrong by typing and right by looking, and
        this is the place to look.
      </div>
    `;
  }
  return html`<div class="bench-blank">nothing run yet — trial run to see it</div>`;
}

/* ------------------------------------------------------------------ the rail */

/* One contract's own help, from the live Click tree. `--help` and the bench
 * read the same strings, so there is no second copy to fall behind. */
function Reference({ entry, name }) {
  const acts = entry ? entry.acts : name === "run";
  return html`
    <div class="ref-entry">
      <div class="ref-head">
        <span class="ref-name">sb ${name}</span>
        <span class=${`ref-nature ${acts ? "acts" : ""}`}>${acts ? "ACTS" : "OBSERVES"}</span>
      </div>
      <div class="ref-blurb">${entry ? entry.summary : "not in this tree"}</div>
      ${entry &&
      entry.options.length > 0 &&
      html`
        <div class="ref-flags">
          ${entry.options.map(
            (o) => html`
              <div class="ref-flag" key=${o.flag}>
                <span class="ref-flag-name">${o.flag}</span>
                <span class="ref-flag-desc">${o.help}</span>
              </div>
            `
          )}
        </div>
      `}
    </div>
  `;
}

/* ------------------------------------------------------------------- screen */

export function Bench({ commands, draft, actions }) {
  const byName = {};
  for (const c of commands) byName[c.name] = c;

  const composed = compose(draft);
  const chosen = draft.contract;
  /* Follows the contract once there is one; before that it lists all four,
   * which is the same thing the empty state is asking you to choose between. */
  const shown = chosen ? [chosen] : CONTRACTS;

  const pick = (name) => html`
    <button
      key=${name}
      class=${`bench-pick ${chosen === name ? "on" : ""} ${ACTS.includes(name) ? "acts" : ""}`}
      onClick=${() => actions.pick(name)}
    >
      ${name}
    </button>
  `;

  return html`
    <div class="bench">
      <div class="bench-main">
        <div class="panel bench-contract">
          <div class="panel-head">CONTRACT</div>
          <div class="bench-groups">
            <div class="bench-group">
              <span class="bench-nature">observes</span>
              ${OBSERVES.map(pick)}
            </div>
            <div class="bench-group">
              <span class="bench-nature acts">acts</span>
              ${ACTS.map(pick)}
            </div>
          </div>
          <span class="bench-note">the one bit no parser can tell you</span>
        </div>

        ${!chosen
          ? html`
              <div class="panel bench-open">
                <b>choose a contract.</b>
                <p>
                  Nothing is selected because nothing has been asserted, and the
                  bench does not guess. It gates everything below it: which
                  renderer draws the result, whether a cadence may be offered,
                  and whether there is a trial run at all.
                </p>
                <p>
                  Three of these observe and one acts. That is the only division
                  in sb that a command cannot be talked out of.
                </p>
              </div>
            `
          : html`
              <div class="panel bench-draft">
                <div class="draft-row">
                  <span class="draft-label">--cwd</span>
                  <input
                    class="draft-cwd"
                    value=${draft.cwd}
                    title="where this command runs"
                    onInput=${(e) => actions.setCwd(e.target.value)}
                  />
                </div>
                <div class="draft-row">
                  <span class="draft-label">argv</span>
                  <input
                    class="draft-argv"
                    value=${draft.argv}
                    placeholder="the argv, verbatim…"
                    onInput=${(e) => actions.setArgv(e.target.value)}
                    onKeyDown=${(e) => e.key === "Enter" && actions.trial()}
                  />
                  ${chosen !== "run" &&
                  html`<button
                    class="draft-trial"
                    disabled=${!composed || draft.running}
                    onClick=${() => actions.trial()}
                  >
                    ${draft.running ? "running…" : "trial run"}
                  </button>`}
                </div>
                <div class="draft-line">
                  ${composed
                    ? html`<span class="draft-sb">sb</span> ${composed.join(" ")}`
                    : html`<span class="dim">the line the bench will run appears here</span>`}
                </div>
              </div>

              <div class="panel bench-result">
                <${Band}
                  where="top"
                  chrome=${draft.chrome}
                  result=${draft.result}
                  running=${draft.running}
                  contract=${chosen}
                />
                <div class="body">
                  ${draft.error
                    ? html`<div class="fail">${draft.error}</div>`
                    : chosen === RESIDENT && draft.lines.length
                      ? html`<${Tail} lines=${draft.lines} />`
                      : draft.result
                        ? html`<${Body} result=${draft.result} />`
                        : html`<${Blank} contract=${chosen} composed=${composed} />`}
                </div>
                <${Band}
                  where="foot"
                  chrome=${draft.chrome}
                  result=${draft.result}
                  running=${draft.running}
                  contract=${chosen}
                />
              </div>
            `}
      </div>

      <div class="panel bench-ref">
        <div class="panel-head">REFERENCE</div>
        <div class="ref-list">
          ${shown.map(
            (name) => html`<${Reference} key=${name} name=${name} entry=${byName[name]} />`
          )}
        </div>
        <div class="ref-foot">one help string, two surfaces</div>
      </div>
    </div>
  `;
}
