/* The schedule screen — what fires next, across every project that declares
 * one. The third nav entry, and the first reversal of *there is deliberately
 * no nav entry for the plan or the tower*.
 *
 * **That rule is not being broken; its condition is.** It said a nav offering
 * a screen that is not there is the palette's own failure wearing different
 * clothes. The objection was to *offering* something absent, so building the
 * screen answers it rather than overriding it. What stays blocked is the rest
 * of the drawn flight plan — CLAIMS, CLOCK SOURCE, IN FLIGHT, LIMITS — which
 * needs job identity, a claim vocabulary and a clock source, none of which
 * exist. This screen deliberately shows only the read-only half, and is named
 * `schedule` rather than `plan` for exactly that reason: a nav entry reading
 * `plan` above a table of fire times would be the same over-promise the rule
 * was written against.
 *
 * Every decision about *which columns* still lives in Python — this renders
 * the authored view `sb schedule` hands it. See [[schedule]] round 4.
 */
import { html } from "./vendor/htm-preact.js";

/* Rows for one project, in the order the command returned them.
 *
 * **Not re-sorted here.** `cli/schedule.py` orders by the parsed instant, with
 * everything undated after everything dated — a decision that needed a real
 * timestamp parse and an offset, which this file has neither of. Grouping
 * preserves that order inside each group, so a project's own rows stay in
 * fire order and the screen adds nothing. */
export function byProject(rows) {
  const groups = [];
  const index = new Map();
  for (const row of rows || []) {
    const name = row.project || "";
    if (!index.has(name)) {
      index.set(name, { project: name, rows: [] });
      groups.push(index.get(name));
    }
    index.get(name).rows.push(row);
  }
  return groups;
}

/* The single most imminent row, or null.
 *
 * The command already sorted, so this is `find` and not a scan for a minimum —
 * re-deriving "soonest" here would be a second opinion about ordering, and it
 * would have to parse the offsets to be right. A row whose `fires` is empty
 * has no next run at all and can never be next up. `late` is skipped for the
 * same reason it is drawn loudly below: it has already fired, so it is not
 * what is *about* to happen. */
export function nextUp(rows) {
  return (rows || []).find((r) => r.fires && !r.fires.startsWith("late")) || null;
}

/* Projects that answered but declare no schedule.
 *
 * Round 1's rule, arriving on a screen: **counted, never drawn**. A project
 * with no schedule is the common case and not an error, but silence about it
 * is indistinguishable from a project whose schedule is empty. The command
 * says so in a warning; the screen has room to say which. */
export function silentProjects(warnings) {
  for (const line of warnings || []) {
    const m = /projects declare a schedule — no schedule for (.+)$/.exec(line);
    if (m) return m[1].split(",").map((s) => s.trim()).filter(Boolean);
  }
  return [];
}

/* How stale the reading is, in the vocabulary `chrome.ago` uses.
 *
 * **The screen has no cadence, so it owes this.** Every relative string on it
 * — `in 3h`, `21m ago` — was computed by Python at read time and does not
 * move afterwards. Without a visible age they would rot silently while looking
 * exactly like fresh ones, which is this repo's own named failure. A browser
 * timer was rejected as the fix rather than forgotten: a hidden page has its
 * timers clamped to roughly one fire a minute, so a cadence would quietly
 * become a different cadence at the moment you stopped being able to see it.
 * Stating the age is honest at any refresh rate, including none. */
export function readAge(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function Row({ row, columns }) {
  return html`
    <div class="pl-row">
      ${columns.map(
        (c) => html`
          <span class=${c.key === "fires" ? fireClass(row.fires) : `pl-c pl-${c.key}`}>
            ${row[c.key] || ""}
          </span>
        `
      )}
    </div>
  `;
}

/* `late` is the one word on this screen that gets emphasis, and it is the
 * provider's fact rather than a judgment: it published a next-run time that
 * has passed. Anything else is drawn flat. */
function fireClass(fires) {
  return `pl-c pl-fires${fires && fires.startsWith("late") ? " pl-late" : ""}`;
}

export function Plan({ result, readAt, now, onRefresh }) {
  if (!result) return html`<div class="plan"><div class="spin">…</div></div>`;
  if (result.error) return html`<div class="plan"><div class="fail">${result.error}</div></div>`;

  const envelope = result.envelope || {};
  const rows = Array.isArray(envelope.data) ? envelope.data : [];
  const warnings = envelope.warnings || [];
  const view = envelope.view || null;
  /* The authored view or nothing. No fallback to every key: this screen exists
   * to draw the five columns the command chose, and a silent widening to seven
   * is the bug round 3 spent its afternoon on. */
  /* **`project` is dropped, and only here.** The rows are grouped under a
   * heading that already names it, so drawing it again spends the narrowest
   * column on a constant. This is a *drawing* decision about a screen whose
   * structure carries the field — the envelope still has it, the window form
   * still draws it, and nothing about the view changed. A view describes; the
   * grouping is what makes this one redundant. */
  const columns = ((view && view.columns) || []).filter((c) => c.key !== "project");
  const soon = nextUp(rows);
  const quiet = silentProjects(warnings);
  const groups = byProject(rows);

  return html`
    <div class="plan">
      <div class="pl-head">
        <span class="pl-title">next up</span>
        ${soon
          ? html`<span class="pl-soon">
              <b>${soon.name}</b> · ${soon.project} · <b>${soon.fires}</b>
            </span>`
          : html`<span class="pl-soon v-dim">nothing scheduled</span>`}
        <div class="spacer"></div>
        <span class="pl-age" title=${`read at ${new Date(readAt).toLocaleTimeString()}`}>
          read ${readAge((now - readAt) / 1000)} ago
        </span>
        <button class="sbtn plain" onClick=${onRefresh}>⟳</button>
      </div>

      ${groups.map(
        (g) => html`
          <div class="pl-group" key=${g.project}>
            <div class="pl-gname">
              ${g.project}<span class="v-dim"> · ${g.rows.length} jobs</span>
            </div>
            <div class="pl-rows">
              <div class="pl-row pl-hrow">
                ${columns.map((c) => html`<span class="pl-c">${c.label}</span>`)}
              </div>
              ${g.rows.map(
                (row, i) => html`<${Row} key=${i} row=${row} columns=${columns} />`
              )}
            </div>
          </div>
        `
      )}

      ${quiet.length > 0 &&
      html`<div class="pl-quiet">
        declares no schedule: ${quiet.join(", ")}
      </div>`}

      ${rows.length === 0 &&
      html`<div class="pl-empty">
        no project declares a schedule — add a
        <code>[project.NAME.schedule]</code> table to projects.toml
      </div>`}
    </div>
  `;
}
