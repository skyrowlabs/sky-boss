/* The entry point: the one place the surface touches the DOM on import.
 *
 * Everything else in `static/` is importable outside a browser, which is what
 * lets `npm test` reach the pure logic — see [[canvas]] round 12. Keeping that
 * true means anything with a side effect at module scope belongs here and
 * nowhere else. This file is deliberately two lines long.
 */
import { html, render } from "./vendor/htm-preact.js";
import { App } from "./app.js";

render(html`<${App} />`, document.getElementById("root"));
