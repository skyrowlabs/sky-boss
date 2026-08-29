---
status: active
created: 2026-08-20
updated: 2026-08-29
agent_value: 3
key_files:
  - cli/tools.py
  - cli/helpers.py
  - cli/output.py
  - cli/read.py
  - cli/data.py
  - cli/follow.py
  - cli/helpers.py
  - cli/__init__.py
  - cli/canvas/catalog.py
  - cli/canvas/server.py
  - cli/canvas/static/app.js
  - cli/canvas/static/bench.js
  - cli/canvas/static/api.js
  - cli/canvas/static/sb.css
  - cli/canvas/prefs.py
  - tests/test_prefs.py
  - tools.example.toml
  - tests/test_tools.py
  - tests/conftest.py
---

# The tools — commands the operator saves

*Slug renamed `toolbox` → `tools` on 2026-08-22, when the repo took the name `toolbox`. Links are
`[[tools]]`, which is also the command group this documents. The collection was called "the
toolbox" here until 2026-08-27, when the `tb` → `sb` rename took that word with it and the
container lost its nickname — see the dated entry at the foot of Notes.*

## Why

The command this repo exists to make easy currently reads:

```
sb wrap --cols number,title,merge_state,behind,checks.failed \
        --cwd ~/src/jam.sense -- jam pr list --json
```

That is 110 characters, three of which are the part you were thinking about. It has to be retyped
into the palette every time, it dies with the window, and two of its arguments are things you have
to *remember*: that `jam` needs `--cwd` because its wrapper resolves `.venv` against the working
directory, and which five of its fourteen columns are the ones worth seeing.

Neither of those is a fact about sb. They are facts about *this operator's machine*, learned once,
and there is nowhere to put them. So they get retyped, or more realistically they get retyped
wrong and the window comes back with fourteen columns again.

The wireframe already has the answer drawn: `Sky Boss Surface.dc.html` carries a 184px sidebar
headed **TOOLS**, with a footer reading `sb <tool>`. The sidebar is empty — a `flex:1` spacer
between a header and a footer. This is the feature that fills it, and the footer is the whole
specification in three words: **a saved command is invocable as `sb <name>`.**

```
sb jam-pr-list
```

## Shape

A file the operator writes, at `$SB_HOME/tools.toml`:

```toml
[tool.jam-pr-list]
description = "Open PRs, with the merge column GitHub cannot show"
argv  = ["wrap", "--cols", "number,title,merge_state,behind,checks.failed",
         "--cwd", "~/src/jam.sense",
         "--", "jam", "pr", "list", "--json"]
every = 30
```

`$SB_HOME` defaults to `~/.sky-boss/`. **Content, not state** — `$SB_STATE` already exists for the
browser profile, which is machine-generated and something you would reasonably `rm -rf` to reset
the canvas. A file you authored must not be in the blast radius of that.

*Amended 2026-08-23: the default moved from `~/.config/sb/` to `~/.sky-boss/` at the operator's
word. The original reasoning was XDG's — config belongs under `~/.config` — and what it missed is
that these files are **content, edited by hand and often**, not settings a program wrote for
itself. The distinction this section actually turns on is `$SB_HOME` versus `$SB_STATE`, and that
is untouched. Round 1's box below still says `~/.config/sb/` because that is what it shipped as.*

And **not in the repo**, which is the rule [[canvas]] and `CLAUDE.md` both paid for already: the
`--cwd` above is `~/src/jam.sense`, an operator path, exactly the class of thing that
carried a tailnet address into every commit last time operator content lived here. Keep the two
apart from the start, take no fallback path between them, and **let an absent home degrade rather
than raise** — no file means zero tools, exit 0, and no warning, because a fresh clone having no
tools is not a problem to report.

### The tools are registered into the Click tree

This is the load-bearing decision and it is what makes the feature cheap.

`CLAUDE.md`'s hardest-won invariant is that **nothing keeps a command table** — the palette comes
from `/api/catalog`, which walks the live Click tree, so it cannot offer a command that does not
exist. A naive tools list breaks that immediately: a sidebar reading a TOML file is a second list of
commands, drifting against the first.

So tools are not a second list. At startup `cli/__init__.py` reads the file and calls
`cli.add_command()` for each one, building a `click.Command` whose callback re-dispatches into the
root group with the declared argv. Everything downstream then works with **no code change at all**:

| comes free | because |
|---|---|
| `sb jam-pr-list` | Click knows the command |
| `sb --help` lists it | Click knows the command |
| the palette offers it | `catalog.walk` walks the real tree — two lines added, see Notes |
| shell completion completes it | `_SB_COMPLETE=fish_source` walks the real tree |
| the TOOLS sidebar | filters the catalog it already fetches on `sb_saved` |

The sidebar marks its entries with `sb_saved` set on the command object, mirroring how `sb ui`
excludes itself with `sb_surface` — **a property on the command, never a name written down in a
module.** A name in a skip-list is the beginning of the command table this design refuses to keep.

### Four rules that are not negotiable

1. **`argv` is a sky.boss argv, never a shell argv.** `["wrap", "--", "jam", …]` means `sb wrap --
   jam …`. A tool cannot name an arbitrary executable, because a tool that could would be a second
   `sb run` — one that skips the read/write distinction the whole design rests on. Everything a tool
   wants is already reachable through `run` or `wrap`, and going through them is what keeps **`sb
   run` the single command that acts**.

2. **`acts` is inherited, never declared.** Resolve the expansion's leaf in the Click tree and take
   *its* `acts`. A tool expanding to `run` acts and the canvas will not offer it a cadence; a tool
   expanding to `wrap` reads and may be pinned. The operator already made this assertion when they
   chose `run` or `wrap` — asking again in the TOML would be asking them to contradict themselves,
   and a safety property must have one source. It follows that **`every` on a tool that acts is
   refused at load**, for the same reason the canvas hides the pin control on one.

3. **A builtin always wins.** *(Round 2 retired this into structure: saved commands live behind the
   `tools` group, where `[tool.run]` collides with nothing — `sb run` is the builtin and `sb tools
   run` is the tool. The rule below was validation while tools sat on the root, and its reasoning is
   kept as written.)* A tool named `run`, `wrap`, `ui` or `tools` is skipped with a warning naming
   the collision. Nothing operator-authored may shadow a sky.boss command — otherwise a stray
   `[tool.run]` silently redefines the one door that writes.

4. **~~No *surface* writes this file, and sky.boss only ever appends to it.~~ Reversed in round 4
   (2026-08-28).** The surface creates, replaces and deletes; sky.boss splices one block and backs
   the file up first. *The original, kept because its final clause named the condition for its own
   reversal:*

   > *(Round 3, 2026-08-22, narrowed this from "sky.boss never writes this file" — `--save` writes
   > one appended block from the terminal. The security argument below is unchanged and is what the
   > narrowing was measured against; the sentence it was protecting was broader than the argument.)*
   > Creation and every edit are `$EDITOR`'s. The canvas server is remote code execution bound to a
   > port and is treated that way; giving it a route that writes a file sky.boss will later
   > *execute* would convert a transient compromise into a persistent one. A hostile page that
   > defeated the header-and-token guard today gets one command; with a write route it would get
   > every command from then on. That is not a trade worth making for a save button, **and the
   > button can be added later against a design that has thought about it.**

   **What was wrong with it: "gets one command".** A page past the guard gets `/api/run`, which runs
   an arbitrary argv — and one arbitrary argv appends to `tools.toml`, or writes a crontab line, or
   a shell profile. Persistence was already on the far side of that boundary the day `/api/run`
   shipped, so the write route hands an attacker who is already executing as the operator exactly
   nothing. The guard is the whole defence and is unchanged: loopback bind, the required header that
   forces a preflight nothing answers, the per-launch token, the `Origin` check, and no CORS
   allow-origin header anywhere.

   The operator's case is the one that carried it: *"the user is going to want to edit commands
   without jumping out of the UI."*

`~` in an argv is expanded, since the whole point is that these are operator paths.

`sb tools` lists what is declared — a read, so a window may hold it open.

**Does not do:**

- **~~No writing, from anywhere.~~** No `sb tool add`, no `POST /api/tools`, no "save this window as
  a tool" button. See rule 4. This is the round that proves the read half; the write half is a
  separate design with a security argument to make. *(Round 3 built exactly that separate design
  and kept two thirds of this line: there is still no route and still no button. What exists is
  `--save`, typed by the operator in their own terminal — the same trust level as `$EDITOR`,
  reached the same way. **Round 4, 2026-08-28, spent the last third: `POST /api/tools` exists, the
  bench's button writes it, and the rail deletes. The security argument it was waiting for turned
  out to be an argument against a premise that was false — see rule 4.**)*
- **No arguments.** A tool is a *fixed* argv. `sb jam-pr-list 945` is refused rather than appended,
  because a tool that takes arguments is a shell function, and this is not a shell.
- **No groups, no nesting.** Flat names at the top level. `sb jam-pr-list`, not `sb jam pr-list`.
  *Amended 2026-08-28 (round 5), and the sentence above still holds every word of what it was
  about.* A tool may now declare `group = "jam"`, which is a **label the surfaces sort under and
  nothing else**. The address is untouched: `sb tools jam-pr-list`, never `sb tools jam pr-list`,
  and there is still no such thing as a group you can invoke. It follows that **names stay globally
  unique** — two tools in different groups may not share a name, because the thing that has to be
  unambiguous is the word you type, and that word never carries the group.
- **No shell.** No pipes, no `&&`, no interpolation, no `shell=True`. Argv only, unchanged from
  [[canvas]].
- **No sync, no sharing, no machine awareness.** One file, one machine. A tool naming a host that
  is not on this tailnet fails when run, not at load — sky.boss does not validate the world.
- **Does not read the repo.** There is no in-repo fallback path to `$SB_HOME` and there must never
  be one. That fallback is precisely how operator content ended up committed last time.

## Phases

### Round 6 — a group is a thing (2026-08-29)

Round 5 made a group a *label on a command*, which is the cheapest thing that could have worked and
is why it shipped in a day. It also means **a group does not exist** — it is a string that happens
to appear on two blocks, so there is nowhere to put one that is empty, nothing to name, and no
gesture that makes or unmakes one. Every ask in this round runs into that same wall.

Five asks, one model change under all of them.

**1. ~~The window is called COMMANDS.~~ Declined by the operator, 2026-08-29, before it was
built.** The argument for it, kept because the ambiguity it names is real and will come back:

> The word *tool* does two jobs in this repo and they are not the same job: `[tool.prs]` is a
> command the operator saved, and *"a tool that gates its output on `isatty()`"* is the foreign CLI
> being wrapped. The surface is where the ambiguity costs something, because the rail sits next to
> a palette that runs foreign CLIs all day. So on screen it is a **command**. **The CLI, the file
> and the slug keep the word** — `sb tools`, `tools.toml`, `[tool.x]` and [[tools]] unchanged.

What killed it is the sentence that was already in the proposal admitting the cost: *"that
divergence is deliberate and it is not free — it is the second time this repo has had a surface and
a CLI disagree about a noun."* Buying clarity in one surface by making two surfaces disagree is not
obviously a trade worth making, and **nothing else in this round depended on it** — the group model
never touched the word. The rail says `TOOLS`, and if the word is ever worth changing it is worth
changing everywhere, in a round that owns the file migration.

**2. A group can be declared, so an empty one can exist.**

```toml
[group.jam]
description = "jam.sense"

[tool.prs]
group = "jam"
argv  = ["data", "--", "gh", "pr", "list", "--json"]

[group.archive]        # declared, empty, and therefore deletable
```

The rule, which is what keeps every file that works today working:

> **A group exists if any command names it, or if it is declared.** Neither implies the other.

So round 5's files need no edit — a `group = "jam"` with no `[group.jam]` is exactly as valid as it
was — and `[group.archive]` with nothing pointing at it is a group with no commands rather than a
declaration nobody honoured. A declared group may carry a `description`; that is the only field,
and the name takes the same `_NAME` shape a command does, for the reason round 5 gave: it is a key.

**The union and its order are computed in Python, not in the rail.** `/api/catalog` gains a
`groups` list, already ordered, already counted, so `sectionsOf` in `app.js` stops holding a copy of
an ordering rule that is decided in `cli/tools.py`. That is round 5's own argument arriving one
layer down: the deciding half goes where pytest reaches it. `sb tools` grows the same list, so an
empty group is visible from the terminal too — the CLI/rail parity round 5 was built to preserve.

**3. The rail makes and unmakes them.** A `+ group` control creates one; a section header carries a
✕ **when it holds no commands.** The refusal is server-side: `remove_group` refuses a group any
command still names, and says which. A surface that only declines to *draw* a button has not
refused anything — the same sentence round 5 wrote about `/api/trial`, applied here.

**4. Dragging a command into a group changes one line.** And that is not a convenience, it is the
only correct way to do it, because of something this round found on its way in:

> **`block()` does not serialise `highlight`, so any rewrite through the bench silently drops a
> declared ruleset.** Measured: a `[tool.applog]` carrying `highlight = "jam"` comes back without
> it. A round-4 defect, live since 2026-08-28, and invisible until the day the stream drew grey.

A drag that round-tripped a command through the surface would inherit that bug and add its own —
the rail knows a command's `summary`, not its `description`, and writing one back as the other
invents a description equal to the expansion. So a regroup **splices the `group =` line inside the
block** rather than rewriting the block, which preserves every other key *by construction* —
`highlight`, anything a future round adds, and the comments *inside* the block that a replacement
would take. Round 4's own argument, one level finer.

`block()` is fixed to carry `highlight` regardless, because the bench's save path still rewrites
and still drops it.

**A drag is a write and is backed up like every other write.** The operator's call: the rule is
*before every mutating write*, and an exception for writes deemed small is how the next person
learns the rule has exceptions. The cost is real and is stated rather than designed around —
reorganising ten commands spends ten of the twenty backup slots.

**5. The bench picks from what exists, and can still name what does not.** A `datalist`, so typing
`jam` completes and typing `archive-2` creates. The failure it removes is the near-miss: `jamm` is
a perfectly valid group name and silently a second group, where `Jam` at least gets refused.

**Does not do:**

- **No nested groups.** One level, unchanged from round 5. `[group.jam.prs]` is not a thing.
- **No group operations beyond make, unmake and move.** No "run the group", no collapse-all, no
  reordering by hand — a group's position is alphabetical and there is no `order` field, because an
  ordering the operator maintains by hand is one more thing to keep true.
- **No renaming a group in place.** A rename is a delete and N writes, and doing it atomically over
  a hand-edited file is a bigger promise than this round should make. `$EDITOR` and a
  find-and-replace is the honest answer, and the file is backed up.
- **Deleting a group never deletes a command.** It is refused while any command names it, and the
  refusal names them. A cascade here would be the surface deciding that "delete this label" meant
  "delete this work".
- **Nothing is renamed.** See ask 1 — the surface keeps saying `TOOLS`, and so do the CLI, the
  file and the slug. If the word changes it changes everywhere, in a round that owns the migration.
- **`/api/groups` is not a config editor**, the same line round 4 drew for `/api/tools`. Groups in
  `tools.toml`, nothing else, nowhere else.
- **No drag between the rail and a window, or onto the canvas.** Dragging is for reorganising the
  rail. A command is opened by clicking it, as it always was.

- [x] **The model.** `[group.NAME]` parsed by a `parse_groups` beside `parse` — a separate pure
      function rather than a third return value, so nothing that calls `load` changes. `Group(name,
      description)`; `_NAME` shape; a malformed group is skipped and named like a malformed tool.
      `groups()` returns the union — declared ∪ named — alphabetical, with a count each.
- [x] **`sb tools` shows them**, including the empty ones, in the same listing as tools, formats
      and highlights. *The envelope grows a `groups` key **always**, the shape `formats` and
      `highlights` already have — so "byte-identical" narrowed to "the `tools` table is unchanged".
      See Notes.*
- [ ] **The catalog carries the ordered list**, and `sectionsOf` in `app.js` becomes a bucket-by-
      name rather than a second copy of the ordering rule.
- [ ] **The writer.** `write_group`, `remove_group` — refusing one that any command still names,
      naming them — and `block_range` generalised to a table prefix so it can find `[group.x]`.
      Backups as ever. `POST /api/groups`, guarded, joining the route-inventory test.
- [x] **`highlight` round-trips.** `block()` serialises it; a test saves a tool that has one, reads
      it back, and finds it still there. This is a round-4 defect fixed in passing, not new work.
      *Shipped first, on its own, at the operator's word — it is data loss and it depends on
      nothing in this round. The bench half turned out to be different from what this line assumed;
      see Notes.*
- [ ] **`set_field` and the regroup.** A line-level splice inside a block: replace the key, insert
      it if absent, remove it if the value is empty. `POST /api/tools` gains a `regroup` verb that
      goes through it. Tests: every other key survives, a comment *inside* the block survives, and
      a regroup of a tool carrying `highlight` keeps it.
- [ ] **`+ group` and the ✕**, with the delete asking once and the refusal shown when the server
      declines.
- [ ] **Drag and drop.** Rows draggable, sections and the ungrouped bucket as targets, a visible
      drop state. Verified by reading the DOM back, and swept at more than one `--scale`.
- [ ] **The bench's picker** — a `datalist` fed from the catalog's groups, free text still allowed.
- [ ] **Docs.** `CLAUDE.md` on the group model, `tools.example.toml` grows a `[group.…]`,
      README's saving section.

### Round 5 — the rail gets sections (2026-08-28)

The rail is a flat alphabetical list, which is exactly right for six tools and wrong for thirty.
It is one `flex: 1` column between a header and a footer, and the only thing separating a
jam.sense read from a breeze.brain follow is that they sort into different parts of the alphabet.
The operator's ask: **group them.**

**A group is a declared label, not an address.** One optional field:

```toml
[tool.jam-pr-list]
group = "jam"
argv  = ["data", "--cwd", "~/src/jam.sense", "--", "jam", "pr", "list", "--json"]
refresh = 30
```

Three things this deliberately is not, each rejected against something already written down here:

- **Not inferred from the name.** `jam-pr-list` and `jam-ci` share a prefix, and splitting on the
  first dash would group them for free with no new field and no edit to any existing tool. It is
  also a heuristic, and this repo has rejected that shape twice — the `--pretty` that guesses
  columns, and the bench that would read a trailing `--json` and pick `data` for you. The
  workbench's rule is the one that governs: **the contract is asserted, never inferred.** A
  prefix rule cannot be told apart from a coincidence, so `disk-free` invents a `disk` group and
  the operator's only recourse is to rename a tool to escape a grouping they never asked for.
- **Not derived from what it wraps.** Grouping by `argv[0]` — all the reads here, all the follows
  there — is free and needs no field at all. It groups by *mechanism* when the question the rail
  answers is about *subject*: the operator wants their jam.sense tools together, and whether one
  of them is a `read` and another a `follow` is already on the row.
- **Not a namespace.** See the amended Does-not-do line above. The group never enters the address,
  so names stay globally unique and `sb tools <name>` is unchanged.

**The grouping lives in the envelope, not in `app.js`.** `sb tools` prints its sections from the
same field the rail draws from, which is the rule [[table-views]] already paid for: the deciding
half goes where pytest reaches it, and both renderers draw what they are told. The alternative —
grouping as pure presentation in the frontend — would give the CLI and the rail two different
readings of one file, in the repo whose frontend has no test runner.

The field rides the established path and adds no new one: `Tool.group` → `sb_group` on the
registered command object → the catalog, exactly as `sb_saved`, `sb_acts` and `sb_refresh` already
travel. **A property on the command, never a name written down in a module.**

**A group name is a key, not just a caption**, so it takes the same shape a tool name does —
lowercase letters, digits and hyphens, `_NAME` as it stands. It is what the collapsed-state store
is keyed on and what the writer splices, and a free-text caption means `jam ` and `jam` are two
groups that look like one. The rail uppercases it for display, which is where the caption lives.
`group = ""` is ungrouped, identical to omitting it — a bench field left blank is the common case
and refusing it would be a modal for nothing.

**Order is alphabetical: groups, then tools within them, with the ungrouped last** under no
heading, after a divider. Declaration order was the tempting answer — the file is hand-written and
its order is an assertion, the same reasoning that makes `--save` keep the argv you typed — and it
was rejected because **the catalog already sorts** (`catalog.py`, `sorted(command.commands)`, and
`_listing`'s `sorted(tools.commands.items())`). Preserving file order means threading a position
index through a structure that exists to read properties off command objects, to buy an ordering
the operator can get by naming a group. With zero groups declared, alphabetical-within-ungrouped is
byte-identical to what the rail draws today, which is the property worth having.

**Collapse persists, or it is not a fold.** A group header toggles; the set of collapsed groups
survives a restart, because a rail with thirty tools is the whole reason to build this and a fold
that reopens on every `sb ui` is a fold you stop using. Two constraints on where that state goes:

- **Not `tools.toml`.** That is operator content, hand-authored, and writing a UI preference into
  it would put sky.boss's own state in a file the operator owns — and drag a backup rotation
  behind every chevron click.
- **`$SB_STATE`, conceptually** — this is machine state, and `rm -rf ~/.local/state/sb` resetting
  the surface is the documented meaning of that directory.

~~The cheapest implementation of "in `$SB_STATE`" is `localStorage`~~ — **the check said no, and
the fallback is what shipped.** The paragraph as written, because the reason it was wrong is not the
reason it expected:

> The cheapest implementation of "in `$SB_STATE`" is `localStorage`, which needs no route and no
> Python at all, and lands in the browser profile that already lives there on the `--browser` path.
> **Whether it survives in the native webview is unverified** — nothing in `cli/canvas/static/`
> touches `localStorage` today, and `shell.py` configures no storage path. So the phase checks it
> rather than assuming, and names its fallback: a small JSON file in `$SB_STATE` behind a guarded
> route, the same guard as every other.

The native webview was the suspect and it was not the problem: `private_mode` defaults to `True`,
and setting `private_mode=False` with a `storage_path` makes WebKitGTK persist `localStorage`
across a full restart — measured twice, `null` then the value.

**`sb ui` binds an ephemeral port every launch.** `port = port or _free_port()`, so the page is
served from `http://127.0.0.1:<different>/` each time, browser storage is keyed by origin, and a
fold written under one launch's origin is *not there* under the next. That is true in all three
shells, has nothing to do with private mode, and cannot be configured away without pinning the
port. So `cli/canvas/prefs.py` holds it: a small JSON file in `$SB_STATE` behind `GET`/`POST
/api/prefs`, guarded like every other route, strictly shaped so it cannot become a second config
file. An absent or unreadable store degrades to **everything open**, and a key naming a group that
no longer exists is dropped on write rather than kept forever.

**Does not do:**

- **Does not group the palette.** The palette is a search and typing is already the filter;
  sections inside a list that is being narrowed keystroke by keystroke are noise. The rail is a
  standing list, which is what makes grouping worth anything there.
- **No `--group` on `--save`.** Round 3's argument against `--describe` is unchanged and applies
  word for word: it is a second thing to type at exactly the moment the operator wants to type
  less. A group is added later, in the bench or in `$EDITOR`, where the tool is being thought
  about rather than captured.
- **No nested groups.** One level. A group of groups is the nesting the address already refuses,
  arriving through the sidebar.
- **No group operations.** No "run the group", no "collapse all", no drag-to-regroup, no delete-a-
  group. A group is a string on a tool; the way to empty one is to stop writing it.
- **No colour per group, no icons, no ordering field.** The rail has one palette and it is
  [[header]]'s; a per-group hue is the first hex outside `theme.py` waiting to happen.

- [x] **The field and the loader.** `group` on `Tool`, validated in `_check` against `_NAME` with
      `""` and absent both meaning ungrouped; `sb_group` set on the registered command in
      `cli/__init__.py`. Tests: a valid group survives, a bad shape is skipped and *named* while
      the other tools load, and a tool with no group is unchanged from today.
- [x] **`sb tools` groups.** `_listing` carries `group` on every declared row and orders them —
      groups alphabetical, tools alphabetical within, ungrouped last. *Shipped as a `GROUP` column
      with the groups contiguous rather than as headed sections; see Notes.* A test that a file
      with no groups produces the listing byte-identical to today's.
- [x] **The catalog and the rail.** `group` through `catalog.py` beside `saved`; `Tools()` in
      `app.js` renders headers with a count and an ungrouped bucket after a divider. **Swept at
      more than one `--scale`** — new fixed `rem` heights inside a 184px rail is precisely the
      shape that starved the bench's last step for three rounds. Verified by reading the DOM back
      from headless Chromium, and no `/* */` inside an `htm` tag.
- [x] **Collapse, persisted.** Chevron on the header; the folded set in `$SB_STATE` behind
      `/api/prefs`, *not* `localStorage` — the check found the reason and it was not the one this
      line expected. See Notes. Unknown keys ignored on read and dropped on write; an unreadable
      store means everything open.
- [x] **The bench and the writer.** A group field on the bench beside description; `/api/tools`
      carries `group` through create/replace; the splice writes and removes the line within the
      block, so comments above it still survive (round 4's guarantee, now with one more line in
      the block). The shared validator gains the group check, so the writer still cannot accept a
      tool the loader will refuse.
- [x] **Docs.** `CLAUDE.md` (the command table row, `$SB_STATE`'s new file, the
      declared-not-inferred rule, and the ephemeral-origin finding), README's saving section,
      `tools.example.toml` grows groups — and the test that the tracked example names no home
      directory keeps passing. The example's header also lost a paragraph round 4 had already
      falsified; see Notes.

### Round 4 — the interface writes (2026-08-28)

**Rule 4 is relaxed at the operator's direction**, and the sentence it turns on was already false
when it was written. As stated:

> A hostile page that defeated the header-and-token guard today gets one command; with a write
> route it would get every command from then on.

The first half is the error. A page past the guard does not get *one command* — it gets
`/api/run`, which runs an arbitrary argv, and one arbitrary argv is `sh -c 'cat >> ~/.sky-boss/tools.toml'`,
or a crontab line, or `~/.bashrc`. **Persistence was already on the far side of that boundary.** The
write route adds a convenience for the operator and nothing at all for an attacker who is already
executing commands as them. What actually defends this surface is unchanged and is where the
argument belonged all along: loopback bind, the required custom header that forces a never-answered
preflight, the per-launch token, the `Origin` check, and no CORS allow-origin header anywhere.

The operator's case, which is the one that matters: *"the user is going to want to edit commands
without jumping out of the UI."* Round 3 already conceded the shape of this — it narrowed rule 4
from "sky.boss never writes this file" and said the button *"can be added later against a design
that has thought about it."* This is that design.

**The surface may create, edit and delete a tool. sky.boss still never rewrites a file it did not
have to touch.**

**Splice, do not round-trip.** `tools.toml` is hand-written and carries the operator's comments —
in this very repo, `# --cwd is required: jam's wrapper does not set PYTHONSAFEPATH…`. A TOML
library that parses and re-serialises the whole document silently reformats every block, including
the ones nobody asked to change; a style-preserving library (`tomlkit`) avoids most of that and is
still a new dependency doing more than is needed. Instead a write locates the target block's **line
range** and replaces or removes exactly those lines. Every other byte in the file is untouched by
construction, which is a stronger guarantee than any round-trip can offer and needs no dependency.

- A block runs from its `[tool.NAME]` line to the line before the next table header at column 0,
  or to EOF.
- **Comments above a block survive an edit**, because the range starts at the header. They are the
  operator's prose and may still be true of the edited tool.
- **A delete takes the contiguous comment lines immediately above it** — no blank line between —
  since those unambiguously describe the block being removed. A comment separated by a blank line
  is a section heading and stays.

**Every mutating write backs up first**, at the operator's request. The current file is copied to
`$SB_HOME/backups/tools.<utc-stamp>.toml` before the new one is written, and the last 20 are kept.
Cheap, outside the repo, and it makes "undo" a `cp` rather than a feature.

**The write is one route, guarded like every other**, taking a whole tool rather than a patch: name,
argv, refresh, description. Create and edit are the same call — a name that exists is replaced, a
name that does not is appended. Delete is its own verb.

**Every refusal the loader already makes, the writer makes first.** A tool that writes cleanly and
then fails to load is the worst of both, which is round 3's rule and does not change: the argv must
start with a sky.boss command, a cadence is refused on a tool that acts or is resident by nature,
`refresh` must be one of `INTERVALS`, and a name may not shadow a sky.boss command.

**Does not do:**

- **Does not become a config editor.** Tools only. `formats.toml` and `projects.toml` are not
  reachable from any route, and `projects.toml` in particular is declared operator-owned by
  [[roll-call]] and never written by sky.boss.
- **Does not edit a file it cannot parse.** If the target block cannot be located unambiguously the
  write is refused with the reason, and `$EDITOR` is still there. A surface that guesses at a
  malformed file is how you lose a tool you spent an afternoon on.
- **Does not preserve a comment through an edit of the block it is inside.** Comments *within* a
  block go when the block is replaced — the block is being restated, and a comment about the old
  argv is worse than no comment. Comments above it survive.
- **Does not offer a diff, a history, or a restore UI.** The backups are files. `ls` and `cp`.
- **Still refuses to run a tool whose argv does not start with a sky.boss command.** The write path
  changes who may author a tool, not what a tool may be.

- [x] **The splice** — `replace_block`, `remove_block`, `block_range` in `cli/tools.py`, plus the
      backup. Tests for: comments above survive an edit, contiguous comments go with a delete, a
      separated section heading stays, every other block is byte-identical, an unlocatable block
      refuses.
- [x] **The validator runs before the write**, sharing one function with the loader's refusals so
      the two cannot drift.
- [x] **`POST /api/tools`** — create/replace and delete, guarded like every route, with the refusal
      as a 400 carrying its reason. A test that it refuses an unauthenticated request, alongside
      the existing route inventory.
- [x] **The bench saves for real.** Its `--save` row currently prints a block for you to paste;
      it writes it. The name check it already does becomes the create/replace decision.
- [x] **The sidebar edits and deletes.** A tool row opens its argv in the bench; a delete asks
      once and says where the backup went.
- [x] **Docs**: rule 4 rewritten in place with the original kept and struck, `CLAUDE.md` § tools
      and § Where things live updated, README's saving section.

### Round 1 — the tools read (2026-08-20)

- [x] `SB_HOME` in `cli/helpers.py` alongside `STATE_DIR`, defaulting to `~/.config/sb/`.
- [x] `cli/tools.py`: load and validate `tools.toml` as pure functions over a parsed dict, plus
      `tests/test_tools.py`. Absent file → `[]`. Malformed tool → skipped with a warning naming it,
      never an exception; one bad entry must not cost the operator the other nine.
- [x] Validation covers the four rules: sb-argv only, `acts` inherited, builtin collisions refused,
      `every` refused on a tool that acts.
- [x] Register tools onto the root group in `cli/__init__.py`. `sb jam-pr-list` runs; `sb --help`
      lists it. **`catalog.py` needed two lines after all** — the claim that it would need none was
      too strong, and the second line was a real safety hole. See Notes.
- [x] `sb tools` — a read listing name, description, expansion and `acts`.
- [x] `sb_saved` on generated commands; catalog carries it through.
- [x] TOOLS sidebar in `app.js` renders catalog entries where `sb_saved`, click opens a window,
      a tool's `every` becomes the window's starting interval. Tracked as a task of [[canvas]]
      Round 5, which owns the sidebar's chrome.
- [x] Ship a `tools.example.toml` in the repo. Generic — no operator paths in a tracked file, and
      a test asserts the tracked example names no home directory.


### Round 2 — the tools get their own door (2026-08-22)

Prompted by the operator reading `sb --help`: `jam-pr-list` renders between `follow` and
`read`, and the builtin/operator line — the sharpest line in the design — is invisible in the
one listing where it matters most. The operator's call: **saved commands move behind
`sb tools`**, with `-t` as the short spelling.

    sb tools jam-pr-list --refresh 30
    sb -t jam-pr-list --refresh 30

**This reverses a round-1 decision and keeps its reasons.** Round 1 registered tools on the
root so the palette, `--help` and completion would work for free; nesting keeps all three —
the catalog already walks groups, and a leaf under `tools` is still an ordinary leaf. What
nesting *dissolves* is the shadowing defense: `sb tools run` collides with nothing, so
"a builtin always wins" stops being a validation rule and becomes structure. The name check
stays only as the shape a command word must have.

- **`tools` becomes a group that still lists when bare.** `sb tools` with no subcommand
  prints exactly today's listing (declared, refused, and — per [[capture]] when it lands —
  formats). One door for "what did I save"; no second listing command.
- **`-t` is an argv spelling of `tools`, rewritten at the root** — not a Click alias and not
  a flag with behavior: `sb -t …` becomes `sb tools …` before parsing, in one tested place.
  Options follow the tool name, as they do on every sky.boss command; the prefix form
  (`sb -t --refresh 30 jam-pr-list`) was considered and rejected — it would teach the group a
  forwarded option that belongs to the leaf.
- **The envelope says the dotted path**, `tools.jam-pr-list`. Round 1 ruled "the envelope
  names the tool, not `data`" because `data` is an implementation detail the operator did not
  type; `tools.` is now something they *do* type, and the dotted path is the standing
  convention. The round-1 argument is superseded only that far.
- **The palette entry is the tool, shown by its own name.** The catalog leaf's name is
  `tools jam-pr-list`; the sidebar and palette display the tool's short name with the saved
  badge, and the expansion preview already shows the truth. Typing either form finds it.
- **The REFRESH column stays, presented as the default it is.** Raised by the operator in the
  same review: is showing the field beside `--refresh` mixing behaviors? No — the constitution
  made them one number on purpose: the field is the *default* (the canvas opens at it; bare
  `--refresh` adopts it), and a keyword in the terminal always runs once unless the flag is
  given. The listing keeps the column, and `sb tools`' help states that rule in one line. The
  line to hold is unchanged: the field must never cause residency on its own.

Does not do, this round: no change to tools.toml (declarations are untouched; only the
address moves), no back-compat top-level registration — a hard move, one operator, and the
palette teaches the new spelling immediately.

- [x] **The group.** `tools` becomes `invoke_without_command`; registration targets it;
      the listing behavior is byte-identical when bare. Shadowing tests retire into
      structure; name-shape validation stays.
- [x] **`-t`.** Root-level argv rewrite with tests: `sb -t x` ≡ `sb tools x`, `sb -t` ≡
      `sb tools`, and `-t` anywhere else is untouched.
- [x] **Surfaces.** Envelope says `tools.<name>` (test updated with the reversal noted);
      palette/sidebar show the short name; canvas execution unchanged through the runner.
- [x] **Docs.** CLAUDE.md command table says `sb tools <name>` / `sb -t <name>`; `sb tools`
      help carries the refresh-default sentence; [[refresh]] bare-flag prose confirmed
      unchanged.

### Round 3 — saving the command you just ran (2026-08-22)

**The gap is the one round 1 named and deferred.** A tool is a name plus a sky.boss argv, and the
only way to make one is to open `$EDITOR`, remember the TOML shape, and retype an argv you had
working thirty seconds ago in your shell. The command this whole doc exists to make easy is *still*
110 characters the first time, and the moment you have it right is the moment you are furthest from
a text editor.

    sb data --cols number,title,merge_state --cwd ~/src/jam.sense \
            -- jam pr list --json --save=prs

Then `sb tools prs` forever. **Save by example, from the terminal, at the end of the command
that worked.**

**This narrows rule 4 and keeps its argument intact.** The rule said *sky.boss never writes this
file*; the argument underneath it was about **the canvas server**, which is remote code
execution bound to a port, and about a *route* that would turn a transient compromise into a
persistent one. None of that applies to a flag the operator types in their own shell — that is
the same trust level as `$EDITOR`, arrived at by a shorter path. What survives unchanged: no
`POST /api/tools`, no save button on a window, no write from any surface. The narrowing is
recorded in Shape rule 4 with the original sentence visible beside it.

**Three properties make the write safe to have at all:**

1. **sky.boss appends; it never rewrites.** The saved entry is a `[tool.<name>]` block added at the
   end of the file. Nothing above it is re-serialised, reordered, or reformatted, so every
   comment, blank line and hand-written argv the operator wrote survives byte-for-byte. This is
   not politeness — round-tripping TOML would mean either a writer dependency or sky.boss's own
   serialiser deciding how the operator's file should look, and both are ways to lose a file
   that is not sky.boss's. **Editing and deleting stay `$EDITOR`'s**, which is also why there is no
   `--save` overwrite: a name already declared is refused, naming what it currently runs.
2. **The saved argv is what you typed.** Taken from the invocation itself, from the sky.boss command
   word onward, with the `--save` token removed and nothing else added, normalised or guessed.
   A tool whose expansion does not match the line that created it is the failure this feature
   would otherwise introduce, and it would be invisible until the day the tool ran.
3. **Nothing about the tool model changes.** `acts` is still inherited from `argv[0]`, a
   `refresh` in force at save time is recorded as the tool's field, a follow still refuses one,
   and the entry is loaded by the same loader that reads a hand-written one — proven by
   re-registering the file after the write rather than by trusting the writer.

**`--save` is on the observes only — `data`, `read` and `follow`.** `run` does not take it, and
the absence in `run --help` is the act/observe split made visible exactly as `--refresh`'s
absence already is. `tools.toml` still *accepts* `[tool.deploy]` over `run`; the asymmetry is
deliberate and it is about the gesture rather than the file — **`--save` saves by example, and
the example ran.** A read that ran twice costs nothing; a write saved by having just been
performed is a different act, and one that deserves the deliberation of opening the file. The
operator's call, taken 2026-08-22.

**It saves, then runs.** The flag is appended to a command that is about to do its job, and it
does its job — for `follow`, the tool is written and then the stream opens. Saving first is
what makes the resident commands work at all (a follow never reaches its own exit), and it
means the tool exists even if the run fails, which is correct: **you are saving an argv, not a
result.** The envelope says where it went; under `--json` that is a field, not prose.

**Does not do:**

- **No description, no editing, no removal.** `--save` writes a name and an argv. A description, a
  changed argv, a deleted tool: `$EDITOR`, one file, no ceremony. A `--describe` flag is a second
  thing to type at exactly the moment the operator wants to type less.
- **No overwrite, no `--force`.** An existing name is refused with what it currently runs. The fix
  is to edit the file, which is the one place edits happen.
- **Still no route and still no button.** The canvas gains nothing. Its argv path can carry the flag
  the same way it can carry any word, and that is honestly not a new hole: a client that can reach
  the API can already ask for `sb run -- <anything>`, which is strictly more. sky.boss does not
  filter the flag out server-side, because a filter would be the server keeping a list of sky.boss's
  flags — the command table this design refuses to keep, in its most brittle form.
- **No `~` re-contraction.** The shell expanded `~` before sky.boss ever saw it, so an absolute path
  is what gets saved. `_expand` still exists for the hand-written `~` in a file the operator typed.
- **No validation of the world.** A saved argv naming a host, a repo or a tool that is not there
  fails when it runs, exactly as a hand-written one does.

- [x] **The writer.** `save()` in `cli/tools.py`: validate the name against `_NAME`, refuse one
      already declared (naming its expansion), append a `[tool.<name>]` block with the argv and
      any `refresh`. Pure-ish over an injected home; tests write to `tmp_path` and never to the
      real `$SB_HOME` (`conftest.py` already redirects it, and this is the round where that
      matters most). The module docstring's "Nothing here writes" is amended with the reversal.
- [x] **The flag, on the three observes.** `--save NAME` on `data`, `read` and `follow`; absent
      from `run`. The argv is reconstructed from the invocation, and a test asserts the
      round-trip: save a real invocation, re-register the file, and the tool's expansion equals
      the line that made it — including `--cols`, `--cwd`, `--from` and the `--` separator.
- [x] **Save, then run.** The write happens before execution, so a resident command saves and a
      failing command still saves. Proven on `follow` without opening a stream, the way the
      dispatch test already proves the file form.
- [x] **What it says.** The envelope carries where it went and what it will run; `--help` on all
      three carries the flag with a runnable example, which the [[refresh]] help test already
      enforces. `sb tools` needs no change — the new entry is an entry.
- [x] **Docs.** CLAUDE.md's `$SB_HOME` row says the operator *and* `--save` author `tools.toml`;
      its "Nothing here writes" claim, if it carries one, is amended with the same reversal.

## Notes

### Round 6 — a group is a thing (2026-08-29)

*Accreting as the round lands.*

**The `highlight` loss had two halves and only one was the one written down.** The visible half was
`block()`: it serialised `description`, `group`, `argv` and `refresh` and simply did not know about
`highlight`, so any rewrite dropped it. That is fixed, and fixed with a **guard rather than a
patch** — `test_block_serialises_every_declared_field_of_a_tool` walks `Tool`'s own dataclass
fields, minus the two that are *derived* from the argv (`acts`, `resident`), and fails if any
declared one cannot reach the file. The next field added cannot repeat this.

The second half was in the bench, and it is the opposite of what the phase assumed. The phase said
*"the bench has no control for a ruleset"* — it does, a visible `--highlight` field that **composes
into the argv**. So the bench never needed a hidden pass-through; what it needed was **seeding**.
A tool declaring `highlight = "jam"` as a *field* has no `--highlight` in its argv for `edit()` to
decompose, so the bench opened with the control blank and composed a line without it. Seeding the
control from `tool.highlight` fixes it, and the catalog now carries the field so it can.

**The `groups` key is always present, which is a narrowing of what the phase promised.** It said a
file with no `[group.…]` should produce a listing *byte-identical* to round 5's. That is achievable
— round 5 itself omits a row's `group` key when empty, for exactly that property — and it is the
wrong call one level up: `formats` and `highlights` are always in this envelope even when empty,
because "what did I declare" is a fixed set of questions with sometimes-empty answers. A key that
appears only sometimes makes every consumer handle its absence. So the promise that held is the one
that matters: **the `tools` table is unchanged**, and a test asserts it field for field.

**Groups are captured at registration, not read by the listing.** The first cut had `_listing` call
`load_groups()`, which reads the home *now* while the tools it lists came from the tree as
registered. Those two can disagree the instant anything writes — and the test suite found it
immediately, because its fixture registers from a `tmp_path` the ambient home knows nothing about.
`GROUPS` is a module global filled by `register` beside the tools, one read, and `register` now
returns both kinds of problem in one list.

Two consequences worth writing down. **The route accepts `highlight` but the client deliberately
does not send it** — the bench composes the flag into the argv, so sending the field as well would
apply the ruleset twice; the parameter exists for a caller that wants the field form. And a bench
edit **changes the representation**, field to flag, which is visible in the block the bench draws
before it saves. That is acceptable where a silent drop was not.

### Round 5 — the rail gets sections (2026-08-28)

**Six phases, all shipped.** A tool declares `group`; the loader validates it, the listing orders
by it, the catalog carries it, the rail draws sections that fold, the bench writes it and the
splice preserves it. Nothing was deferred. The three findings worth keeping are below: the listing
groups without headings, `localStorage` could never have worked here, and the shipped example was
still asserting a rule round 4 had reversed.

**The listing groups without a heading, and the reason is that a heading would have been
presentation encoded as data.** The phase said "prints sections", and the obvious way to get them
was to reshape `data["tools"]` from a list of rows into a mapping of group → rows —
`_render_mapping` already draws an accent heading per key, so it would have cost nothing and looked
right. It was rejected on the rule [[table-views]] settled: a view *describes* data and never
restructures it. A mapping keyed by group is a table that has had its rendering folded into its
shape, and `sb --json tools` would then hand a consumer a different type depending on whether the
operator happened to declare a group.

What shipped instead is a `group` key on each row, rows ordered so groups are contiguous with the
ungrouped last, and the existing column renderer drawing a `GROUP` column. **The key is omitted
rather than set to `""` when a tool is ungrouped**, which is what makes the "no groups declared
means the listing is exactly what it was" property true rather than approximately true:
`_render_columns` takes every key of every row, so an absent key is an absent column, and a file
with no groups produces byte-identical output with no special case anywhere.

**The rail was verified headless at four scales — 1.0, 1.15, 1.8, 2.4 — and the section heading is
`--sb-text-2`, not `--sb-text-3`.** Reaching for the dimmest token is the obvious move for a
heading that must not compete with the tool names under it, and [[fundamentals]] § the label tier
had already ruled that one out: `TEXT_3` is *"structure, not reading text"* and is what `BORDER`
is. A group name is read. Nothing starved at any scale; the rail's own `overflow: auto` takes the
list under the fold at 2.4, which is what it is for.

*Observed, not caused:* at `--scale 2.4` in a 1300px viewport the **top bar** overflows and the
right-hand counters clip. That is the bar's geometry, not this round's, and it is what the
"verified at one value of it has been verified once" rule predicts.

**`localStorage` cannot work here, and the reason is not the one the phase was written to check.**
The phase suspected the native webview, on the grounds that nothing in `static/` used
`localStorage` and `shell.py` set no storage path. That suspicion was correct about the mechanism
and irrelevant to the outcome. Measured, in this order:

1. `webview.start`'s `private_mode` defaults to **`True`**, so the native shell keeps nothing
   between launches. Read off the signature rather than guessed.
2. Setting `private_mode=False` with a `storage_path` under `$SB_STATE` **fixes exactly that** —
   a two-run probe against WebKitGTK returned `null`, then the value, with the store landing at
   `<storage>/localstorage/http_127.0.0.1_<port>.localstorage`.
3. **And that filename is the answer.** `sb ui` calls `_free_port()` unless told otherwise, so
   every launch serves the page from a **different origin**, and per-origin storage is empty on
   arrival by construction. The webview fix makes the fold survive a restart *of the browser* and
   not a restart *of `sb ui`*, which is the only restart anyone cares about. Pinning the port to
   buy a stable origin would be the tail wagging the dog.

So the `shell.py` change was reverted — it was no longer needed, and turning off private mode
persists cookies and cache nobody asked for — and the doc's own named fallback shipped:
`cli/canvas/prefs.py`, a strictly-shaped JSON file in `$SB_STATE` behind a guarded `/api/prefs`.
Verified end to end the way the substitute demands: fold `jam` on port 8820, kill the server,
start a new one on **8821** with a **fresh browser profile**, and the group comes back folded with
its count. `localStorage` could not have passed that test in any configuration.

**The route is shaped, not open.** `KEYS` names what may be stored and anything else is dropped, so
this is the surface's own state rather than a second config file — round 4's line when it refused
to let `/api/tools` become a config editor, applied one route over. It joins the guarded-route
inventory test, which is what catches a route added later without the guard.

**The bench's group field is declared, like everything else on that screen.** It does not read a
prefix off the name and offer a guess, for the reason the contract is not read off a trailing
`--json`. Blank is ungrouped and `block()` writes **no line at all**, so clearing the field removes
`group` from the block rather than leaving `group = ""` behind — which would load identically and be
one more line nobody wrote on purpose.

Verified through the real route against a real file: `/api/tools` created a grouped tool, refused
`group = "No Good"` with **the loader's own message** (`write_problem` calls `_check`, so there is
still one opinion), and the operator's comment above the untouched block survived byte for byte.

**`tools.example.toml` was still asserting a rule reversed three commits earlier.** Its header
carried round 4's *"No surface writes this file. The canvas server is remote code execution bound
to a port…"* — the paragraph round 4 spent its whole Why disproving. Round 4 updated `CLAUDE.md`,
the README and rule 4 itself, and missed the shipped example, which is the one of the four a new
operator reads *first*. Rewritten to describe what the surface actually does. Worth naming as a
class: a reversal has to be swept for by grepping the claim, not by remembering where it was
written.

*Observed, not caused — and checked rather than assumed:* **the workbench overlaps itself at
`--scale 2.4`** in a 1500×950 viewport, panels stacking over each other with the job strip's own
fields clipped behind the save row. It looked exactly like the failure `CLAUDE.md` warns this round
would cause, so the same shot was taken with this round's three frontend files stashed — and it is
pixel-for-pixel the same overlap. Pre-existing, vertical, and worth a round in [[workbench]]; not
this one's. At 1.8 the row wraps the group under the name and reads correctly, which is the
behaviour `flex-wrap` was already there for.

### Round 1 — what shipped, and the claim that did not survive (2026-08-20)

The model held exactly as designed: a tool is a name plus a sky.boss argv, registered
onto the Click tree, and `sb jam-pr-list`, `sb --help`, shell completion and the
palette all worked the moment registration did. The four rules earned their
keep — a `[tool.run]` and a `["docker", "ps"]` were both in the first real
`tools.toml` written by hand, and both were refused and named.

**"`catalog.py` is untouched" was too strong, and one of the two lines it
actually needed was a safety hole.** The Shape table originally claimed the
palette would find a tool with no change to `cli/canvas/catalog.py` at all. The
first line is benign: `saved` has to reach the sidebar somehow, and it is read
off the command object exactly the way `sb_surface` is.

The second is the interesting one. `acts` was computed as
`path[:1] == ("run",)` — correct for every command that existed when it was
written, and **wrong for a saved command by construction**, because the path of
`sb deploy-thing` is one word and the `run` hiding inside it is invisible from
there. Left alone, a tool wrapping `sb run` would have come back `acts: false`
and the canvas would have offered a refresh cadence on a write. That is the
exact failure the read/write split exists to prevent, arriving through the
feature that was supposed to inherit the split rather than break it.

The invariant the claim was *protecting* survived intact: nothing keeps a
command table, and neither line names a command. What was wrong was the
strength of the claim, not the design. A property read off a command object is
still a property read off a command object even when a second one is needed.

**Two smaller ones.** `htm` does not decode HTML entities, so `sb &lt;tool&gt;`
in a template renders those four characters on screen rather than `sb <tool>`;
angle brackets have to arrive as a string expression. Caught only by reading the
DOM back, which is the argument for doing that at all.

And the test asserting the shipped example names no home directory was written
against the file *text*, where it immediately failed on a comment saying
`~/.config/sb/tools.toml`. Naming the XDG default is documentation; the rule is
about paths a real machine has. The test now parses the example and checks the
*argvs*, which is the thing that could leak.

**`SB_HOME` isolation matters more than `SB_STATE`'s.** A tool is an argv sky.boss
will run, so a suite that read the real home would register the operator's own
commands into the tree under test, and `sb --help` would differ between two
machines running the same suite. `tests/conftest.py` redirects it before
anything imports `cli`, for the same reason and at the same point.

**Not built, and still not wanted:** anything that writes. No `sb tool add`, no
`POST /api/tools`, no save button. The argument in Shape rule 4 is unchanged by
having built the read half — if anything it is stronger now that a tool is
demonstrably an argv sky.boss will execute on a cadence.

### 2026-08-21 — the words moved; the history stays (supersession)

`wrap` was renamed `data` and the `every` field renamed `refresh` — hard renames, no aliases;
see [[refresh]]. This doc predates the rename and its prose says `wrap` because it *was*
`wrap`; that is history being accurate, and nothing above has been scrubbed.

### Round 2 — drafted, awaiting the word (2026-08-22)

Drafted at the operator's direction from the `sb --help` screenshot. The reversal is recorded
above with round 1's reasoning kept: registration-for-free was the argument, and it survives
nesting; only the root-level address and the shadowing rule change. The REFRESH-column
question was resolved as presentation, not model — the field is a default, the flag is a
request, one number by design.

### Round 2 — shipped (2026-08-22)

The move held its promise: the group is `invoke_without_command`, registration targets it,
and the bare listing came through byte-identical without a second listing command. Three
things worth recording:

- **The dotted envelope path cost nothing.** `make_command` already built the sub-context
  with the group's context as parent, so `_command_path` produced `tools.jam-pr-list` the
  moment registration moved — the surfaces phase's envelope work landed inside the group
  phase, by construction rather than by code.
- **The catalog needed one honest new idea**: a group that runs bare is a leaf as well as a
  container, so `walk` offers `sb tools` (the listing, pinnable) while plain groups stay
  out. And `resolve_follow` now descends groups to find a saved keyword, still server-side,
  still off the live tree.
- **The short name nearly ate an argument.** `open()` in app.js sliced typed words by the
  argv's length; with `prs` naming the two-word argv `tools prs`, the first word typed after
  the name would have been dropped silently. Caught by reading the flow, fixed by counting
  the words the typed text spent *naming* the entry. The palette's short-name matching was
  verified by importing the live module inside the served page — the no-test-runner
  workaround in its newest form.

`-t` is one function applied in the root group's `main`, and the prefix form
(`sb -t --refresh 30 x`) needed no rule of its own — it is an ordinary usage error because
the group owns no such option. Deliberately not built: any back-compat top-level
registration; the palette teaches the new spelling by showing it.

### Round 3 — drafted, awaiting the word (2026-08-22)

Asked for in the same breath as [[follow]] round 2: *"i think we also need to spec a save
mechanism that allows someone to append a `--save=[name-of-tool]` to the end of data, read, and
follow commands."* The three commands named are the three observes, and the two decisions that
were the operator's rather than the doc's were put to them directly and answered the same day:
**observes only**, and **save then run**.

**The interesting part of this round is what it does *not* reverse.** Round 1 ended with "Not
built, and still not wanted: anything that writes", and it would have been easy to read that as
settled and refuse the request, or to read the request as permission and drop the rule. Neither
is right. The sentence was broader than the argument holding it up: every word of the reasoning
is about the *canvas server* — a port, a route, a transient compromise made persistent. A flag
typed in the operator's own shell is not any of those things, and the rule survives in the form
its argument actually supports. That is the whole reason Notes accretes rather than rewrites:
the original argument was still legible, so it could be checked against the new request instead
of remembered as a slogan.

**Append-only was the design decision, not the flag.** The obvious shape — read the TOML, add a
key, write it back — quietly requires a TOML *writer* (stdlib has `tomllib`, which only reads),
and whichever one you pick then owns how the operator's hand-written file looks: comments gone,
argv lists reflowed, ordering by whatever the serialiser prefers. Appending one block sidesteps
all of it and buys a stronger claim than tidiness: **sky.boss never touches a line the operator
wrote.** It is also what makes "no overwrite" natural rather than a restriction — you cannot
edit in place if you never rewrite, so editing stays exactly where it already was.

**The property most worth testing is the round-trip**, and it is testable end to end because
the loader is already pure over an injected home: save an invocation, re-register the file, and
assert the registered tool's expansion is the line that created it. A save that produced a tool
which merely *looked* right would be invisible until the day it ran — the same class of failure
as the `every`-field rename in [[refresh]] round 1, which is the precedent for insisting on it.

### 2026-08-22 — the slug moved, the name did not

The repo took the name **toolbox**, which put the project and this doc on the same word.
The doc took the new slug `[[tools]]` rather than the project taking a different one: it documents
`sb tools`, which is where round 2 put saved commands anyway, so the slug now matches the command
instead of matching the concept's nickname. Nothing in the prose was scrubbed — "the toolbox" is
still what the collection is called, here and in `cli/tools.py`, and the 16 links that pointed at
`[[toolbox]]` were rewritten in one pass. This is the only doc whose slug the rename touched.

### Round 3 — executed (2026-08-22)

What the execution argued back:

- **`sys.argv` could not be the source, and finding that out early shaped the design.** "Save
  what you typed" reads like `sys.argv[1:]` until you write the first test: under a `CliRunner`
  that is *pytest's* argv, so every test of the feature would have been an integration test
  against a real process. The record is taken in `Root.main` instead — the one place both a
  terminal and the suite pass through — which made `saved_argv` a pure function over a list and
  the round-trip assertion cheap. A seam that exists for testability usually costs something;
  this one was also the only correct place.
- **The cadence had to be lifted out of the argv, and the spec's one line about it was
  load-bearing.** `refresh` is recorded as the tool's *field*, so `--refresh 30` must not also
  survive inside the saved argv — left there, `sb tools prs` would go resident on its own, and
  [[refresh]] is explicit that residency is never ambient. Lifting it turned out to need a
  second rule immediately: a value the surface cannot cycle to (`--refresh 7`) is refused **at
  save time**, because writing cleanly and then failing to load is the worst of both outcomes
  and the operator would meet it days later.
- **The `--` boundary is where a naive scan would have corrupted an argv.** `sb read --save=mine
  -- sometool --save=theirs` is legal and means two different things by the same word. Click
  never parsed the second one as ours, so neither does the scan: it stops looking at `--` and
  copies the rest verbatim. This is the failure that would have been invisible until someone
  wrapped a tool that happens to have a `--save` of its own.
- **The envelope needed a human half the spec did not mention.** "The envelope says where it
  went; under `--json` that is a field, not prose" — true, and it leaves the *human* path saying
  nothing at all, so `sb read --save=x -- thing` would print the output and no confirmation. The
  answer is one `saved_note` on stderr, called from `render`, naming the **expansion** rather
  than just the file: the file says a write happened, the expansion is the operator's one chance
  to notice the saved line is not the line they meant while they still remember typing it.
- **Hand-rolled TOML escaping earned its keep on the first real run.** `sb read --save greet --
  printf 'hello %s\n' world` round-tripped through `"hello %s\\n"` and came back printing a
  newline, which is exactly the case a naive `f'"{part}"'` would have silently broken. The
  stdlib reads TOML and does not write it, and this is the whole reason appending — rather than
  re-serialising the operator's file — is the safe shape.


### 2026-08-27 — the name moved again, and this time it took the noun

`tb` became `sb` and `toolbox` became `sky.boss` across current-tense prose, code and identifiers.
That reversed the ruling three entries above. The 2026-08-22 record stands unedited because the
argument it makes is still the interesting one: a project name and a common noun can share a word
without confusion, and "the toolbox" was what the collection *was*.

What broke it was not the argument but the CLI. Once `tb` → `sb` was in scope, keeping "toolbox"
meant the box of saved commands was named after a tool that no longer existed under that name — a
noun pointing at nothing. Rather than coin a replacement, the container lost its nickname: it is
**the tools**, `sb tools` lists them, and `cli/tools.py` documents them. The sidebar header reads
`TOOLS`, and its CSS is `.tools` wrapping the `.tool` rows that were always there, which is a
better pairing than `.toolbox` wrapping `.tool` ever was.

The cost is that this doc's slug, `[[tools]]`, now matches the concept as well as the command — the
2026-08-22 entry chose it for the command precisely *because* the concept was called something
else. The slug did not need to move a second time, which is the only piece of luck in the change.

### Round 4 — executed (2026-08-28)

**The reversal was the easy part; the premise it rested on was the interesting part.** Rule 4's
security argument had one load-bearing clause — *"a hostile page that defeated the guard today gets
one command"* — and that clause was false from the day `/api/run` shipped. A page past the guard
gets an arbitrary argv, and one argv appends to `tools.toml` on its own. The rule was defending a
boundary that had already moved, which is the most durable kind of wrong: nothing about it looked
stale, because the sentence was still well-written and the guard it named was still real.

**Splicing beat round-tripping and the reason is not aesthetic.** `tomlkit` would have preserved
comments and re-serialised the whole document; a line-range splice leaves every other byte
identical *by construction*, which is a claim a test can make cheaply and completely
(`after[after.index("[tool.beta]"):] == before[...]`). The dependency was the smaller cost and
still the wrong trade.

**Two defects the first hand-exercise caught, both invisible to a passing test:**

- Replacing a block **ate the blank line** separating it from its neighbour. The file still parsed
  and the tool still ran; it just read as sky.boss having reformatted something nobody asked it to
  touch — the exact thing splicing exists to avoid, reintroduced by the splice.
- The fix for that then **doubled** the blank line, because the range was shrunk to exclude the
  trailing blanks *and* those blanks were re-emitted. Both directions of the same off-by-one, found
  by printing the file rather than by asserting on it.

**`--save`'s split turned out to be a mechanism, not a design.** The bench had two save paths — a
button for observes, a paste-this-block for acts — and the reason was that saving ran the argv again
with `--save` in it, `--save` saves by example, and there is no example for a write you have not
run. A route needs no example, so the split dissolved: one button, every contract. Worth recording
because the doc had rationalised the asymmetry as principle for two rounds.

**The catalog was shipping the wrong argv for this job, and only building against it showed that.**
A saved command's `argv` is the path you *type* — `["tools", "drainer"]` — which is correct for
running it and empty of information for editing it. The edit action was written against it and
recovered the string `"drainer"` as the whole command line. `expansion` is now a separate field,
which keeps `argv` meaning one thing.

**Verified end to end against a scratch `$SB_HOME`** rather than the operator's real one: create an
act from the bench, reopen it from the rail, replace it, delete it. The file returned **byte for
byte** to its starting state with both comments intact, and three backups were written — one per
write, which is the promise.
