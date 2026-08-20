# The tb CLI

The complete command surface, and the contract every command in it honours.

**The reference below is generated from the live Click tree** by
`tests/test_cli_reference.py`, which fails when this file disagrees with the code. Regenerate it
after adding or changing a command:

```bash
TB_WRITE_CLI_DOC=1 .venv/bin/python -m pytest -k cli_reference
```

That is not tidiness. **Nothing in this repo keeps a command table** — `tb tui` dispatches through
the real tree rather than mirroring it, and the MCP allowlist is a property of where a command
lives rather than a list somebody maintains. A hand-written reference would be the first thing to
break that rule, and the first to be wrong, because a reference is read exactly when the reader
does not already know the answer.

Only the block between the markers is generated. Everything else here is prose.

## How the surface is organised

**Commands are grouped by mood — what they do to the world — not by domain.** The domain axis
grows without bound: every new machine or service would be a new group. The mood axis is closed.

| Group | Mood | Owns | Writes |
|---|---|---|---|
| `tb run` | imperative | Run a job, an internal task, or ad-hoc argv | **yes** |
| `tb auto` | temporal | Job definitions, lanes, scheduling, ledger, logs | schedules only |

There were four moods until 2026-08-20. `tb info` and `tb check` were removed with everything
behind them — the inventory subsystem, the drift/tools/unpushed checks, and watches. Round 2 of
the `command-taxonomy` feature doc records what went and why.

**`tb run` is the only door that writes.** Nothing changes state without a ledger entry, because
there is no other way in. That is what makes the MCP allowlist a rule rather than a maintained
list: `auto`'s read verbs are unconditionally safe, and `run` is the single gate. A command added next year is safe or gated by where it lives, with nobody having to
remember to classify it.

Where a new command goes is one question: does it act (`run`) or schedule (`auto`)?
**A command that wants to both read and write is two commands.**

The full argument, including the alternatives that were rejected and the two moods since removed,
is in the `command-taxonomy` feature doc. Note that the ASCII block near the top of that doc is
the *pre-taxonomy* layout it exists to replace — this page is the current surface.

### Surfaces are the honest exception

`tb tui` is in none of the four moods, because it adds no verb. It renders the same envelope every
command returns, and its only verb is "dispatch a string" — which is what keeps `tb run` the
single door that writes even with a surface in front of it. `tb mcp serve` will join it.
`tests/test_taxonomy.py` enforces both halves.

## The contract every command honours

### Commands return data; they never print

Every command returns a `Result` envelope and all rendering goes through `cli/output.py`:

```python
Result(data=..., ok=True, partial=False, warnings=[])
```

`ok` is False only on **hard failure** — the command could not do its job at all. `partial` means
it did some of it. `warnings` records a degraded source without failing.

The surface and the MCP server are both consumers of that envelope. A command that prints prose
has to be written twice, which is the whole reason the contract exists. The full argument is
in the `output-contract` feature doc.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | ok |
| `1` | hard failure — the command could not do its job |
| `3` | partial — some of the work succeeded |

**Not `2`.** Click uses 2 for usage errors, and `tb` never returns it from a command. That
collision is precisely why partial was given 3.

### `--json`

A **root-group flag**, stored in the Click context, so it works on every command with no
per-command handling:

```bash
tb --json auto status
tb --json auto list
```

Under `--json` stdout carries the envelope and nothing else. Warnings still go to stderr, so
stdout stays parseable — a pipeline is never broken by a degraded source.

### Degrading rather than crashing

An unreachable host or an absent config warns in yellow **on stderr** and continues rather than
crashing. `tb auto status` reads a ledger that may be missing entries and a systemd that may not
have the unit; neither is a reason to return nothing.

The distinction that matters, and the one a status board usually gets wrong: **"reports clear" and
"cannot see" are different answers.** A command that cannot reach a source says so rather than
reporting nothing-wrong.

## Global options

| Option | What it does |
|---|---|
| `--json` | Emit the envelope as JSON on stdout. Root-group flag; applies to any command. |
| `--version` | Print the version, from `git describe`, or `dev` outside a checkout. |
| `--help` | Available on every command and group. |

## Running it from anywhere

`tb` is a bash wrapper that resolves its own symlink before setting `PYTHONPATH`, and sets
`PYTHONSAFEPATH=1`. Both are load-bearing:

- `python -m` prepends the **current directory** to `sys.path` ahead of `PYTHONPATH`, so without
  `PYTHONSAFEPATH` running `tb` from inside any directory containing a `cli/` package imports that
  one instead. This has already bitten: generating systemd units from inside an older checkout
  wrote every unit with the old `WorkingDirectory`, successfully and silently.
- Without `realpath` on the symlink, `python -m cli` resolves the package relative to
  `~/.local/bin`.

The consequence is a hard rule: **`tb` never assumes the current directory is the project root.**
Every path derives from `PROJECT_ROOT` in `cli/helpers.py`.

Installation, shell completion, and the fish-alias gotcha are in the top-level `README.md`.

## Where a command reads and writes

| What | Where | Authored by |
|---|---|---|
| Code, tests, docs, templates | this repo | the project |
| Job definitions | `~/.tackle-box/` (`$TB_HOME`) | **the operator** |
| Run ledger, logs | `~/.local/state/tb/` | the machine |

Nothing in `cli/` reads job definitions from the repo. An absent `$TB_HOME` degrades rather than
raising — the surface asks for jobs on its first tick, before any exist.

## Reference

<!-- reference:start -->

### Every command

| Command | Writes | What it does |
|---|---|---|
| `tb run` | **yes** | Run a job, an internal task, or ad-hoc work — always through the ledger. |
| `tb auto` | no | Homebase jobs — deterministic and agentic. |
| `tb auto install` | no | Generate and enable this job's systemd user units. |
| `tb auto list` | no | Every declared job. |
| `tb auto log` | no | Recent runs of a job, most recent first. |
| `tb auto prune` | no | Trim the ledger and remove orphaned log files. |
| `tb auto since` | no | Every run across all jobs in a window — the overnight view. |
| `tb auto status` | no | Last outcome per job, worst first. |
| `tb auto uninstall` | no | Disable and remove this job's systemd user units. |
| `tb auto windows` | no | Reserved windows from the crontab — read-only, never written. |
| `tb tui` | no | Open the interactive surface — input below, transcript above. |

### `tb run`

Run a job, an internal task, or ad-hoc work — always through the ledger.

Exits with the work's own meaning: 0 ok, 3 partial, 1 failed.

| Argument | Type | Required |
|---|---|---|
| `TARGET` | text | no |

| Option | Type | Default | Description |
|---|---|---|---|
| `--lane` | `committing` · `read-only` | — | Run loose argv as an ad-hoc job in this lane. Required for ad-hoc work. |
| `--timeout` | integer | `900` | Ad-hoc timeout, seconds. |

### `tb auto`

Homebase jobs — deterministic and agentic.

A group. `tb auto` on its own prints help.

#### `tb auto install`

Generate and enable this job's systemd user units.

| Argument | Type | Required |
|---|---|---|
| `NAME` | text | yes |

| Option | Type | Default | Description |
|---|---|---|---|
| `--no-enable` | flag | off | Write the units but do not enable the timer. |

#### `tb auto list`

Every declared job.

#### `tb auto log`

Recent runs of a job, most recent first.

| Argument | Type | Required |
|---|---|---|
| `NAME` | text | yes |

| Option | Type | Default | Description |
|---|---|---|---|
| `--limit` | integer | `10` | How many runs to show. |
| `--run` | text | — | Show one run's captured output. |

#### `tb auto prune`

Trim the ledger and remove orphaned log files.

| Option | Type | Default | Description |
|---|---|---|---|
| `--keep` | integer | `50` | Runs to keep per job. |

#### `tb auto since`

Every run across all jobs in a window — the overnight view.

| Argument | Type | Required |
|---|---|---|
| `WINDOW` | text | no |

#### `tb auto status`

Last outcome per job, worst first.

With no notifier, this is the command that answers what a notification would have — so silence never reads as success.

#### `tb auto uninstall`

Disable and remove this job's systemd user units.

| Argument | Type | Required |
|---|---|---|
| `NAME` | text | yes |

#### `tb auto windows`

Reserved windows from the crontab — read-only, never written.

jam.sense's entries are somebody else's schedule. tb derives them so it can avoid landing on top of them, and touches nothing.

### `tb tui`

Open the interactive surface — input below, transcript above.

The second honest exception to the mood taxonomy, alongside `tb mcp serve`. Neither is a command in a mood: they are surfaces over the same envelope every command returns, and `tb run` remains the only door that writes.

<!-- reference:end -->
