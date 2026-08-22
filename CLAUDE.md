# CLAUDE.md

Guidance for Claude Code when working in this repository.

Machine-specific context — this operator's network, sibling repositories, and home setup — lives
in `CLAUDE.local.md`, which is gitignored. If you are reading this in a fresh clone, that file is
absent and nothing here depends on it.

## What this repo is

**toolbox** is the homebase kit for a primary workstation and the machines around it, behind one
operator CLI: `tb`.

**It was called `tackle-box` until 2026-08-22.** The name is gone from the working tree — code,
docs, mockups and their filenames — because it would otherwise read as a second project. Git
history keeps it, deliberately: rewriting history to chase a rename is a cost with no reader.

**This is a machine-neutral repo, as of the 2026-08-22 pass.** Nothing tracked here names a host,
a distro, a desktop environment, or a window-manager rule — the mechanisms are documented, the
machine that hit them is not. That is not squeamishness: it is the same rule as `$TB_HOME`.
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
| `tb run -- <argv>` | Runs a command and reports what it printed. **The only command that acts** |
| `tb data -- <argv>` | Reads another CLI's JSON as data. An observe; `--refresh N` keeps it resident |
| `tb read -- <argv>` | Shows what a command printed, verbatim. An observe, for tools with no `--json` |
| `tb follow -- <argv>` | Holds a command's stream open. Resident by nature; any exit is a visible death |
| `tb follow <path>` | Follows a file with a native stat cursor, so quiet and dead are different words |
| `tb tools` | Lists the operator's saved commands, and any that failed to load |
| `tb ui` | Opens the canvas — a command palette over tiled and floating windows |
| `tb tools <name>` | Runs a saved command; `tb -t <name>` is the short spelling. See [[tools]] |

**`--save NAME` on `read`, `data` and `follow`** saves the invocation as a tool and then runs it.
It is the only thing in tb that writes `tools.toml`, it only ever **appends** one block, and it
refuses a name that already exists — editing and deleting stay `$EDITOR`'s. No surface writes:
still no route, still no button. `run` does not take it, because `--save` saves by example and
the example ran. See [[tools]].

`tb` and `tb --help` open with the mark — `docs/design/cli-header.png` drawn in half-blocks, see
[[header]]. It refuses to draw on a narrow or non-terminal surface rather than wrapping.

**Check before you describe.** This is young and moving, and it just lost most of its surface area.
When asked about a command or module, confirm it exists rather than inferring it from this
document, and correct the document when it has fallen behind.

## Scope

There is no taxonomy to defend yet. The one property worth preserving from the version that was
removed is this: **`tb run` is the single command that acts.** Everything else reads. When a group
of commands returns, that is the line to keep — a command that wants to both read and write is two
commands.

That line is now load-bearing rather than aesthetic. The canvas reads it — `acts` in the catalog —
to decide whether a window may be given a refresh cadence, because **re-running a read is a
refresh and re-running a write is a scheduler nobody asked for.** tb cannot tell a read from a
write by inspecting an argv and does not try: choosing `data` over `run` is the operator's
assertion that this one is a read.

A saved command **inherits** that assertion rather than restating it — `acts` comes from the first
word of its argv and a declared one is ignored, so `[tool.deploy]` wrapping `run` is refused a
cadence exactly as `tb run` is. This is also why a tool's argv must start with a tb command: a tool
that could name a bare executable would be a second `tb run` that skips the split entirely.

The removed design grouped commands by *mood* — imperative, temporal, descriptive, evaluative —
rather than by domain, on the reasoning that the domain axis grows without bound while the mood
axis is closed. That reasoning held; what did not hold was carrying four moods for eleven
commands. If groups come back, group them that way and be slower to add one.

**Considered and deliberately rejected** — do not re-propose without being asked:

- **`tb ctx`** and **`tb secrets`** (unified context switching, a secrets manager as root of trust
  for `aws`/`gh`/`stripe`). **External CLIs keep their own authentication.** `tb` is never in the
  credential path. This is what keeps a future MCP surface safe to expose.
- **Judging a followed line.** Tint is *shape* — a timestamp, a number, a path — and it is
  computed in `cli/highlight.py` for both surfaces. A severity vocabulary (ERROR/WARN/INFO) is a
  judgment wearing a regex's clothes and tb does not ship one; the operator declares their own
  words under `[highlight.<name>]` in `formats.toml` and names it with `--highlight`. Those rules
  run **after** tb's and claim only unclaimed text, so a declaration can never repaint a
  timestamp. See [[highlight]].
- **Parsing a tool's human output into rows** — *narrowed 2026-08-22 by [[capture]]: **declared**
  capture is in; inference stays out.* `tb read` shows it verbatim and says that is what it is
  doing; inferring columns from whitespace is the "silently wrong" failure, and a tool with real
  structure has `--json`. What [[capture]] added is the operator asserting the structure by name —
  a format in `$TB_HOME/formats.toml` with a pattern and optionally a jq transform, named on
  `tb data --from <name>`. No format, no table; a `--pretty` flag that guesses remains rejected.
- **Wrapping an external CLI for passthrough.** `tb gh pr list` is strictly worse than
  `gh pr list`. Reach for an external tool only where `tb` does something that tool cannot express.
  `tb data` is the carve-out and it earns it: holding a foreign CLI's output open on a canvas and
  re-running it on a cadence is not something that CLI can do for itself. It returns *parsed data*
  — a tool that printed something other than JSON has failed its contract, and the envelope says
  so rather than carrying the bytes.

## The interactive surface

`tb ui` opens **the canvas**: a command palette over a window canvas, where every command opens a
window and a pinned window re-runs itself on a cadence, with the operator's saved commands down
the left. It is a consumer of the output contract,
not a second CLI. It replaced `tb tui` on 2026-08-20 — the terminal could not do overlapping
draggable windows, which is the central metaphor. `docs/features/done/canvas.md` records the whole
design, and `docs/design/toolbox-demo.html` is the mockup it was built from.

The rules that are not negotiable:

- **Nothing keeps a command table.** The palette comes from `/api/catalog`, which walks the real
  Click tree, so it cannot drift from the CLI. A palette offering a command that does not exist is
  worse than no palette, because it has already told you it does. A *surface* excludes itself by
  setting `tb_surface` on its own command object rather than by being named in a skip-list here.

  **A raw command is not a drift.** Anything typed whose first word is not a tb command is offered
  as `tb read -- <argv>`, synthesised from the query rather than from any list, with the expansion
  shown before it runs. It defaults to `$HOME` — neutral, because the canvas inherits whatever
  directory `tb ui` started in, and any repo with a `cli/` package shadows a tool's own.
- **Only a read may be given a cadence.** See § Scope.
- **The refresh clock lives in Python, keyed to the connection.** A watcher runs while its stream
  is open, so it pauses when the window closes and keeps running when the window is merely
  minimized. It cannot be a browser timer: a hidden page has its timers clamped to roughly one
  fire per minute, so a 5s watcher would silently become a 60s one at the exact moment you stopped
  being able to see that it had. Nothing survives the last window, which is what makes this a
  scheduler and not a daemon.
- **Reads in, execution out.** Introspection runs in-process because walking the tree runs
  nothing. Commands run in a *subprocess*, because a thread cannot be cancelled and a watcher
  fires unattended — one hung `git fetch` would strand a thread forever. `tb --json` already
  prints the envelope, so nothing parses human output.
- **No single result may render unbounded.** The terminal surface froze for exactly this, and a
  120k-line result kills a browser tab as dead as it killed a `RichLog`. The substrate changed;
  the rule did not. See `MAX_ROWS` and `MAX_CHARS` in `cli/canvas/static/render.js`.
- **The server is remote code execution bound to a port, and is treated that way.** Four things,
  none optional: loopback bind, a required custom header (which forces a preflight that is never
  answered — this is the one that actually stops a hostile page), a per-launch token, and an
  `Origin` check. **There is no CORS allow-origin header anywhere and adding one would undo most
  of that.** A test asserts its absence.
- **Everything in `cli/canvas/static/` is served.** Anything left there is published; a test
  declares the inventory. Two scratch pages lived there during the build, one with a live token
  baked in.
- **One number drives every size.** `--tb-scale` is injected from `tb ui --scale` and the
  stylesheet is written in `rem` where `1rem` is four scaled pixels. Do not add a `px`. CSS `zoom`
  was rejected because it breaks dragging — `clientX` is unzoomed and `left` is zoomed — and
  `--force-device-scale-factor` because it *overrides* display scaling rather than multiplying it.
- **The shell is a native webview** (`cli/canvas/shell.py`), because three things the operator
  asked for are impossible in a browser: a frameless window that is still resizable, a page that
  moves its own window, and no port exposed to any other tab. `--browser` and `--no-browser` keep
  the old paths, and `--no-browser` is still the mode to develop in.
- **`frameless=True` is a request, and a window manager may refuse it.** GTK reports
  `DECORATED = False` and the window manager can still draw a title bar — measured, not assumed.
  Removing it is a window-manager rule matched on `WM_CLASS`, which is why the shell sets one
  (`toolbox`) — and **nothing here writes that rule.** A desktop belongs to whoever runs it, the
  spelling differs per environment, and a tool that edited one would be reaching outside itself.
- **Drag is not `pywebview-drag-region`.** That is a Cocoa and Windows feature; the GTK backend has
  no drag regions at all, only `easy_drag`, which makes the whole page a handle and would mean
  dragging a window inside the canvas also drags the canvas. The bar calls
  `Gtk.Window.begin_move_drag` instead, so the window manager owns the drag and it snaps and tiles
  like every other window.
- **The surface carries its own close button**, guarded like every other route, because the frame
  it would otherwise rely on may not be there.
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
- **The frontend has no automated tests.** There is no JS test runner and adding one means npm.
  The pure parts — `unwrap`, `suggest`, `roleFor` — are what a runner would be for. Verified by
  rendering headless Chromium against the live server and reading the DOM back, which is not the
  same thing and caught two real bugs.

## CLI setup

**`tb` is installed on PATH.** Symlink `~/.local/bin/tb` → this repo's `tb` (that directory is
already first on PATH), because `tb` is a homebase tool you run from anywhere.

**`PYTHONSAFEPATH=1` in the wrapper is load-bearing.** `python -m` prepends the current directory
to `sys.path` *ahead of* `PYTHONPATH`, so running `tb` from inside any directory containing a
`cli/` package imports that one. This has already bitten once: generating systemd units from
inside an older checkout wrote every unit with the old `WorkingDirectory`, successfully and
silently.

**The consequence is a hard rule: `tb` never assumes cwd is the project root.** Every path derives
from `PROJECT_ROOT` in `cli/helpers.py`, and the wrapper resolves its own symlink with `realpath`
before setting `PYTHONPATH` — otherwise `python -m cli` resolves the package relative to
`~/.local/bin`. This is a whole class of bug: relative `PATH` entries re-resolving against each
child's cwd, 112 tests failing from a tmp dir. Read the wrapper's comments before touching it.

**A sibling CLI on PATH is not necessarily runnable from anywhere.** A wrapper that resolves its
`.venv` against the *cwd* rather than the resolved symlink fails outside its own repo. So
**anything tb runs from another repo needs an explicit working directory**, not just PATH.

- **Dependencies:** `.venv` + `requirements.txt`. No `pyproject.toml`, pyright, or pre-commit
  until something needs them. Python here is 3.14.7 — new enough that a dependency may lack wheels.
- **`--json` is a root-group flag** stored in the Click context, so the output decorator handles
  every command with no per-command boilerplate.
- **Shell completion:** for fish, `_TB_COMPLETE=fish_source tb > ~/.config/fish/completions/tb.fish`.

**If your login shell is fish**, note that a fish *function* resolves ahead of PATH. A
distro-packaged fish config that defines a `tb` alias will therefore shadow this CLI, and because
that file is package-owned it comes back on update. The fix is an override in
`~/.config/fish/config.fish`: `functions --query tb; and functions --erase tb`. If `tb` ever stops
resolving after a system update, check there first.

### Where things live

| What | Where | Authored by | Versioned |
|---|---|---|---|
| Code, tests, docs | this repo | the project | here |
| Saved commands (`tools.toml`) | `~/.config/tb/` (`$TB_HOME`) | the operator, and `--save` | never |
| Capture formats and highlight rules (`formats.toml`) | `~/.config/tb/` (`$TB_HOME`) | the operator | never |
| Browser profile for the canvas | `~/.local/state/tb/` (`$TB_STATE`) | the machine | never |

**`$TB_HOME` is the operator content directory, and it is outside the repo with no fallback path
into it.** The rule it exists under: operator content used to live in this repo, justified by *the
git diff is the maintenance log*, and a machine record carried a tailnet address into every commit,
so the tool could not be published without publishing the operator. An absent home degrades to
nothing declared rather than raising — a fresh clone has no tools and saying so every invocation
would be noise. It is separate from `$TB_STATE` because `rm -rf ~/.local/state/tb` is a reasonable
way to reset the surface and must not also delete every tool the operator wrote.

**The suite redirects `TB_HOME` as well as `TB_STATE`**, and that one matters more: a tool is an
argv tb will *run*, so a suite reading the real home would register the operator's commands into
the tree under test.

**The suite never touches the real state directory** — `tests/conftest.py` redirects `TB_STATE`
before anything imports `cli`. **Nothing operator-specific in tracked files.**

### Testing

```bash
.venv/bin/python -m pytest              # whole suite (fast — no network)
.venv/bin/python -m pytest -k capture   # by name
```

`pytest.ini` sets `pythonpath = .` so `cli` imports without installation, and `asyncio_mode = auto`
because the canvas's session loop is async. Dev dependencies are in `requirements-dev.txt`.

**To work on the surface**, run `tb ui --no-browser --port 8765` and point a browser at it.
**Live reload is on and rides the session stream** — the server fingerprints `static/` on its
existing tick and pushes a `reload` frame. A CSS edit is swapped in place and every window keeps
its state; anything else is a full reload and loses them, because the module graph is already
evaluated and half-old JavaScript holding live state is the "wrong but looks right" failure. Only
a change to Python needs a restart, and that one is not made hot-reloadable on purpose.

**Test the decisions, not the ceremony.** The suite catches what would break silently: the
exit-code mapping (including why partial is 3 and not 2), stdout purity under `--json`, that every
API route refuses an unauthenticated request, that a watcher dies with its window, and that `data`
never carries a failed tool's output.

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
makes an exception safe is not which command it is, it is **who named the argv**: `tb run` and
`tb read` both run an argv the operator typed, and seeing its output is the feature. Any command
that shells out on its own initiative still keeps that output out of `data`.

**`tb data` is deliberately not an exception even so** — it carries parsed data only, and a tool
that printed something else has failed its contract. See [[text-reads]].

**Gotcha:** never `from cli.<mod> import <same_name>` in `cli/__init__.py` — it rebinds the package
attribute from the module to the Command and shadows the module. Import under an alias.

## Conventions

Shared with sibling CLIs so the family feels like one tool.

- **Python 3 + Click.** Available here: Python 3.14.7, click 8.3.3. Fail fast with a readable
  install message on a missing dependency.
- **Layout:** `tb` bash wrapper → `cli/__main__.py` thin entry → `cli/` package. The wrapper does
  path work only (resolve symlinks, prefer `.venv`, set `PYTHONPATH`, `exec python -m cli "$@"`).
- **Shared plumbing in `cli/helpers.py`** — `PROJECT_ROOT`, `STATE_DIR`, `run_command`. Command
  modules call these rather than building paths directly.
- **Ops commands act on real machines** via SSH, systemd, or the filesystem — never through an API
  client. Keep any HTTP behind a dedicated adapter module.
- **A command tb spawns gets the operator's environment, not tb's.** Everything that shells out
  goes through `child_env()` in `cli/helpers.py`, which drops `PYTHONPATH` and `PYTHONSAFEPATH` —
  the two the wrapper exports so `python -m cli` resolves. Without it a wrapped Python tool imports
  *this* `cli` package from anywhere on the machine. `PATH` is deliberately kept: stripping the
  venv the wrapper prepends would be tb choosing which `python3` a foreign tool finds. Not a
  clean room — scrub what tb added to boot and nothing else. See [[subprocess-env]].
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
  only `data` carries fields nobody here chose — tb's own commands picked theirs deliberately and
  auto-dropping one would be a bug wearing a feature's clothes. The key is *omitted* rather than
  null when absent, so an unshaped envelope stays byte-identical to one from before views existed.
  The rules live in `cli/view.py` and not in `render.js`, because the frontend has no test runner:
  that puts the deciding half where pytest reaches it and leaves both renderers drawing what they
  are told. See [[table-views]].
- **Degrade gracefully.** An unreachable host or absent config warns in yellow on **stderr** and
  continues. Keep stdout clean so `--json` stays parseable, and never collapse "reports clear"
  into "cannot see".
- **`.env` is gitignored and never committed.** Ship a `.env.example`.

## Feature workflow

`docs/design/fundamentals.md` is **the constitution**: the 2026-08-21 pass that treated the
built surface as pure concept and decided the eight primitives, with dated decisions and
visible reversals. Feature specs convert it into buildable rounds; read it before proposing a
primitive-level change. `docs/features/done/` holds the completed docs — `canvas.md` (the
surface, five rounds), `table-views.md` (the shaping contract), `follow.md` (the streaming
substrate), `tools.md` (saved commands, three rounds), `highlight.md` (lexical tint, three rounds),
`header.md` (the mark), `text-reads.md`,
`subprocess-env.md`, and the constitution's rounds as they land. `docs/features/` is empty. Every earlier
spec was deleted with the system it described; the done docs that predate the 2026-08-21
renames say `wrap`/`every` on purpose — dated, never scrubbed.

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
