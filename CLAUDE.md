# CLAUDE.md

Guidance for Claude Code when working in this repository.

Machine-specific context — this operator's network, sibling repositories, and home setup — lives
in `CLAUDE.local.md`, which is gitignored. If you are reading this in a fresh clone, that file is
absent and nothing here depends on it.

## What this repo is

**tackle-box** is the homebase toolbox for a primary workstation and the machines around it. It
pairs **deterministic scripts** (things that must do exactly the same thing every time) with
**agentic automations** (things a Claude run decides and then reports on), behind one operator
CLI: `tb`.

**Check before you describe.** This is young and moving. When asked about a command or module,
confirm it exists rather than inferring it from this document, and correct the document when it
has fallen behind.

## Scope

**Commands are grouped by mood — what they do to the world — not by domain.** The domain axis
grows without bound (every new machine or service is a new group); the mood axis is closed at
four. See `docs/features/command-taxonomy.md`.

| Group | Mood | Owns | Writes? |
|---|---|---|---|
| `tb run` | imperative | Run a job, an internal task, or ad-hoc argv — always with a lane, a ledger entry and a log | **yes** |
| `tb auto` | temporal | Job definitions, lanes, scheduling, ledger, logs. The center of gravity | schedules only |
| `tb info` | descriptive | What a thing *is* — `tb info assets` today; `tb info home`, `tb info net` later | never |
| `tb check` | evaluative | What is *wrong* — `tools`, `unpushed`, `drift`. Bare `tb check` runs them all, worst-first | never |

`tb doctor` is the one kept alias, onto `tb check tools`.

**Surfaces are the honest exception** — in none of the four moods, because they add no verb: they
render the same envelope every command returns. `tb tui` is the interactive one; `tb mcp serve`
will join it. A surface must never reach a mutating function directly — its only verb is
"dispatch a string" — so `tb run` stays the single door that writes. `tests/test_taxonomy.py`
enforces both halves.

**The property this exists for: `tb run` is the only door that writes.** Nothing changes state
without a ledger entry, because there is no other way in. That makes the MCP allowlist a rule
rather than a maintained list — `info`, `check`, and `auto`'s read verbs are unconditionally
safe; `run` is the single gate. A command added next year is safe or gated by where it lives.

The one narrow exception: a surface may own **view verbs** — words that change what is rendered
and never what exists. `inspect` is the first. They are resolved *after* the Click tree, never
before, so no real command can be shadowed; `cli/tui/verbs.py` carries the rule.

**Where a new command goes:** does it act (`run`), schedule (`auto`), describe (`info`), or judge
(`check`)? A command that wants to both read and write is two commands.

**Considered and deliberately rejected** — do not re-propose without being asked:

- **`tb check unpushed` stays a data-risk question**, not a project-orchestration one: is any work
  living on a single disk. It does not act on repos and must not grow into doing so.
- **`tb power`** (energy telemetry) — premature; revisit when there is a site to measure.
- **`tb ctx`** and **`tb secrets`** (unified context switching, a secrets manager as root of trust
  for `aws`/`gh`/`stripe`) — rejected. **External CLIs keep their own authentication.** `tb` is
  never in the credential path. This is what keeps the MCP surface safe to expose.

## Boundary: what tackle-box does not own

Sibling projects run one repo per deployable thing, each with its own CLI. tackle-box is the layer
above and **must not absorb their jobs.** A project that has its own scheduler keeps it; `tb auto`
is homebase-level only and never manages, generates, or edits another project's schedule.

The distinction that keeps this clear is **asset register vs operation**. tackle-box records the
hardware the operator *owns* — every machine, Pi and prototype — because nothing else tracks them
all in one place. A project that runs a business on some of that hardware owns the operation.
Where a sibling has claimed a word for its own concept, do not reuse it for a tackle-box command.

Rule of thumb: if a task is about *one project*, it belongs to that project's CLI. tackle-box is
for what spans machines, or what has no project to belong to.

**Separate ownership is not separate awareness.** Other schedulers may run on the same machine.
Derive their reserved windows by reading `crontab -l`; never duplicate a foreign schedule into a
file here, because a copy drifts. Treat any entry `tb` did not generate as an opaque busy window,
**read only** — never write, reorder, or remove one. Those entries often carry comments recording
expensively-learned constraints; read them before scheduling anything nearby. Collision avoidance
with cron is **advisory**, enforced at schedule time: systemd `Conflicts=` only mutexes between
units, and cron jobs are not units.

## Job management — the core

The design problem this repo exists to solve: long jobs that need starting, tracking, and
reporting on, across several machines, without a terminal babysitting them.

**Substrate: systemd user units and timers, generated by `tb`.** Not cron, and not a hand-rolled
scheduler. systemd provides journal logging, exit-status tracking, timeouts, restart policy,
detachment surviving logout, and — the reason it wins — `After=` and `Conflicts=` expressing
ordering and mutual exclusion natively. `tb` generates and inspects units; it does not reimplement
a scheduler.

The job layer owns:

- **Declarative definitions** — what runs, where, timeout, which lane. The schedule is generated
  output, never hand-edited.
- **Lanes, enforced** — a job declares the lane it needs; the runner queues or refuses rather than
  overlapping. This is the thing cron comments cannot do.
- **A target** — local or another machine, from the same definition. This is what makes it
  homebase rather than per-project.
- **A durable ledger** — what ran, when, exit status, duration, log path. Spans machines.
- **Notification** on finish or failure.

**Agentic runs are just jobs with a Claude runner** — same lanes, same ledger, same logs.
Deterministic and agentic work share one management surface.

## Home automation

**Drive the existing Home Assistant instance; do not reimplement a device layer.** HA owns
integrations and device state; `tb home` is the operator CLI and the agentic layer above it.

- **Security and locks are read-only from `tb`. No exceptions.** Read armed state, sensors, and
  event history; surface them in `tb info home` and `tb check home`. **Never arm, disarm, unlock,
  or actuate.** The failure modes are asymmetric — a false disarm while away, or arming with
  someone home — and the MCP surface means any Claude session could reach it. Actuation stays
  where a human is deliberately present.
- **Distinguish "reports clear" from "cannot see."** A cloud-backed integration makes state
  unreadable during an internet outage while the panel itself keeps working. A status board that
  collapses those two is worse than none.
- **Derive the device inventory from HA's registry; do not hand-write one.** Same rule as the
  crontab: a copy drifts. (The *machine* inventory is hand-maintained only because no registry
  exists for it.)
- Lighting and scenes are fine left in HA. They do not need a CLI.

## The interactive surface

`tb tui` holds tb open. It exists because a one-shot command **structurally cannot show what is
happening now** — `run_job` appends to the ledger only after a process exits, so a lane held at
this instant is invisible to `tb auto status`. Lanes are the job layer's headline feature and the
CLI can only ever report them in the past tense.

It is a consumer of the output contract, not a second CLI. The design and every surprise are in
`docs/features/`: `tui.md`, `surface-panes.md`, `surface-concepts.md`. Read those before touching
`cli/tui/`. The four rules that are not negotiable:

- **Nothing keeps a command table.** Dispatch drives the real Click tree
  (`standalone_mode=False`); completion and the help pane read off the same tree. None can drift
  from the CLI.
- **`cli/output.py` owns every byte**, including inside the surface. Its consoles are
  thread-local, because watches refresh concurrently with what you type and module globals let
  two captures steal each other's output.
- **Never decide a lane is held by whether its lock file exists** — the file outlives the lock.
  **Never probe by trying to take it**: `lane_lock` is non-blocking, so a poll holds the lane for
  an instant and a `tb run` in that window records `skipped`. Read `/proc/locks`.
- **Every dispatch runs on a thread worker.** `check unpushed` walks the projects directory and
  `run` blocks for a whole job; either on the event loop freezes the surface.

## MCP

`tb mcp serve` exposes the **job surface** — start a job, check status, read a log, list what is
running — so any Claude surface can trigger and monitor long homebase work without needing a shell
on the machine.

- **Expose narrow `tb` verbs, never raw passthrough.** A `run_aws_command` tool is a shell with
  extra steps and no guard rails; the value is that `tb` verbs are narrow enough for guards to
  hold.
- **Read-only by default.** Status, logs, and listings are safe. Anything that touches a live
  machine or spends money goes behind an explicit allowlist — unlike a terminal, nobody is
  watching each call.

## Feature workflow

One doc per feature at `docs/features/<slug>.md`, from first sentence to done. **The doc never
moves** — `status:` transitions `draft → active → complete` in frontmatter.

That is a deliberate divergence from the sibling project that files completed specs into a second
directory. Its `git mv` step breaks both the relative links inside the moved doc and every link
elsewhere pointing at the old path; 141 links were dead before anyone noticed, 128 of them
generated by that exact step. It now needs two link checkers and a CI ratchet to stay consistent.
One folder cannot have that bug.

- `docs/features/_template.md` — the skeleton. Sections: **Why** · **Shape** (including an explicit
  *"Does not do"*) · **Phases** with `- [ ]` boxes · **Notes**.
- `.claude/skills/feature/SKILL.md` — the `/feature` skill. Takes an existing slug (execute) or a
  plain description (write the spec, confirm, then execute). **No subagents.**
- Cross-document links are `[[slug]]`, never relative paths — they survive any reorganisation.
- Check boxes and append to **Notes** *as you go*. A dead session must be resumable from the doc
  alone.
- `agent_value` (1–3) tells a future session whether a completed doc is load-bearing design
  context or just history.

**Do not build index machinery** — categories, generated READMEs, link checkers, index JSON. The
frontmatter is already machine-readable; add tooling when volume demands it.

## CLI setup

**`tb` is installed on PATH.** Symlink `~/.local/bin/tb` → this repo's `tb` (that directory is
already first on PATH), because `tb` is a homebase tool you run from anywhere.

**The consequence is a hard rule: `tb` never assumes cwd is the project root.** Every path derives
from `PROJECT_ROOT` in `cli/helpers.py`, and the wrapper resolves its own symlink with `realpath`
before setting `PYTHONPATH` — otherwise `python -m cli` resolves the package relative to
`~/.local/bin`. This is a whole class of bug: relative `PATH` entries re-resolving against each
child's cwd, 112 tests failing from a tmp dir. Read the wrapper's comments before touching it.

**A sibling CLI on PATH is not necessarily runnable from anywhere.** A wrapper that resolves its
`.venv` against the *cwd* rather than the resolved symlink fails outside its own repo. So
**anything tb runs from another repo needs an explicit working directory**, not just PATH — which
is why watch definitions carry `cwd:`.

- **Dependencies:** `.venv` + `requirements.txt`. No `pyproject.toml`, pyright, or pre-commit
  until something needs them. Python here is 3.14.7 — new enough that a dependency may lack wheels.
- **Command shape:** `<group> <verb>` (`tb info assets`, `tb check drift`). `tb run` and the
  `tb doctor` alias are the only top-level verbs.
- **`--json` is a root-group flag** stored in the Click context, so the output decorator handles
  every command with no per-command boilerplate.
- **Shell completion:** for fish, `_TB_COMPLETE=fish_source tb > ~/.config/fish/completions/tb.fish`.

**If your login shell is fish**, note that a fish *function* shadows PATH. CachyOS's packaged fish
config defines `alias tb='nc termbin.com 9999'`, which resolves ahead of this CLI. That file is
package-owned and reverts on update, so the fix is an override in `~/.config/fish/config.fish`:
`functions --query tb; and functions --erase tb`. If `tb` ever stops resolving after a
`cachyos-fish-config` update, check there first.

### Where things live

**Three homes, and the rule for each is who authored the bytes.**

| What | Where | Authored by | Versioned |
|---|---|---|---|
| Code, tests, docs, `templates/` | this repo | the project | here |
| Inventory, job definitions, watches | `~/.tackle-box/` (`$TB_HOME`) | **the operator** | its own git repo |
| Run ledger, logs | `~/.local/state/tb/` | the machine | never |

Operator content used to live in this repo, justified by *the git diff is the maintenance log*.
That reasoning survives — it is still versioned, in a repo of its own — but the arrangement did
not: a machine record carried a tailnet address into every commit, so the tool could not be
published without publishing the operator. `docs/features/operator-home.md` has the whole thing.
The rules that bite:

- **Nothing in `cli/` may read `PROJECT_ROOT / "inventory" | "jobs" | "watches"`.** A leftover
  works on the one machine that still has the old directory and silently reads nothing everywhere
  else. `tests/test_operator_home.py` fails on one.
- **No fallback, ever.** Two sources of truth for a system of record is worse than none, and
  editing one while tb reads the other fails silently.
- **An absent home degrades, never raises.** The surface asks for jobs and watches on its first
  tick, before any exist.
- **The suite never reads the real `TB_HOME`** — `tests/conftest.py` redirects it before anything
  imports `cli`. A test that loads your machines depends on whose machine it runs on.
- **Nothing operator-specific in tracked files.** Fixtures use `100.64.0.1` and
  `device.tailnet-name.ts.net`, never real ones.

### Testing

```bash
.venv/bin/python -m pytest              # whole suite (fast — no network, no subprocesses)
.venv/bin/python -m pytest -k stripe    # by name
```

`pytest.ini` sets `pythonpath = .` so `cli` imports without installation. Dev dependencies are in
`requirements-dev.txt`.

**Test the decisions, not the ceremony.** The suite catches what would break silently: the
exit-code mapping (including why partial is 3 and not 2), the `warn`/`degrade` distinction, stdout
purity under `--json`, and facts about third-party CLIs that could change underneath us.

**Every command that shells out needs a secret-containment test** — see
`test_probe_output_never_reaches_envelope`. Command output reaches stdout and MCP, so raw tool
output must never be carried into `data`.

**Gotcha:** never `from cli.<mod> import <same_name>` in `cli/__init__.py` — it rebinds the package
attribute from the module to the Command and shadows the module. Import under an alias.

## Conventions

Shared with sibling CLIs so the family feels like one tool.

- **Python 3 + Click.** Available here: Python 3.14.7, click 8.3.3. Fail fast with a readable
  install message on a missing dependency.
- **Layout:** `tb` bash wrapper → `cli/__main__.py` thin entry → `cli/` package. The wrapper does
  path work only (resolve symlinks, prefer `.venv`, set `PYTHONPATH`, `exec python -m cli "$@"`).
- **Shared plumbing in `cli/helpers.py`** — `PROJECT_ROOT`, `TB_HOME`, `run_command`, path
  constants. Command modules call these rather than building paths directly.
- **Do not wrap external CLIs for passthrough.** `tb gh pr list` is strictly worse than
  `gh pr list`. Only reach for an external tool where `tb` is doing something that tool cannot
  express — a cross-tool rollup, a managed job, or a live view the tool cannot hold open itself.
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

  A test also fails if any module outside `theme.py` names a hex. There is no theme switching.
- **Commands return data; they never print.** All rendering goes through `cli/output.py` and the
  `Result` envelope (`ok` / `partial` / `data` / `warnings`). Exit codes: `0` ok, `1` hard failure,
  `3` partial — **not 2**, which Click uses for usage errors. Bare `tb check` and the MCP server
  are both consumers of that envelope — a command that prints prose has to be written twice. See
  `docs/features/output-contract.md`.
- **Degrade gracefully.** An unauthenticated tool, unreachable host, or absent config warns in
  yellow on **stderr** and continues; it does not crash the rollup. Keep stdout clean so `--json`
  stays parseable.
- **Inventory is a system of record, and its git diff is the maintenance log.** Record the *why*
  inline as a field comment.
- **Machines are addressed by Tailnet IP** (`100.x`) where one exists, not LAN IP.
- **`.env` is gitignored and never committed.** Ship a `.env.example`.
