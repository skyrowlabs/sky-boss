/* One window, doing the least that proves the pipe.
 *
 * This is a stub and is meant to be thrown away. The renderer that belongs
 * here is cli/canvas/static/render.js — 418 lines that already know how to
 * draw the `view` envelope, and which carry the one rule worth keeping across
 * every substrate this surface has had: **no single result may render
 * unbounded.** The terminal froze for that, then a browser tab died of it, and
 * `MAX_ROWS` / `MAX_CHARS` are where the lesson lives. A window is not
 * exempt. Port render.js before showing this to anything real.
 *
 * What this file does demonstrate is the shape: a window is addressed by the
 * main process, a command is a window rather than a div, and nothing here has
 * ever seen the token or the port.
 */

const root = document.getElementById("root");
const title = document.getElementById("title");

document.getElementById("close").onclick = () => window.sb.close();

window.sb.onDown((error) => {
  root.innerHTML = "";
  const p = document.createElement("p");
  p.className = "down";
  // A dead session is said, never blank. `roll-call` refuses to render a
  // missing project as an empty row for the same reason: unreachability is
  // visible, staleness is not.
  p.textContent = `session down${error ? ` — ${error}` : ""}`;
  root.append(p);
});

function show(label, payload) {
  title.textContent = label;
  root.innerHTML = "";
  const pre = document.createElement("pre");
  // The envelope, verbatim. render.js is what turns this into a table; until
  // it is ported, showing the raw shape is at least honest about being a stub.
  pre.textContent = JSON.stringify(payload, null, 2);
  root.append(pre);
}

/* The palette. Not a command table — the list comes off the live Click tree,
 * which is the whole reason the canvas cannot offer a command that does not
 * exist. Nothing here writes a name down. */
async function palette() {
  title.textContent = "sky.boss";
  const { commands } = await window.sb.catalog();
  root.innerHTML = "";
  for (const command of commands) {
    const button = document.createElement("button");
    button.className = "cmd";
    button.innerHTML =
      `<code>${command.name}</code> ` +
      `<span class="sum">${command.summary}</span>` +
      (command.acts ? ` <span class="acts">acts</span>` : "");
    // A command opens a window. In the canvas this appended a div to the same
    // document; here it asks the desktop, and the window manager places it.
    button.onclick = () => window.sb.open(command.argv);
    root.append(button);
  }
}

/* A command's own window. */
async function command(argv) {
  const label = argv.join(" ");
  title.textContent = label;
  root.textContent = `running ${label}…`;

  // Frames addressed to this window arrive here and nowhere else — main.js
  // routes on `frame.window`, and this window's id was never guessable from
  // inside the page because the page was never told anyone else's.
  window.sb.onFrame((frame) => {
    if (frame.type === "run") show(label, frame.result);
    if (frame.type === "stream") show(label, frame);
  });

  show(label, await window.sb.run(argv));

  // Only a read may be given a cadence. The catalog carries `acts` precisely
  // so a surface cannot offer a refresh on a write, and this stub honours it
  // by asking for nothing at all — wiring the interval picker is where the
  // real window starts.
}

window.sb.ready().then(({ argv }) => (argv ? command(argv) : palette()));
