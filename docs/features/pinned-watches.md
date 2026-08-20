---
slug: pinned-watches
title: Pinned watches — an external command, live, held on screen
status: draft
created: 2026-08-19
updated: 2026-08-19
agent_value: 2
key_files: []
---

# Pinned watches — an external command, live, held on screen

## Why

`jam pr list` prints the one table about open PRs that GitHub cannot show. It answers a question
you ask repeatedly while working — *is anything ready, is anything blocked* — and answering it
means leaving what you are doing, running it, reading it, and coming back. Ten minutes later it
is stale and you do it again.

The rail already solves the one-line version of this: a `check` reduced to a glyph and an age.
That is the right shape for *is anything wrong*, and the wrong shape for a table. A verdict
compresses to a glyph; a list of pull requests does not.

**jam cannot fix this for itself.** A CLI that printed and then held the terminal open is no
longer a CLI — it cannot be piped, scheduled, or composed, and every sibling would need its own
copy of the loop. This is the case CLAUDE.md's rule against wrapping external CLIs explicitly
allows: *"only reach for an external tool where `tb` is doing something that tool cannot
express."* A live-updating pinned pane is something `jam` cannot express about itself, and it
generalises — `bbrain fleet`, `gh run list`, anything whose answer changes while you work.

Two facts found while scoping this, both load-bearing:

- **`jam` only runs from inside its own repo.** It is symlinked onto PATH at `/usr/local/bin/jam`,
  so `which jam` succeeds, but its wrapper resolves `.venv` against the *cwd* rather than against
  the resolved symlink, and from anywhere else it exits with `missing required Python
  dependencies`. That is jam.sense's bug to fix, not tackle-box's — but it means **a watched
  external command needs a `cwd:` or it fails on its first tick.** (CLAUDE.md also states that
  `jam` is *not* on PATH. It is. `bbrain` is not.)
- **`jam pr list` calls GitHub.** A few-second poll would burn rate limit for no benefit. Short
  intervals must be awkward for these, not convenient.

## Shape

**One mechanism, two forms.** `watches/*.yaml` already declares a condition, an interval and a
host scope. It gains a second form:

```yaml
# watches/jam-prs.yaml
argv:  [jam, pr, list]          # a list, never a string — nothing is shell-parsed
cwd:   ~/src/jam.sense  # required for argv watches; validated at load
every: 60s
```

The existing `command:` form (a tb `check` or `info`) is unchanged. A file declares one or the
other, never both.

**`watch` and `unwatch` are view verbs, and that is what makes this safe.** They are handled by
the surface before dispatch, and they start nothing that was not already declared in a file
under version control. The surface gains no ability to execute anything — it gains the ability
to decide *where a declared watch renders*: as a rail line, or as a pinned pane. Deciding what
to render is the one thing a surface is for.

That is the whole reason this is declaration-first rather than `watch 60s jam pr list` typed at
the prompt. The typed form is better ergonomics and a second write door in everything but name:
it would hand the surface arbitrary argv, and `tb mcp serve` inherits whatever the surface can
do. A file reviewed once in git costs one edit and keeps the property.

**Execution lives in `cli/watch.py`, never in `cli/tui/`.** The surface calls one function and
gets a result back. `tests/test_taxonomy.py` currently bans the surface from reaching a list of
mutating functions by name; a raw `subprocess.run` inside `cli/tui/` would pass that test while
violating everything it stands for. The banned set grows to cover process spawning.

**A pinned watch renders above the transcript**, full width, with a header naming it, its age and
its interval. The transcript shrinks to fit. Several may be pinned; they stack.

```
 TACKLEBOX
┌ jam-prs · 42s · every 60s ───────────────────────┐
│ #   TITLE                    DRAFT   READY?      │
│ 91  fix the thing            yes     no          │
│ 88  add the other            no      yes         │
└──────────────────────────────────────────────────┘
 ▸ check --list
 ● check  3 rows
```

**Does not do:**

- **No argv from the prompt.** `watch <name>` names a declared watch. If the surface could take
  argv it would be an exec verb, and MCP would inherit it.
- **No shell.** `argv` is a list and is passed as one. No `shell=True`, no string splitting, no
  globbing, no `&&`.
- **Nothing is ledgered.** The ledger records what *changed*; a read repeated two hundred times
  is not history, and writing it there would drown the thing the ledger is for. Watches remain
  reads — see [[surface-panes]] for why that restriction is also what makes them safe to run
  concurrently.
- **No writes, still.** An `argv` watch is trusted to be a read because a human wrote the file.
  tb cannot verify that, and does not pretend to — which is exactly why the file is the boundary
  and the prompt is not.
- **No persistence of what is pinned.** Pins die with the surface. Remembering them is a config
  schema, and the defaults should be shown wrong first.
- **No fixing jam's wrapper.** That is jam.sense's repo and jam.sense's bug. `cwd:` works around
  it and is independently correct for any external command.

## Phases

### Phase 1 — The `argv` form

- [ ] `argv:` + `cwd:` accepted in `watches/*.yaml`; a file declares `argv` or `command`, not both
- [ ] `cwd` expands `~`, is required for `argv` watches, and must exist at load
- [ ] `execute()` in `cli/watch.py`: no shell, a timeout, stdout and stderr captured
- [ ] A floor on `every`, so a network command cannot be polled at a few seconds
- [ ] Child gets `COLUMNS` for the pane it renders into, so its table fits
- [ ] Move the existing tb-verb execution into the same function, so the surface has one door
- [ ] Test: a string `argv` is refused; nothing is ever shell-parsed
- [ ] Test: a missing `cwd` is refused at load, naming the file
- [ ] Test: a command that hangs is killed by the timeout rather than wedging the watch
- [ ] Extend `test_taxonomy.py`: `cli/tui/` may not spawn a process

### Phase 2 — The pinned pane

- [ ] `watch <name>` / `unwatch <name>` handled as surface view verbs before dispatch
- [ ] Unknown name lists what is declared rather than failing silently
- [ ] Pinned panes stack above the transcript, which shrinks
- [ ] Header: name, age, interval — and a visibly different state when the last run failed
- [ ] Output rendered through `Text.from_ansi`, as the transcript already does
- [ ] Release with `unwatch`, and a binding to release the most recent
- [ ] Test: pinning does not put anything in the dispatch queue or the ledger
- [ ] Test: a failing watch is visibly failing rather than showing stale output as current

### Phase 3 — Live it

- [ ] `watches/jam-prs.yaml`, the case this was built for
- [ ] Confirm the table renders legibly at the pane's real width
- [ ] Completion for `watch` / `unwatch` from the declared names

## Notes

Filled in during implementation.
