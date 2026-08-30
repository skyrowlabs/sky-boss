# CLAUDE.md

Guidance for Claude Code when working in this repository.

Machine-specific context — this operator's network, sibling repositories, and home setup — lives
in `CLAUDE.local.md`, which is gitignored. If you are reading this in a fresh clone, that file is
absent and nothing here depends on it.

## What this repo is

**sky.boss** is the homebase kit for a primary workstation and the machines around it, behind one
operator CLI: `sb`.

**It was `tackle-box` until 2026-08-22, `toolbox` until 2026-08-26, and the CLI was `tb` until
2026-08-27.** All three are gone from current-tense prose, because an old project name reads as a
second project. Git history keeps them: rewriting history to chase a rename is a cost with no
reader.

**The 2026-08-27 pass finished what the previous two left open**, and it reversed two decisions
that were written down here as settled. `tb` → `sb` was explicitly out of scope and is now done.
The common noun was explicitly staying and is now gone: [[tools]] had ruled that "the toolbox" —
the box of saved commands — was not the project's name and could keep the word, but the CLI rename
took the word with it, so the container simply lost its nickname rather than gaining a new one.
It is **the tools**, which is what `sb tools` already called them. The identifier cluster —
*one decision, not four*, as [[open]] held it until the item was closed and removed — moved as
one: `$SB_HOME` defaulting to
`~/.sky-boss`, the MCP server name `sky-boss`, the window class `sb`, and the internal CSS and
package names.

**One thing still says the old name, on purpose.** *A name recorded as history* — "it was
`toolbox` until 2026-08-26" — is a fact about the past, and scrubbing it would make the sentence
false; that is why the rename notes in [[tools]] and [[header]] read the way they do. The **mark**
was the other one and is not any more: it was a drawing of a toolbox lettered `TOOLBOX`, printed
beside the word by `cli/banner.py`, and it was redrawn the same day as a **control tower**
([[header]] round 2). `ART` in `cli/banner.py` is the picture; `docs/design/render-mark.py` renders
both PNGs from it, so the drawing and the word cannot drift apart again — which they had, for
exactly as long as it took to notice.

**This is a machine-neutral repo, as of the 2026-08-22 pass.** Nothing tracked here names a host,
a distro, a desktop environment, or a window-manager rule — the mechanisms are documented, the
machine that hit them is not. That is not squeamishness: it is the same rule as `$SB_HOME`.
Operator content used to live in this repo and carried a tailnet address into every commit, so
the tool could not be published without publishing the operator. Machine-specific context belongs
in `CLAUDE.local.md`, which is gitignored. **A host name in a tracked file is a bug to fix, not
context to preserve.**

**A real example is kept on purpose.** Feature docs work through `jam pr list --json` — a sibling
CLI — rather than a placeholder, because the arguments are load-bearing on a *real* tool: why
`--cwd` is needed at all, why fourteen columns is the wrong number, why a foreign CLI cannot hold
itself open. A `mytool` makes those paragraphs vague and unfalsifiable. What was removed is the
**path** it lived at, which said something about a machine; what stayed is a tool name, which does
not. Apply that test to the next example rather than reaching for a placeholder by reflex.

**It is young.** On 2026-08-20 the job layer, the asset register, the check suite and the watch
system were removed to design that half over from a clean base, and the terminal surface was
replaced by a browser one the same day. What exists:

| Command | Does |
|---|---|
| `sb run -- <argv>` | Runs a command and reports what it printed. **The only command that acts**. `--delay 5m` runs it once, later, behind a countdown you can cancel |
| `sb data -- <argv>` | Reads another CLI's JSON as data. An observe; `--refresh N` keeps it resident |
| `sb data <path>` | Reads a file of records as data — `--from jsonl` is one object per line. See [[jsonl-reads]] |
| `<project>:<path>` | An address, not a command: a declared project's state directory. See [[state-root]] |
| `sb read -- <argv>` | Shows what a command printed, verbatim. An observe, for tools with no `--json` |
| `sb follow -- <argv>` | Holds a command's stream open. Resident by nature; any exit is a visible death. Arrows and PgUp scroll back through the ring |
| `sb follow <path>` | Follows a file with a native stat cursor, so quiet and dead are different words. `--due 15m` makes late a word too |
| `sb roll-call` | Asks every declared project how it is and folds the answers. An observe. See [[roll-call]] |
| `sb mcp` | Speaks MCP on stdio, offering the tools to an agent. A surface. See [[mcp]] |
| `sb tools` | Lists the operator's saved commands, and any that failed to load, grouped |
| `sb ui` | Opens the surface: **the canvas**, a command palette over tiled and floating windows, and **the workbench**, where a command gets authored. See [[workbench]] |
| `sb tools <name>` | Runs a saved command; `sb -t <name>` is the short spelling. See [[tools]] |

**`--save NAME` on `read`, `data` and `follow`** saves the invocation as a tool and then runs it,
appending one block and refusing a name that exists — `--save` saves *by example*, and there is no
example for a write you have not run, which is why `run` does not take it.

**The surface writes too, as of [[tools]] round 4 (2026-08-28), and that reverses a rule stated
twice here.** `POST /api/tools` creates, replaces and deletes; the bench's save button goes down it
and the tools rail carries ✎ and ✕. Three things make it not the thing that was refused. A write
**splices one block's line range** rather than round-tripping the document, so every other byte —
including the operator's comments — is untouched by construction. Every mutating write **copies the
file into `$SB_HOME/backups/` first**, last 20 kept. And `write_problem` runs the *loader's own*
`_check`, so the writer cannot accept a tool the tree will then refuse.

The security argument that had blocked it was against a false premise: it held that a hostile page
past the guard "gets one command", where a write route would get every command from then on. A page
past the guard gets `/api/run` and an arbitrary argv, which appends to `tools.toml` by itself.
**Persistence was already on that side of the boundary**, so the route hands an attacker nothing.
The guard is unchanged and is still the whole defence.

`sb` and `sb --help` open with the mark — `docs/design/cli-header.png` drawn in half-blocks, see
[[header]]. It refuses to draw on a narrow or non-terminal surface rather than wrapping.

**Check before you describe.** This is young and moving, and it just lost most of its surface area.
When asked about a command or module, confirm it exists rather than inferring it from this
document, and correct the document when it has fallen behind.

## Scope

There is no taxonomy to defend yet. The one property worth preserving from the version that was
removed is this: **`sb run` is the single command that acts.** Everything else reads. When a group
of commands returns, that is the line to keep — a command that wants to both read and write is two
commands.

That line is now load-bearing rather than aesthetic. The canvas reads it — `acts` in the catalog —
to decide whether a window may be given a refresh cadence, because **re-running a read is a
refresh and re-running a write is a scheduler nobody asked for.** sky.boss cannot tell a read from a
write by inspecting an argv and does not try: choosing `data` over `run` is the operator's
assertion that this one is a read.

**A path is the one case that needs no assertion**, and it is the rule's own reasoning that
retires it rather than an exception carved beside it. `sb data <path>` is never executed, so there
is no write to be uncertain about — inspection works here, and the reason for refusing to inspect
is gone. The dispatch is argument shape, the same split `sb follow` makes, minus one case: follow
calls a bare unknown word a file because a log must be followable before its first write, and a
file with no records has nothing to wait for. See [[jsonl-reads]].

A saved command **inherits** that assertion rather than restating it — `acts` comes from the first
word of its argv and a declared one is ignored, so `[tool.deploy]` wrapping `run` is refused a
cadence exactly as `sb run` is. This is also why a tool's argv must start with a sky.boss command: a
tool that could name a bare executable would be a second `sb run` that skips the split entirely.

The removed design grouped commands by *mood* — imperative, temporal, descriptive, evaluative —
rather than by domain, on the reasoning that the domain axis grows without bound while the mood
axis is closed. That reasoning held; what did not hold was carrying four moods for eleven
commands. If groups come back, group them that way and be slower to add one.

**Considered and deliberately rejected** — do not re-propose without being asked:

- **`sb ctx`** and **`sb secrets`** (unified context switching, a secrets manager as root of trust
  for `aws`/`gh`/`stripe`). **External CLIs keep their own authentication.** `sb` is never in the
  credential path. This is what keeps a future MCP surface safe to expose.
- **Judging a followed line.** Tint is *shape* — a timestamp, a number, a path — and it is
  computed in `cli/highlight.py` for both surfaces. A severity vocabulary (ERROR/WARN/INFO) is a
  judgment wearing a regex's clothes and sky.boss does not ship one; the operator declares their own
  words under `[highlight.<name>]` in `formats.toml` and names it with `--highlight`. Those rules
  run **after** sky.boss's and claim only unclaimed text, so a declaration can never repaint a
  timestamp. See [[highlight]].
- **Parsing a tool's human output into rows** — *narrowed 2026-08-22 by [[capture]]: **declared**
  capture is in; inference stays out.* `sb read` shows it verbatim and says that is what it is
  doing; inferring columns from whitespace is the "silently wrong" failure, and a tool with real
  structure has `--json`. What [[capture]] added is the operator asserting the structure by name —
  a format in `$SB_HOME/formats.toml` with a pattern and optionally a jq transform, named on
  `sb data --from <name>`. No format, no table; a `--pretty` flag that guesses remains rejected.
- **Splitting a file of variant records by its discriminator.** [[jsonl-reads]] round 3 reports
  variance and refuses to act on it: a `--where kind=run` is the query language the bullet above
  rejects, arriving through a side door. What sky.boss owes the operator is the *reason* a table is
  thirty columns wide — that no single record has thirty fields — and `--cols` is already how a
  wide table gets narrowed. The rule that decides it is `union > widest single shape`, which fires
  when the header describes a record that was never written, and stays silent when one shape merely
  nests inside another.
- **Wrapping an external CLI for passthrough.** `sb gh pr list` is strictly worse than
  `gh pr list`. Reach for an external tool only where `sb` does something that tool cannot express.
  `sb data` is the carve-out and it earns it: holding a foreign CLI's output open on a canvas and
  re-running it on a cadence is not something that CLI can do for itself. It returns *parsed data*
  — a tool that printed something other than JSON has failed its contract, and the envelope says
  so rather than carrying the bytes.

## The interactive surface

`sb ui` opens **the canvas**: a command palette over a window canvas, where every command opens a
window and a pinned window re-runs itself on a cadence, with the operator's saved commands down
the left. It is a consumer of the output contract,
not a second CLI. It replaced `sb tui` on 2026-08-20 — the terminal could not do overlapping
draggable windows, which is the central metaphor. `docs/features/done/canvas.md` records the whole
design, and `docs/design/sky-boss-demo.html` is the mockup it was built from.

**It has a second screen as of 2026-08-27: the workbench**, where a command gets *authored* rather
than invoked. The palette is a one-line composer, which is right for something you already trust
and wrong for something you do not; the bench is where the contract is asserted, the argv is
drafted, and a **trial run** draws the real envelope through the real renderer. See [[workbench]].
Two rules there are the canvas's own, arriving on a new screen:

- **The contract is asserted, never inferred**, and nothing is selected when the bench opens. A
  bench that read a trailing `--json` and chose `data` would be the act/observe split undone by a
  heuristic. The same rule governs a tool's **group** ([[tools]] round 5): it is a declared field,
  not a prefix read off the name, because a prefix rule cannot be told apart from a coincidence and
  `disk-free` would invent a group nobody asked for. A group is a *label the surfaces sort under*
  and never part of the address — `sb tools <name>` is unchanged and names stay globally unique.
  Round 6 gave a group a `[group.NAME]` table of its own, under the rule that **a group exists if
  any command names it, or if it is declared** — neither implies the other, which is what let empty
  groups exist without invalidating a single file written before them. `/api/trial` is `/api/run` with one rule added — **an act has no trial run** — and it
  is a second route rather than a flag because the palette must keep opening `sb run` windows. The
  refusal is server-side: a surface that declines to draw a button has not refused anything.
- **A follow trial is a pseudo-window on the session**, held open by `/api/follow` under the window
  id `bench`, so it dies with the session exactly as a window's stream does. No second transport.
- **A chip re-shapes; it does not re-run.** `/api/shape` is a pure function of the payload the
  trial already returned — introspection, like `/api/catalog`. A view *describes* data and never
  filters it, so which columns are drawn is a question about the drawing, and re-running to settle
  it would also make every chip compare against a different dataset. It shapes **twice**: once with
  what was asked for, and once with nothing asked for, because with `--cols` in force `shape`
  returns only what was named and `hidden` is empty — a checklist built from that would lose a
  column the instant you unticked it.

**There is deliberately no nav entry for the plan or the tower.** They are drawn in
`docs/design/` and need four primitives that do not exist. A nav offering a screen that is not
there is the palette's own failure wearing different clothes — it has already told you the thing
exists. See `docs/open.md`.

The rules that are not negotiable:

- **Nothing keeps a command table.** The palette comes from `/api/catalog`, which walks the real
  Click tree, so it cannot drift from the CLI. A palette offering a command that does not exist is
  worse than no palette, because it has already told you it does. A *surface* excludes itself by
  setting `sb_surface` on its own command object rather than by being named in a skip-list here.

  **A raw command is not a drift.** Anything typed whose first word is not a sky.boss command is
  offered as `sb read -- <argv>`, synthesised from the query rather than from any list, with the
  expansion shown before it runs. It defaults to `$HOME` — neutral, because the canvas inherits
  whatever directory `sb ui` started in, and any repo with a `cli/` package shadows a tool's own.
- **Only a read may be given a cadence.** See § Scope.
- **A rewrite has to know every field; a splice does not.** `block()` serialises a tool, so a
  field it has not heard of is dropped on every rewrite — which is not hypothetical: a declared
  `highlight` was lost that way for a day, visible only as a stream that stopped being tinted. A
  test now walks `Tool`'s dataclass fields so the next one added cannot repeat it. And the surgical
  path is `set_field`, which splices **one line inside a block**: everything else survives by
  construction, including keys the caller has never heard of and the operator's comments *inside*
  the block. Dragging a command between groups goes down it, because the rail knows a command's
  `summary` and not its `description` and cannot see a `highlight` at all — a surface must not
  restate what it cannot read. See [[tools]] round 6.
- **A window that runs accrues; a window that refreshes does not.** An unpinned `run` or `read` is
  held open on the session stream and its lines arrive as they are printed, exactly as they do in a
  terminal; a pinned one is a watcher and gets a whole envelope on a cadence. The endings are the
  distinction and the reason this is not a follow: a follow's exit — zero included — is a **death**,
  and an act's exit 0 is the **answer**. It is a third route rather than a mode on `/api/run`, by
  the argument that already made `/api/trial` a route. And **the 60s `DEFAULT_TIMEOUT` is the
  watcher's ceiling, not everyone's** — it killed any long run at sixty seconds while
  `sb run --timeout` was accepted and then overridden, which is the "wrong but looks right" failure
  in its purest form. An accruing window carries no default bound. See [[follow]] round 4.
- **The refresh clock lives in Python, keyed to the connection.** A watcher runs while its stream is
  open, so it pauses when the window closes and keeps running when the window is merely minimized.
  It cannot be a browser timer: a hidden page has its timers clamped to roughly one fire per minute,
  so a 5s watcher would silently become a 60s one at the exact moment you stopped being able to see
  that it had. Nothing survives the last window, which is what makes this a scheduler and not a
  daemon.
- **A tool's `group` is where it lives; its `tags` are what it is about.** One value against many,
  and they stopped being redundant the moment both existed ([[tools]] round 8) — the group is the
  rail's sort order, the tags are the axis it filters on. The rejected alternative was letting a
  tool name several groups: an ordering cannot be many-valued without the rail drawing the same tool
  twice. **Type is derived and is not a filter** — `expansion[0]` *is* the contract, so a declared
  `type` would be a second opinion about something the argv settles, and as a filter it has four
  values of which three are reads. It is drawn as a marker, absent for a `run`, whose `!` is a
  warning rather than a label and must not be diluted into one of four equal badges. **The rail has
  two independent size axes** — `--scale` and the width the operator drags — and a layout is swept
  across both or it is not swept: measured clean at three scales while the filter shrank to 11px and
  spilled outside the rail at its 18rem minimum.
- **Changing behaviour without changing the message leaves the surface arguing with itself.**
  [[tools]] round 4 made a taken name a *replace*; two places recorded that in code and neither
  touched the sentence, so for two rounds the bench performed the replace while announcing a
  refusal and sending the operator to `tools.toml` by hand ([[workbench]] round 5). Two rules come
  out of it. **A message is part of the behaviour** — a refusal that no longer happens is a
  false claim, not stale prose, and the operator has no reason to doubt the words. And **a
  fixed destructure on a payload path drops a field it has not heard of**, which is the `block()`
  trap generalised: `writeTool({name, argv, …})` swallowed the `was` that made a rename a rename,
  so the rename ran as a create with nothing reported anywhere. Caught only by a test that read the
  file rather than the response.
- **An act is confirmed before it runs, and that is not a security control.** `acts` labelled things
  until [[canvas]] round 11; it now stops one. Every launch converges on one funnel, so the dialog
  sits there rather than at each call site. Three parts are load-bearing. It is **client-side on
  purpose** and does not contradict the rule that *a surface which declines to draw a button has not
  refused anything* — that rule governs a **refusal**, which must live where the permission does;
  nothing is refused here, an act is merely asked about, and a question needs a human, which the
  server has not got. The confirm is **never the focused default and never answers to Enter**, since
  Enter is how a palette row launches and a guard defeated by the gesture it exists to catch is
  worse than none. And it **shows the expansion, not the nickname** — a saved tool is a short name in
  the rail, and the argv is what happens.
- **The session stream reconnects, and a window says so when it cannot.** Everything the surface
  does — every watcher, every follow, live reload — rides one stream, so losing it freezes the whole
  page; until [[canvas]] round 10 it froze permanently, because the stream was opened once and never
  retried. Two rules came out of fixing it and both generalise. **A per-launch credential makes a
  restart unrecoverable**: the token is written into the page, so a page outliving its server is
  refused forever at any backoff, and *wait* and *reload* are opposite remedies that must be told
  apart rather than shown as one "disconnected". And **a window has to carry its own doubt** — a
  band reading `quiet` over a dead stream is not stale information but a false claim, since `quiet`
  means a `stat` happened and nothing is being stated. A footer note is not where anyone is looking.
  The same reasoning governs anything that resumes: a reconnect that silently re-pushed a backfilled
  tail would duplicate lines, and one that dropped it would hide the gap, so the seam is announced
  in the stream's own voice.
- **The surface has no stable origin, so browser storage cannot hold anything across launches.**
  `sb ui` binds an *ephemeral* port unless told otherwise, so the page is served from
  `http://127.0.0.1:<different>/` every time and `localStorage` — which is keyed by origin — is
  empty on arrival by construction. True in all three shells. Anything the surface must remember
  between launches goes in `$SB_STATE` through `cli/canvas/prefs.py` and the guarded `/api/prefs`,
  which is strictly shaped so it cannot become a second config file. **The native webview is a red
  herring here**: `pywebview`'s `private_mode` does default to `True`, and turning it off with a
  `storage_path` really does make WebKitGTK persist `localStorage` — across a restart of the
  *browser*, which is not the restart anyone cares about. See [[tools]] round 5.
- **Reads in, execution out.** Introspection runs in-process because walking the tree runs nothing.
  Commands run in a *subprocess*, because a thread cannot be cancelled and a watcher fires
  unattended — one hung `git fetch` would strand a thread forever. `sb --json` already prints the
  envelope, so nothing parses human output.
- **An offset that crosses to the browser is in the wrong units until it is converted.** Python
  counts code points and JavaScript's `slice` counts UTF-16 code units, so every astral character —
  🔴, 🟢, 👍, every emoji above U+FFFF — is one on one side and two on the other. Highlight marks
  shipped raw for a week and cut surrogate pairs in half, shifting every offset after them on the
  line. **Both halves were self-consistent, which is why nothing caught it**: the terminal applies
  the same offsets to the same Python string, the suite compares marks to marks and never slices,
  and the most common glyph in the live log is inside the BMP. Converted at the wire in
  `highlight.utf16`. Any future offset shipped to the page owes the same conversion, and its test
  owes an actual slice rather than a comparison. See [[highlight]] round 5.
- **A rendered line is a block, not a span plus a newline.** `markedLine` emits one `<span class="ln">`
  per line with no trailing `"\n"`, because `text-indent` applies to a block container and an inline
  span inside a `<pre>` cannot take one — which [[wrap]]'s hanging indent needs. Two things follow and
  both are load-bearing: a block *and* a newline is two line boxes, so re-adding the newline
  double-spaces every window; and an empty block has no line box, so a blank line needs
  `min-height`, or the gaps an agent writes between findings close up. Also note `pre.raw` sets
  `min-width: min-content` — that is what makes a wide result scroll sideways, and wrapping without
  clearing it wraps the text inside a box too wide to see it in.
- **No single result may render unbounded.** The terminal surface froze for exactly this, and a
  120k-line result kills a browser tab as dead as it killed a `RichLog`. The substrate changed; the
  rule did not. See `MAX_ROWS` and `MAX_CHARS` in `cli/canvas/static/render.js`.
- **The server is remote code execution bound to a port, and is treated that way.** Four things,
  none optional: loopback bind, a required custom header (which forces a preflight that is never
  answered — this is the one that actually stops a hostile page), a per-launch token, and an
  `Origin` check. **There is no CORS allow-origin header anywhere and adding one would undo most of
  that.** A test asserts its absence.
- **Everything in `cli/canvas/static/` is served.** Anything left there is published; a test
  declares the inventory. Two scratch pages lived there during the build, one with a live token
  baked in.
- **One number drives every size, so `--scale` is a geometry and not a preference.** `--sb-scale`
  is injected from `sb ui --scale` and the stylesheet is written in `rem` where `1rem` is four
  scaled pixels. Do not add a `px`. **A layout verified at one value of it has been verified once**
  — every fixed `rem` width and height grows with the scale while the window does not, so a panel
  that fits at 1.15 can starve its neighbour at 2.4. The workbench lost its last step this way and
  nobody saw it for three rounds. Check a layout change at more than one scale; `[[workbench]]`
  round 4 sweeps five. CSS `zoom` was rejected
  because it breaks dragging — `clientX` is unzoomed and `left` is zoomed — and
  `--force-device-scale-factor` because it *overrides* display scaling rather than multiplying it.
- **The shell is a native webview** (`cli/canvas/shell.py`), because three things the operator asked
  for are impossible in a browser: a frameless window that is still resizable, a page that moves its
  own window, and no port exposed to any other tab. `--browser` and `--no-browser` keep the old
  paths, and `--no-browser` is still the mode to develop in.
- **`frameless=True` is a request, and a window manager may refuse it.** GTK reports `DECORATED =
  False` and the window manager can still draw a title bar — measured, not assumed. Removing it is a
  window-manager rule matched on `WM_CLASS`, which is why the shell sets one (`sb`) — and **nothing
  here writes that rule.** A desktop belongs to whoever runs it, the spelling differs per
  environment, and a tool that edited one would be reaching outside itself.
- **Drag is not `pywebview-drag-region`.** That is a Cocoa and Windows feature; the GTK backend has
  no drag regions at all, only `easy_drag`, which makes the whole page a handle and would mean
  dragging a window inside the canvas also drags the canvas. The bar calls
  `Gtk.Window.begin_move_drag` instead, so the window manager owns the drag and it snaps and tiles
  like every other window.
- **The surface carries its own close button**, guarded like every other route, because the frame it
  would otherwise rely on may not be there.
- **A progress bar shows time to the next refresh, and nothing else.** A running subprocess has no
  percentage, and a bar that animates to look busy is decoration that reads as information. A
  watcher has one because `interval` and `last_run` are known. It reads the *label* clock, which a
  hidden page throttles — correct, and what the Python-side refresh clock buys: a stale bar is a
  cosmetic bug where a throttled scheduler would be a silent one.
- **`htm` has no notion of a comment.** It is a template-literal parser, not JSX, so a `/* … */`
  written *inside* a tag is parsed as attribute text and silently mangles that element's children.
  It does not throw and the element still renders — the children just quietly vanish. Put comments
  above the `html\`` block or inside a `${…}` expression. One in a `<div>` opening tag removed an
  `<input>` from the DOM entirely, and only rendering the page found it.
- **The frontend has no automated tests.** There is no JS test runner and adding one means npm. The
  pure parts — `unwrap`, `suggest`, `roleFor` — are what a runner would be for. Verified by
  rendering headless Chromium against the live server and reading the DOM back, which is not the
  same thing and caught two real bugs. **Treat that pass as an obligation, not a formality**: it is
  what found `dead · exited undefined` — `Chrome.to_dict` dropped every falsy value, so a clean exit
  never reached the page, in the one state that rendering exists to draw. The suite could not see it
  because the terminal band reads the dataclass rather than the dict.

## CLI setup

**`sb` is installed on PATH.** Symlink `~/.local/bin/sb` → this repo's `sb` (that directory is
already first on PATH), because `sb` is a homebase tool you run from anywhere.

**`PYTHONSAFEPATH=1` in the wrapper is load-bearing.** `python -m` prepends the current directory
to `sys.path` *ahead of* `PYTHONPATH`, so running `sb` from inside any directory containing a
`cli/` package imports that one. This has already bitten once: generating systemd units from
inside an older checkout wrote every unit with the old `WorkingDirectory`, successfully and
silently.

**The consequence is a hard rule: `sb` never assumes cwd is the project root.** Every path derives
from `PROJECT_ROOT` in `cli/helpers.py`, and the wrapper resolves its own symlink with `realpath`
before setting `PYTHONPATH` — otherwise `python -m cli` resolves the package relative to
`~/.local/bin`. This is a whole class of bug: relative `PATH` entries re-resolving against each
child's cwd, 112 tests failing from a tmp dir. Read the wrapper's comments before touching it.

**A sibling CLI on PATH is not necessarily runnable from anywhere.** A wrapper that resolves its
`.venv` against the *cwd* rather than the resolved symlink fails outside its own repo. So
**anything sky.boss runs from another repo needs an explicit working directory**, not just PATH.

- **Dependencies:** `.venv` + `requirements.txt`. No `pyproject.toml`, pyright, or pre-commit
  until something needs them. Python here is 3.14.7 — new enough that a dependency may lack wheels.
- **`--json` is a root-group flag** stored in the Click context, so the output decorator handles
  every command with no per-command boilerplate.
- **Shell completion:** for fish, `_SB_COMPLETE=fish_source sb > ~/.config/fish/completions/sb.fish`.

**If your login shell is fish**, note that a fish *function* resolves ahead of PATH, so a
distro-packaged fish config that happens to define a function of the same name shadows this CLI —
and because that file is package-owned it comes back on update. This is not hypothetical: it is
what the old name `tb` collided with, and the 2026-08-27 rename dissolved that particular collision
rather than solving it. The mechanism is unchanged and `sb` is a two-letter name too. The fix, if
it ever happens again, is an override in `~/.config/fish/config.fish`:
`functions --query sb; and functions --erase sb`. If `sb` stops resolving after a system update,
check there first.

### Where things live

| What | Where | Authored by | Versioned |
|---|---|---|---|
| Code, tests, docs | this repo | the project | here |
| Saved commands (`tools.toml`) | `~/.sky-boss/` (`$SB_HOME`) | the operator, `--save`, and the surface | never |
| Capture formats and highlight rules (`formats.toml`) | `~/.sky-boss/` (`$SB_HOME`) | the operator | never |
| Declared projects and the agent-state root (`projects.toml`) | `~/.sky-boss/` (`$SB_HOME`) | the operator | never |
| Backups of `tools.toml` | `~/.sky-boss/backups/` | sky.boss, before every write | never |
| Browser profile for the canvas | `~/.local/state/sb/` (`$SB_STATE`) | the machine | never |
| What the surface remembers about itself (`prefs.json`) | `~/.local/state/sb/` (`$SB_STATE`) | the surface | never |

**`$SB_HOME` is the operator content directory, and it is outside the repo with no fallback path
into it.** *It does have one fallback path* **outside** *the repo*: the 2026-08-27 rename moved the
default from `~/.toolbox` to `~/.sky-boss`, and `_default_home()` in `cli/helpers.py` still returns
the old path while it is the only one that exists. That bridge is there because an absent home
degrades to *nothing declared* rather than raising — a silent move would have made every saved
tool, format and project vanish with no error to read. It stops applying the moment `~/.sky-boss`
exists, and there is deliberately no merge of the two. The rule it exists under: operator content used to live in this repo, justified by *the
git diff is the maintenance log*, and a machine record carried a tailnet address into every commit,
so the tool could not be published without publishing the operator. An absent home degrades to
nothing declared rather than raising — a fresh clone has no tools and saying so every invocation
would be noise. It is separate from `$SB_STATE` because `rm -rf ~/.local/state/sb` is a reasonable
way to reset the surface and must not also delete every tool the operator wrote.

**The suite redirects `SB_HOME` as well as `SB_STATE`**, and that one matters more: a tool is an
argv sky.boss will *run*, so a suite reading the real home would register the operator's commands
into the tree under test.

**The suite never touches the real state directory** — `tests/conftest.py` redirects `SB_STATE`
before anything imports `cli`. **Nothing operator-specific in tracked files.**

### Testing

```bash
.venv/bin/python -m pytest              # whole suite (fast — no network)
.venv/bin/python -m pytest -k capture   # by name
```

`pytest.ini` sets `pythonpath = .` so `cli` imports without installation, and `asyncio_mode = auto`
because the canvas's session loop is async. Dev dependencies are in `requirements-dev.txt`.

**To work on the surface**, run `sb ui --no-browser --port 8765` and point a browser at it.
**Live reload is on and rides the session stream** — the server fingerprints `static/` on its
existing tick and pushes a `reload` frame. A CSS edit is swapped in place and every window keeps
its state; anything else is a full reload and loses them, because the module graph is already
evaluated and half-old JavaScript holding live state is the "wrong but looks right" failure. Only
a change to Python needs a restart, and that one is not made hot-reloadable on purpose.

**Test the decisions, not the ceremony.** The suite catches what would break silently: the
exit-code mapping (including why partial is 3 and not 2), stdout purity under `--json`, that every
API route refuses an unauthenticated request, that a watcher dies with its window, and that `data`
never carries a failed tool's output.

**The naming rule is checked, not remembered** — `tests/test_naming.py` masks every fenced block,
indented block, inline span and HTML tag, then fails on whatever still spells the command in prose.
The mask preserves length, so a failure names a real line — and so the sweep that closed the
original 368 could edit at exactly the offsets it reports rather than running a find-and-replace of
its own, which is the thing that caused this. `.html` is out, for the reason it is out of
`tests/test_theme.py`: `docs/design/*.dc.html` are renders, and hand-editing one is how a render
stops matching its source.

**`[[slug]]` references are checked** — `tests/test_docs.py`. Slugs exist so a doc can move between
`docs/features/` and `done/` without breaking a link, which they do; what they cannot survive is
naming a doc nobody wrote. The check found two dead on its first run (`keys` and `theme`, cited
from `cli/resident.py`, `cli/banner.py` and a test), both dead long enough that nothing recorded
when they broke. A slug that resolves to nothing is worse than a broken path, because it *looks*
like it survived the move that broke it. The allowlist is two entries and each is tested to still
need to be there.

**CI runs the whole suite on push and PR** — `.github/workflows/ci.yml`, no cost gating, because
this suite is under five seconds with no network and deciding whether to run it would cost more.
It builds a real `.venv` rather than a bare `pip install`: `tests/test_readme.py` runs the
README's examples through the
actual `sb` wrapper with `PATH` pinned, so the wrapper must find `.venv/bin/python` or those tests
fail only on a runner. Verified against a clean tree with no GTK and no system site-packages —
`pywebview` installs, `gi` does not, and nothing imports either until a window opens.

**Bound every wait.** Three tests hung rather than failed while the canvas was being built. A
`TestClient` cannot open an endless stream at all — it collects the whole body first — so the
session loop is driven directly instead. And a guard that stops after N frames bounds how many
frames you accept, not how long you wait for one: a loop yielding nothing blocks on the first
pull. Prefer testing a property about what *does not* happen against the pure layer (`Session.due`)
rather than by waiting for a silence.

**Assert against the mechanism, not the timing.** Inject the clock. `Session` takes one for the
same reason the old watchdog did: proving a five-second cadence should not cost five seconds of
suite.

**Raw command output must not reach `data`** for anything the CLI runs **on its own initiative** —
a probe can print a token, and `data` reaches stdout and any future MCP surface. The property that
makes an exception safe is not which command it is, it is **who named the argv**: `sb run` and
`sb read` both run an argv the operator typed, and seeing its output is the feature. Any command
that shells out on its own initiative still keeps that output out of `data`.

**A cadence off a terminal is a stream of envelopes, not a refusal.** `sb data --refresh` down a
pipe, or under `--json`, emits one NDJSON line per tick — the single-shot envelope plus `tick` and
`at`, so every reader of `sb --json data` reads one of these lines unchanged. [[refresh]] round 3
refused it and round 4 reversed that on the operator's ruling; the objection was *answered* rather
than dropped, since a resident render has no **single** envelope and a stream of them is not one.
`read` still refuses — verbatim text has no envelope worth streaming. Two consequences worth
keeping: **a test may never enter a residency**, only intercept it (four did, and the suite hung
rather than failed), and **a consumer leaving is a normal end** — an unhandled `BrokenPipeError`
reported `✗ data failed` when nothing had, which is *worked fine, told nobody* inverted and no less
wrong.

**`sb data` is deliberately not an exception even so** — it carries parsed data only, and a tool
that printed something else has failed its contract. See [[text-reads]].

**Gotcha:** never `from cli.<mod> import <same_name>` in `cli/__init__.py` — it rebinds the package
attribute from the module to the Command and shadows the module. Import under an alias.

## Conventions

Shared with sibling CLIs so the family feels like one tool.

- **The wordmark in prose, the command in code spans.** The project is **sky.boss**; `sb` is what
  you type. Outside code the wordmark is the only spelling, and `sb` appears only inside backticks,
  naming the literal thing being typed. This is the house rule from
  `skyrow-workspace/strategy/naming.md`, and this repo was the one place breaking it: on 2026-08-28
  a sweep replaced **368** bare commands standing in for the project — 195 in Markdown, 173 in
  docstrings and comments — against **one** such use in jam-sense's and breeze-brain's `CLAUDE.md`
  put together. It was not a style drift but a rename artefact. The project was `tackle-box`, then
  `toolbox`, then this; the CLI was `tb` until 2026-08-27. Each of those passes replaced a name
  with a name, and prose that had meant the *project* came out meaning the *command*. The
  fingerprint was `a sb command`, fifteen times — nobody writing that fresh writes `a sb`.
  `tests/test_naming.py` is what makes the next rename harmless, and identifiers (`$SB_HOME`,
  `SB_STATE`, the window class) are outside it by construction.
- **Python 3 + Click.** Available here: Python 3.14.7, click 8.3.3. Fail fast with a readable
  install message on a missing dependency.
- **Layout:** `sb` bash wrapper → `cli/__main__.py` thin entry → `cli/` package. The wrapper does
  path work only (resolve symlinks, prefer `.venv`, set `PYTHONPATH`, `exec python -m cli "$@"`).
- **Shared plumbing in `cli/helpers.py`** — `PROJECT_ROOT`, `STATE_DIR`, `run_command`. Command
  modules call these rather than building paths directly.
- **Ops commands act on real machines** via SSH, systemd, or the filesystem — never through an API
  client. Keep any HTTP behind a dedicated adapter module.
- **A command sky.boss spawns gets the operator's environment, not sky.boss's.** Everything that
  shells out goes through `child_env()` in `cli/helpers.py`, which drops `PYTHONPATH` and
  `PYTHONSAFEPATH` — the two the wrapper exports so `python -m cli` resolves. Without it a wrapped
  Python tool imports *this* `cli` package from anywhere on the machine. `PATH` is deliberately
  kept: stripping the venv the wrapper prepends would be sky.boss choosing which `python3` a foreign
  tool finds. Not a clean room — scrub what sky.boss added to boot and nothing else. See
  [[subprocess-env]].
- **A tool that gates its output on `isatty()` is the operator's to declare.** Every child gets a
  pipe, so a tool that decides *what to print* by asking whether it has a terminal prints less
  under sky.boss than in your shell — not late, not narrow, **absent**, and absent output looks
  exactly like a job quietly working. sky.boss supplies `COLUMNS` and `PYTHONUNBUFFERED` because it
  *knows* those two; it cannot know what a tool would have said to a terminal, so it does not
  guess and keeps no table of tools. `--env NAME=VALUE` on `run`, `read`, `follow` and `data` is
  how you say it, applied last over sky.boss's own two, and it rides into a saved tool in the argv
  exactly as `--cwd` does. **Not a credential path** — the value is written verbatim into
  `tools.toml` and drawn in a window title; anything secret is already inherited.
  `env NAME=VALUE …` in the argv is *not* the same thing and is rejected in
  [[subprocess-env]] round 4: it makes the bench report `env resolves /usr/bin/env`, so the
  surface vouches for the wrapper instead of the tool.
- **One palette, in `cli/theme.py`** — Skyrow Labs' **design system**, copied verbatim from its own
  `colors_and_type.css`, vendored at `docs/design/` so the copy is checkable. The system is
  dark-only by declaration.

  **Two renderings, one system.** The canvas paints its own background and takes the tokens
  unmodified, as CSS custom properties from `css_variables`, injected into the page by the server. The CLI renders into whoever's terminal, where the tokens are not dim but gone —
  brand measures 2.14:1 on white, warn 1.44:1 — so every CLI role is the smallest darkening of its
  token that clears 3.5:1 against *both* white and the void. The two vocabularies differ on purpose — `STYLES` names what a value *is*, `css_variables` names
  what the design system calls it — and a test asserts that every hue the CLI darkens ships to the
  canvas undarkened. The contrast floor is measured rather than eyeballed: two grey roles missed it
  by a hair while looking perfectly fine.

  **A role may also paint its own ground, and that is the second escape clause.** `sb.ref` — the
  `#123` chip — fills with the brand at the design system's own ring alpha and draws the brand
  undarkened on top, because a role that supplies its own background removes the unknown the floor
  exists for. It is checked rather than exempted: the text floor applies to its text on its own
  ground, and the ground is judged by perceptual distance from either terminal against the system's
  smallest deliberate surface step. **This is the only axis left** — the system holds four hues
  (`--bb` *is* `--ok`, `--mh` *is* `--warn`) and sky.boss spends all four, so a fifth is a brand
  decision and not this tool's. See [[highlight]] round 6.

  **A composite role has to be resolved by hand.** `bold sb.ok` is not something Rich can read:
  `get_style` finds a theme entry for the whole string or falls through to `Style.parse`, which
  tries to read `sb.ok` as a colour, fails, and raises — and the render path *swallows it*, so the
  span comes out unstyled with no error anywhere. An earlier version of this file said Rich reads
  it directly; it never did, and every ✓ ✗ ⚠ in a followed line rendered plain for a week.
  `role_style` in `cli/output.py` is the resolver. **And the canvas half is the same rule from the
  other side**: a `mk-<role>` class lands whether or not the stylesheet has a rule for it, so
  `.mk-ok`, `.mk-fail` and `.mk-warn` were unpainted for the same week. A test enumerates the roles
  off `_RULES` now. *Both bugs were invisible to a check that asks whether the mark landed — the
  answer is yes in both, and the colour is the thing that has to be read.*

  **The mark is the one thing outside that floor**, and the escape clause is the canvas's own:
  it *paints its own background*, so it takes the tokens at full strength. Not a convenience —
  its hues fail in opposite directions (the light handle on white, the dark slate on black), so
  no pair of darkened values exists. It lives outside `STYLES` for exactly that reason and a test
  says so, because darkening it back is the tidy-looking change that dims a brand mark for no
  reader. See [[header]].

  A test fails if any file outside `theme.py` names a hex, **in any language** — the scan covers
  `.py`, `.css` and `.js`, because the surface now has all three and a stylesheet is the most
  natural place for someone to paste one. Vendored code is exempt. A second test rejects `rgba()`
  literals, which is the form the drift would actually take here: the mockup is built out of them.
  Tints are `color-mix` against an injected role. There is no theme switching.
- **Commands return data; they never print.** All rendering goes through `cli/output.py` and the
  `Result` envelope (`ok` / `partial` / `data` / `warnings`, plus an optional `view`). Exit codes:
  `0` ok, `1` hard failure, `3` partial — **not 2**, which Click uses for usage errors. The surface
  is a second consumer of that envelope — a command that prints prose has to be written twice.

  **A `view` describes how to present `data`; it never filters it.** Only `data` sets one, because
  only `data` carries fields nobody here chose — sky.boss's own commands picked theirs deliberately
  and auto-dropping one would be a bug wearing a feature's clothes. The key is *omitted* rather than
  null when absent, so an unshaped envelope stays byte-identical to one from before views existed.
  The rules live in `cli/view.py` and not in `render.js`, because the frontend has no test runner:
  that puts the deciding half where pytest reaches it and leaves both renderers drawing what they
  are told. **The warnings a shaping is owed live there too** as of 2026-08-27 — *which columns went
  quiet* is the same kind of decision, and it stopped being inline in `cli/data.py` the moment the
  bench became a second caller. See [[table-views]].
- **Degrade gracefully.** An unreachable host or absent config warns in yellow on **stderr** and
  continues. Keep stdout clean so `--json` stays parseable, and never collapse "reports clear" into
  "cannot see".
- **Worked fine, told nobody.** The rule above, turned on sky.boss itself, and it is the failure this
  repo produces most. A command that runs perfectly and renders nothing leaves a consumer unable to
  tell *absence of output* from *absence of event* — which is the same lie as a wrong answer, minus
  the chance of noticing. Named 2026-08-29 by the skyrow-workspace session after a day that produced
  five instances. **Three were sky.boss's own, all fixed 2026-08-29:** `sb follow` down a pipe drew
  nothing while the loop ran; `sb data --refresh` down a pipe did the same and **hung** while doing
  it, because residency never exits — now a usage error naming the fix ([[refresh]] round 3); and
  `sb ui --no-browser` promised to print a URL and printed nothing, because `server.run()` blocks
  before `emit` renders ([[canvas]] round 9).

  **Fixing that last one turned up two more in the same function**, neither reported: the
  browser-fallback degrade — a message whose whole content is *"serving only — open {url}"* —
  blocked on the same call, and `sb --json ui` promised an envelope and then blocked, where
  `sb follow` had refused exactly that a week earlier. Three from one report, which is the argument
  for sweeping this class rather than fixing instances: a reporter finds the one that costs them
  something, and the others are sitting beside it. **Two are the same class elsewhere**, which
  is what makes it a class rather than a quirk of this repo: a typo'd table in the operator's
  `projects.toml` returned zero projects and zero problems, identical to a fresh clone — the typo
  was theirs, the *silence* was this parser's (fixed) — and jam.sense's
  `state_dir(INFLIGHT, "inflight")` was green in its own suite because the writer and the reader
  agreed with each other.

  The tell is always the same: **the silent path and the healthy path are the same bytes.** When a
  command can produce nothing, ask what a consumer seeing nothing would conclude, and if the answer
  is "the same thing they'd conclude if it never ran", say something. Refusing is a legitimate way
  to say it — a refusal is a sentence where a hang is not. See [[open]] § Where a follow ends.

  **None of the five was caught by a test suite.** All were found by running the thing and looking
  at what came out — three by this repo, two by a consumer. That distribution is the part worth
  taking seriously, and the two consumer-found ones are the two a suite *structurally could not*
  have caught: `inflight/inflight` was green precisely because writer and reader shared the mistake,
  and `sb data --refresh` is covered by tests that read the dataclass rather than the rendered pipe.

  The generalisation, which lives in the workspace guide because it is not one repo's:
  **no repo's suite can find a disagreement about an artifact it publishes, because the suite is
  written by the same author as the code it tests.** A writer and a reader inside one repo agree by
  construction, and green proves only that. You cannot fix it by testing harder — the blind spot is
  in the assumption the suite encodes — so the fix is to run the real consumer against the real
  producer at every seam, before believing either.

  *(An earlier version of this paragraph claimed four of the five were consumer-found. That was
  wrong: `sb follow`, `sb ui --no-browser` and the `projects.toml` silence were all found here.
  Corrected rather than quietly restated, because the workspace guide links to this list.)*
- **`.env` is gitignored and never committed.** Ship a `.env.example`.

## Feature workflow

`docs/design/fundamentals.md` is **the constitution**: the 2026-08-21 pass that treated the
built surface as pure concept and decided the eight primitives, with dated decisions and
visible reversals. Feature specs convert it into buildable rounds; read it before proposing a
primitive-level change. `docs/features/done/` holds the completed docs — `canvas.md` (the
surface, five rounds), `follow.md` (the streaming substrate, four rounds), `tools.md` (saved commands, three
rounds), `highlight.md` (lexical tint, four rounds), `capture.md` (declared structure),
`refresh.md`, `header.md` (the mark, two rounds), `text-reads.md`, `subprocess-env.md`, `table-views.md` (the
shaping contract, five rounds), `roll-call.md` (federating over projects), `file-follow.md` (the
native cursor, two rounds), `chrome.md` (what a window knows about its output, three rounds), `mcp.md` (the tools offered to
an agent), `delay.md` (once, later), `workbench.md` (the authoring surface, three rounds — opened
and finished 2026-08-26/27), and the constitution's rounds as they land.
**`docs/features/` is empty**: everything written so far has been executed. Every earlier spec was deleted with the
system it described; the docs that predate the 2026-08-21 renames say `wrap`/`every` on purpose —
dated, never scrubbed.

**`docs/open.md` is the running list of what is decided-to-build but not decided-how**, kept
apart from `docs/ideas.md` (*should we build it*) and fundamentals' Decisions (*settled, with the
reasoning*). An item leaves it by being taken over somewhere else, and the line records where it
went rather than being deleted.

One doc per feature at `docs/features/<slug>.md`, from first sentence to done; completed docs move
to `docs/features/done/`. `.claude/skills/feature/SKILL.md` drives it. The rules that earned their
place:

- Sections are **Why** · **Shape** (including an explicit *"Does not do"*) · **Phases** · **Notes**.
- **Expand the existing doc rather than adding a new one.** A change, a new capability or a defect
  worth designing around is a new *round* in the doc that already owns the feature. The failure
  this prevents is a directory where four files describe one thing and none is the one to read.
- **Notes accretes, never rewrites** — one dated entry per round. A superseded argument left
  visible beside its reversal is the most useful thing in one of these files; deleting it is how a
  doc loses the ability to stop someone making the same mistake again.
- Cross-document links are `[[slug]]`, never relative paths. Reference a doc **by slug in code
  comments too** — a path breaks the moment that feature reopens.
- **No index machinery yet.** There was a generated one; it went with the docs. `ls` is an
  adequate index for a directory with one file in it, and the test that kept the old one honest is the model to
  copy if volume ever demands one again.
