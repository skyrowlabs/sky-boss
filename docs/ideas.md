# Ideas List

*Note: This is a list of potential ideas to add. Remove them if once spec'd or shelved*

*This file answers **should we build it**. Questions about something already being
built — decided, but not decided how — live in `docs/open.md`.*

- ~~watcher for cron jobs~~ — spec'd as [[file-follow]] round 2 (`sb follow --due 15m <path>`); the
  systemd half needs no code, see the doc
- ~~piping commands to claude or other agents~~ — answered: chaining needs nothing (`sb follow --
  claude -p …` already works, and a pipeline is a shell pipe). The inverse is spec'd as [[mcp]] —
  the tools offered to an agent over stdio
- ~~future runs (non crontab or systemd), `sb run` --delay=[seconds] [cmd]~~ — spec'd as [[delay]]
- ~~build in embedded scrolling for follow~~ — shipped as [[follow]] round 3. The inherited
  rejection relied on "scrollback and `less` already exist", which is false for a follow: a line
  pushed out of the visible frame was never printed anywhere
- an opt-in `--pty` for follow — **re-measured 2026-08-23 and the case is now half of what it was.**
  The buffering half is already fixed: `child_env(stream=True)` sets `PYTHONUNBUFFERED=1`
  ([[subprocess-env]] round 3), so a Python child streams line by line under sky.boss where a raw
  pipe holds everything to exit. For a *non*-Python tool `stdbuf -oL` works — measured on a C
  binary, 2.00s-all-at-once becomes 0.4s apart — and it needs no sky.boss feature at all, because
  `sb follow -- stdbuf -oL <cmd>` is an argv the operator can type and save. What is left is only a
  tool's **auto** colour (`git log --oneline` emits 0 escapes to a pipe, 80 with colour forced),
  bought at the cost of control sequences in the ring, resize handling, and the child believing it
  is interactive — which means pagers and progress bars. Weaker than it looked; shelve unless the
  colour alone is worth it
- ~~a log analyzer / view setup utility~~ — answered: lnav 0.14.0 headless already emits JSON (`lnav
  -n -q -c ';SELECT …' -c ':write-json-to -'`), so it is a `sb data --from json --` source and a
  saved tool, not a new command. Measured 2026-08-23
- ~~a richer result header (type, dimensions, size, modified, END OF DATA)~~ — split by owner: type
  and dimensions are in-band, spec'd as [[table-views]] round 4; the band and the terminator are
  out-of-band, spec'd as [[chrome]] round 3. `size`/`modified` were already on chrome's file cursor
  row. The leading `|` gutter is rejected — it breaks copy-paste and `sb read` is verbatim by
  contract
- ~~a centralized system to manage how six projects' agents work~~ — spec'd as [[roll-call]]
- ~~`--cols` naming a column that does not exist renders dashes rather than saying so~~ — fixed as
  [[table-views]] round 5; still drawn, now reported, in both renderers
- ~~two table tests inherit the ambient terminal width instead of pinning one~~ — fixed as
  [[table-views]] round 5. The suite is now clean from 40 to 300 columns; it had passed only at 80
  since it was written
- **a dock for a canvas window** — a toggle in the window's header bar collapses it to a small
  rectangle near the top of the canvas: the last full message, a little activity stat, and a
  visual alert when something changes. Untoggle puts it back. Raised 2026-08-30, from watching a
  follow window that only mattered when it moved.

  Two things worth knowing before this is spec'd. **The canvas has no window state between open
  and closed** — a header carries `＋tag`, `WRAP`, `⟳`, `✕` and nothing else — so a dock is the
  first one, and the question it really asks is whether that state belongs to the *window* or to a
  new strip that owns docked things. (The "keeps running while minimized" comment in `app.js` is
  about the page being hidden, not a window; it is not precedent.)

  **The alert is the hard half, and it is not a rendering problem.** A docked window is by
  definition the one nobody is looking at, so "no alert" has to mean *nothing happened* and never
  *nothing is arriving* — the same distinction a follow's `quiet` band makes, and the same one a
  dropped session breaks today. A calm dock over a dead stream is the worst version of this
  surface's oldest failure. Whatever answers that for the band answers it here first.

- a cheap model classifying a followed log — Haiku or similar watching a stream and tinting by what
  a line *means* rather than what shape it has. **Two versions, and the rules already written
  separate them.** *Inline* — a model in the render path, per line — loses three ways. It is a
  judgment, and [[highlight]] round 3 settled whose judgment counts: sky.boss ships none, the
  operator declares theirs in `formats.toml`, and a model is a third party that rule has no slot
  for. `marks()` is pure because the frontend has no test runner and two renderers holding their
  own opinions would drift; a model in there means the same line tints differently twice, and
  `spans()` joining back to exactly the text stops being provable. And a round trip per line puts a
  stalled API where a quiet log should be — *worked fine, told nobody*, byte for byte. Two further
  costs are constitutional: sky.boss would hold a credential for the first time, against the rule
  that keeps a future agent surface safe to expose, and a log is the likeliest place on the machine
  for a token or an internal hostname, so every followed line becomes egress.

  **The version worth building inverts the unit.** A log is repetitive — an hour of a chatty stream
  is tens of thousands of lines and perhaps forty distinct shapes, so classifying line 30,000 pays
  to re-derive an answer already bought. Sample the log once, have the model draft the
  `[highlight.<name>]` block in the schema `check_rules()` already validates, write it through the
  same spliced path the tools rail uses, and never call a model again. Deterministic at read time,
  no per-line cost or latency, one sample leaves the machine instead of the whole stream, and the
  operator reads and edits the block before it ever runs — so it is their opinion after all,
  drafted rather than authored, which satisfies the round-3 rule instead of dodging it. Absent
  model, key or network degrades to no ruleset, which is today. Costed 2026-08-30 against Haiku
  4.5's $1/$5 per MTok: per line with a cached prefix is a few dollars an hour per followed log,
  batched a hundred at a time is under one, and once-per-log is a rounding error — four orders of
  magnitude, which is the whole argument. Use a stronger model for that one call; cost stops
  mattering when it happens once.

  **This is [[highlight]] round 5**, where round 3's declaration gets a drafting assistant. The
  inline version belongs to [[open]] item 13 — the governor is already LLM narration over a log,
  and already owes the same four answers: who calls it, on what cadence, against what budget, and
  what it shows when the model cannot run
