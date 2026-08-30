/* The pure half of the two renderers — [[canvas]] round 12.
 *
 * `unwrap` and `tagPool` are the functions CLAUDE.md named as "what a runner
 * would be for" when it recorded that there was no runner.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { dimensions, unwrap } from "../../cli/canvas/static/render.js";
import { tagPool } from "../../cli/canvas/static/bench.js";

test("tagPool is sorted, deduplicated, and survives a tool with no tags", () => {
  assert.deepEqual(
    tagPool([{ tags: ["ops", "jam"] }, { tags: ["jam", "release"] }, {}]),
    ["jam", "ops", "release"]
  );
});

test("tagPool of nothing is empty rather than a crash", () => {
  assert.deepEqual(tagPool([]), []);
  assert.deepEqual(tagPool(undefined), []);
});

test("unwrap tags a plain payload as a value, not as rows", () => {
  const rows = [{ a: 1 }, { a: 2 }];
  assert.deepEqual(unwrap({ ok: true, data: rows }), { kind: "value", value: rows });
});

test("unwrap lifts rows out of a wrapped run's stdout, and says it wrapped", () => {
  const out = unwrap({ data: { stdout: '[{"a": 1}]', exit_code: 0 } });
  assert.equal(out.kind, "rows");
  assert.deepEqual(out.rows, [{ a: 1 }]);
  assert.equal(out.wrapped, true);
});

test("stdout that is not JSON after all falls through to text, never blank", () => {
  const out = unwrap({ data: { stdout: "[not json", exit_code: 0 } });
  assert.equal(out.kind, "text");
  assert.equal(out.text, "[not json");
});

test("unwrap of an empty or absent envelope is a value, not a crash", () => {
  assert.doesNotThrow(() => unwrap({ ok: true, data: null }));
  assert.deepEqual(unwrap({}), { kind: "value", value: undefined });
  assert.deepEqual(unwrap(null), { kind: "value", value: null });
});

/* [[schedule]] round 3 — the band the terminal and the canvas must agree on.
 * They did not: `_dimensions` grew the `of` form and both JS call sites kept
 * their own copy of the old string. A headless render caught it. */
test("dimensions says drawn-of-arrived when a view hides columns", () => {
  const rows = [{ a: 1, b: 2, c: 3 }];
  assert.equal(
    dimensions(rows, { columns: [{ key: "a" }], details: [], hidden: ["b", "c"] }),
    "table · 1 row · 1 of 3 columns"
  );
});

test("dimensions is unchanged when nothing is hidden", () => {
  const rows = [{ a: 1, b: 2, c: 3 }];
  const whole = { columns: [{ key: "a" }, { key: "b" }, { key: "c" }], details: [], hidden: [] };
  assert.equal(dimensions(rows, whole), "table · 1 row · 3 columns");
  assert.equal(dimensions(rows, null), "table · 1 row · 3 columns");
});

test("dimensions counts details as drawn, because they are", () => {
  const rows = [{ a: 1, b: 2, c: 3 }];
  const view = { columns: [{ key: "a" }], details: [{ key: "b" }], hidden: ["c"] };
  assert.equal(dimensions(rows, view), "table · 1 row · 2 of 3 columns");
});
