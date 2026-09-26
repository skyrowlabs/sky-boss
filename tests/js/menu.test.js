/* The right-click menu's pure half — [[canvas]] round 15.
 *
 * What the menu offers is a function of the span's mark roles and whether a
 * selection exists, and where it goes is a function of four numbers, so both
 * are decided here where `node --test` reaches them. The DOM half is thin on
 * purpose and is checked by the headless pass, which is the only thing that
 * can see a menu drawn off the edge of a window.
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { OFFERS, copy, itemsFor, perform, place } from "../../skyboss/canvas/static/menu.js";

const labels = (items) => items.map((i) => i.label);

test("a location copies whole, colon and line number included", () => {
  const items = itemsFor({ roles: ["path"], text: "report.py:75", line: "at report.py:75" });
  assert.deepEqual(labels(items), ["Copy", "Copy line"]);
  assert.equal(items[0].value, "report.py:75");
  assert.equal(items[0].act, "copy");
});

test("a link offers copy and open, and open goes to the server", () => {
  const items = itemsFor({ roles: ["url"], text: "https://example.com/x" });
  assert.deepEqual(labels(items), ["Copy link", "Open link"]);
  assert.deepEqual(
    items.map((i) => [i.act, i.value]),
    [
      ["copy", "https://example.com/x"],
      ["open", "https://example.com/x"],
    ]
  );
});

test("a composite role is read past its weight", () => {
  const items = itemsFor({ roles: ["bold", "path"], text: "src/app.js" });
  assert.deepEqual(labels(items), ["Copy"]);
});

test("a role that offers nothing adds nothing", () => {
  for (const role of ["num", "ok", "fail", "warn", "muted", "accent", "bold"]) {
    assert.deepEqual(itemsFor({ roles: [role], text: "x" }), [], role);
  }
});

test("a selection comes first and copies exactly what was selected", () => {
  const items = itemsFor({ selection: "a  b\n c", roles: ["ref"], text: "#12", line: "see #12" });
  assert.deepEqual(labels(items), ["Copy selection", "Copy", "Copy line"]);
  assert.equal(items[0].value, "a  b\n c");
  assert.equal(items[0].detail, "a b c");
});

test("nothing under the pointer is an empty menu, not a menu of nothing", () => {
  assert.deepEqual(itemsFor({}), []);
});

test("a long detail is shortened for display and copied whole", () => {
  const line = "x".repeat(200);
  const [item] = itemsFor({ line });
  assert.equal(item.value, line);
  assert.ok(item.detail.length <= 48);
});

test("every role maps to a function or to an explicit null", () => {
  for (const [role, offer] of Object.entries(OFFERS)) {
    assert.ok(offer === null || typeof offer === "function", role);
  }
});

test("a menu that fits opens at the pointer", () => {
  assert.deepEqual(place({ x: 100, y: 100, w: 200, h: 150, vw: 1000, vh: 800 }), { left: 100, top: 100 });
});

test("near the bottom-right corner it flips on both axes", () => {
  assert.deepEqual(place({ x: 990, y: 790, w: 200, h: 150, vw: 1000, vh: 800 }), { left: 790, top: 640 });
});

test("a flip that would leave the screen is clamped, on every path", () => {
  // Flipping above a pointer near the top of a short viewport is still off
  // screen. The clamp runs last, whatever the flip decided.
  assert.deepEqual(place({ x: 50, y: 60, w: 200, h: 150, vw: 1000, vh: 100 }), { left: 50, top: 4 });
  // A menu wider than the viewport pins to the margin rather than to a
  // negative offset.
  assert.deepEqual(place({ x: 10, y: 10, w: 400, h: 50, vw: 300, vh: 800 }), { left: 4, top: 10 });
});

test("a clipboard write that succeeds reports nothing", async () => {
  const written = [];
  assert.equal(await copy("abc", { writeText: async (t) => written.push(t) }), null);
  assert.deepEqual(written, ["abc"]);
});

test("a rejected clipboard write comes back as a sentence, not a rejection", async () => {
  const said = await copy("abc", {
    writeText: async () => {
      throw new Error("Document is not focused.");
    },
  });
  assert.match(said, /copy failed: Document is not focused/);
});

test("a shell with no clipboard says so", async () => {
  assert.match(await copy("abc", null), /no clipboard/);
});

test("perform routes an open to the opener and reports its refusal", async () => {
  const opened = [];
  const item = { act: "open", value: "https://example.com/" };
  assert.equal(await perform(item, { open: async (u) => opened.push(u) }), null);
  assert.deepEqual(opened, ["https://example.com/"]);
  const said = await perform(item, {
    open: async () => {
      throw new Error("no desktop opener found");
    },
  });
  assert.match(said, /could not open: no desktop opener found/);
});
