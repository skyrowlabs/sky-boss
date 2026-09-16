# Ideas List

*This file answers **should we build it**. Questions about something already being
built — decided, but not decided how — live in `docs/open.md`; once somebody has
decided **how**, it becomes a plan in `docs/TODO/`. See
[`README.md`](README.md) for the three boundaries.*

*An entry is **struck through with a pointer**, never removed. The instruction here
used to read "remove them once spec'd or shelved" and the file had never once obeyed
it — every resolved entry below names where it went, which is the half worth keeping:
a deleted memo is an invitation to buy the same investigation twice. Moved from
`docs/ideas.md` on 2026-09-07; `[[ideas]]` is unchanged.*

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
- ~~a dock for a canvas window~~ — *moved 2026-09-16 → [[open]] item 23. The blocker named below
  was discharged on the day this entry was written, and neither document noticed.* A toggle in the
  window's header bar collapses it to a small rectangle near the top of the canvas: the last full
  message, a little activity stat, and a visual alert when something changes. Untoggle puts it
  back. Raised 2026-08-30, from watching a follow window that only mattered when it moved.

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

  **The precondition is discharged, recorded 2026-09-16.** The band was answered by [[canvas]]
  round 10 — [[open]] item 22, closed 2026-08-30, the same day this entry was raised: a window has
  to carry its own doubt, and `quiet` over a dead stream is an affirmative false claim rather than
  information that has merely gone stale. **Both were written the same day and neither points at
  the other**, which is this file's own pointer rule failing between two documents instead of
  inside one — and it is the harder direction, because an entry that names a live blocker reads as
  more credible the longer the blocker has been dead. What is still open is the *how*: whether dock
  state belongs to the window or to a new strip that owns docked things. That is a `docs/open.md`
  question, not a plan.

- ~~a cheap model classifying a followed log~~ — **ruled 2026-09-16 on the operator's word, and
  split three ways.** *Phase A → [[highlight]] round 8, reopened into `docs/TODO/` to take it.
  Phases B and C stay here, below, as the record of what was deliberately not taken.* Haiku or
  similar watching a stream and tinting by what a line *means* rather than what shape it has. **Two versions, and the rules already written
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

  ~~**This is [[highlight]] round 5**, where round 3's declaration gets a drafting assistant.~~
  **It is round 8 — corrected 2026-09-16, and the correction is worth more than the number.**
  Round 5 shipped 2026-08-29 as *weight instead of hue*, and rounds 6 and 7 shipped after it — so
  the number was spent, twice overtaken, and still being claimed here.
  [[highlight]] itself contains no mention of a model, a sample or a drafted ruleset, so the
  forward declaration was **never received** — a pointer into another document is a claim about
  that document, and nothing checks it the way `tests/test_docs.py` checks that the slug resolves.
  The inline version belongs to [[open]] item 13 — the governor is already LLM narration over a log,
  and already owes the same four answers: who calls it, on what cadence, against what budget, and
  what it shows when the model cannot run.

  **And one question looked like it decided whether this can be a plan at all: who holds the
  credential.** The costs listed above put *"sky.boss would hold a credential for the first time"*
  under the inline version, but the once-per-log version calls a model too — one call rather than
  thousands, which cuts the egress and the latency and does nothing whatever to the credential.
  `CLAUDE.md` lists that under considered-and-deliberately-rejected: **external CLIs keep their own
  authentication**, sky.boss is never in the credential path, and that is what keeps a future
  [[mcp]] surface safe to expose. The escape is already in this file, in the *piping commands to
  agents* entry near the top: `sb follow -- claude -p …` works today, so an argv that shells out to
  a provider's own CLI puts the key on the far side of the boundary and the rule is satisfied
  rather than dodged.

  **Ruled 2026-09-16 on the operator's word: never hold a key — and note that the credential was
  not the binding gate.** Checking the tree rather than this paragraph turned up three premises
  that do not hold, and the first of them blocks more than the credential does:

  - **There is no spliced write path for `formats.toml`, and the entry above assumes one.** `backup`,
    `write_block` and `set_field` all live in `skyboss/tools.py` and are bound to `tools.toml`;
    every `formats.toml` reference in `skyboss/` is a **read**. So *"write it through the same
    spliced path the tools rail uses"* names a path that does not reach this file.
  - **[[highlight]] round 5 ruled that out on purpose**, in its own *Does not do*: `tools.toml`
    writes are safe because they splice one block and back the file up first, `formats.toml` has
    neither, and building both was judged a larger round than round 5 was. This idea was gated on a
    deferred write path before it was ever gated on a credential.
  - **`check_rules()` does not exist.** The validator is `_check_rule` and `parse_rulesets` in
    `skyboss/highlight.py`. The intent survives — a validator is there — but the name was written
    from memory.

  **That is twice this one paragraph has been wrong about [[highlight]], in two different ways**,
  which is the transferable half: an idea written from a remembered tree ages into a plan nobody
  can pick up, and the wrongness is invisible because every sentence still reads as confident. The
  round-5 pointer above was the first; these are the second.

  **So the recommendation is to split the idea at the credential line and build only what sits
  below it:**

  - **Phase A — the sample, with no model in it at all.** Reduce an hour of log to its few dozen
    distinct shapes. That is pure computation over data sky.boss already reads, it is an observe,
    pytest reaches it, and it is worth having *on its own*: forty shapes in front of you is often
    enough to write the block by hand. No credential, no write path, no rule crossed. **It is worth
    doing whether or not B or C ever happen, which is the test a first phase should pass.**

    **The shape key is the one real design question in it, and the obvious answer is wrong.** The
    tempting key is the `marks()` role signature, and it collapses exactly the lines that differ in
    the interesting way — unclaimed text is precisely what a new rule wants to claim, so two lines
    with identical signatures are the pair a sample most needs to keep apart. The key wants to mask
    the *claimed* spans and normalise what is left.
  - **Phase B — the model call is an argv the operator types.** `sb read … | claude -p …`, or saved
    as a tool. The key stays with `claude`, which is what *external CLIs keep their own
    authentication* means, and the draft lands on stdout for the operator to paste. This satisfies
    round 3 **more** strongly than the original design did: the block is not merely reviewed by the
    operator, it is installed by them, so *their opinion* is a fact about the file rather than a
    claim about a workflow. It also survives `CLAUDE.md`'s passthrough test, which asks whether
    sky.boss does something the wrapped tool cannot express: the sample is that thing, and it is
    phase A. Note what that means — **B is not a wrapper around `claude`, it is A with a pipe after
    it**, so there is nothing here for sky.boss to wrap and the test is passed by having no
    passthrough rather than by justifying one.
  - **Phase C — sky.boss writes `formats.toml` itself.** Probably never, and last regardless. It
    needs round 5's deferred splice-and-backup built first, and it is the only step that buys
    *convenience* rather than capability: A supplies the thing a model cannot, B supplies the model
    without the key, and C only saves a paste. If it is ever taken, it is a `formats.toml` write
    round in its own right and not a clause of this one — the backup and the block-splice are the
    feature, and a drafting assistant riding in on them would be two decisions in one commit.

  **Phase A left this file on 2026-09-16 → [[highlight]] round 8.** It is a round of that doc and
  never was an idea, so the graduation was reopening it into `docs/TODO/` rather than writing
  anything new — and not one `[[slug]]` citing it needed editing, which is what slugs are for.
  **B and C stay here on purpose**, and not because nobody got to them: taking three phases into
  one doc would have made the first wait for the other two, and C in particular is a `formats.toml`
  write round in its own right that would arrive wearing a drafting assistant's clothes. If either
  is ever taken, it exits from here the same way, with the line recording where it went

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

  **Two sources, not one — and this repo has stopped being the proof.** It read: *sky.boss has no
  `.skeletor.json` and will not — it consumes components*. Both halves are now false. It was
  scaffolded on 2026-09-06 and the components manifest was deleted on 2026-09-07, so this tree
  answers to `skeletor-upgrade` alone. The underlying point survives and needs a different
  example: the two tools answer genuinely different questions — *does this tree still reproduce a
  render* versus *has anything I copied moved since* — and a fleet view that ran only the first
  would be blind to every component consumer. A tree that is both is the case that needs both,
  and this one is no longer one.

  Unresolved, and the reason this is an idea rather than a plan: it is a **third** provider shape
  next to [[roll-call]]'s argv and path, and one whose answer is about a *relationship* between
  two repos rather than about the project itself. Whether that belongs in `sb roll-call`, in a
  command of its own, or nowhere is the question. The inverse proposal is also open — skeletor
  emitting a declaration of where a repo's truth lives, so `projects.toml` stops being hand-typed
  — and the two are complementary: this one works today and covers only adopters, that one needs
  a template change and covers every repo
