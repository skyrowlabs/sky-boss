/* Turning one envelope into what a window shows.
 *
 * The window renders from `data`, never from sky.boss's rendered bytes. That is the
 * whole reason the wrapped-CLI contract is `--json`: a chip that re-sorts a
 * column needs rows, and an ANSI table is a picture of rows. Nothing here
 * parses human output.
 *
 * No colour is named in this file. Cells carry a *role* class and the
 * stylesheet resolves it against the injected palette, so the rule that only
 * cli/theme.py names a colour holds in JavaScript too.
 */

import { html } from "./vendor/htm-preact.js";

/* A DOM that grows without bound is this medium's version of the freeze the
 * terminal surface had: a 120k-line result kills a browser tab as dead as it
 * killed a RichLog. The substrate changed; the rule did not.
 */
export const MAX_ROWS = 2000;
export const MAX_CHARS = 200000;

/* Above this, a string is prose rather than a verdict. See `roleFor`. */
const VERDICT_MAX = 20;

/* Conventions the CLI already renders on, read here rather than re-decided.
 * `ok` drives a glyph in the terminal; it drives a colour here.
 */
function roleFor(key, value) {
  const k = String(key || "").toLowerCase();
  if (value === null || value === undefined || value === "") return "v-dim";
  if (value === true) return "v-ok";
  if (value === false) return "v-bad";
  if (k === "ok") return value ? "v-ok" : "v-bad";
  if (k === "exit_code") return Number(value) === 0 ? "v-ok" : "v-bad";
  if (k.endsWith("_s") || k.endsWith("_ms") || typeof value === "number") return "v-num";
  if (k === "error" || k === "stderr") return "v-bad";

  /* A verdict word colours its cell whatever column it is in. `merge: DIRTY`
   * and `checks: 1 failed` are the cells you scan a dense table for, and they
   * do not live under a key called `state`.
   *
   * The length guard is what makes this safe rather than clever: it applies
   * only to short values, so a PR title containing the word "failed" stays
   * plain text instead of turning the row red. A column of verdicts is short;
   * a column of prose is not.
   */
  if (typeof value === "string" && value.length <= VERDICT_MAX) {
    const s = value.toLowerCase();
    if (/\b(fail|failed|failing|down|dirty|error|missing|absent)\b/.test(s)) return "v-bad";
    if (/\b(partial|warn|warning|stale|behind|pending|draft)\b/.test(s)) return "v-warn";
    if (/\b(ok|pass|passed|ready|clean|up|verified|current)\b/.test(s)) return "v-ok";
  }
  return "";
}

/* Reach a dotted key. Only `--cols` produces one; the heuristic never invents
 * a dotted key, because flattening a nested dict turns one column into six. */
function resolve(row, key) {
  let current = row;
  for (const part of String(key).split(".")) {
    if (current === null || typeof current !== "object") return null;
    current = current[part];
  }
  return current === undefined ? null : current;
}

/* A nested dict as one cell: `passed=2 skipped=7`, zeroes dropped.
 *
 * This is the one piece of `cli/view.py` that has a second implementation, and
 * the duplication is deliberate rather than overlooked. The alternative is
 * shipping the rendered string in the envelope, which would make the view a
 * transformation of `data` instead of a description of it — the single
 * property this whole feature rests on. Four lines that must agree is the
 * cheaper of the two prices. Keep it in step with `summarise_mapping`.
 */
function summariseMapping(value) {
  const parts = Object.entries(value)
    .filter(([, v]) => !isEmptyish(v))
    .map(([k, v]) => `${k}=${v}`);
  return parts.length ? parts.join(" ") : "—";
}

/* `_EMPTY` in cli/view.py, plus zero. Written out rather than inlined because
 * the first version of this checked null/undefined/""/0/false and forgot empty
 * arrays — so a `checks` dict carrying `failing_names: []` rendered
 * `failing_names=` in the cell here while the terminal, correctly, dropped it.
 * That is the drift the duplication was warned about, one day later. */
function isEmptyish(v) {
  if (v === null || v === undefined || v === "" || v === 0 || v === false) return true;
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object") return Object.keys(v).length === 0;
  return false;
}

function cellText(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.length ? value.map(cellText).join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/* Columns in first-seen order across every row, not from the first row alone.
 * A row that carries a field the others lack would otherwise drop it silently,
 * which for a table about what is wrong is exactly the wrong thing to lose.
 */
function columnsOf(rows) {
  const seen = [];
  for (const row of rows) {
    for (const key of Object.keys(row)) if (!seen.includes(key)) seen.push(key);
  }
  return seen;
}

/* The columns a view describes, or every key at equal weight when there is no
 * view. Nothing here decides which columns are worth showing — that is
 * `cli/view.py`, deliberately, because this file has no test runner. */
function columnSpecs(rows, view) {
  if (view && view.columns) return view.columns;
  return columnsOf(rows).map((key) => ({ key, label: key.toUpperCase() }));
}

function cellOf(row, spec) {
  const value = resolve(row, spec.key);
  if (spec.summarise && value && typeof value === "object" && !Array.isArray(value)) {
    return summariseMapping(value);
  }
  return cellText(value);
}

/* A weight and a floor, straight from the view. `ch` rather than a pixel
 * count: the stylesheet is written in scaled units and a window is draggable,
 * so there is no fixed width for a character count to mean anything against. */
/* A quarter character of slack on every ch-derived bound.
 *
 * A column whose floor equals its label exactly — `NUMBER` at 6, `MERGE_STATE`
 * at 11 — asks the engine for precisely as many `ch` as the label renders in.
 * Blink lands that on the nose; WebKitGTK, which is what the native shell runs,
 * rounds the flex distribution a hair under and the ellipsis fires, so the
 * header reads `NUMBE…` inside a column sized to fit it. A truncated *header*
 * is a column you cannot identify at all — the rule this file has followed
 * since Round 1 — so the bound gets a rounding guard.
 *
 * In `ch` rather than a pixel because the error scales with the font: the
 * stylesheet is written in scaled units and a hardcoded pixel would stop
 * covering the gap the moment --sb-scale moved. Ten columns cost 2.5ch total.
 */
const SLACK = 0.25;

function sizing(spec) {
  if (!spec.flex) return undefined;
  const parts = [`flex:${spec.flex} 1 0`, `min-width:${(spec.min || 1) + SLACK}ch`];
  /* The width the column would take if nothing competed. Without it a table of
   * four scan columns spreads them across the whole window, and a right-aligned
   * `946` ends up nowhere near the `NUMBER` above it. */
  if (spec.max) parts.push(`max-width:${spec.max + SLACK}ch`);
  /* On the header too, so the label sits over its own values rather than at
   * the far side of a column the values are right-aligned in. */
  if (spec.align === "right") parts.push("text-align:right");
  return parts.join(";");
}

function Table({ rows, view }) {
  /* An empty result is a result. Rendering nothing at all is indistinguishable
   * from a window that failed to load, and "no open pull requests" is exactly
   * the answer a pinned window exists to keep telling you. */
  if (rows.length === 0) return html`<div class="v-dim">no rows</div>`;

  const specs = columnSpecs(rows, view);
  const shaped = Boolean(view && view.columns);
  const shown = rows.slice(0, MAX_ROWS);
  const hidden = (view && view.hidden) || [];
  /* Named by hand and carried by no row. A property of the *run*, like
   * `hidden` and unlike the width fitting below it, so it belongs in the
   * envelope and is drawn identically in both renderers. Without this the
   * canvas would keep the very defect round 5 fixed in the terminal. */
  const missing = (view && view.missing) || [];
  /* Columns you *read* rather than scan. They left the row in the shaping
   * layer, and here they get the full width on their own line beneath it —
   * indented under the second column by a spacer carrying the first column's
   * sizing, so the identifier stays the leftmost thing on the record. */
  const details = (view && view.details) || [];
  return html`
    <div class=${`grid ${shaped ? "shaped" : ""}`}>
      <div class="row head">
        ${specs.map((s) => html`<span key=${s.key} style=${sizing(s)}>${s.label}</span>`)}
      </div>
      ${shown.map(
        (row, i) => html`
          <div class=${`rec ${details.length ? "spaced" : ""}`} key=${i}>
            <div class="row">
              ${specs.map((s) => {
                const text = cellOf(row, s);
                /* The full value stays reachable on hover. A clipped cell that
                 * cannot be recovered is a table that lies about what it holds. */
                return html`<span
                  key=${s.key}
                  style=${sizing(s)}
                  title=${text}
                  class=${roleFor(s.key, resolve(row, s.key))}
                  >${text}</span
                >`;
              })}
            </div>
            ${details.map((d) => {
              const text = cellOf(row, d);
              if (!text || text === "—") return null;
              return html`<div class="row detail" key=${d.key}>
                <span class="gut" style=${sizing(specs[0])}></span>
                <span class="v-dim" title=${d.label}>${text}</span>
              </div>`;
            })}
          </div>
        `
      )}
      ${rows.length > shown.length &&
      html`<div class="row"><span class="truncated">
        ${rows.length - shown.length} more rows not shown
      </span></div>`}
      ${hidden.length > 0 &&
      html`<div class="row"><span class="truncated">
        ${hidden.length} columns hidden: ${hidden.join(", ")}
      </span></div>`}
      ${missing.length > 0 &&
      html`<div class="row"><span class="truncated">
        no row has: ${missing.join(", ")}
      </span></div>`}
    </div>
  `;
}

/* `_plural` in cli/output.py. Four words rather than a shipped string, for the
 * same reason the count itself is arithmetic here. */
function plural(n, word) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/* `_dimensions` in cli/output.py, mirrored for the same reason `plural` is:
 * it is arithmetic over a view Python already decided, not a second opinion
 * about which columns to draw. `5 of 7` when the view draws fewer than
 * arrived — a command that authors its own view has no hidden-columns warning
 * to lean on, so the band is where the difference gets said.
 *
 * Both call sites go through here. They each had their own copy of the string,
 * and the terminal grew the `of` form while these two silently kept the old
 * one — which a headless render caught and no test could have. */
export function dimensions(rows, view) {
  const count = columnsOf(rows).length;
  const drawn = ((view && view.columns) || []).length + ((view && view.details) || []).length;
  const columns = view && drawn > 0 && drawn < count ? `${drawn} of ${plural(count, "column")}` : plural(count, "column");
  return `table · ${plural(rows.length, "row")} · ${columns}`;
}

/* The view describing one nested key, or null. A single payload names the one
 * list it shaped (`rows`); a fold carries a view per block under `blocks`,
 * because six independent payloads cannot share one column list. Mirrors
 * `view_for` in cli/view.py — a lookup, not a judgment. */
function viewFor(view, key) {
  if (!view) return null;
  if (view.blocks && view.blocks[key]) return view.blocks[key];
  if (view.rows === key) return view;
  return null;
}

/* A payload that wraps its rows — `{generated: …, jobs: [ … ]}` — renders the
 * wrapper as lines and the rows as a table, which is what the terminal does
 * and what the operator wants: a generated-at stamp is a useful line, just not
 * a column.
 *
 * The view belongs to exactly one nested list, named by `view.rows`. Handing it
 * to any other would draw a table with another list's columns. Which list that
 * is was decided in `cli/view.py`; this only obeys. See [[table-views]] round 4.
 *
 * Before this, a nested row list rendered as `JSON.stringify` in a single cell —
 * twenty-seven jobs as one blob of text.
 *
 * The size is counted here rather than shipped in the envelope. That is not the
 * `summariseMapping` duplication over again: counting rows and keys is
 * *arithmetic*, which is the standard this file is held to, and putting the
 * rendered string in the view would make a view a transformation of `data`
 * rather than a description of it. Round 3 split the same way over fitting. */
function Mapping({ value, view }) {
  return html`
    <div class="grid">
      ${Object.entries(value).map(([key, item]) => {
        const sub = viewFor(view, key);
        if (Array.isArray(item) && item.length && item.every((r) => r && typeof r === "object")) {
          const dims = dimensions(item, sub);
          return html`<div class="rec" key=${key}>
            <div class="row">
              <span class="v-label">${key}</span>
              <span class="v-dim">${dims}</span>
            </div>
            <${Table} rows=${item} view=${sub} />
          </div>`;
        }
        if (item && typeof item === "object" && !Array.isArray(item)) {
          return html`<div class="rec" key=${key}>
            <div class="row"><span class="v-label">${key}</span></div>
            <${Mapping} value=${item} view=${sub} />
          </div>`;
        }
        return html`
          <div class="row" key=${key}>
            <span class="v-label">${key}</span>
            <span class=${`wrap ${roleFor(key, item)}`}>
              ${typeof item === "object" && item !== null
                ? JSON.stringify(item, null, 1)
                : cellText(item)}
            </span>
          </div>
        `;
      })}
    </div>
  `;
}

function Raw({ text }) {
  const clipped = text.length > MAX_CHARS;
  return html`
    <pre class="raw">${clipped ? text.slice(0, MAX_CHARS) : text}</pre>
    ${clipped &&
    html`<div class="truncated">
      ${text.length - MAX_CHARS} more characters not shown
    </div>`}
  `;
}

/* `sb run` carries the wrapped command's stdout in `data`, which is the one
 * documented exception to output never reaching an envelope — you named the
 * argv and seeing what it printed is the feature.
 *
 * If that stdout is itself JSON, the window shows the table rather than the
 * text. This is what makes wrapping `jam pr list --json` produce a real table
 * with sortable columns instead of a picture of one.
 */
export function unwrap(envelope) {
  const data = envelope && envelope.data;
  if (!data || typeof data !== "object") return { kind: "value", value: data };

  if (typeof data.stdout === "string" && "exit_code" in data) {
    const text = data.stdout.trim();
    if (text.startsWith("[") || text.startsWith("{")) {
      try {
        const parsed = JSON.parse(text);
        const rows = Array.isArray(parsed)
          ? parsed
          : Array.isArray(parsed.data)
            ? parsed.data
            : null;
        if (rows && rows.every((r) => r && typeof r === "object" && !Array.isArray(r))) {
          return { kind: "rows", rows, wrapped: true };
        }
        return { kind: "value", value: parsed, wrapped: true };
      } catch {
        /* Not JSON after all. Fall through and show it as text — a wrapped
         * tool that printed a banner before its JSON is a real thing, and
         * blanking the window would hide the evidence. */
      }
    }
    return { kind: "text", text: data.stdout || data.stderr || "", wrapped: true };
  }

  return { kind: "value", value: data };
}

/* `shaped` overrides the envelope's own view, and only the bench passes one.
 * It is the *same* view, re-derived by `/api/shape` from the same payload with
 * different columns asked for — still Python's opinion, still one opinion.
 * The envelope itself is left alone: it stays byte-identical to the CLI's,
 * which is the boundary tests/test_chrome.py and cli/view.py both hold.
 *
 * `warnings` overrides the envelope's for the same reason: which columns went
 * quiet is a fact about *this* shaping, and the ones the trial run came back
 * with describe the shaping it happened to do. See [[workbench]] round 2. */
export function Body({ result, shaped, warnings: given }) {
  if (!result) return html`<div class="spin">…</div>`;
  if (result.error) return html`<div class="fail">${result.error}</div>`;

  const envelope = result.envelope;
  if (!envelope) return html`<div class="v-dim">no envelope</div>`;

  const view = unwrap(envelope);
  const warnings = given || envelope.warnings || [];

  /* A view describes `data`. When the rows came out of `sb run`'s stdout
   * instead, `data` is the run envelope and the view would be describing the
   * wrong object — so it applies only to rows that are the data themselves. */
  const shape = view.wrapped ? null : shaped !== undefined ? shaped : envelope.view;

  let body;
  if (view.kind === "rows") body = html`<${Table} rows=${view.rows} view=${shape} />`;
  else if (view.kind === "text") body = html`<${Raw} text=${view.text} />`;
  else if (Array.isArray(view.value)) {
    const rows = view.value;
    body = rows.every((r) => r && typeof r === "object" && !Array.isArray(r))
      ? html`<${Table} rows=${rows} view=${shape} />`
      : html`<${Raw} text=${rows.map(cellText).join("\n")} />`;
  } else if (view.value && typeof view.value === "object") {
    body = html`<${Mapping} value=${view.value} view=${shape} />`;
  } else {
    body = html`<${Raw} text=${cellText(view.value)} />`;
  }

  return html`
    ${envelope.ok === false && html`<div class="fail">${envelope.command} failed</div>`}
    ${envelope.partial && html`<div class="warn">${envelope.command} — partial</div>`}
    ${warnings.map((w, i) => html`<div class="warn" key=${i}>⚠ ${w}</div>`)}
    ${body}
  `;
}

/* What a window's footer says about its payload.
 *
 * A canvas window already has a frame, so it never needed the two rules the
 * terminal grew in [[chrome]] round 3 — the frame is the band. What it did need
 * is the same *fact*: the row count was here and the column count was not, and
 * the column count is what says whether the shaping did what was meant. Kept
 * word-for-word in step with `_dimensions` in cli/output.py. */
export function summarise(result) {
  if (!result) return "";
  if (result.error) return result.error;
  const view = unwrap(result.envelope || {});
  /* Two shapes carry rows: `run`'s wrapped stdout (`kind: "rows"`) and a plain
   * `data` payload, which unwrap leaves as a value because that is all it is.
   * The old count only ever fired for the first, so `sb data` — the command
   * this footer is most often above — never showed one. */
  const rows =
    view.kind === "rows"
      ? view.rows
      : Array.isArray(view.value) && view.value.every((r) => r && typeof r === "object")
        ? view.value
        : null;
  if (rows && rows.length) {
    /* Wrapped stdout has no view — the envelope's belongs to `run`, not to the
     * foreign JSON inside it. A bare `data` array is described by the
     * envelope's view directly, the same way Python hands it straight to
     * `_render_sequence` when there is no key to look up. */
    const shape = view.kind === "rows" ? null : (result.envelope || {}).view || null;
    return dimensions(rows, shape);
  }
  const envelope = result.envelope || {};
  if (envelope.partial) return "partial";
  return envelope.ok === false ? "failed" : "ok";
}

/* One followed line, marks applied dumbly. The rules live in Python and the
 * offsets arrive beside the verbatim text ([[highlight]]); this only slices
 * and wraps — a page holding its own opinion about what a timestamp looks
 * like is the drift the one-rule-set design exists to prevent. A stderr line
 * never carries marks and keeps its warn tint.
 *
 * Here rather than in app.js because two surfaces draw a followed line now:
 * a canvas window living with a stream, and the bench trialling one so you
 * can see which words `--highlight` claimed. Two copies of a slicer would
 * be the same drift this function exists to prevent, one level up. */
export function markedLine(l) {
  /* Each line is a *block*, and carries its own hanging indent as a custom
   * property. See [[wrap]].
   *
   * It used to be an inline span ending in a literal "\n", which is the same
   * thing to look at and cannot take an indent: `text-indent` applies to a
   * block container, and a span in a `<pre>` is not one. Making the line a
   * block means the newline has to go — a block *and* a trailing newline is
   * two line boxes, so every line would have drawn double-spaced.
   *
   * `--hang` is a number rather than a length so the stylesheet decides the
   * unit, and the unit is `ch`: the indent is a column count, and a column is
   * a different number of pixels at every `--scale`. */
  const hang = l.indent ? `--hang:${l.indent}` : undefined;
  if (l.stderr || !l.marks || !l.marks.length)
    return html`<span
      class=${`ln ${l.voice ? "voice" : l.stderr ? "err" : ""}`}
      style=${hang}
      >${l.text}</span
    >`;
  const parts = [];
  let cursor = 0;
  for (const [start, end, role] of l.marks) {
    if (start > cursor) parts.push(l.text.slice(cursor, start));
    /* A role may be composite — "bold sb.path" — because bold is a weight
     * rather than a colour and composes instead of competing for the slot.
     * Each word becomes its own class; CSS stacks them for free. */
    const classes = role
      .split(" ")
      .map((r) => "mk-" + r.replace("sb.", ""))
      .join(" ");
    parts.push(html`<span class=${classes}>${l.text.slice(start, end)}</span>`);
    cursor = end;
  }
  parts.push(l.text.slice(cursor));
  return html`<span class="ln" style=${hang}>${parts}</span>`;
}
