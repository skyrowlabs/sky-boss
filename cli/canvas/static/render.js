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

function Table({ rows }) {
  /* An empty result is a result. Rendering nothing at all is indistinguishable
   * from a window that failed to load, and "no open pull requests" is exactly
   * the answer a pinned window exists to keep telling you. */
  if (rows.length === 0) return html`<div class="v-dim">no rows</div>`;

  const columns = columnsOf(rows);
  const shown = rows.slice(0, MAX_ROWS);
  return html`
    <div class="grid">
      <div class="row head">
        ${columns.map((c) => html`<span key=${c}>${c.toUpperCase()}</span>`)}
      </div>
      ${shown.map(
        (row, i) => html`
          <div class="row" key=${i}>
            ${columns.map(
              (c) => html`<span key=${c} class=${roleFor(c, row[c])}>${cellText(row[c])}</span>`
            )}
          </div>
        `
      )}
      ${rows.length > shown.length &&
      html`<div class="row"><span class="truncated">
        ${rows.length - shown.length} more rows not shown
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

  let body;
  if (view.kind === "rows") body = html`<${Table} rows=${view.rows} />`;
  else if (view.kind === "text") body = html`<${Raw} text=${view.text} />`;
  else if (Array.isArray(view.value)) {
    const rows = view.value;
    body = rows.every((r) => r && typeof r === "object" && !Array.isArray(r))
      ? html`<${Table} rows=${rows} />`
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
