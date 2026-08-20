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
  "x-tb-token": window.TB_TOKEN,
});

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: HEADERS(),
    body: JSON.stringify(body),
  });
  if (!response.ok && response.status !== 409) {
    throw new Error(`${path} → ${response.status}`);
  }
  return response.json();
}

export async function catalog() {
  const response = await fetch("/api/catalog", { headers: HEADERS() });
  if (!response.ok) throw new Error(`catalog → ${response.status}`);
  return response.json();
}

export function run(argv, timeout) {
  return post("/api/run", { argv, timeout });
}

export function watch(session, window, argv, interval) {
  return post("/api/watch", { session, window, argv, interval });
}

export function unwatch(session, window) {
  return post("/api/watch", { session, window, stop: true });
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
        headers: { "x-tb-token": window.TB_TOKEN },
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
