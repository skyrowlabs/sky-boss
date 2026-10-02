/* The one place the vendored modules are bound together, so nothing else
 * imports from `vendor/` and swapping either is a one-file change. */
import { h, render, Fragment } from "./preact.mjs";
import htm from "./htm.mjs";

export const html = htm.bind(h);
export { h, render, Fragment };
export * from "./hooks.mjs";
