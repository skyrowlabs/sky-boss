---
status: draft
created: 2026-08-21
updated: 2026-08-21
agent_value: 2
key_files: []
---

# Following a file — the native cursor

## Why

The mission (`docs/design/fundamentals.md`) is following work as it happens — especially agentic
work — and the concrete driver is jam.sense's `tmp/reporting/cron.log`: agent runs write there
around the clock, and nothing in tb can hold a growing file open. The closest approximation,
`tb read -- cat …` on a cadence, re-reads the whole file every tick, renders the wrong end of it,
and cannot answer the only question that matters mid-run: *is anything happening?*

That question is harder than it looks, because the log's silences are meaningful. A line like
"handing to 'claude' (no output until it finishes; ceiling 90 min)" is followed by up to ninety
minutes of nothing *while everything is fine*. A surface that cannot distinguish "quiet" from
"dead" turns the normal case into a permanent false alarm.

**Why a native loop and not a spawned `tail -F`:** the constitution first routed files through
the process stream as `tail -F <path>` — one primitive, zero special cases — and reversed it the
same day, because the improvements a file follow needs are made of file knowledge a spawned tail
cannot see. tb can *stat* the file, so the liveness clock can say "file untouched since 19:00"
rather than merely "no new lines arrived". Rotation and truncation are detected by inode and
size rather than inherited from tail's flavor. Backfill-then-follow is one mechanism instead of
a flag. The reversal and its original reasoning are recorded in the constitution; this doc
builds the reversed form. **The file cursor owns files; the process stream ([[follow]]) owns
commands.**

**One verb fronts both.** This mechanism surfaces as `tb follow <path>` — not as a `watch`
command — because `-f` *is* `--follow` in tail, journalctl, docker and kubectl, and a second
verb fought that muscle memory in the operator's own hands during spec review. [[follow]] owns
the command registration and the dispatch rule; this doc owns the file mechanism behind the
path form. `watch` is reserved for the future change-detection rule.

## Shape

`tb follow <path>` — resident by nature, in both renderings.

**The cursor.** Open, stat, seek: backfill the last N lines into the ring, remember the byte
offset. Each tick, stat again and compare:

- *Grown* → read from the offset, emit whole lines. A partial final line is held until its
  newline arrives — never emitted half.
- *Same* → update the quiet clock. This is the state the status line exists for.
- *Shrunk, or a different inode* → truncation or rotation. Say so in the stream, then start over
  from the new file's tail. Rotation is an event worth seeing, not a condition to paper over.
- *Absent* → "waiting for it to exist", and begin at offset zero when it appears. A log that has
  not had its first write yet is a legitimate thing to follow — refusing it would make the
  command unusable at exactly the moment a new job is first wired up.

**The tick rides what exists.** On the canvas, the poll is driven by the same Python-side,
connection-keyed clock every watcher uses ([[canvas]]) — the cursor pauses when its window
closes and keeps running while it is merely minimized, and nothing survives the last window. In
the terminal, the resident loop owns its own tick and Ctrl-C ends it.

**The status line is the feature.** `following · last write 19:00 (3m ago) · 198 KB` — quiet
and dead are different words because the loop stats the file. It renders through the [[chrome]]
contract — the cursor supplies the facts (stat clock, size, absent/rotated/quiet), the chrome
draws them. Frames to the canvas carry *appended lines*, not the whole ring; the window appends
and trims.

**Bounded.** The ring holds the last N lines (default 200, `--lines` to change); the file
remains the scrollback of record. Same rule as every result here — no single window renders
unbounded.

**A read, and savable.** `follow` observes; a keyword whose argv starts with `follow` inherits
that through the standard [[toolbox]] rule. ANSI is stripped, never interpreted, per
[[text-reads]].

**Does not do:**

- **Does not parse, filter, or judge lines.** Verbatim lines only. The cron.log evidence is the
  argument: timestamped lines, untimestamped `[isolation]` lines, blank spacers, multi-line
  blocks — any structure inferred here would be silently wrong. Highlighting and the delta view
  are Rule branches that bind *onto* this loop later; they are not this loop.
- **Does not use inotify.** The poll rides ticks that already exist and costs one `stat` when
  nothing changed. Event-driven wakeups are an optimization with a portability bill; earn them
  with a real latency complaint first.
- **Does not restart, persist, or daemonize.** The offset dies with the window; reopening
  backfills fresh. Nothing survives the last window.
- **Does not follow directories, globs, or multiple files.** One file per window. Directory
  events, when wanted, are `inotifywait -m` under the process form ([[follow]]).
- **Does not reach over the network.** Local paths only. A remote log is
  `tb follow -- ssh host tail -F …`, where the ssh process owns the remoteness.

## Phases

### Round 1 — the cursor and the path form (2026-08-21)

- [ ] **The cursor, pure.** A `FileCursor` (module beside `cli/follow.py`) over an injectable
      clock and filesystem: backfill, advance, quiet, rotation, truncation,
      absent-then-appearing. Tests assert the mechanism, never the timing — no sleeps, no
      tmp-file races; the fs is a fake.
- [ ] **`tb follow <path>` in the terminal.** Resident rendering with the status line and ring;
      `--lines`; Ctrl-C exits cleanly. Absent and rotated states visible. The path form's help
      and example live in `follow`'s `--help` beside the process form — the [[refresh]] help
      test enforces it from birth.
- [ ] **The canvas window.** A stream-framed window kind on the session stream: append frames,
      the liveness clock in the chrome, absent/rotated/quiet states. Follow windows get no
      cadence picker — they are resident by nature, and only snapshot reads get cadences.
- [ ] **Keywords and docs.** `argv[0] == "follow"` with a path loads and inherits observe; the
      palette offers it; CLAUDE.md's command table gains the row.

## Notes

### Round 1 — written as spec, from the constitution (2026-08-21)

Specced before any code, out of the fundamentals pass that treated the built surface as concept.
The evidence that shaped it: 198 KB of live cron.log, whose silences run to ninety minutes by
design ("no output until it finishes"), whose lines are deliberately non-uniform, and whose
authorship is exactly the agentic work the app exists to follow. The tail-`F`-as-sugar design
was recorded and reversed inside one day — the reversed reasoning lives in
`docs/design/fundamentals.md` and is summarized in Why so nobody re-proposes the spawned tail
without meeting the stat argument first.

**Renamed the same day it was specced.** This doc began life as `watch.md`, the command as
`tb watch <path>`. The operator's review probe (`tb follow -- jam pr list --refresh 60`)
demonstrated the naming fighting Unix muscle memory — `-f` is `--follow` everywhere, for files
and commands alike — so one verb now fronts both mechanisms and this doc's slug became
`file-follow`. The mechanism was not touched; only its name on the surface.
