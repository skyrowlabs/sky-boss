---
status: active
created: 2026-08-21
updated: 2026-08-22
agent_value: 3
key_files:
  - cli/filefollow.py
  - cli/follow.py
  - cli/resident.py
  - cli/keys.py
  - cli/canvas/server.py
  - tests/test_filefollow.py
  - tests/test_canvas_stream.py
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
the terminal, the resident loop owns its own tick, and `q`, `Esc` or Ctrl-C ends it — amended
2026-08-22 by [[follow]] round 2, which owns the leaving contract for both follow forms.

**The status line is the feature.** `following · last write 19:00 (3m ago) · 198 KB` — quiet
and dead are different words because the loop stats the file. It renders through the [[chrome]]
contract — the cursor supplies the facts (stat clock, size, absent/rotated/quiet), the chrome
draws them. Frames to the canvas carry *appended lines*, not the whole ring; the window appends
and trims.

**Bounded.** The ring holds the last N lines (default 200, `--lines` to change); the file
remains the scrollback of record. Same rule as every result here — no single window renders
unbounded.

**A read, and savable.** `follow` observes; a keyword whose argv starts with `follow` inherits
that through the standard [[tools]] rule. ANSI is stripped, never interpreted, per
[[text-reads]].

**Does not do:**

- **Does not parse, filter, or judge lines.** Verbatim lines only. The cron.log evidence is the
  argument: timestamped lines, untimestamped `[isolation]` lines, blank spacers, multi-line
  blocks — any structure inferred here would be silently wrong. Highlighting and the delta view
  are Rule branches that bind *onto* this loop later; they are not this loop.
  *(Amended 2026-08-22 by [[highlight]], narrowly: recognition-for-tinting is permitted —
  marks ride beside the verbatim text and a missed match costs a color, not a fact. Parsing,
  filtering and judging stay refused; the argument above stands for structure.)*
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

- [x] **The cursor, pure.** A `FileCursor` (module beside `cli/follow.py`) over an injectable
      clock and filesystem: backfill, advance, quiet, rotation, truncation,
      absent-then-appearing. Tests assert the mechanism, never the timing — no sleeps, no
      tmp-file races; the fs is a fake.
- [x] **`tb follow <path>` in the terminal.** Resident rendering with the status line and ring;
      `--lines`; Ctrl-C exits cleanly. Absent and rotated states visible. The path form's help
      and example live in `follow`'s `--help` beside the process form — the [[refresh]] help
      test enforces it from birth.
- [x] **The canvas window.** A stream-framed window kind on the session stream: append frames,
      the liveness clock in the chrome, absent/rotated/quiet states. Follow windows get no
      cadence picker — they are resident by nature, and only snapshot reads get cadences.
- [x] **Keywords and docs.** `argv[0] == "follow"` with a path loads and inherits observe; the
      palette offers it; CLAUDE.md's command table gains the row.

### Round 2 — late is a word the operator earns (2026-08-22)

From the ideas list: *"watcher for cron jobs."* The trap in that sentence is thinking it needs a
crontab parser. It does not, and it must not have one.

**A schedule is a declaration; a run is evidence.** `crontab -l` tells you what is *supposed* to
happen. Whether it happened is a different fact, living in a log. The interesting product is the
join — and for systemd it already exists: `systemctl list-timers` has done it for you (LAST,
NEXT, PASSED), so that half is a `formats.toml` entry and **no code at all**:

    tb data --from timers -- systemctl list-timers --output=json

**Cron is the gap precisely because it keeps no ledger.** The only evidence a cron job ran is
what it printed, which is a file, which this doc already follows. So the cron watcher is not a
new command. It is one word added to a cursor that already knows almost everything it needs:

    tb follow --due 15m tmp/reporting/cron.log

Today the band says `quiet 3m` — knowledge, from a `stat`, not a guess from silence. That is the
whole feature of this doc, and it stops one step short of the question actually being asked,
which is *"is that bad?"* tb cannot know. **The operator can, and `--due` is where they say it.**
Given an expectation, quiet 3m of 15m is *fine* and quiet 47m is **late**, and the difference is
arithmetic rather than judgment.

**It is a word on a band, and nothing else.** No alert, no exit code, no notification, no
re-running anything. A follow is resident and observes; lateness is a fact it displays, and the
moment it *acts* on that fact tb has become a monitoring system that pages you, which is a
different product with a different failure mode.

**Both follow forms take it**, because both already carry the clock it needs: the cursor has
`last_write_at` from its `stat`, the process stream has `last_line_at` from its ring. A
long-running job that stops printing is the same question as a log that stops growing, and
answering it in one place and not the other would be an asymmetry with no argument behind it.

**Nothing new travels to the canvas.** `attention` is already in the chrome facts and already
reaches a window; `late` is a new value in a slot that exists. The saved-command side is free
too — a tool's argv carries `--due 15m` like any other flag, so `[[tools]]` needs no field.

**Does not do:**

- **No crontab parsing, ever.** tb does not read `crontab -l`, does not compute a next-run time
  and does not know what a schedule is. The operator asserts an interval; tb subtracts.
- **No alerting or escalation.** Not an exit code, not a notification, not a webhook. If a late
  log should page someone, that belongs to something whose job is paging.
- **No expectation about content.** Lateness is time. "The log ticked but said the wrong thing"
  is a Rule-branch question and belongs to [[highlight]]'s declared patterns.
- **No history.** A follow shows what is happening now; "how often was it late last week" is a
  report, and reports are what the tools tb watches already write.

- [x] **A duration is a shared parser.** `15m`, `2h`, `90s` → seconds, in `cli/helpers.py`,
      because [[delay]] needs the identical spelling and two parsers for one syntax is how they
      start disagreeing. Rejects anything else loudly, at parse time, not at first tick.
- [ ] **`late` in the chrome contract.** `Chrome` gains the declared interval for a cursor and a
      stream, `attention` gains `late`, and the band says which — `quiet 3m of 15m` against
      `late 47m, due 15m`. Pure, over an injected clock, per [[chrome]].
- [ ] **`--due` on `tb follow`**, both forms, passed to the cursor and the stream alike.
- [ ] **The canvas wears it** with no new plumbing — proven by a test that the frame's chrome
      carries `late`, not by adding a field to the wire.

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

### Round 1 — executed (2026-08-21)

What the execution argued back:

- **Rotation and truncation announcements live in the ring**, as lines marked with the stderr
  tag — the cursor's own voice, tinted like a process's stderr, without plumbing a third
  channel. The alternative was chrome-only announcement, and an event that scrolls with the
  lines it interrupted is worth more than one that vanishes on the next state change.
- **The backfill is bounded at 256 KiB** and drops the fragment at the cut — following a
  gigabyte log opens by reading its tail, and a file that *appears* already huge under a
  waiting cursor gets the same treatment.
- **Truncation wears the `rotated` attention word.** It is the same class of event — the
  history you were reading is gone, the cursor started over — and a fourth word would have
  widened the chrome vocabulary for a distinction the announcement line already makes.
- **On the canvas, the cursor is a follower like any other.** One interface (`fresh`, `lines`,
  `exit_code`, `kill`) covers both mechanisms; the server ticks a cursor off the event loop
  because stat blocks, and a *state change with no new lines* still frames out — a window
  whose file vanished must not keep saying quiet. `exit_code` is permanently None: a file
  never dies, absent is a state to wait out.
- **A CLI test blocked the suite once**: invoking the real path form under CliRunner enters
  the residency and never returns — which is what resident-by-nature means. Dispatch is
  proven by interception, the residency by driving `follow_file` with a fake fs, injected
  clock and a tick bound. The suite stays at two and a half seconds.
- Verified live end-to-end through the canvas: backfill arrived `quiet`, growth arrived
  `running`, a `mv`-rotation arrived announced with the new file's tail, and the quiet frames
  in between carried chrome only.

### 2026-08-22 — the boundary, amended by [[highlight]]

The first Rule-branch rung landed: followed lines now carry lexical tint — a leading
timestamp muted, a positional `[tag]` in the accent, a URL in the path role — computed by one
pure rule set in `cli/highlight.py` and applied by both terminal forms and the canvas. The
amendment is recognition-for-tinting only: lines stay verbatim, unfiltered, unordered, and
the "does not parse, filter, or judge" argument above stands untouched for structure. The
cursor's own voice (rotation, truncation) keeps its warn tint; highlight never re-tags it.

### 2026-08-22 — how it is left, and where it draws, moved to [[follow]]

The cursor loop changed shape without changing what it does. Round 1's *"Ctrl-C exits cleanly"*
is now *"`q`, `Esc` or Ctrl-C"*, and the frame is drawn **inline below the prompt** by default
rather than on the alternate screen — `--screen` keeps the old behaviour. Both follow forms
took the change together, because they are one command with one way out, and **[[follow]] round
2 is where that contract is recorded**: it is the doc that wrote down "Ctrl-C leaves (and
kills)", so it is the doc that reverses it. Read it for the reasoning, including the one place
the two forms genuinely differ — leaving a process kills its child, leaving a file lets go of an
offset.

The mechanical consequence here: `follow_file` takes a `wait` where it took a `sleep`, and the
loop, the frame clipping and the body assembler are now shared with the process form through
`cli/resident.py`. The clip keeps the **tail** — a log's interesting end is its newest line, and
the ring outruns the terminal on every frame.

### Round 2 — drafted, awaiting the word (2026-08-22)

Drafted from the ideas list rather than from a defect, which makes the scoping the whole job. The
sentence was "watcher for cron jobs" and the first three shapes it suggests are all wrong for
this project: a crontab parser (tb inferring a schedule), a health checker (tb judging), and a
notifier (tb acting on its own initiative). Each is refused by a rule that already exists.

What survives is small enough to be almost embarrassing: **one flag, one new word in a slot that
already exists, and a subtraction.** That is the sign it is the right shape here — the cursor
already knew how long the file had been quiet and already had somewhere to put a verdict; what
it lacked was the one number only the operator has.

The systemd half being free is worth stating loudly, because it is the strongest evidence for
the [[capture]] design: a whole class of "watch my scheduled jobs" is answered by a declared
format over a command that has already done the join, with no code shipped at all.

