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

- an estate-currency view — **which declared projects are behind their scaffold, and by how
  much.** Raised 2026-09-05 by jam.sense's session after skeletor declined to build it, and the
  refusal is the reason it lands here: a sibling glob inside skeletor would bake one workspace's
  home layout into a tool other people run, and on any machine laid out differently it enumerates
  zero trees and reports "nothing is behind" forever — permanently green and worth nothing. That
  is the same leak class [[state-root]] names, one level up. `$SB_HOME/projects.toml` has no such
  problem: it is operator-owned, outside every repo, and already declares each project and its
  `cwd`. It is an adopter list nobody has to guess at, and the guessing is the part skeletor is
  right to refuse.

  **The obvious source is the wrong one, and wrong in the direction that looks fine.** A tree's
  `.skeletor.json` records `skeletor_ref` — the ref it was *scaffolded* at — and the manifest is
  only rewritten by a run that applies something, so a tree current through four releases still
  reports the day it was made. Reading that field alone answers the question backwards. The
  authoritative form is `skeletor-upgrade <tree> --dry-run --json`, which emits `base_ref` and
  `head_ref` as separate fields so that currency is never inferred from one string, writes
  nothing, and is never refused. Measured over five trees, the ref ordering and the work ordering
  disagree: one repo a single minor behind had the most friction and another two minors behind
  needed one file. **Behind by a ref and behind by a file are different things and only the second
  is work** — which is a fact about a provider's answer, so sky.boss reports both and ranks
  neither. `render_dirt` is a third field and not a synonym for the `-dirty` suffix inside
  `head_ref`: one asks whether unversioned content reaches the render, the other whether the
  checkout is modified at all. Same spelling, two questions, and a consumer filtering on the
  suffix inherits both of the string's errors silently.

  **Two sources, not one, and this repo is the proof.** `skeletor-upgrade` answers only for a tree
  with a `.skeletor.json`. sky.boss has none and will not — it consumes components, recorded in
  `.skeletor-components.json`, where the question is `skeletor-components report`. Those answer
  genuinely different things: *does this tree still reproduce a render*, versus *has anything I
  copied moved since*. A view that ran only the first would report its own author as absent.

  Unresolved, and the reason this is an idea rather than a plan: it is a **third** provider shape
  next to [[roll-call]]'s argv and path, and one whose answer is about a *relationship* between
  two repos rather than about the project itself. Whether that belongs in `sb roll-call`, in a
  command of its own, or nowhere is the question. The inverse proposal is also open — skeletor
  emitting a declaration of where a repo's truth lives, so `projects.toml` stops being hand-typed
  — and the two are complementary: this one works today and covers only adopters, that one needs
  a template change and covers every repo
