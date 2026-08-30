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
import { byHour, plottable, ticks, timeline } from "../../cli/canvas/static/schedule.js";

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

test("timeline places a mark at its fraction of the span", () => {
  const rows = [{ name: "half", at: NOW_S + 12 * HOUR, fires: "in 12h" }];
  const { marks } = timeline(rows, NOW_MS, 24 * HOUR);
  assert.equal(marks.length, 1);
  assert.equal(Math.round(marks[0].percent), 50);
});

test("timeline counts what is beyond the window instead of pinning it", () => {
  const rows = [
    { name: "inside", at: NOW_S + HOUR, fires: "in 1h" },
    { name: "outside", at: NOW_S + 80 * HOUR, fires: "in 3d" },
  ];
  const { marks, beyond } = timeline(rows, NOW_MS, 24 * HOUR);
  /* A mark pinned to the right edge would read as "fires at the end of the
   * window" — a different and false claim. */
  assert.deepEqual(marks.map((m) => m.row.name), ["inside"]);
  assert.equal(beyond, 1);
});

test("timeline clamps a late row to the left rather than off the axis", () => {
  const rows = [{ name: "late", at: NOW_S - 5 * HOUR, fires: "late 5h" }];
  const { marks, beyond } = timeline(rows, NOW_MS, 24 * HOUR);
  assert.equal(marks[0].percent, 0);
  assert.equal(beyond, 0);
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
