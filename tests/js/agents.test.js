/* The agents screen's pure half — [[agent-sessions]] round 3. A claim is
 * read off the rows Python sent; nothing here derives one. */
import { test } from "node:test";
import assert from "node:assert/strict";

import { claimGroups, headline } from "../../skyboss/canvas/static/agents.js";

test("claimGroups collects rows by letter in the order they arrived", () => {
  const rows = [
    { name: "a", claim: "A" },
    { name: "b", claim: "" },
    { name: "c", claim: "B" },
    { name: "d", claim: "A" },
  ];
  const groups = claimGroups(rows);
  assert.deepEqual(groups.map((g) => g.letter), ["A", "B"]);
  assert.deepEqual(groups[0].members.map((r) => r.name), ["a", "d"]);
});

test("claimGroups of nothing is empty rather than a crash", () => {
  assert.deepEqual(claimGroups(null), []);
  assert.deepEqual(claimGroups([{ name: "x" }]), []);
});

test("headline says nothing about claims when there are none", () => {
  assert.deepEqual(headline([{ claim: "" }]), { sessions: "1 session", claims: "" });
  assert.equal(headline([{ claim: "A" }, { claim: "A" }]).claims, "1 shared repository");
});
