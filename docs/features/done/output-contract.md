---
slug: output-contract
title: Uniform output contract
status: complete
created: 2026-08-18
updated: 2026-08-18
agent_value: 3
key_files:
  - cli/output.py
  - cli/doctor.py
  - cli/__init__.py
  - tb
  - cli/__init__.py
  - cli/__main__.py
  - cli/helpers.py
---

# Uniform output contract

## Why

Every `tb` command will be read by three different consumers: a human at a terminal,
`tb brief` merging results across domains, and the MCP server exposing the same verbs to
Claude sessions. If commands `print()` prose, the second and third consumers have to
re-parse text that was formatted for the first — and `tb brief` and `tb mcp serve` end up
reimplementing every command's output.

This is foundational, not polish. Retrofitting an output contract across a dozen existing
commands is a rewrite; establishing it before the first command is roughly a hundred lines.
It is therefore **feature #1** — nothing else lands before it.

There is also a state this repo needs that most CLIs lack. `tb` degrades gracefully by
convention: an unreachable host or unauthenticated tool warns and continues. So "3 of 6
hosts reachable" is neither success nor failure, and every consumer would otherwise have to
guess. The contract needs a first-class **partial** result.

## Shape

`cli/output.py` owns all rendering. **Command functions return data; they never print.**

A single result envelope:

```python
Result(
    command="fleet.status",   # dotted verb, stable — this is also the MCP tool name
    ok=True,                  # False only on hard failure
    partial=False,            # True when some sources failed but output is still useful
    data={...},               # the payload, JSON-serializable
    warnings=[...],           # human-readable, one per degraded source
)
```

Two renderers over that envelope:

- **human** (default) — colorized, tables, `warnings` to **stderr** in yellow so stdout
  stays clean.
- **`--json`** — the envelope verbatim to stdout, nothing else. Warnings stay on stderr.

Exit codes: `0` ok · `1` hard failure · `3` partial. (**Not** 2 — Click already uses 2 for usage errors.) A caller can branch on the exit code
without parsing anything, which is what makes these composable inside job definitions.

`tb brief` then merges envelopes rather than scraping text, and `tb mcp serve` becomes close
to free: the dotted `command` name is the tool name, `data` is the tool result, and `partial`
is what stops a Claude session reporting "all hosts healthy" when half were unreachable.

**Does not do:** no logging framework (stdlib `logging` to the journal, separate concern),
no output templating or user-configurable formats, no pagination, no progress bars.
Two renderers, one envelope.

## Phases

### Phase 0 — Repo skeleton

The scaffold is prerequisite to this feature and covered by no other doc, so it lives here
rather than in a ceremonial doc of its own.

- [x] `git init`, `.gitignore` (`.venv/`, `__pycache__/`, `.env`)
- [x] `tb` wrapper — resolve own symlink with `realpath`, prefer `.venv`, set `PYTHONPATH`,
      `exec python -m cli "$@"`
- [x] `cli/__init__.py` (Click root group, version from `git describe`), `cli/__main__.py`,
      `cli/helpers.py` (`PROJECT_ROOT`, `run_command`)
- [x] `.venv` + `requirements.txt` (click)
- [x] Symlink `~/.local/bin/tb` → `~/tackle-box/tb`; confirm `tb --help` works from `~`

### Phase 1 — Envelope and renderers

- [x] `Result` dataclass in `cli/output.py`
- [x] Human renderer: scalars, key/value, and list-of-dicts as a table
- [x] JSON renderer: envelope verbatim to stdout
- [x] Warnings to stderr in both modes
- [x] Global `--json` flag on the root Click group

### Phase 2 — Exit codes and wiring

- [x] Map `ok`/`partial` to exit codes 0/1/3
- [x] A decorator that lets a command return a `Result` and handles rendering + exit
- [x] An uncaught exception becomes a well-formed `ok: false` envelope, not a traceback

### Phase 3 — Prove it

- [x] Implement `tb doctor` against the contract as the first real consumer
- [x] Confirm `--json` output parses with `jq` and that a degraded run exits 3
- [x] Record the contract in CLAUDE.md as a convention

## Notes

Sequenced before `fleet` and `auto` on purpose: `doctor` is the cheapest command that
exercises the whole contract end to end, including the partial state (one tool
unauthenticated among several).

**Phase 0 (2026-08-18).** Only `cli/` was created. `inventory/`, `jobs/`, `agents/`, and
`scripts/` were deliberately *not* — each belongs to a feature that is not specced yet, and
their formats are undesigned. Creating them now would mean either empty directories git
cannot track, or inventing a job-definition format before the job runner is specced. They
arrive with their features.

`tb` is confirmed working from `~` through the `~/.local/bin` symlink, which is the property
the `realpath` + `PYTHONPATH` dance in the wrapper exists to guarantee. `--version` reports
the git SHA since no tags exist yet.

**Phase 1 (2026-08-18).** `Result` grew two methods the spec did not name: `warn()` records a
degraded source *without* marking the result partial (some warnings are informational), and
`degrade()` does both. Keeping them separate means `partial` stays a deliberate claim rather
than a side effect of any warning.

Warnings are emitted to stderr **and** retained in the JSON envelope. Verified with
`tb --json ... | jq`: stdout parses as pure JSON while the warning still reaches the terminal.

The table renderer takes the union of all rows' keys in first-seen order, so a row missing a
key renders `-` instead of shifting columns.

**Phase 2 (2026-08-18).** The spec said partial should exit `2`. It cannot: Click already
exits `2` on usage errors, so a job branching on exit codes would read a typo'd invocation as
a degraded run. Partial is now `3`. Verified that a bad option still gets Click's own handling
and its own `2`.

`Result.command` became optional and is filled by `emit` from Click's command path
(`tb assets status` → `fleet.status`). Deriving it rather than repeating it in every command
means the envelope name and the MCP tool name cannot drift from the real command path.

`emit` re-raises Click's own control-flow exceptions (`ClickException`, `Abort`, `Exit`) —
swallowing those would break `--help` and usage errors. Everything else becomes an `ok: false`
envelope, with `TB_DEBUG=1` as the escape hatch that re-raises for a real traceback. Without
it, tidy error envelopes make the CLI undebuggable.

A command returning a non-`Result` is caught explicitly and named in the error, since that is
the one mistake the whole contract exists to prevent.

**Phase 3 (2026-08-18).** `tb doctor` is the first real consumer and exercises the whole
contract: a live degraded run (bws unauthenticated) renders a table, warns on stderr, keeps
stdout pure JSON under `--json`, and exits 3. Run from `~`, so it also proves the wrapper's
symlink handling with a real command rather than `--help`.

**Doctor never retains raw tool output.** `stripe config --list` prints API keys, and the
envelope reaches stdout and MCP. Probe output is inspected locally to derive a boolean and
discarded; only tb's own strings reach `data`. Any future check must hold to this.

Stripe needed a custom verifier: `stripe config --list` exits 0 even with nothing configured,
so the exit code alone is not a signal — presence of a profile section is.

Doctor reports `ok: true` with `partial` set when a tool is unhealthy. Doctor itself succeeded;
`partial` describes what it looked at. That is what makes `tb doctor` usable as a gate inside a
job definition.

**Scope gap to close later:** CLAUDE.md describes doctor as checking "installed, authenticated,
unexpired, pointed where you think". This version covers installed and authenticated only.
Credential *expiry* and *which account/context* each tool is pointed at are not implemented —
the latter matters most for Stripe live-vs-test.
