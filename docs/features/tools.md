---
status: active
created: 2026-08-20
updated: 2026-08-22
agent_value: 3
key_files:
  - cli/tools.py
  - cli/helpers.py
  - cli/__init__.py
  - cli/canvas/catalog.py
  - cli/canvas/server.py
  - cli/canvas/static/app.js
  - cli/canvas/static/tb.css
  - tools.example.toml
  - tests/test_tools.py
  - tests/conftest.py
---

# The toolbox — commands the operator saves

*Slug renamed `toolbox` → `tools` on 2026-08-22, when the repo took the name `toolbox`. Links are
`[[tools]]`, which is also the command group this documents; the collection itself is still called
the toolbox throughout, because that is what it is.*

## Why

The command this repo exists to make easy currently reads:

```
tb wrap --cols number,title,merge_state,behind,checks.failed \
        --cwd ~/src/jam.sense -- jam pr list --json
```

That is 110 characters, three of which are the part you were thinking about. It has to be retyped
into the palette every time, it dies with the window, and two of its arguments are things you have
to *remember*: that `jam` needs `--cwd` because its wrapper resolves `.venv` against the working
directory, and which five of its fourteen columns are the ones worth seeing.

Neither of those is a fact about tb. They are facts about *this operator's machine*, learned once,
and there is nowhere to put them. So they get retyped, or more realistically they get retyped
wrong and the window comes back with fourteen columns again.

The wireframe already has the answer drawn: `Toolbox Surface.dc.html` carries a 184px sidebar
headed **TOOLBOX**, with a footer reading `tb <tool>`. The sidebar is empty — a `flex:1` spacer
between a header and a footer. This is the feature that fills it, and the footer is the whole
specification in three words: **a saved command is invocable as `tb <name>`.**

```
tb jam-pr-list
```

## Shape

A file the operator writes, at `$TB_HOME/tools.toml`:

```toml
[tool.jam-pr-list]
description = "Open PRs, with the merge column GitHub cannot show"
argv  = ["wrap", "--cols", "number,title,merge_state,behind,checks.failed",
         "--cwd", "~/src/jam.sense",
         "--", "jam", "pr", "list", "--json"]
every = 30
```

`$TB_HOME` defaults to `~/.config/tb/`. **Config, not state** — `$TB_STATE` already exists for the
browser profile, which is machine-generated and something you would reasonably `rm -rf` to reset
the canvas. A file you authored must not be in the blast radius of that.

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
exist. A naive toolbox breaks that immediately: a sidebar reading a TOML file is a second list of
commands, drifting against the first.

So tools are not a second list. At startup `cli/__init__.py` reads the file and calls
`cli.add_command()` for each one, building a `click.Command` whose callback re-dispatches into the
root group with the declared argv. Everything downstream then works with **no code change at all**:

| comes free | because |
|---|---|
| `tb jam-pr-list` | Click knows the command |
| `tb --help` lists it | Click knows the command |
| the palette offers it | `catalog.walk` walks the real tree — two lines added, see Notes |
| shell completion completes it | `_TB_COMPLETE=fish_source` walks the real tree |
| the TOOLBOX sidebar | filters the catalog it already fetches on `tb_saved` |

The sidebar marks its entries with `tb_saved` set on the command object, mirroring how `tb ui`
excludes itself with `tb_surface` — **a property on the command, never a name written down in a
module.** A name in a skip-list is the beginning of the command table this design refuses to keep.

### Four rules that are not negotiable

1. **`argv` is a tb argv, never a shell argv.** `["wrap", "--", "jam", …]` means `tb wrap -- jam …`.
   A tool cannot name an arbitrary executable, because a tool that could would be a second `tb run`
   — one that skips the read/write distinction the whole design rests on. Everything a tool wants
   is already reachable through `run` or `wrap`, and going through them is what keeps **`tb run`
   the single command that acts**.

2. **`acts` is inherited, never declared.** Resolve the expansion's leaf in the Click tree and take
   *its* `acts`. A tool expanding to `run` acts and the canvas will not offer it a cadence; a tool
   expanding to `wrap` reads and may be pinned. The operator already made this assertion when they
   chose `run` or `wrap` — asking again in the TOML would be asking them to contradict themselves,
   and a safety property must have one source. It follows that **`every` on a tool that acts is
   refused at load**, for the same reason the canvas hides the pin control on one.

3. **A builtin always wins.** *(Round 2 retired this into structure: saved commands live behind
   the `tools` group, where `[tool.run]` collides with nothing — `tb run` is the builtin and
   `tb tools run` is the tool. The rule below was validation while tools sat on the root, and its
   reasoning is kept as written.)* A tool named `run`, `wrap`, `ui` or `tools` is skipped with a
   warning naming the collision. Nothing operator-authored may shadow a tb command — otherwise a
   stray `[tool.run]` silently redefines the one door that writes.

4. **No *surface* writes this file, and tb only ever appends to it.** *(Round 3, 2026-08-22,
   narrowed this from "tb never writes this file" — `--save` writes one appended block from the
   terminal. The security argument below is unchanged and is what the narrowing was measured
   against; the sentence it was protecting was broader than the argument.)* Creation and every
   edit are `$EDITOR`'s. The canvas server is remote code execution bound to a port and is
   treated that way; giving it a route that writes a file tb will later *execute* would convert
   a transient compromise into a persistent one. A hostile page that defeated the
   header-and-token guard today gets one command; with a write route it would get every command
   from then on. That is not a trade worth making for a save button, and the button
   can be added later against a design that has thought about it.

`~` in an argv is expanded, since the whole point is that these are operator paths.

`tb tools` lists what is declared — a read, so a window may hold it open.

**Does not do:**

- **No writing, from anywhere.** No `tb tool add`, no `POST /api/tools`, no "save this window as a
  tool" button. See rule 4. This is the round that proves the read half; the write half is a
  separate design with a security argument to make. *(Round 3 built exactly that separate design
  and kept two thirds of this line: there is still no route and still no button. What exists is
  `--save`, typed by the operator in their own terminal — the same trust level as `$EDITOR`,
  reached the same way.)*
- **No arguments.** A tool is a *fixed* argv. `tb jam-pr-list 945` is refused rather than appended,
  because a tool that takes arguments is a shell function, and this is not a shell.
- **No groups, no nesting.** Flat names at the top level. `tb jam-pr-list`, not `tb jam pr-list`.
- **No shell.** No pipes, no `&&`, no interpolation, no `shell=True`. Argv only, unchanged from
  [[canvas]].
- **No sync, no sharing, no machine awareness.** One file, one machine. A tool naming a host that
  is not on this tailnet fails when run, not at load — tb does not validate the world.
- **Does not read the repo.** There is no in-repo fallback path to `$TB_HOME` and there must never
  be one. That fallback is precisely how operator content ended up committed last time.

## Phases

### Round 1 — the toolbox reads (2026-08-20)

- [x] `TB_HOME` in `cli/helpers.py` alongside `STATE_DIR`, defaulting to `~/.config/tb/`.
- [x] `cli/tools.py`: load and validate `tools.toml` as pure functions over a parsed dict, plus
      `tests/test_tools.py`. Absent file → `[]`. Malformed tool → skipped with a warning naming it,
      never an exception; one bad entry must not cost the operator the other nine.
- [x] Validation covers the four rules: tb-argv only, `acts` inherited, builtin collisions refused,
      `every` refused on a tool that acts.
- [x] Register tools onto the root group in `cli/__init__.py`. `tb jam-pr-list` runs; `tb --help`
      lists it. **`catalog.py` needed two lines after all** — the claim that it would need none was
      too strong, and the second line was a real safety hole. See Notes.
- [x] `tb tools` — a read listing name, description, expansion and `acts`.
- [x] `tb_saved` on generated commands; catalog carries it through.
- [x] TOOLBOX sidebar in `app.js` renders catalog entries where `tb_saved`, click opens a window,
      a tool's `every` becomes the window's starting interval. Tracked as a task of [[canvas]]
      Round 5, which owns the sidebar's chrome.
- [x] Ship a `tools.example.toml` in the repo. Generic — no operator paths in a tracked file, and
      a test asserts the tracked example names no home directory.


### Round 2 — the toolbox gets its own door (2026-08-22)

Prompted by the operator reading `tb --help`: `jam-pr-list` renders between `follow` and
`read`, and the builtin/operator line — the sharpest line in the design — is invisible in the
one listing where it matters most. The operator's call: **saved commands move behind
`tb tools`**, with `-t` as the short spelling.

    tb tools jam-pr-list --refresh 30
    tb -t jam-pr-list --refresh 30

**This reverses a round-1 decision and keeps its reasons.** Round 1 registered tools on the
root so the palette, `--help` and completion would work for free; nesting keeps all three —
the catalog already walks groups, and a leaf under `tools` is still an ordinary leaf. What
nesting *dissolves* is the shadowing defense: `tb tools run` collides with nothing, so
"a builtin always wins" stops being a validation rule and becomes structure. The name check
stays only as the shape a command word must have.

- **`tools` becomes a group that still lists when bare.** `tb tools` with no subcommand
  prints exactly today's listing (declared, refused, and — per [[capture]] when it lands —
  formats). One door for "what did I save"; no second listing command.
- **`-t` is an argv spelling of `tools`, rewritten at the root** — not a Click alias and not
  a flag with behavior: `tb -t …` becomes `tb tools …` before parsing, in one tested place.
  Options follow the tool name, as they do on every tb command; the prefix form
  (`tb -t --refresh 30 jam-pr-list`) was considered and rejected — it would teach the group a
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
  given. The listing keeps the column, and `tb tools`' help states that rule in one line. The
  line to hold is unchanged: the field must never cause residency on its own.

Does not do, this round: no change to tools.toml (declarations are untouched; only the
address moves), no back-compat top-level registration — a hard move, one operator, and the
palette teaches the new spelling immediately.

- [x] **The group.** `tools` becomes `invoke_without_command`; registration targets it;
      the listing behavior is byte-identical when bare. Shadowing tests retire into
      structure; name-shape validation stays.
- [x] **`-t`.** Root-level argv rewrite with tests: `tb -t x` ≡ `tb tools x`, `tb -t` ≡
      `tb tools`, and `-t` anywhere else is untouched.
- [x] **Surfaces.** Envelope says `tools.<name>` (test updated with the reversal noted);
      palette/sidebar show the short name; canvas execution unchanged through the runner.
- [x] **Docs.** CLAUDE.md command table says `tb tools <name>` / `tb -t <name>`; `tb tools`
      help carries the refresh-default sentence; [[refresh]] bare-flag prose confirmed
      unchanged.

### Round 3 — saving the command you just ran (2026-08-22)

**The gap is the one round 1 named and deferred.** A tool is a name plus a tb argv, and the only
way to make one is to open `$EDITOR`, remember the TOML shape, and retype an argv you had
working thirty seconds ago in your shell. The command this whole doc exists to make easy is
*still* 110 characters the first time, and the moment you have it right is the moment you are
furthest from a text editor.

    tb data --cols number,title,merge_state --cwd ~/src/jam.sense \
            -- jam pr list --json --save=prs

Then `tb tools prs` forever. **Save by example, from the terminal, at the end of the command
that worked.**

**This narrows rule 4 and keeps its argument intact.** The rule said *tb never writes this
file*; the argument underneath it was about **the canvas server**, which is remote code
execution bound to a port, and about a *route* that would turn a transient compromise into a
persistent one. None of that applies to a flag the operator types in their own shell — that is
the same trust level as `$EDITOR`, arrived at by a shorter path. What survives unchanged: no
`POST /api/tools`, no save button on a window, no write from any surface. The narrowing is
recorded in Shape rule 4 with the original sentence visible beside it.

**Three properties make the write safe to have at all:**

1. **tb appends; it never rewrites.** The saved entry is a `[tool.<name>]` block added at the
   end of the file. Nothing above it is re-serialised, reordered, or reformatted, so every
   comment, blank line and hand-written argv the operator wrote survives byte-for-byte. This is
   not politeness — round-tripping TOML would mean either a writer dependency or tb's own
   serialiser deciding how the operator's file should look, and both are ways to lose a file
   that is not tb's. **Editing and deleting stay `$EDITOR`'s**, which is also why there is no
   `--save` overwrite: a name already declared is refused, naming what it currently runs.
2. **The saved argv is what you typed.** Taken from the invocation itself, from the tb command
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

- **No description, no editing, no removal.** `--save` writes a name and an argv. A description,
  a changed argv, a deleted tool: `$EDITOR`, one file, no ceremony. A `--describe` flag is a
  second thing to type at exactly the moment the operator wants to type less.
- **No overwrite, no `--force`.** An existing name is refused with what it currently runs. The
  fix is to edit the file, which is the one place edits happen.
- **Still no route and still no button.** The canvas gains nothing. Its argv path can carry the
  flag the same way it can carry any word, and that is honestly not a new hole: a client that
  can reach the API can already ask for `tb run -- <anything>`, which is strictly more. tb does
  not filter the flag out server-side, because a filter would be the server keeping a list of
  tb's flags — the command table this design refuses to keep, in its most brittle form.
- **No `~` re-contraction.** The shell expanded `~` before tb ever saw it, so an absolute path is
  what gets saved. `_expand` still exists for the hand-written `~` in a file the operator typed.
- **No validation of the world.** A saved argv naming a host, a repo or a tool that is not there
  fails when it runs, exactly as a hand-written one does.

- [ ] **The writer.** `save()` in `cli/tools.py`: validate the name against `_NAME`, refuse one
      already declared (naming its expansion), append a `[tool.<name>]` block with the argv and
      any `refresh`. Pure-ish over an injected home; tests write to `tmp_path` and never to the
      real `$TB_HOME` (`conftest.py` already redirects it, and this is the round where that
      matters most). The module docstring's "Nothing here writes" is amended with the reversal.
- [ ] **The flag, on the three observes.** `--save NAME` on `data`, `read` and `follow`; absent
      from `run`. The argv is reconstructed from the invocation, and a test asserts the
      round-trip: save a real invocation, re-register the file, and the tool's expansion equals
      the line that made it — including `--cols`, `--cwd`, `--from` and the `--` separator.
- [ ] **Save, then run.** The write happens before execution, so a resident command saves and a
      failing command still saves. Proven on `follow` without opening a stream, the way the
      dispatch test already proves the file form.
- [ ] **What it says.** The envelope carries where it went and what it will run; `--help` on all
      three carries the flag with a runnable example, which the [[refresh]] help test already
      enforces. `tb tools` needs no change — the new entry is an entry.
- [ ] **Docs.** CLAUDE.md's `$TB_HOME` row says the operator *and* `--save` author `tools.toml`;
      its "Nothing here writes" claim, if it carries one, is amended with the same reversal.

## Notes

### Round 1 — what shipped, and the claim that did not survive (2026-08-20)

The model held exactly as designed: a tool is a name plus a tb argv, registered
onto the Click tree, and `tb jam-pr-list`, `tb --help`, shell completion and the
palette all worked the moment registration did. The four rules earned their
keep — a `[tool.run]` and a `["docker", "ps"]` were both in the first real
`tools.toml` written by hand, and both were refused and named.

**"`catalog.py` is untouched" was too strong, and one of the two lines it
actually needed was a safety hole.** The Shape table originally claimed the
palette would find a tool with no change to `cli/canvas/catalog.py` at all. The
first line is benign: `saved` has to reach the sidebar somehow, and it is read
off the command object exactly the way `tb_surface` is.

The second is the interesting one. `acts` was computed as
`path[:1] == ("run",)` — correct for every command that existed when it was
written, and **wrong for a saved command by construction**, because the path of
`tb deploy-thing` is one word and the `run` hiding inside it is invisible from
there. Left alone, a tool wrapping `tb run` would have come back `acts: false`
and the canvas would have offered a refresh cadence on a write. That is the
exact failure the read/write split exists to prevent, arriving through the
feature that was supposed to inherit the split rather than break it.

The invariant the claim was *protecting* survived intact: nothing keeps a
command table, and neither line names a command. What was wrong was the
strength of the claim, not the design. A property read off a command object is
still a property read off a command object even when a second one is needed.

**Two smaller ones.** `htm` does not decode HTML entities, so `tb &lt;tool&gt;`
in a template renders those four characters on screen rather than `tb <tool>`;
angle brackets have to arrive as a string expression. Caught only by reading the
DOM back, which is the argument for doing that at all.

And the test asserting the shipped example names no home directory was written
against the file *text*, where it immediately failed on a comment saying
`~/.config/tb/tools.toml`. Naming the XDG default is documentation; the rule is
about paths a real machine has. The test now parses the example and checks the
*argvs*, which is the thing that could leak.

**`TB_HOME` isolation matters more than `TB_STATE`'s.** A tool is an argv tb
will run, so a suite that read the real home would register the operator's own
commands into the tree under test, and `tb --help` would differ between two
machines running the same suite. `tests/conftest.py` redirects it before
anything imports `cli`, for the same reason and at the same point.

**Not built, and still not wanted:** anything that writes. No `tb tool add`, no
`POST /api/tools`, no save button. The argument in Shape rule 4 is unchanged by
having built the read half — if anything it is stronger now that a tool is
demonstrably an argv tb will execute on a cadence.

### 2026-08-21 — the words moved; the history stays (supersession)

`wrap` was renamed `data` and the `every` field renamed `refresh` — hard renames, no aliases;
see [[refresh]]. This doc predates the rename and its prose says `wrap` because it *was*
`wrap`; that is history being accurate, and nothing above has been scrubbed.

### Round 2 — drafted, awaiting the word (2026-08-22)

Drafted at the operator's direction from the `tb --help` screenshot. The reversal is recorded
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
  container, so `walk` offers `tb tools` (the listing, pinnable) while plain groups stay
  out. And `resolve_follow` now descends groups to find a saved keyword, still server-side,
  still off the live tree.
- **The short name nearly ate an argument.** `open()` in app.js sliced typed words by the
  argv's length; with `prs` naming the two-word argv `tools prs`, the first word typed after
  the name would have been dropped silently. Caught by reading the flow, fixed by counting
  the words the typed text spent *naming* the entry. The palette's short-name matching was
  verified by importing the live module inside the served page — the no-test-runner
  workaround in its newest form.

`-t` is one function applied in the root group's `main`, and the prefix form
(`tb -t --refresh 30 x`) needed no rule of its own — it is an ordinary usage error because
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
all of it and buys a stronger claim than tidiness: **tb never touches a line the operator
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
`tb tools`, which is where round 2 put saved commands anyway, so the slug now matches the command
instead of matching the concept's nickname. Nothing in the prose was scrubbed — "the toolbox" is
still what the collection is called, here and in `cli/tools.py`, and the 16 links that pointed at
`[[toolbox]]` were rewritten in one pass. This is the only doc whose slug the rename touched.
