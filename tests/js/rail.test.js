/* The tools rail's two pure decisions — [[tools]] round 8, [[canvas]] round 12.
 *
 * These run under `node --test` with no dependency and no DOM. They cover the
 * half a headless render is worst at: branching over data. They do NOT replace
 * the headless pass, which is the only thing that can see a mark with no
 * stylesheet rule or a dialog whose buttons fall off the screen.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { kindOf, matches } from "../../cli/canvas/static/app.js";

const tool = (over = {}) => ({
  name: "tools jam-prs",
  summary: "PRs as data",
  group: "jam-sense",
  tags: ["jam", "review"],
  expansion: ["data", "--cwd", "/src/jam", "--", "jam", "pr", "list", "--json"],
  saved: true,
  ...over,
});

test("kindOf reads the contract off the expansion, never a declared field", () => {
  assert.equal(kindOf(tool()), "data");
  assert.equal(kindOf(tool({ expansion: ["follow", "/var/log/x"] })), "follow");
  assert.equal(kindOf(tool({ expansion: ["read", "--", "df"] })), "read");
});

test("kindOf says nothing for a run, whose ! is a warning and not a label", () => {
  assert.equal(kindOf(tool({ expansion: ["run", "--", "deploy"] })), "");
});

test("kindOf falls back to argv when there is no expansion", () => {
  assert.equal(kindOf({ argv: ["follow"], expansion: [] }), "follow");
  assert.equal(kindOf({}), "");
});

test("an empty filter matches everything", () => {
  assert.equal(matches(tool(), ""), true);
  assert.equal(matches(tool(), "   "), true);
});

test("the filter reaches the tag, which is the axis that scales", () => {
  assert.equal(matches(tool(), "review"), true);
  assert.equal(matches(tool(), "ops"), false);
});

test("the filter reaches the expansion, so a type needs no selector of its own", () => {
  assert.equal(matches(tool(), "data"), true);
  assert.equal(matches(tool({ expansion: ["follow", "/var/log/x"] }), "follow"), true);
});

test("every term must match, so a second word narrows rather than widens", () => {
  assert.equal(matches(tool(), "jam review"), true);
  assert.equal(matches(tool(), "jam nope"), false);
});

test("the filter is case-insensitive in both directions", () => {
  assert.equal(matches(tool(), "REVIEW"), true);
  assert.equal(matches(tool({ tags: ["Release"] }), "release"), true);
});

test("a tool with no tags is not broken by a tag search", () => {
  assert.equal(matches(tool({ tags: undefined }), "review"), false);
  assert.equal(matches(tool({ tags: undefined }), "prs"), true);
});
