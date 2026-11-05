/* The agents screen — which agent sessions are running now, and which of them
 * share a repository. The fourth nav entry, and the tower's second screen
 * after `schedule`. See [[agent-sessions]] round 3.
 *
 * Named `agents` rather than `in flight` for the reason `schedule` is not
 * `plan`: a nav entry names what the screen shows. Every column decision is
 * Python's — this draws the authored view `sb agents` returns through the same
 * `Body` a window uses, and adds only the claim band above it.
 */
import { html } from "./vendor/htm-preact.js";
import { Body } from "./render.js";
import { readAge } from "./schedule.js";

/* Sessions grouped by claim letter, in the order the command sent them.
 *
 * **A claim is read off the rows, never re-derived.** Python asked git and
 * shipped a letter; this only collects the rows that carry the same one. */
export function claimGroups(rows) {
  const groups = new Map();
  for (const row of rows || []) {
    if (!row || !row.claim) continue;
    if (!groups.has(row.claim)) groups.set(row.claim, []);
    groups.get(row.claim).push(row);
  }
  return [...groups].map(([letter, members]) => ({ letter, members }));
}

/* What the head says: how many are running, and how many share. */
export function headline(rows) {
  const n = (rows || []).length;
  const sessions = `${n} session${n === 1 ? "" : "s"}`;
  const claims = claimGroups(rows).length;
  if (!claims) return { sessions, claims: "" };
  return { sessions, claims: `${claims} shared ${claims === 1 ? "repository" : "repositories"}` };
}

function label(row) {
  return row.name || row.id || `pid ${row.pid}`;
}

export function Agents({ result, readAt, now, onRefresh }) {
  const envelope = (result && result.envelope) || {};
  const rows = Array.isArray(envelope.data) ? envelope.data : [];
  const head = headline(rows);
  const groups = claimGroups(rows);

  return html`
    <div class="plan">
      <div class="pl-head">
        <span class="pl-title">running now</span>
        ${result && !result.error
          ? html`<span class="pl-soon">
              <b>${head.sessions}</b>${head.claims && html` · <b>${head.claims}</b>`}
            </span>`
          : ""}
        <div class="spacer"></div>
        ${readAt > 0 &&
        html`<span class="pl-age" title=${`read at ${new Date(readAt).toLocaleTimeString()}`}>
          read ${readAge((now - readAt) / 1000)} ago
        </span>`}
        <button class="sbtn plain" onClick=${onRefresh} title="re-read">⟳</button>
      </div>

      ${/* **Advisory, and it says so.** A claim is a mark that two sessions
          * sit in one repository — worktrees included — and sky.boss never
          * locks, refuses or ranks because of one. Item 7's ruling, stated
          * where the mark is drawn rather than only in a doc. */ ""}
      ${groups.map(
        (g) => html`
          <div class="ag-claim" key=${g.letter}>
            <span class="ag-letter">${g.letter}</span>
            <span>
              ${/* The separator is an expression because htm drops the
                  * whitespace around a line break, which ran `—JS1` together. */ ""}
              <b>${g.members.length}</b> sessions in one repository${" — "}${g.members
                .map(label)
                .join(", ")}
            </span>
            <span class="ag-note">advisory · nothing is locked</span>
          </div>
        `
      )}

      <div class="pl-panel ag-table">
        <${Body} result=${result} />
      </div>
    </div>
  `;
}
