---
status: draft
created: 2026-08-20
updated: 2026-08-20
agent_value: 3
key_files:
  - cli/tools.py
  - cli/helpers.py
  - cli/__init__.py
  - cli/canvas/catalog.py
  - cli/canvas/static/app.js
  - tests/test_tools.py
---

# The toolbox — commands the operator saves

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

The wireframe already has the answer drawn: `Tackle Box Surface.dc.html` carries a 184px sidebar
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
| the palette offers it | `catalog.walk` walks the real tree — `catalog.py` is untouched |
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

3. **A builtin always wins.** A tool named `run`, `wrap`, `ui` or `tools` is skipped with a warning
   naming the collision. Nothing operator-authored may shadow a tb command — otherwise a stray
   `[tool.run]` silently redefines the one door that writes.

4. **tb never writes this file.** Creation is `$EDITOR`. The canvas server is remote code execution
   bound to a port and is treated that way; giving it a route that writes a file tb will later
   *execute* would convert a transient compromise into a persistent one. A hostile page that
   defeated the header-and-token guard today gets one command; with a write route it would get
   every command from then on. That is not a trade worth making for a save button, and the button
   can be added later against a design that has thought about it.

`~` in an argv is expanded, since the whole point is that these are operator paths.

`tb tools` lists what is declared — a read, so a window may hold it open.

**Does not do:**

- **No writing, from anywhere.** No `tb tool add`, no `POST /api/tools`, no "save this window as a
  tool" button. See rule 4. This is the round that proves the read half; the write half is a
  separate design with a security argument to make.
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

- [ ] `TB_HOME` in `cli/helpers.py` alongside `STATE_DIR`, defaulting to `~/.config/tb/`.
- [ ] `cli/tools.py`: load and validate `tools.toml` as pure functions over a parsed dict, plus
      `tests/test_tools.py`. Absent file → `[]`. Malformed tool → skipped with a warning naming it,
      never an exception; one bad entry must not cost the operator the other nine.
- [ ] Validation covers the four rules: tb-argv only, `acts` inherited, builtin collisions refused,
      `every` refused on a tool that acts.
- [ ] Register tools onto the root group in `cli/__init__.py`. `tb jam-pr-list` runs; `tb --help`
      lists it. Assert `catalog.py` needed no edit — that assertion is the point of the design.
- [ ] `tb tools` — a read listing name, description, expansion and `acts`.
- [ ] `tb_saved` on generated commands; catalog carries it through.
- [ ] TOOLBOX sidebar in `app.js` renders catalog entries where `tb_saved`, click opens a window,
      a tool's `every` becomes the window's starting interval. Tracked as a task of [[canvas]]
      Round 5, which owns the sidebar's chrome.
- [ ] Ship a `tools.example.toml` in the repo. Generic — no operator paths in a tracked file, and
      a test asserts the tracked example names no home directory.

## Notes

