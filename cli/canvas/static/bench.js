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
import { Body, markedLine, summarise } from "./render.js";

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
export function compose(draft) {
  const { contract, cwd, argv } = draft;
  if (!contract) return null;
  const tail = words(argv);
  if (!tail.length) return null;
  const out = [contract];
  if ((cwd || "").trim()) out.push("--cwd", cwd.trim());
  /* The view controls, each on the contract that has the flag. Offering
   * `--cols` under `read` would be a control for a table that contract cannot
   * return, which is the same mistake as offering a cadence on a write. */
  if (contract === "data") {
    if (draft.cols && draft.cols.length) out.push("--cols", draft.cols.join(","));
    if ((draft.rows || "").trim()) out.push("--rows", draft.rows.trim());
    if ((draft.from || "").trim()) out.push("--from", draft.from.trim());
  }
  if (contract === RESIDENT) {
    if ((draft.due || "").trim()) out.push("--due", draft.due.trim());
    if ((draft.highlight || "").trim()) out.push("--highlight", draft.highlight.trim());
  }
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
function Band({ chrome, where, result, running, contract, warnings }) {
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

  /* The warnings on screen, not the ones the trial run happened to come back
   * with. Once a chip has re-shaped the payload, the envelope's count is about
   * a shaping nobody is looking at any more — and a foot saying "1 warning"
   * above a body showing none is the looks-right-and-isn't failure in
   * miniature. See [[workbench]] round 2. */
  const count = warnings !== undefined ? warnings.length : (chrome && chrome.warnings) || 0;

  return html`
    <div class="band foot">
      <span>
        ${streaming
          ? `showing last ${chrome.ring_shown || 0} of ${chrome.ring_limit || 0}`
          : result
            ? summarise(result)
            : ""}
      </span>
      ${count > 0 &&
      html`<span class="band-warn">${count} warning${count === 1 ? "" : "s"}</span>`}
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

/* A follow trial's tail, with the marks applied.
 *
 * Round 1 drew this plain, on the reasoning that the tinting belongs to a
 * window living with a stream rather than to one being drafted. Round 2
 * reverses that, and the reversal is the whole point of `--highlight` being a
 * control here: **you cannot choose a ruleset by name and then not see what it
 * claimed.** The rules still live in Python and the offsets still arrive
 * beside the verbatim text; `markedLine` is shared with the canvas rather than
 * copied, so there is one slicer and no second opinion about what a timestamp
 * looks like.
 *
 * Still deliberately without the parked ring and the restart band: those are
 * for living with a stream, and this one is being drafted. */
function Tail({ lines }) {
  /* Newest lines stay in view. A live log showing anything but its tail is
   * broken, and the bench is no more exempt from that than a window is. */
  const ref = useRef(null);
  useEffect(() => {
    const node = ref.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [lines]);
  return html`<pre class="raw stream" ref=${ref}>
${lines.map(markedLine)}</pre
  >`;
}

/* Why there is nothing to draw yet, said in the pane that would draw it.
 *
 * A blank result pane is the failure this replaces: it looks identical whether
 * the bench is waiting for you, waiting for a command, or broken. */
function Blank({ contract, composed, checks, onRun, running }) {
  if (contract === "run") {
    return html`
      <div class="bench-blank act">
        <b>an act has no trial run.</b>${" "}sb will not execute a write to show
        you what it would print. Every other contract on this bench is drafted by
        running it and looking; this one is drafted by reading it and meaning
        it.${" "}What it can still check without running, it has:
        ${checks.length > 0 &&
        html`<div class="checks">
          ${checks.map(
            (c, i) => html`<div class=${`check ${c.ok ? "" : "bad"}`} key=${i}>
              <span class="mark">${c.ok ? "✓" : "✕"}</span>
              <span class="what">${c.label}</span>
              <span class="detail">${c.detail}</span>
            </div>`
          )}
        </div>`}
        <div class="act-go">
          <button
            class="draft-real"
            disabled=${!composed || running || checks.some((c) => !c.ok)}
            onClick=${onRun}
          >
            ${running ? "running…" : "run it for real"}
          </button>
          <span>it will do the thing. There is no dry run to fall back to.</span>
        </div>
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

/* ------------------------------------------------------------ view controls */

/* One flag with a text value. Enough of them to be worth a component, and all
 * of them share the one thing worth saying: whether changing it re-draws what
 * is on screen or waits for the next trial run. */
function Field({ label, value, placeholder, note, onChange }) {
  return html`
    <div class="vc-field">
      <span class="vc-label">${label}</span>
      <input
        value=${value}
        placeholder=${placeholder || ""}
        onInput=${(e) => onChange(e.target.value)}
      />
      ${note && html`<span class="vc-note">${note}</span>`}
    </div>
  `;
}

/* The view controls, per contract, because a view describes rows and not every
 * contract returns any.
 *
 * `data` gets the checklist and the two flags that change what counts as a
 * row. `follow` gets the two that make a stream's silence and its vocabulary
 * legible. `read` gets neither and is told why — a view describes rows, and
 * verbatim output has none to describe. `run` returns an exit code.
 */
function ViewControls({ draft, actions }) {
  const contract = draft.contract;

  if (contract === "run") {
    return html`
      <div class="panel bench-view">
        <div class="panel-head">NO VIEW</div>
        <div class="vc-body">
          <span class="vc-none">
            nothing to shape. An act returns an exit code, not rows — and the exit
            code is the whole verdict.
          </span>
        </div>
      </div>
    `;
  }

  if (contract === "read") {
    return html`
      <div class="panel bench-view">
        <div class="panel-head">NO VIEW</div>
        <div class="vc-body">
          <span class="vc-none">
            <b>read has no view</b>${" "}— a view describes rows, and this contract
            returns none. Output is shown verbatim by contract; inferring columns
            from whitespace is the silently-wrong failure, and a tool with real
            structure has ${"`--json`"}. Tint is still on, and it is shape rather
            than judgment.
          </span>
        </div>
      </div>
    `;
  }

  if (contract === RESIDENT) {
    return html`
      <div class="panel bench-view">
        <div class="panel-head">VIEW</div>
        <div class="vc-body">
          <${Field}
            label="--due"
            value=${draft.due}
            placeholder="15m"
            note="what makes late a word this window can say"
            onChange=${(v) => actions.set("due", v)}
          />
          <${Field}
            label="--highlight"
            value=${draft.highlight}
            placeholder="a ruleset in formats.toml"
            note="runs after sb's own and claims only unclaimed text"
            onChange=${(v) => actions.set("highlight", v)}
          />
          <span class="vc-note wide">
            Both open the stream, so they take effect on the next trial run — and
            the tint you then see is the answer to which words your rules claimed.
          </span>
        </div>
      </div>
    `;
  }

  /* data. The checklist is the thing this whole screen was opened for.
   *
   * A chip is lit when its column is *drawn*, which is not the same as when it
   * was *named*. With no `--cols` in force the shaping has already decided —
   * an empty column and an opaque sha are hidden by rule — so lighting every
   * chip would say the table is showing nine columns when it is showing six.
   * Read off the view rather than inferred, like everything else here. */
  const chosen = draft.cols;
  const explicit = chosen.length > 0;
  const shaped = draft.hasShaped ? draft.shaped : null;
  const drawn = shaped
    ? new Set([
        ...shaped.columns.map((c) => c.key),
        ...shaped.details.map((c) => c.key),
      ])
    : new Set(draft.offered);
  return html`
    <div class="panel bench-view">
      <div class="panel-head">VIEW</div>
      <div class="vc-body">
        ${draft.offered.length === 0
          ? html`<span class="vc-none">
              the checklist is what the run returned — trial run it first
            </span>`
          : html`
              <div class="vc-chips">
                ${draft.offered.map(
                  (key) => html`<button
                    key=${key}
                    class=${`vc-chip ${drawn.has(key) ? "on" : ""}`}
                    onClick=${() => actions.toggle(key)}
                  >
                    ${key}
                  </button>`
                )}
              </div>
              <span class="vc-note wide">
                ${explicit
                  ? `--cols ${chosen.join(",")} — every column drawn is one you named.`
                  : "no --cols yet, so the lit ones are the shaping's own choices."}${" "}The
                checklist is what the run returned, not what you remember — and a
                column a rule hid is still one you may name.
              </span>
            `}
        <div class="vc-row">
          <${Field}
            label="--rows"
            value=${draft.rows}
            placeholder="where the rows are, if the payload wraps them"
            onChange=${(v) => actions.setRows(v)}
          />
          <${Field}
            label="--from"
            value=${draft.from}
            placeholder="json, or a format you declared"
            note="changes how the bytes are read — next trial run"
            onChange=${(v) => actions.set("from", v)}
          />
        </div>
      </div>
    </div>
  `;
}

/* --------------------------------------------------------------- the job strip */

/* The last step, and it reads left to right: the name, the cadence, and the
 * line the bench will run.
 *
 * `run` has no `--save` at all — `--save` saves by example and the example
 * ran — so it gets the `[tool.NAME]` block to paste instead, rendered by the
 * same function `--save` appends with, so what you copy and what sky.boss would have
 * written are the same bytes.
 */
function JobStrip({ draft, actions }) {
  const contract = draft.contract;
  const acts = contract === "run";
  const composed = compose(draft);
  const named = Boolean(draft.save) && !draft.nameProblem;

  const saveLine =
    composed && draft.save
      ? [composed[0], "--save", draft.save, ...composed.slice(1)]
      : null;

  return html`
    <div class="panel bench-job">
      <div class="panel-head">AS A JOB</div>
      <div class="job-body">
        <div class="job-row">
          <span class="job-label">${acts ? "name" : "--save"}</span>
          <input
            class="job-name"
            value=${draft.save}
            placeholder=${acts ? "what to call it in tools.toml" : "keep this line"}
            onInput=${(e) => actions.setSave(e.target.value)}
          />
          ${/* **No cadence control, and it is absent rather than disabled.**
              The mockup drew one here and building it found why it cannot be:
              a cadence is saved by having a `--refresh` in force on the line
              being saved, and `--refresh` goes *resident* — which a surface
              running a subprocess to completion cannot do. `--refresh` under
              `--json` is a usage error, so the bench would compose a line that
              refuses itself. See [[workbench]] round 3. */
          html`<span class="job-note">
            no cadence here — one is saved by having --refresh in force, and
            that goes resident. Add${" "}<code>refresh = 30</code>${" "}in
            $EDITOR; editing was always $EDITOR's.
          </span>`}
        </div>

        ${draft.nameProblem && html`<div class="job-problem">${draft.nameProblem}</div>`}

        ${acts
          ? html`
              <div class="job-line block">${draft.block || "name it to see the block"}</div>
              <span class="job-note">
                run does not take --save — --save saves by example, and the example
                ran. Paste the block yourself; editing and deleting stay $EDITOR's.
              </span>
            `
          : html`
              <div class="job-row">
                <span class="job-arrow">→</span>
                <div class="job-line">
                  ${saveLine
                    ? html`<span class="draft-sb">sb</span> ${saveLine.join(" ")}`
                    : html`<span class="dim">name it to see the line</span>`}
                </div>
                <button
                  class="job-save"
                  disabled=${!named || !composed || draft.saving}
                  onClick=${() => actions.save()}
                >
                  ${draft.saving ? "saving…" : "save"}
                </button>
              </div>
              ${draft.saved &&
              html`<div class=${`job-result ${draft.saved.ok ? "" : "bad"}`}>
                ${draft.saved.ok
                  ? `saved — it runs ${draft.saved.runs || "(no expansion reported)"}`
                  : draft.saved.error}
              </div>`}
              <span class="job-note">
                <b>Save is a second run, not a confirmation.</b>${" "}It runs the same
                argv again with --save in it, and --save writes${" "}<i>before</i>${" "}the
                run produces anything — which is why the name is checked before the
                button is offered. --save is still the only writer of tools.toml and
                it only ever appends.
              </span>
            `}
      </div>
    </div>
  `;
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
                        ? html`<${Body}
                            result=${draft.result}
                            shaped=${draft.hasShaped ? draft.shaped : undefined}
                            warnings=${draft.hasShaped ? draft.shapeWarnings : undefined}
                          />`
                        : html`<${Blank}
                            contract=${chosen}
                            composed=${composed}
                            checks=${draft.checks}
                            running=${draft.running}
                            onRun=${() => actions.runForReal()}
                          />`}
                </div>
                <${Band}
                  where="foot"
                  chrome=${draft.chrome}
                  result=${draft.result}
                  running=${draft.running}
                  contract=${chosen}
                  warnings=${draft.hasShaped ? draft.shapeWarnings : undefined}
                />
              </div>

              <${ViewControls} draft=${draft} actions=${actions} />
              <${JobStrip} draft=${draft} actions=${actions} />
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
