/* Everything the page knows how to say to the server.
 *
 * One module, on purpose. The whole point of putting the transport behind a
 * seam is that swapping the browser for a native webview later replaces this
 * file and nothing else — every other module talks to these functions rather
 * than to `fetch`.
 *
 * The token goes in a header rather than the URL. That is not decoration: a
 * cross-origin request carrying a custom header stops being a "simple request",
 * so the browser must preflight it, and the server never answers a preflight.
 * A form POST or an <img> cannot set a header at all. See cli/canvas/server.py.
 */

const HEADERS = () => ({
  "content-type": "application/json",
  "x-sb-token": window.SB_TOKEN,
});

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: HEADERS(),
    body: JSON.stringify(body),
  });
  /* 409 and 400 carry a body worth reading. 409 is a session the page has not
   * noticed died; 400 is a refusal with its reason in it — the bench shows
   * that reason, so throwing it away and reporting a status code would lose
   * the only useful half. */
  if (!response.ok && response.status !== 409 && response.status !== 400) {
    throw new Error(`${path} → ${response.status}`);
  }
  return response.json();
}

export async function catalog() {
  const response = await fetch("/api/catalog", { headers: HEADERS() });
  if (!response.ok) throw new Error(`catalog → ${response.status}`);
  return response.json();
}

/* What the operator declared about output, and what sky.boss already does with it.
 *
 * Fetched once when the bench opens rather than with the catalog, because the
 * canvas never needs it: the palette runs saved tools, and only the bench
 * *authors* one. Re-fetched on each open so editing `formats.toml` under a
 * running surface is the REPL, the same way the rules themselves are read at
 * use rather than cached. */
export async function vocabulary() {
  const response = await fetch("/api/vocabulary", { headers: HEADERS() });
  if (!response.ok) throw new Error(`vocabulary → ${response.status}`);
  return response.json();
}

export function run(argv, timeout) {
  return post("/api/run", { argv, timeout });
}

/* The bench's run ([[workbench]]). Not `run` with a flag: the server refuses
 * an act here, and a route that sometimes refuses `run` and sometimes does not
 * is a route with two contracts. A refusal comes back as 400 with a reason. */
export function trial(argv, timeout) {
  return post("/api/trial", { argv, timeout });
}

/* Re-shape a payload the bench already has, without re-running anything. A
 * view describes how to present data and never filters it, so which columns
 * are drawn is a question about the drawing — answering it by re-fetching
 * would also make every chip click compare against a different dataset.
 * See [[workbench]] round 2. */
export function shape(data, { cols, drop, rows } = {}) {
  return post("/api/shape", { data, cols, drop, rows });
}

/* Everything the bench can say about an argv without running it: the checks an
 * act gets instead of a trial run, whether the `--save` name is free, and the
 * `[tool.NAME]` block `run` cannot save by example. Runs nothing.
 * See [[workbench]] round 3. */
export function preflight(argv, { name, refresh } = {}) {
  return post("/api/preflight", { argv, name, refresh });
}

export function watch(session, window, argv, interval) {
  return post("/api/watch", { session, window, argv, interval });
}

export function unwatch(session, window) {
  return post("/api/watch", { session, window, stop: true });
}

/* A held-open stream ([[follow]]). The argv is sb-level — `follow -- …` or a
 * saved keyword — and the server resolves it, because expansions live on the
 * Click tree and nothing client-side keeps a command table. Re-POSTing for a
 * window that already follows is the restart affordance. */
export function follow(session, window, argv) {
  return post("/api/follow", { session, window, argv });
}

export function unfollow(session, window) {
  return post("/api/follow", { session, window, stop: true });
}

/* An accruing run ([[follow]] round 4). Same transport as `follow`, different
 * ending: a `run` or `read` whose lines arrive while it works and whose exit
 * is the verdict it was always going to produce, not a death.
 *
 * Not a mode on `run` for that route's own reason — one route that sometimes
 * returns an envelope and sometimes returns "watch the stream" is a route with
 * two contracts. A 400 here means the server will not accrue this argv, and
 * the caller falls back to `run`, which honours every sb-level flag by
 * running the real `sb`. */
export function accrue(session, window, argv) {
  return post("/api/accrue", { session, window, argv });
}

export function unaccrue(session, window) {
  return post("/api/accrue", { session, window, stop: true });
}

/* Create, replace or delete one saved command ([[tools]] round 4).
 *
 * The route rule 4 said would never exist. It exists because the argument
 * against it was wrong: a page past the guard already has `/api/run`, and one
 * arbitrary argv appends to tools.toml by itself — persistence was never on
 * this side of the boundary. What guards it is what guards everything here.
 *
 * Not `/api/run` with `--save` in the argv, which is what the bench did until
 * now: that path can only ever append and can only ever refuse a name that
 * exists, because it is `--save`, and `--save` saves by example. Editing and
 * deleting need a door that is not an example. */
/* `highlight` is deliberately absent: the bench composes `--highlight` into
 * the argv, so sending the field as well would apply the ruleset twice. The
 * route accepts it for a caller that wants the field form. */
export function writeTool({ name, argv, refresh, description, group }) {
  return post("/api/tools", { name, argv, refresh, description, group });
}

export function deleteTool(name) {
  return post("/api/tools", { name, delete: true });
}

/* Move one command between groups. Not `writeTool` with a different `group`:
 * that restates the whole tool, and the rail knows a command's `summary` — not
 * its `description` — so a round-trip through here would invent a description
 * equal to the expansion and drop any field the surface cannot see. This
 * changes one line. See [[tools]] round 6. */
export function regroupTool(name, group) {
  return post("/api/tools", { name, group, regroup: true });
}

/* Groups. A second door rather than a verb on `/api/tools`, because a group is
 * a different object with its own validator — and that route is shaped as a
 * whole tool, which a group is not. See [[tools]] round 6. */
export function writeGroup({ name, description }) {
  return post("/api/groups", { name, description });
}

export function deleteGroup(name) {
  return post("/api/groups", { name, delete: true });
}

/* What the surface remembers about itself between launches — currently which
 * tool groups are folded. A route rather than `localStorage` because `sb ui`
 * binds an ephemeral port every launch, so the page has a different origin
 * every time and per-origin storage is empty on arrival by construction. See
 * [[tools]] round 5.
 *
 * Both directions swallow their failure: a preference that cannot be read or
 * written costs the preference, never the rail. */
export async function prefs() {
  try {
    const response = await fetch("/api/prefs", { headers: HEADERS() });
    return response.ok ? await response.json() : {};
  } catch {
    return {};
  }
}

export function savePrefs(body) {
  return post("/api/prefs", body).catch(() => ({}));
}

/* Ends the whole surface. The window has no frame, so this is the close
 * button — and it is guarded like every other route, because ending your
 * session is a real effect and a page you did not open must not be able to
 * cause it. */
export function quit() {
  return post("/api/quit", {});
}

/* The session, as newline-delimited JSON over a streaming fetch.
 *
 * Not EventSource, which cannot set a request header and so cannot carry the
 * token — the one route where dropping the header would matter most is the one
 * EventSource would force us to drop it on.
 *
 * `onFrame` is called per frame; the returned function ends the session, which
 * is also what ends every watcher in it.
 */
export function stream(onFrame, onDown) {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch("/api/stream", {
        headers: { "x-sb-token": window.SB_TOKEN },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`stream → ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // A frame is a whole line. A chunk boundary lands mid-frame often
        // enough that parsing per chunk would be a bug that only shows up on a
        // large result.
        let cut;
        while ((cut = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, cut).trim();
          buffer = buffer.slice(cut + 1);
          if (line) onFrame(JSON.parse(line));
        }
      }
      onDown();
    } catch (error) {
      if (error.name !== "AbortError") onDown(error);
    }
  })();

  return () => controller.abort();
}
