/* Turning one envelope into what a window shows.
 *
 * The window renders from `data`, never from tb's rendered bytes. That is the
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
    .filter(([, v]) => v !== null && v !== undefined && v !== "" && v !== 0 && v !== false)
    .map(([k, v]) => `${k}=${v}`);
  return parts.length ? parts.join(" ") : "—";
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
function sizing(spec) {
  if (!spec.flex) return undefined;
  return `flex:${spec.flex} 1 0;min-width:${spec.min || 1}ch`;
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
  return html`
    <div class=${`grid ${shaped ? "shaped" : ""}`}>
      <div class="row head">
        ${specs.map((s) => html`<span key=${s.key} style=${sizing(s)}>${s.label}</span>`)}
      </div>
      ${shown.map(
        (row, i) => html`
          <div class="row" key=${i}>
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
    </div>
  `;
}

function Mapping({ value }) {
  return html`
    <div class="grid">
      ${Object.entries(value).map(
        ([key, item]) => html`
          <div class="row" key=${key}>
            <span class="v-label">${key}</span>
            <span class=${`wrap ${roleFor(key, item)}`}>
              ${typeof item === "object" && item !== null
                ? JSON.stringify(item, null, 1)
                : cellText(item)}
            </span>
          </div>
        `
      )}
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

/* `tb run` carries the wrapped command's stdout in `data`, which is the one
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

export function Body({ result }) {
  if (!result) return html`<div class="spin">…</div>`;
  if (result.error) return html`<div class="fail">${result.error}</div>`;

  const envelope = result.envelope;
  if (!envelope) return html`<div class="v-dim">no envelope</div>`;

  const view = unwrap(envelope);
  const warnings = envelope.warnings || [];

  /* A view describes `data`. When the rows came out of `tb run`'s stdout
   * instead, `data` is the run envelope and the view would be describing the
   * wrong object — so it applies only to rows that are the data themselves. */
  const shape = view.wrapped ? null : envelope.view;

  let body;
  if (view.kind === "rows") body = html`<${Table} rows=${view.rows} view=${shape} />`;
  else if (view.kind === "text") body = html`<${Raw} text=${view.text} />`;
  else if (Array.isArray(view.value)) {
    const rows = view.value;
    body = rows.every((r) => r && typeof r === "object" && !Array.isArray(r))
      ? html`<${Table} rows=${rows} view=${shape} />`
      : html`<${Raw} text=${rows.map(cellText).join("\n")} />`;
  } else if (view.value && typeof view.value === "object") {
    body = html`<${Mapping} value=${view.value} />`;
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

export function summarise(result) {
  if (!result) return "";
  if (result.error) return result.error;
  const view = unwrap(result.envelope || {});
  if (view.kind === "rows") return `${view.rows.length} rows`;
  const envelope = result.envelope || {};
  if (envelope.partial) return "partial";
  return envelope.ok === false ? "failed" : "ok";
}
