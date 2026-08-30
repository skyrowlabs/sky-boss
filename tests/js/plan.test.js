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
