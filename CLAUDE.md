# CLAUDE.md

Guidance for Claude Code when working in this repository.

Machine-specific context — this operator's network, sibling repositories, and home setup — lives
in `CLAUDE.local.md`, which is gitignored. If you are reading this in a fresh clone, that file is
absent and nothing here depends on it.

## What this repo is

**tackle-box** is the homebase toolbox for a primary workstation and the machines around it,
behind one operator CLI: `tb`.

**It is currently a scaffold, deliberately.** On 2026-08-20 the job layer, the asset register, the
check suite and the watch system were all removed to design that half over from a clean base. What
survives is the part worth building on:

| Command | Does |
|---|---|
| `tb run -- <argv>` | Runs a command and reports what it printed. The only command that acts |
| `tb tui` | Holds tb open — input at the top, newest result under it |

**Check before you describe.** This is young and moving, and it just lost most of its surface area.
When asked about a command or module, confirm it exists rather than inferring it from this
document, and correct the document when it has fallen behind.

## Scope

There is no taxonomy to defend yet. The one property worth preserving from the version that was
removed is this: **`tb run` is the single command that acts.** Everything else reads. When a group
of commands returns, that is the line to keep — a command that wants to both read and write is two
commands.

The removed design grouped commands by *mood* — imperative, temporal, descriptive, evaluative —
rather than by domain, on the reasoning that the domain axis grows without bound while the mood
axis is closed. That reasoning held; what did not hold was carrying four moods for eleven
commands. If groups come back, group them that way and be slower to add one.

**Considered and deliberately rejected** — do not re-propose without being asked:

- **`tb ctx`** and **`tb secrets`** (unified context switching, a secrets manager as root of trust
  for `aws`/`gh`/`stripe`). **External CLIs keep their own authentication.** `tb` is never in the
  credential path. This is what keeps a future MCP surface safe to expose.
- **Wrapping an external CLI for passthrough.** `tb gh pr list` is strictly worse than
  `gh pr list`. Reach for an external tool only where `tb` does something that tool cannot express.

## The interactive surface

`tb tui` holds tb open. It is a consumer of the output contract, not a second CLI. **Read
`cli/tui/app.py`'s module docstring before touching `cli/tui/`** — the design and the expensive
surprises are recorded there and in the comments, now that the feature docs are gone.

The rules that are not negotiable:

- **Nothing keeps a command table.** Dispatch drives the real Click tree
  (`standalone_mode=False`); completion and the help pane read off the same tree. None can drift
  from the CLI. `dispatch`, `candidates` and `help.view` each take an injectable tree for tests,
  which is the only reason the real one may be small.
- **`cli/output.py` owns every byte**, including inside the surface. Its consoles are
  thread-local, because a dispatch runs on a worker thread while you keep typing, and module
  globals let two captures steal each other's output.
- **No single turn of the event loop may be unbounded.** The older phrasing was "a dispatch never
  runs on the event loop", and it named the wrong unit: the dispatch was always on a thread, but
  the *result* came back through `call_from_thread` and rendered on the loop, where a large one
  blocked for 17s and no key — including the ones that leave — was ever read. `write_body` is the
  single door and bounds what it writes.
- **Leaving must always work.** A thread worker cannot be cancelled, and `asyncio.run` joins it at
  shutdown for `THREAD_JOIN_TIMEOUT` — 300 seconds on 3.14. `cli/tui/app.run` owns its loop and
  leaves through `os._exit` when a worker is still alive.
- **A stall must explain itself.** `cli/tui/watchdog.py` is a daemon thread heartbeated by a loop
  timer; on a stall it dumps every thread's stack to `$STATE_DIR/tui-stall.txt`. Detection has to
  be off-loop — an async task cannot report a blocked loop, because the thing it would report is
  the reason it is not running.

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

**If your login shell is fish**, note that a fish *function* shadows PATH. CachyOS's packaged fish
config defines `alias tb='nc termbin.com 9999'`, which resolves ahead of this CLI. That file is
package-owned and reverts on update, so the fix is an override in `~/.config/fish/config.fish`:
`functions --query tb; and functions --erase tb`. If `tb` ever stops resolving after a
`cachyos-fish-config` update, check there first.

### Where things live

| What | Where | Authored by | Versioned |
|---|---|---|---|
| Code, tests, docs | this repo | the project | here |
| Input history, stall dumps | `~/.local/state/tb/` (`$TB_STATE`) | the machine | never |

There is **no operator content directory** at the moment — nothing declares anything. When one
comes back, the rule it existed for still holds: operator content used to live in this repo,
justified by *the git diff is the maintenance log*, and a machine record carried a tailnet address
into every commit, so the tool could not be published without publishing the operator. Keep the
two apart from the start, take no fallback path between them, and let an absent home degrade
rather than raise.

**The suite never touches the real state directory** — `tests/conftest.py` redirects `TB_STATE`
before anything imports `cli`. **Nothing operator-specific in tracked files.**

### Testing

```bash
.venv/bin/python -m pytest              # whole suite (fast — no network)
.venv/bin/python -m pytest -k capture   # by name
```

`pytest.ini` sets `pythonpath = .` so `cli` imports without installation. Dev dependencies are in
`requirements-dev.txt`, which also carries `textual-dev` for `textual run --dev`.

**Test the decisions, not the ceremony.** The suite catches what would break silently: the
exit-code mapping (including why partial is 3 and not 2), stdout purity under `--json`, that a
finished capture leaves the consoles usable, and that a large result cannot freeze the surface.

**Assert against the mechanism, not the timing.** The freeze guard uses a heartbeat timer rather
than the duration of a call: a write that is merely fast would pass the weaker check, and what has
to hold is that the loop kept getting turns.

**Raw command output must not reach `data`** for anything the CLI runs on its own initiative — a
probe can print a token, and `data` reaches stdout and any future MCP surface. `tb run` is the one
exception and says so in its docstring: you named the argv, and seeing its output is the feature.

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
- **One palette, in `cli/theme.py`** — Skyrow Labs' **design system**, copied verbatim from its own
  `colors_and_type.css`, vendored at `docs/design/` so the copy is checkable. The system is
  dark-only by declaration.

  **Two renderings, one system.** The TUI paints its own background and takes the tokens
  unmodified. The CLI renders into whoever's terminal, where the tokens are not dim but gone —
  brand measures 2.14:1 on white, warn 1.44:1 — so every CLI role is the smallest darkening of its
  token that clears 3.5:1 against *both* white and the void. `STYLES` and `TUI_STYLES` must cover
  the same roles, and a test measures the floor rather than trusting anyone's eye: two grey roles
  missed it by a hair while looking perfectly fine.

  A test fails if any module *or stylesheet* outside `theme.py` names a hex — `cli/tui/tb.tcss`
  gets its `$tb-*` tokens from `TackleBox.get_css_variables`, which is what lets the stylesheet
  live in a file that `textual run --dev` can reload. There is no theme switching.
- **Commands return data; they never print.** All rendering goes through `cli/output.py` and the
  `Result` envelope (`ok` / `partial` / `data` / `warnings`). Exit codes: `0` ok, `1` hard failure,
  `3` partial — **not 2**, which Click uses for usage errors. The surface is a second consumer of
  that envelope — a command that prints prose has to be written twice.
- **Degrade gracefully.** An unreachable host or absent config warns in yellow on **stderr** and
  continues. Keep stdout clean so `--json` stays parseable, and never collapse "reports clear"
  into "cannot see".
- **Machines are addressed by Tailnet IP** (`100.x`) where one exists, not LAN IP.
- **`.env` is gitignored and never committed.** Ship a `.env.example`.

## Feature workflow

`docs/features/` is **empty** — every spec was deleted with the systems it described. The workflow
itself is kept because it is process rather than content, and the first new feature doc recreates
the directory.

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
  adequate index for an empty directory, and the test that kept the old one honest is the model to
  copy if volume ever demands one again.
