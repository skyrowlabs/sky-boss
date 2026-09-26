/* The window body's right-click menu — [[canvas]] round 15.
 *
 * **The page detects nothing.** What a span *is* was decided in Python by
 * `skyboss/highlight.py` and arrives as its `mk-<role>` class; this reads the
 * class and offers what `OFFERS` says that role gets. A regex here deciding
 * whether something is a link would be the second opinion the one-rule-set
 * design exists to prevent, so a shape the highlighter does not recognise
 * gets no item — a missed match costs a menu entry, exactly as it already
 * costs a colour.
 *
 * Split the way round 12 split the frontend: `itemsFor`, `place` and `copy`
 * are pure, so `node --test` reaches every decision; `contextOf` and `Menu`
 * touch the DOM and do nothing at import.
 */
import { html, useEffect, useLayoutEffect, useRef, useState } from "./vendor/htm-preact.js";
import { openLink } from "./api.js";

/* Every role `markedLine` can put on a span, and what the menu makes of it.
 *
 * **Keyed by every role, including the ones that get nothing**, so a role is
 * a decision rather than an omission. `tests/test_canvas_server.py`
 * enumerates the roles off the Python rules and fails on one missing here —
 * a hand-written list would go quiet the week [[highlight]] adds a shape.
 *
 * A copy item names the text it will copy rather than calling it a
 * *location*: `mk-path` is also a code span and a SCREAMING constant, because
 * a role is a colour and all three wear the same one. */
export const OFFERS = {
  path: (text) => [{ label: "Copy", detail: text, act: "copy", value: text }],
  url: (text) => [
    { label: "Copy link", detail: text, act: "copy", value: text },
    { label: "Open link", detail: "ctrl-click", act: "open", value: text },
  ],
  ref: (text) => [{ label: "Copy", detail: text, act: "copy", value: text }],
  muted: null,
  accent: null,
  num: null,
  ok: null,
  fail: null,
  warn: null,
  bold: null,
};

const SHORT = 48;
const shorten = (text) => {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > SHORT ? `${flat.slice(0, SHORT - 1)}…` : flat;
};

/* The items for one right-click, from what is under the pointer.
 *
 * `roles` are the span's own mark roles — `["bold", "path"]` for a composite —
 * and the first one that offers anything wins. Selection first, because a
 * selection is the operator saying exactly what they meant; the whole line
 * last, because it is the widest guess. */
export function itemsFor({ selection = "", line = null, roles = [], text = null } = {}) {
  const items = [];
  if (selection) {
    items.push({ label: "Copy selection", detail: shorten(selection), act: "copy", value: selection });
  }
  if (text) {
    const role = roles.find((r) => OFFERS[r]);
    if (role) items.push(...OFFERS[role](text));
  }
  if (line) items.push({ label: "Copy line", detail: shorten(line), act: "copy", value: line });
  return items;
}

/* Where a menu of size w×h opened at (x, y) goes in a vw×vh viewport.
 *
 * Flipping is the preference and clamping is the contract ([[schedule]]
 * round 6): a menu flipped above a pointer near the top is still off screen,
 * so the clamp runs last and on every path, not only on the ones that needed
 * the flip. */
export function place({ x, y, w, h, vw, vh, margin = 4 }) {
  let left = x + w > vw - margin ? x - w : x;
  let top = y + h > vh - margin ? y - h : y;
  left = Math.max(margin, Math.min(left, vw - w - margin));
  top = Math.max(margin, Math.min(top, vh - h - margin));
  return { left, top };
}

/* Write to the clipboard and say whether it worked.
 *
 * Awaited, and a rejection comes back as a sentence rather than as an
 * `unhandledrejection` — which is where a failure inside a click handler
 * would otherwise go, with the menu closing as though it had worked.
 * *Failed, told nobody.* */
export async function copy(text, clipboard = globalThis.navigator && globalThis.navigator.clipboard) {
  if (!clipboard || !clipboard.writeText) return "this window gives the page no clipboard";
  try {
    await clipboard.writeText(text);
    return null;
  } catch (error) {
    return `copy failed: ${(error && error.message) || error}`;
  }
}

/* Carry out one item. Returns a sentence on failure, null on success. */
export async function perform(item, { write = copy, open = openLink } = {}) {
  if (item.act === "copy") return write(item.value);
  if (item.act === "open") {
    try {
      await open(item.value);
      return null;
    } catch (error) {
      return `could not open: ${(error && error.message) || error}`;
    }
  }
  return `nothing knows how to ${item.act}`;
}

/* What is under the pointer, read off the DOM. The only DOM-reading half. */
export function contextOf(target, selection = "") {
  const element = target && target.nodeType === 1 ? target : target && target.parentElement;
  const ln = element && element.closest(".ln");
  const mark = element && element.closest("[class*='mk-']");
  const inLine = ln && mark && ln.contains(mark);
  return {
    selection,
    line: ln ? ln.textContent : null,
    roles: inLine
      ? [...mark.classList].filter((c) => c.startsWith("mk-")).map((c) => c.slice(3))
      : [],
    text: inLine ? mark.textContent : null,
  };
}

/* The link a ctrl-click landed on, or null. Same rule as the menu: the class
 * says it is a link, or it is not one. */
export function linkAt(target) {
  const element = target && target.nodeType === 1 ? target : target && target.parentElement;
  const link = element && element.closest(".mk-url");
  return link ? link.textContent : null;
}

export function Menu({ at, items, error: given = null, onClose }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);
  const [error, setError] = useState(given);
  const [busy, setBusy] = useState(false);

  /* Measured after layout and placed before paint, so the menu is never seen
   * at an unclamped position. Re-placed when an error line changes its size. */
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    const r = node.getBoundingClientRect();
    setPos(place({ x: at.x, y: at.y, w: r.width, h: r.height, vw: innerWidth, vh: innerHeight }));
  }, [at.x, at.y, error, items]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && onClose();
    const onAway = () => onClose();
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown, true);
    window.addEventListener("resize", onAway);
    window.addEventListener("blur", onAway);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown, true);
      window.removeEventListener("resize", onAway);
      window.removeEventListener("blur", onAway);
    };
  }, [onClose]);

  const choose = async (item) => {
    setBusy(true);
    const problem = await perform(item);
    setBusy(false);
    if (problem) setError(problem);
    else onClose();
  };

  const style = pos
    ? `left:${pos.left}px;top:${pos.top}px`
    : `left:${at.x}px;top:${at.y}px;visibility:hidden`;
  return html`
    <div class="ctx-menu" ref=${ref} style=${style} role="menu" onContextMenu=${(e) => e.preventDefault()}>
      ${items.map(
        (item) => html`<button
          class="ctx-item"
          role="menuitem"
          disabled=${busy}
          onClick=${() => choose(item)}
        >
          <span class="ctx-label">${item.label}</span>
          ${item.detail && html`<span class="ctx-detail">${item.detail}</span>`}
        </button>`
      )}
      ${error && html`<div class="ctx-error">${error}</div>`}
    </div>
  `;
}
