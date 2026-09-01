/* The schedule screen's pure half — [[schedule]] round 4.
 *
 * Everything here is a function of rows the command already ordered. The
 * screen adds no ordering, no judgment and no arithmetic on a timestamp,
 * which is what these assert.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { byProject, nextUp, readAge, silentProjects } from "../../cli/canvas/static/schedule.js";

test("byProject keeps the command's order inside each group", () => {
  const rows = [
    { project: "a", name: "one" },
    { project: "b", name: "two" },
    { project: "a", name: "three" },
  ];
  const groups = byProject(rows);
  assert.deepEqual(groups.map((g) => g.project), ["a", "b"]);
  /* Not re-sorted: cli/schedule.py ordered by the parsed instant, and this
   * file has neither the parse nor the offsets to do it again. */
  assert.deepEqual(groups[0].rows.map((r) => r.name), ["one", "three"]);
});

test("byProject of nothing is empty rather than a crash", () => {
  assert.deepEqual(byProject(null), []);
  assert.deepEqual(byProject([]), []);
});

test("nextUp is the first row that has not already fired", () => {
  const rows = [
    { name: "overdue", fires: "late 4m" },
    { name: "soon", fires: "in 3h" },
    { name: "later", fires: "in 9h" },
  ];
  /* `late` has already happened, so it is not what is *about* to. */
  assert.equal(nextUp(rows).name, "soon");
});

test("nextUp skips a row with no next run at all", () => {
  assert.equal(nextUp([{ name: "unscheduled", fires: "" }, { name: "x", fires: "in 1h" }]).name, "x");
  assert.equal(nextUp([{ name: "unscheduled", fires: "" }]), null);
  assert.equal(nextUp([]), null);
});

test("silentProjects reads the count the command already reported", () => {
  const warnings = ["1 of 3 projects declare a schedule — no schedule for beta, gamma"];
  assert.deepEqual(silentProjects(warnings), ["beta", "gamma"]);
});

test("silentProjects is empty when every project declares one", () => {
  assert.deepEqual(silentProjects([]), []);
  assert.deepEqual(silentProjects(["something else entirely"]), []);
});

test("readAge is chrome.ago's vocabulary, and never negative", () => {
  assert.equal(readAge(4), "4s");
  assert.equal(readAge(90), "1m");
  assert.equal(readAge(7200), "2h");
  assert.equal(readAge(172800), "2d");
  /* A clock that went backwards is not a negative age. */
  assert.equal(readAge(-5), "0s");
});

/* --- round 5: the charts ------------------------------------------------ */
import { byHour, plottable, ticks } from "../../cli/canvas/static/schedule.js";

const HOUR = 3600;
const NOW_MS = 1756_000_000_000;
const NOW_S = NOW_MS / 1000;

test("plottable defers to Python about which rows are datable", () => {
  const rows = [
    { name: "ok", at: NOW_S + HOUR },
    /* Empty is what cli/schedule.py writes when it could not parse an offset.
     * Testing that rather than re-inspecting `next` is the whole point. */
    { name: "naive", at: "" },
    { name: "missing" },
  ];
  assert.deepEqual(plottable(rows).map((r) => r.name), ["ok"]);
});

/* --- round 9: the span decides which rows exist -------------------------
 *
 * These were `timeline()` tests until round 9, when the span stopped filtering
 * one panel and started filtering the screen. The properties are the same ones
 * round 5 paid for — beyond is counted rather than pinned, late is clamped to
 * the left rather than dropped — asserted one level up, where they now decide
 * whether a row is drawn at all. */
import { derivedSpan, percentOf, spanFilter } from "../../cli/canvas/static/schedule.js";

test("percentOf places a mark at its fraction of the span", () => {
  const row = { name: "half", at: NOW_S + 12 * HOUR, fires: "in 12h" };
  assert.equal(Math.round(percentOf(row, NOW_MS, 24 * HOUR)), 50);
});

test("spanFilter counts what is beyond the window instead of pinning it", () => {
  const rows = [
    { name: "inside", at: NOW_S + HOUR, fires: "in 1h" },
    { name: "outside", at: NOW_S + 80 * HOUR, fires: "in 3d" },
  ];
  const out = spanFilter(rows, NOW_MS, 24 * HOUR);
  /* A mark pinned to the right edge would read as "fires at the end of the
   * window" — a different and false claim. Now that the span filters the table
   * too, the count is the only thing saying those rows exist at all. */
  assert.deepEqual(out.rows.map((r) => r.name), ["inside"]);
  assert.equal(out.beyond, 1);
});

test("a late row is never filtered out, whatever the span", () => {
  /* It has already fired, so it is not *beyond* anything. Hiding an overdue job
   * because the operator picked 6h is the worst thing this screen could do. */
  const rows = [{ name: "late", at: NOW_S - 5 * HOUR, fires: "late 5h" }];
  const out = spanFilter(rows, NOW_MS, 6 * HOUR);
  assert.deepEqual(out.rows.map((r) => r.name), ["late"]);
  assert.equal(out.beyond, 0);
  /* And it is clamped to the left edge rather than off the axis. */
  assert.equal(percentOf(rows[0], NOW_MS, 6 * HOUR), 0);
});

test("an undated row is kept, counted apart, and has no position", () => {
  /* `at` is empty exactly where Python refused to order the row. A time filter
   * cannot exclude a row that has no time to compare, and `null` is not `0`:
   * a row that could not be placed is not a row that fires now. */
  const rows = [
    { name: "naive", at: "" },
    { name: "nonext" },
    { name: "dated", at: NOW_S + HOUR },
  ];
  const out = spanFilter(rows, NOW_MS, 6 * HOUR);
  assert.deepEqual(out.rows.map((r) => r.name), ["naive", "nonext", "dated"]);
  assert.equal(out.undated, 2);
  assert.equal(out.beyond, 0);
  assert.equal(percentOf(rows[0], NOW_MS, 6 * HOUR), null);
  assert.equal(percentOf(rows[1], NOW_MS, 6 * HOUR), null);
});

test("spanFilter of nothing is empty rather than a crash", () => {
  assert.deepEqual(spanFilter(null, NOW_MS, HOUR), { rows: [], beyond: 0, undated: 0 });
  assert.deepEqual(spanFilter([], NOW_MS, HOUR), { rows: [], beyond: 0, undated: 0 });
});

test("derivedSpan runs to the furthest row, so `all` has nothing beyond it", () => {
  const rows = [
    { name: "soon", at: NOW_S + HOUR },
    { name: "far", at: NOW_S + 90 * HOUR },
  ];
  const span = derivedSpan(rows, NOW_MS, 24 * HOUR);
  assert.equal(span, 90 * HOUR);
  assert.equal(spanFilter(rows, NOW_MS, span).beyond, 0);
});

test("derivedSpan falls back rather than returning a zero axis", () => {
  /* Every row late, or undated, has no forward extent — and a zero span is a
   * division by zero wearing an axis. */
  assert.equal(derivedSpan([{ at: NOW_S - HOUR }], NOW_MS, 24 * HOUR), 24 * HOUR);
  assert.equal(derivedSpan([{ at: "" }], NOW_MS, 24 * HOUR), 24 * HOUR);
  assert.equal(derivedSpan([], NOW_MS, 24 * HOUR), 24 * HOUR);
  /* And a span that fell back is still a usable one. */
  assert.equal(percentOf({ at: NOW_S - HOUR }, NOW_MS, derivedSpan([], NOW_MS, 24 * HOUR)), 0);
});

test("ticks pick a round step that fits the wanted count", () => {
  const day = ticks(NOW_MS, 24 * HOUR);
  assert.ok(day.length <= 6 && day.length >= 3, `got ${day.length}`);
  /* Derived from the span, so a span this file has not heard of still works. */
  const week = ticks(NOW_MS, 7 * 86400);
  assert.ok(week.length <= 6 && week.length >= 3, `got ${week.length}`);
  assert.ok(day.every((t) => t.percent > 0 && t.percent <= 100));
});

test("byHour always has 24 buckets, including the empty ones", () => {
  const at = new Date("2026-08-30T01:30:00").getTime() / 1000;
  const buckets = byHour([{ name: "nightly", at }]);
  assert.equal(buckets.length, 24);
  assert.deepEqual(buckets[1].rows.map((r) => r.name), ["nightly"]);
  assert.equal(buckets.reduce((n, b) => n + b.rows.length, 0), 1);
});

/* --- round 6: the card and the stack ------------------------------------ */
import { cardState, clampCard, stackOf } from "../../cli/canvas/static/schedule.js";

const VIEW = { width: 1000, height: 800 };
const CARD = { width: 300, height: 200 };

test("clampCard prefers below-right of the anchor", () => {
  const at = clampCard({ left: 100, right: 140, top: 300, bottom: 320 }, CARD, VIEW);
  assert.equal(at.left, 100);
  assert.equal(at.top, 332);
});

test("clampCard pulls a card back inside the right edge", () => {
  /* The failure this exists for: the confirm dialog hung off the right at
   * scale 2.4, and a card is the same component shape. */
  const at = clampCard({ left: 900, right: 940, top: 100, bottom: 120 }, CARD, VIEW);
  assert.ok(at.left + CARD.width <= VIEW.width, `${at.left} + ${CARD.width} > ${VIEW.width}`);
});

test("clampCard flips above the anchor when below would overflow", () => {
  const at = clampCard({ left: 10, right: 50, top: 700, bottom: 740 }, CARD, VIEW);
  assert.ok(at.top + CARD.height <= VIEW.height, `${at.top} + ${CARD.height} > ${VIEW.height}`);
  assert.ok(at.top < 700);
});

test("clampCard never positions off the top or left", () => {
  const tall = { width: 300, height: 900 };
  const at = clampCard({ left: -50, right: 10, top: 20, bottom: 40 }, tall, VIEW);
  assert.ok(at.left >= 0 && at.top >= 0, JSON.stringify(at));
});

test("stackOf splits a bucket by project in a stable order", () => {
  const rows = [
    { project: "zeta", name: "a" },
    { project: "alpha", name: "b" },
    { project: "zeta", name: "c" },
  ];
  const parts = stackOf(rows);
  /* Sorted by name, not by count: an order that followed size would make the
   * same project a different band in every column, which is the one thing a
   * stacked bar exists to let you read across. */
  assert.deepEqual(parts.map((p) => p.project), ["alpha", "zeta"]);
  assert.deepEqual(parts.map((p) => p.rows.length), [1, 2]);
});

test("stackOf of an empty bucket is empty, not a zero-height segment", () => {
  assert.deepEqual(stackOf([]), []);
});

test("clampCard keeps the card inside even when the anchor is not", () => {
  /* `.plan` scrolls, so a row can sit at y=1226 in a 1000px viewport — and
   * *above* an off-screen anchor is still off-screen. Reachable by hovering a
   * row and then scrolling. */
  const at = clampCard({ left: 40, right: 90, top: 1226, bottom: 1260 }, CARD, VIEW);
  assert.ok(at.top + CARD.height <= VIEW.height, `top ${at.top} + ${CARD.height} > ${VIEW.height}`);
  const wide = clampCard({ left: 4000, right: 4100, top: 10, bottom: 40 }, CARD, VIEW);
  assert.ok(wide.left + CARD.width <= VIEW.width, `left ${wide.left}`);
});

test("clampCard degrades to the corner when the card is larger than the window", () => {
  /* Nothing fits; pinning to the top-left at least keeps the readable half on
   * screen, and the card scrolls internally. */
  const huge = { width: 2000, height: 2000 };
  const at = clampCard({ left: 500, right: 540, top: 500, bottom: 540 }, huge, VIEW);
  assert.deepEqual(at, { left: 12, top: 12 });
});

test("cardState refuses to build a card for an empty bucket", () => {
  /* Ten of twenty-four hour buckets are empty in an ordinary grid. Hovering
   * one built a card from `rows[0]` — undefined — and the throw landed inside
   * Preact's render, so the tree stopped updating and every control went dead
   * while still being drawn. */
  assert.equal(cardState([], { left: 0 }), null);
  assert.equal(cardState(null, { left: 0 }), null);
  assert.equal(cardState(undefined, { left: 0 }), null);
});

test("cardState passes a non-empty bucket through", () => {
  const rows = [{ project: "p", name: "j" }];
  assert.deepEqual(cardState(rows, { left: 4 }), { rows, anchor: { left: 4 } });
});
