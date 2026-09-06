# sky.boss

One CLI for watching what other tools do, here and across these repos

> **Before making changes**: load docs on-demand via `docs/README.md` or `.github/DOCS_INDEX.md`.
> Never load the whole tree — a typical task needs one or two documents.

This file is the one every agent reads. `AGENTS.md` is the convention shared
across tools.

`CLAUDE.md` is a pointer to this file rather than a copy, because two files
stating the same rules drift within the week and the copy that is wrong is the
one that happens to get loaded. Put rules here, never there.

The detailed rule files are in `docs/rules/`, and they are plain markdown with
no tool-specific syntax. They sit under `docs/` rather than in a vendor
directory on purpose: nothing loads them automatically for any agent — they are
read because this file names them — so putting them somewhere tool-branded
would have been a claim that was never true, and one that made the conventions
look optional to anybody not using that tool.

---

## Quick Start

```bash
python -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
.venv/bin/pre-commit install --install-hooks
npm install
./dev check pre-push   # every host-runnable CI gate; green on a fresh tree
./dev test unit        # the fast suite
./dev check health     # is the local stack up? (SCAFFOLD: wire the probes)
```

**Every one of them exists** — that is the claim this paragraph is making, and it
is the one worth checking. The install lines came from the same source as the
README's Setup block when this repository was scaffolded, and what keeps them in
step now is `tests/test_setup_blocks_agree.py` rather than the generator, which
left. The three lines after them belong to this file alone and are not compared
with anything. An
earlier version of this file opened with `./dev setup`
and `./dev service up`, which the CLI has never implemented — and `setup`
could not be implemented, because the CLI cannot run until the install it would
be performing has already put `click` in the venv. A quick start that fails on
line one reads as user error at the exact moment a reader has no way to tell.

---

## Services

<!-- SCAFFOLD: replace with this project's real components. Delete the row template. -->

| Service | Stack | Port | Purpose |
| ------- | ----- | ---- | ------- |
|         |       |      |         |

---

## Critical Rules

Numbered so they can be cited in review and in commit bodies. Each one exists because
something went wrong without it — keep the reason attached when you edit one.

### 1. Read the Config From One Place

Never re-derive a value that already has an owner. Feature parameters, schedules, windows,
sort orders, and version numbers are each resolved by exactly one module, which every
consumer **imports**. Two copies of a rule drift within the week, and the copy that is wrong
is always the one being read.

### 2. Test Code Before Delivery

Execute and verify in the correct environment before handing off. "It should work" is not a
result. If the code runs in a container, run it in that container.

### 3. Lint Before Committing

Run the blocking set after any change — see `docs/rules/python.md`. CI blocks on
all of it, and the type check is **whole-project**: one stale error anywhere blocks every
commit, not just commits near it.

### 4. Run Tests Before Committing

`./dev test <suite>` — all tests must pass. Never commit half-working code. Test files
self-register via a module-wide `pytestmark` marker; there are no registries to update.
Full rules in `docs/rules/testing.md`.

### 5. Keep the CLI in Sync

Adding or changing a script means updating the `cli/` package in the same commit. A script
nobody can discover is a script nobody runs.

### 6. Commit Strategy — Frequent, Logical, Bundled

One commit per logical idea, all of its files bundled into that commit. Conventional format,
one subject line. Full rules in `docs/rules/commits.md`.

### 7. Commit Autonomously — Push When Complete

Commit freely as each logical unit lands (tests green, conventions followed) — **no need to
ask permission**. Once the requested work is fully complete and all checks pass, push the
branch autonomously. Don't push half-finished work mid-task. **Force-push is permitted on
your own unreviewed branch** — but never on `develop` or `main`, and
never from an unattended agent.

**Base branch: `develop`.** New branches are cut from it; every PR targets it.
Never commit directly to `main`.

### 8. Open Every PR as a Draft

`gh pr create --draft`. Mark it ready only when you believe it is green.

The expensive CI jobs are gated on draft status: a draft PR runs the cheap gate job alone.
Nothing is un-gated by this — GitHub blocks merging a draft regardless, and marking it ready
fires `ready_for_review`, which runs the full set before it can merge.

**Flip back to draft before pushing a fix** — `gh pr ready --undo <n>`. A `synchronize` event
on a *ready* PR re-runs everything that PR earns; iterating in draft pays once, when the work
is actually done.

### 9. Docs Are Part of the Change, Not a Follow-Up

Decide in planning which docs a change will invalidate, and update them in the same PR. A
plan that is finished **moves** from `docs/TODO/` to `docs/implementations/` — never copies.
Both indexes are generated; never hand-edit them. Full rules in `docs/rules/docs.md`.

### 10. No Temp Files in the Project Root

Use tool-based file editing. If a scratch file is genuinely necessary it goes in `tmp/`
(gitignored). `tmp/` is for things nothing will want next week — the record of what
ran is not a temp file and does not go there. See Rule 14.

### 11. Anything That Stands Up the Stack Stays in Sync

If two files describe the same environment — a dev compose file and a CI one, two workflows
that both boot the stack, a host script that mirrors a CI action — **a drift check owns that
pair**, and intended divergences are recorded in an allowlist with a written reason.

Do not hand-copy setup between them. Enrollment in the drift check is **automatic** (anything
matching the pattern is checked); it is deliberately not a registry, because forgetting to
update a registry is the same bug the check exists to catch.

**An allowlist entry expires, and the check says so.** Every allowlist here is re-read against
the thing it exempts on every run: an entry whose target was fixed has outlived its reason, and
one whose target left the tree is worse — the name can come back for something else and arrive
pre-exempted, which is an exemption nobody made. When a check reports a stale entry, **delete
it**; do not rewrite the reason to keep it alive. Every allowlist in this repository is read by
`scripts/allowlist.py`, which is also where that rule is written down.

### 12. Found an Unrelated Bug? Capture It — Don't Widen Your Scope

A bug you hit that is **not** what you were asked to work on goes to the capture command, not
into your current change and not into a sentence the user will lose when the session ends:

```bash
./dev bug "<one-line summary>" \
    --finding "<path:line + what is wrong>" \
    --reproduce "<exact command; observed vs expected>" \
    --scope "<what is in, what is explicitly out>" \
    --acceptance "<assertions; the command that must pass>"
```

All four sections are required — a capture missing any of them is refused, because a capture
nobody can act on is a note, not a task. Mention what you captured in your response so the
user can kill it if they disagree.

### 13. One Voice, Two Streams

Nothing prints a status symbol or picks a stream by hand. Every emission goes
through `scripts/output.py`: `ok` / `fail` / `warn` / `skip` / `step` to **stderr**,
`line` / `emit` to **stdout**.

The split is what makes `--json` free — the payload has the stream to itself, so
a machine-readable flag is one extra emit rather than a second code path. Every
`scripts/check_*.py` supports `--json` and answers on every path, including the
ones that pass. `dev check output` enrols every file under `cli/` and
`scripts/` by pattern; exceptions go in `scripts/output_allowlist.yaml` with a
reason, and are dropped when they stop exempting anything (see Rule 11). Full
rules in `docs/rules/output.md`.

### 14. Agent State Goes Through the Resolver

Transcripts, ledgers, per-job memory and the payloads agent stages read live under
`state_dir()`, never in this checkout. A record that lives in a working tree is one
`git clean -fdx` from gone, and is invisible to every other worktree of this repo.

Where that resolves to is `scripts/paths.py`'s answer and is deliberately not written
here: a path in this file is a second definition, and this rule is the one forbidding
those. Run `python -c "from scripts.paths import state_root; print(state_root())"` —
`state_root()` rather than `state_dir()` because it reports **which** of the override
and the default answered, and a path alone cannot. When a run writes somewhere
unexpected that is usually the whole question, and a bare path leaves you to guess it.

Reach it with `state_dir()` from `scripts/paths.py`. **Never a literal path, and never
a second definition of one.** The second is the one that looks fine in review: split
the resolver and a test can point the write at a scratch file while the read still
finds the live one — it passes, and proves nothing. `tests/test_state_paths.py` holds
this line; run it rather than trusting the rule.

`state_dir()` being a function does not help a caller that freezes it: a module-level
`LEDGER = state_dir(...)` is evaluated at import, so a fixture setting the environment
runs too late and the suite writes to the live record with every test green. Resolve at
the point of use, or set the variable at `conftest.py` import time.

---

## Documentation Reference

Load on-demand only. Full mapping in `.github/DOCS_INDEX.md`.

| Topic                      | Doc                              |
| -------------------------- | -------------------------------- |
| Architecture / design      | `docs/ARCHITECTURE.md`           |
| Dev setup / CI / testing   | `docs/DEVELOPMENT.md`            |
| CLI commands               | `docs/CLI.md`                    |
| Unfinished work (the tank) | `docs/TODO/README.md`            |
| Completed work (archive)   | `docs/implementations/README.md` |

<!-- SCAFFOLD: add a row per doc as it is written. `dev check docs` fails on a
     doc registered in neither this table nor .github/DOCS_INDEX.md — an
     unregistered doc is one no agent will load, which is the same, from the
     agent's point of view, as a doc that does not exist. -->

---

## Commit Types

`feat` / `fix` / `perf` / `docs` / `refactor` / `chore` / `ci` / `test` / `build`

> `docs:` for `docs/**` changes only — never `feat:`. These subjects are the only
> changelog this repository has.
