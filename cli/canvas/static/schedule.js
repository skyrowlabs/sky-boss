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
import { html, useState } from "./vendor/htm-preact.js";

/* ------------------------------------------------------------- the hover card
 *
 * **It reveals, it never enriches.** Every field is already on the row —
 * `next`, `last` and `at` are *hidden* columns, not absent ones — so nothing
 * here fetches, computes or infers. The card exists because the charts draw a
 * name and a dot, and the instant the dot stands for was nowhere on screen.
 *
 * **Clamped to the viewport rather than trusted to fit.** The confirm dialog
 * fell off the right edge at scale 2.4, which is the same failure in a
 * different component, so the position is measured against the window instead
 * of assumed. */
const CARD_GAP = 12;

export function clampCard(anchor, card, viewport) {
  /* Prefer below-right of the anchor, flip when that would leave the window.
   * Returned as plain numbers so the caller does the styling and this stays a
   * function a test runner can reach. */
  let left = anchor.left;
  let top = anchor.bottom + CARD_GAP;
  if (left + card.width > viewport.width - CARD_GAP) {
    left = Math.max(CARD_GAP, viewport.width - card.width - CARD_GAP);
  }
  if (top + card.height > viewport.height - CARD_GAP) {
    /* Above the anchor rather than below it. */
    top = anchor.top - card.height - CARD_GAP;
  }
  /* **Then clamped unconditionally, because flipping is not enough.** The
   * anchor itself can be outside the window — `.plan` scrolls, so a row can
   * sit at y=1226 in a 1000px viewport, and *above* an off-screen anchor is
   * still off-screen. Preferring a side is a layout choice; staying inside the
   * window is the contract, and a contract enforced only on the paths that
   * happen to need it is not enforced. Reachable in ordinary use: hover a row,
   * then scroll. */
  return {
    left: Math.min(Math.max(CARD_GAP, left), Math.max(CARD_GAP, viewport.width - card.width - CARD_GAP)),
    top: Math.min(Math.max(CARD_GAP, top), Math.max(CARD_GAP, viewport.height - card.height - CARD_GAP)),
  };
}

function Card({ at, rows, declared, innerRef }) {
  if (!at || !rows || rows.length === 0) return null;
  const style = `left:${at.left}px; top:${at.top}px`;
  return html`
    <div class="pl-card" style=${style} ref=${innerRef}>
      ${rows.map(
        (row, i) => html`
          <div class="pl-card-job" key=${i}>
            <div class="pl-card-name">
              <b>${row.name}</b>
              <span class="v-dim"> · ${row.project}</span>
            </div>
            <div class="pl-card-grid">
              <span class="pl-card-k">fires</span>
              <span>${row.fires || "—"}</span>
              <span class="pl-card-abs">${row.next || ""}</span>
              <span class="pl-card-k">ran</span>
              <span>${row.ran || "—"}</span>
              <span class="pl-card-abs">${row.last || ""}</span>
              <span class="pl-card-k">cron</span>
              <span class="pl-card-abs pl-card-wide">${row.schedule || "—"}</span>
            </div>
          </div>
        `
      )}
      ${declared &&
      html`<div class="pl-card-src">${declared.source}</div>`}
    </div>
  `;
}

/* One handler shape for all three anchors, so a table row, a timeline mark and
 * an hour bucket cannot grow three different ideas of what hovering means.
 * Focus is wired to the same thing: a hover-only affordance does not exist for
 * a keyboard, and this card is the only place some of these fields appear. */
export function boxOf(node) {
  /* **`display: contents` has no box.** Round 4 made every `.pl-row` one so
   * the whole group could share a single grid and the columns would align
   * structurally — and an element with no box returns zeros from
   * `getBoundingClientRect`, which pinned the card to the corner of the window
   * with no error anywhere. The union of the children is the row's real
   * extent, and computing it here means the three anchors keep one handler.
   *
   * Falls back to the node's own rect, which is what the timeline lane and the
   * hour bucket actually have. */
  const own = node.getBoundingClientRect();
  if (own.width > 0 || own.height > 0) {
    return { left: own.left, right: own.right, top: own.top, bottom: own.bottom };
  }
  const kids = [...node.children].map((c) => c.getBoundingClientRect()).filter((r) => r.width || r.height);
  if (kids.length === 0) return { left: 0, right: 0, top: 0, bottom: 0 };
  return {
    left: Math.min(...kids.map((r) => r.left)),
    right: Math.max(...kids.map((r) => r.right)),
    top: Math.min(...kids.map((r) => r.top)),
    bottom: Math.max(...kids.map((r) => r.bottom)),
  };
}

export function cardState(rows, anchor) {
  /* **An empty hour has nothing to say, and asking it crashed the app.** Ten of
   * the twenty-four buckets are empty in an ordinary grid; hovering one showed
   * a card built from `rows[0]`, which is `undefined`. That threw *inside
   * Preact's render*, so the tree stopped updating and every control on the
   * screen went dead while still being drawn.
   *
   * Returning null rather than an empty card is deliberate: moving from a full
   * bucket to an empty one should *close* the card, not leave the previous
   * one standing over a bucket it does not describe. */
  if (!rows || rows.length === 0) return null;
  return { rows, anchor };
}

function hoverProps(show, hide, rows) {
  const open = (event) => show(rows, boxOf(event.currentTarget));
  return {
    onMouseEnter: open,
    onFocus: open,
    onMouseLeave: hide,
    onBlur: hide,
    /* Nothing to reveal, nothing to stop on: ten empty tab stops that open
     * nothing are worse than none. */
    tabIndex: rows && rows.length ? 0 : -1,
  };
}

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

/* ------------------------------------------------------------------ charts
 *
 * **Both charts plot `at`, and only `at`.** That is the epoch Python parsed
 * from the provider's `next`, and using it is what keeps this file out of the
 * timestamp business: Python required an offset, refused the naive rows, and
 * ordered what was left. A `Date.parse` here would guess a zone for exactly
 * the rows that were rejected, and would be a second opinion about the one
 * thing round 1 was written to keep single.
 *
 * **Neither chart shows recurrence, and neither pretends to.** sky.boss does
 * not parse cron — a bar repeating every four hours would be this tool
 * inventing a fire time, which round 1 refused because a wrong one looks like
 * an answer. One job, one mark: the next occurrence its provider published.
 */

export function plottable(rows) {
  /* `at` is empty exactly when Python could not order the row. Deferring to
   * that rather than testing the string again is what stops the two halves
   * disagreeing about which rows are datable. */
  return (rows || []).filter((r) => typeof r.at === "number");
}

/* One lane per job on a linear time axis, as a fraction of the span.
 *
 * Rows beyond the window are **counted, not clamped**. A mark pinned to the
 * right edge would read as "fires at the end of the window", which is a
 * different and false claim; the count says how many are out of frame, which
 * is round 1's *counted, never drawn* applied to an axis. */
export function timeline(rows, now, spanSeconds) {
  const marks = [];
  let beyond = 0;
  for (const row of plottable(rows)) {
    const delta = row.at - now / 1000;
    if (delta > spanSeconds) {
      beyond += 1;
      continue;
    }
    marks.push({ row, percent: Math.max(0, Math.min(100, (delta / spanSeconds) * 100)) });
  }
  return { marks, beyond };
}

/* Ticks for the axis, at a round interval that yields a readable number of
 * them. Derived from the span rather than hardcoded per span, so a span this
 * file has not heard of still gets sensible ticks. */
export function ticks(now, spanSeconds, want = 6) {
  const STEPS = [900, 1800, 3600, 10800, 21600, 43200, 86400, 172800, 604800];
  const step = STEPS.find((s) => spanSeconds / s <= want) || STEPS[STEPS.length - 1];
  const out = [];
  for (let t = step; t <= spanSeconds; t += step) {
    out.push({ percent: (t / spanSeconds) * 100, at: now + t * 1000 });
  }
  return out;
}

/* Twenty-four buckets by the local hour a job fires.
 *
 * **The honest caveat, stated here because the screen states it too:** this
 * collapses "tomorrow at 01:00" and "next Monday at 01:00" into one column. It
 * is a picture of *what shape the grid is*, not of what happens next — which is
 * why it is a second view rather than a replacement for the first. The hour
 * itself is not inferred: it is the hour of the instant the provider published,
 * which for a recurring job is the hour it recurs at. */
export function byHour(rows) {
  const buckets = Array.from({ length: 24 }, (_, hour) => ({ hour, rows: [] }));
  for (const row of plottable(rows)) {
    buckets[new Date(row.at * 1000).getHours()].rows.push(row);
  }
  return buckets;
}

/* One bucket's rows split into per-project segments, in a stable order.
 *
 * **Sorted by project name, not by size.** A segment order that follows the
 * count would reshuffle every column and make the same project a different
 * band in each one, which is the thing a stacked bar exists to let you read
 * across. */
export function stackOf(rows) {
  const by = new Map();
  for (const row of rows || []) {
    if (!by.has(row.project)) by.set(row.project, { project: row.project, rows: [] });
    by.get(row.project).rows.push(row);
  }
  return [...by.values()].sort((a, b) => (a.project < b.project ? -1 : 1));
}

function Timeline({ rows, now, span, shadeOf, show, hide }) {
  const { marks, beyond } = timeline(rows, now, span.seconds);
  const axis = ticks(now, span.seconds);
  return html`
    <div class="pl-chart">
      <div class="pl-axis">
        <span class="pl-tick pl-now" style="left:0%">now</span>
        ${axis.map(
          (t) => html`
            <span class="pl-tick" style=${`left:${t.percent}%`}>
              ${new Date(t.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          `
        )}
      </div>
      ${marks.map(
        ({ row, percent }) => html`
          <div
            class=${`pl-lane pl-s${shadeOf(row.project)}`}
            key=${`${row.project}/${row.name}`}
            ...${hoverProps(show, hide, [row])}
          >
            <span class="pl-lane-name">${row.name}</span>
            <div class="pl-track">
              <span
                class=${`pl-mark${row.fires.startsWith("late") ? " pl-late" : ""}`}
                style=${`left:${percent}%`}
              ></span>
            </div>
            <span class="pl-lane-when">${row.fires}</span>
          </div>
        `
      )}
      ${beyond > 0 &&
      html`<div class="pl-quiet">
        ${beyond} ${beyond === 1 ? "job fires" : "jobs fire"} beyond ${span.label} — not drawn
        rather than pinned to the edge
      </div>`}
      ${marks.length === 0 &&
      html`<div class="pl-empty">nothing fires within ${span.label}</div>`}
    </div>
  `;
}

function Hours({ rows, shadeOf, show, hide }) {
  const buckets = byHour(rows);
  const tallest = Math.max(1, ...buckets.map((b) => b.rows.length));
  return html`
    <div class="pl-chart">
      <div class="pl-hours">
        ${buckets.map(
          (b) => html`
            <div
              class="pl-hour"
              key=${b.hour}
              ...${hoverProps(show, hide, b.rows)}
            >
              <div class="pl-bar-space">
                <div class="pl-stack" style=${`height:${(b.rows.length / tallest) * 100}%`}>
                  ${/* **Stacked, not overlaid.** One segment per project, in
                      * the ramp's own order so the same project is the same
                      * band in every column. Overlaying would draw the tallest
                      * project over the others and read as a single bar. */ ""}
                  ${stackOf(b.rows).map(
                    (part) => html`
                      <div
                        class=${`pl-seg pl-s${shadeOf(part.project)}`}
                        key=${part.project}
                        style=${`flex:${part.rows.length} 1 0`}
                      ></div>
                    `
                  )}
                </div>
              </div>
              <span class="pl-count">${b.rows.length || ""}</span>
              <span class="pl-hlabel">${String(b.hour).padStart(2, "0")}</span>
            </div>
          `
        )}
      </div>
      <div class="pl-quiet">
        by the local hour each job next fires. One mark per job, never a
        recurrence — sky.boss does not parse cron. A weekly job sits in the same
        column as a nightly one.
      </div>
    </div>
  `;
}

function Row({ row, columns, show, hide }) {
  return html`
    <div class="pl-row" ...${hoverProps(show, hide, [row])}>
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

const SPANS = [
  { key: "6h", label: "6 hours", seconds: 6 * 3600 },
  { key: "24h", label: "24 hours", seconds: 24 * 3600 },
  { key: "7d", label: "7 days", seconds: 7 * 86400 },
];

/* Where a project's rows came from. Provenance, not data.
 *
 * The mapping is drawn as `payload field → column` in the command's own
 * direction, because that is the direction the operator wrote it in and the
 * direction a mistake is made in. `rows` is shown apart from the four field
 * mappings since it names the *list*, not a column. */
function Source({ declared }) {
  if (!declared) return null;
  const map = declared.schedule;
  return html`
    <div class="pl-source">
      <div class="pl-src-row">
        <span class="pl-src-k">source</span>
        <span class="pl-src-v">${declared.source}</span>
      </div>
      ${declared.cwd &&
      html`<div class="pl-src-row">
        <span class="pl-src-k">in</span><span class="pl-src-v">${declared.cwd}</span>
      </div>`}
      ${map
        ? html`
            <div class="pl-src-row">
              <span class="pl-src-k">rows</span>
              <span class="pl-src-v">${map.rows || "the payload itself"}</span>
            </div>
            <div class="pl-src-row">
              <span class="pl-src-k">maps</span>
              <span class="pl-src-v">
                ${["name", "schedule", "next", "last"]
                  .filter((f) => map[f])
                  .map((f) => `${map[f]} → ${f}`)
                  .join("   ")}
              </span>
            </div>
          `
        : html`<div class="pl-src-row">
            <span class="pl-src-k">schedule</span>
            <span class="pl-src-v v-dim">
              no <code>[project.${declared.name}.schedule]</code> table — sky.boss
              never writes this file
            </span>
          </div>`}
    </div>
  `;
}

export function Plan({ result, projects, readAt, now, onRefresh, ui, setUi }) {
  if (!result) return html`<div class="plan"><div class="spin">…</div></div>`;
  if (result.error) return html`<div class="plan"><div class="fail">${result.error}</div></div>`;

  const envelope = result.envelope || {};
  const all = Array.isArray(envelope.data) ? envelope.data : [];
  /* The card's whole state: what to draw and where. Held here rather than in
   * each view so there is exactly one card in the DOM at a time — three views
   * each owning one is three ways to leave a stale card behind. */
  const [card, setCard] = useState(null);
  const warnings = envelope.warnings || [];
  const view = envelope.view || null;
  /* **`project` is dropped, and only here.** The rows are grouped under a
   * heading that already names it, so drawing it again spends the narrowest
   * column on a constant. This is a *drawing* decision about a screen whose
   * structure carries the field — the envelope still has it, the window form
   * still draws it, and nothing about the view changed. A view describes; the
   * grouping is what makes this one redundant. */
  const columns = ((view && view.columns) || []).filter((c) => c.key !== "project");

  const declared = new Map((projects || []).map((p) => [p.name, p]));
  /* Which ramp step each project draws in. Assigned in `rollcall.parse` and
   * shipped by `/api/projects`, so the CLI and the surface cannot disagree
   * about which project is which colour. */
  const shadeOf = (name) => (declared.get(name) || {}).shade || 0;
  const quiet = silentProjects(warnings);
  /* Every project sky.boss knows about, whether or not it produced a row. A
   * selector built from the rows alone could not offer the project that
   * declares nothing — which is the one you go looking for when the screen is
   * emptier than expected. */
  const names = [...new Set([...byProject(all).map((g) => g.project), ...quiet])];
  /* **Empty means all**, which keeps the default with no extra control and no
   * state to get out of step with it. A name that has left `projects.toml`
   * since it was picked is ignored rather than remembered — the chip it came
   * from is not on screen any more, so honouring it would filter to something
   * the operator cannot see or undo. */
  const picked = (ui.projects || []).filter((n) => names.includes(n));
  const rows = picked.length ? all.filter((r) => picked.includes(r.project)) : all;
  /* **A "declares nothing" panel is the whole answer when there is nothing
   * else**, and that used to be spelled as *exactly one project selected*.
   * Rounds 4-7 needed the narrower test because the table view drew the
   * declaration panels underneath real rows; with three panels on one screen
   * the question that matters is whether any row survived the selection at
   * all, which `rows` already answers. See [[schedule]] round 8. */
  const groups = byProject(rows);
  const soon = nextUp(rows);
  const span = SPANS.find((s) => s.key === ui.span) || SPANS[1];

  /* Measured after paint, not guessed: the card's size depends on its text and
   * on `--scale`, and a guessed width is how a panel ends up half off-screen at
   * one scale and fine at another. Stored unclamped, then clamped in the same
   * render once the node has a box. */
  const show = (rows, anchor) => setCard(cardState(rows, anchor));
  const hide = () => setCard(null);

  const toggle = (name) => {
    const next = picked.includes(name)
      ? picked.filter((n) => n !== name)
      : [...picked, name];
    setUi({ projects: next });
  };

  /* **Every panel is drawn, so nothing decides which one.** Rounds 4 and 5
   * made these three a `ui.mode` switch, which is the shape a *window* has —
   * one command, one result, one drawing. The question this screen answers is
   * a comparison, and a comparison needs two of them at once. The tab labels
   * survive as headings; the buttons do not. See [[schedule]] round 8. */
  const anyRows = rows.length > 0;

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
        <button class="sbtn plain" onClick=${onRefresh} title="re-read">⟳</button>
      </div>

      <div class="pl-controls">
        <div class="seg">
          <button
            class=${picked.length === 0 ? "on" : ""}
            onClick=${() => setUi({ projects: [] })}
          >
            all
          </button>
          ${names.map(
            (n) => html`
              <button
                key=${n}
                class=${`pl-s${shadeOf(n)}${picked.includes(n) ? " on" : ""}`}
                onClick=${() => toggle(n)}
              >
                <span class="pl-swatch"></span>${n}
              </button>
            `
          )}
        </div>
        <div class="spacer"></div>
        ${/* Always drawn, because the timeline is always drawn. This was
            * conditional on `ui.mode === "timeline"`, and that condition no
            * longer names anything. */ ""}
        <div class="seg">
          ${SPANS.map(
            (s) => html`
              <button
                key=${s.key}
                class=${span.key === s.key ? "on" : ""}
                onClick=${() => setUi({ span: s.key })}
              >
                ${s.key}
              </button>
            `
          )}
        </div>
      </div>

      ${/* **The charts are drawn only when there are rows to draw.** Round 5
          * established that "nothing fires within 24 hours" is a correct
          * sentence that misleads when the project declares no schedule at
          * all. On one screen that trap has a wider mouth: an empty timeline
          * beside an empty hour chart beside a "declares no schedule" panel is
          * the same misleading sentence said three times. With no rows the
          * declaration panels are the whole answer. */ ""}
      ${anyRows &&
      html`<div class="pl-panel pl-wide">
        <div class="pl-pname">hours</div>
        <${Hours} rows=${rows} shadeOf=${shadeOf} show=${show} hide=${hide} />
      </div>`}

      <div class="pl-split">
        <div class="pl-panel">
          ${/* **A heading tells two panels apart, so a lone panel needs none.**
              * With no rows the charts are not drawn and this is the only panel
              * on the screen — a `table` label over a "declares no schedule"
              * statement names a table that is not there. */ ""}
          ${anyRows && html`<div class="pl-pname">table</div>`}
          ${groups.map(
            (g) => html`
              <div class="pl-group" key=${g.project}>
                <div class="pl-gname">
                  ${g.project}<span class="v-dim"> · ${g.rows.length} jobs</span>
                </div>
                <${Source} declared=${declared.get(g.project)} />
                <div class="pl-rows">
                  <div class="pl-row pl-hrow">
                    ${columns.map((c) => html`<span class="pl-c">${c.label}</span>`)}
                  </div>
                  ${g.rows.map(
                    (row, i) => html`<${Row} key=${i} row=${row} columns=${columns} show=${show} hide=${hide} />`
                  )}
                </div>
              </div>
            `
          )}

          ${/* A project that declares nothing still deserves a panel when it
              * is on screen — but only when it *is*. Filtering by the same
              * selection the rows use is what keeps the two halves of the
              * screen describing the same set. It lives in the table panel
              * because it is a statement about a declaration, which is what
              * this panel is already full of. */ ""}
          ${quiet
            .filter((n) => picked.length === 0 || picked.includes(n))
            .map(
              (n) => html`
                <div class="pl-group" key=${n}>
                  <div class="pl-gname">${n}<span class="v-dim"> · declares no schedule</span></div>
                  <${Source} declared=${declared.get(n)} />
                </div>
              `
            )}

          ${rows.length === 0 &&
          quiet.length === 0 &&
          html`<div class="pl-empty">
            no project declares a schedule — add a
            <code>[project.NAME.schedule]</code> table to projects.toml
          </div>`}
        </div>

        ${/* **The heading carries the span.** The hour chart plots every
            * datable row and the timeline plots only what falls inside the
            * window, so on one screen their two counts are visible together
            * and could reasonably read as a disagreement. Naming the scope in
            * the heading makes the difference a label rather than an
            * inference. */ ""}
        ${anyRows &&
        html`<div class="pl-panel">
          <div class="pl-pname">timeline<span class="v-dim"> · ${span.label}</span></div>
          <${Timeline}
            rows=${rows}
            now=${now}
            span=${span}
            shadeOf=${shadeOf}
            show=${show}
            hide=${hide}
          />
        </div>`}
      </div>

      ${/* `?.` is a second guard behind `cardState`, kept on purpose: this
          * expression is evaluated during *render*, where a throw takes the
          * whole tree down rather than one component, and the cost of the
          * guard is one character. */ ""}
      ${card &&
      html`<${CardLayer} card=${card} declared=${declared.get(card.rows[0]?.project)} />`}
    </div>
  `;
}

/* Draws the card twice: once off-screen to learn its size, then clamped.
 *
 * **Measured rather than guessed.** The card's box depends on its text and on
 * `--scale`, so a hardcoded width is how a panel fits at 1.15 and hangs off the
 * edge at 2.4 — which is exactly what the confirm dialog did. The first paint
 * is invisible and one frame long; every paint after it is positioned. */
function CardLayer({ card, declared }) {
  const [box, setBox] = useState(null);
  const measure = (node) => {
    if (!node) return;
    const rect = node.getBoundingClientRect();
    if (!box || Math.abs(box.width - rect.width) > 1 || Math.abs(box.height - rect.height) > 1) {
      setBox({ width: rect.width, height: rect.height });
    }
  };
  const at = box
    ? clampCard(card.anchor, box, { width: window.innerWidth, height: window.innerHeight })
    : null;
  /* The ref goes on the card itself, not on a wrapper: the wrapper is a
   * full-viewport layer, so measuring it would return the window and clamp
   * against nothing. */
  return html`
    <div class="pl-card-layer" style=${at ? "" : "visibility:hidden"}>
      <${Card}
        at=${at || { left: 0, top: 0 }}
        rows=${card.rows}
        declared=${declared}
        innerRef=${measure}
      />
    </div>
  `;
}
