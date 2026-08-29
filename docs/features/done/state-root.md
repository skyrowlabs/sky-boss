---
status: complete       # draft | active | complete — the directory follows this
created: 2026-08-29
updated: 2026-08-29
agent_value: 3         # a new seam, a new declaration, and a new address form
key_files: [cli/agentstate.py, cli/rollcall.py, cli/data.py, cli/follow.py,
            cli/canvas/server.py, tests/test_agentstate.py]
---

# The agent-state root

## Why

The sibling repos' automation writes its transcripts, ledgers and per-job memory to a state root
outside every checkout — one directory per project, named with the project's **slug**, holding six
class directories (`log/`, `ledger/`, `input/`, `memory/`, `inflight/`, `product/`). The contract is
`skyrow-workspace/strategy/seams/agent-state.md`, and the layout was designed so a path is derivable
from a project sky.boss already knows: the directory under the root is the same key `projects.toml`
uses for the project.

**sky.boss cannot derive it, because it knows the slug and not the root.** The writers each carry a
default — `Path.home() / "skyrow.labs" / "sl-agent-logs"` — and sky.boss must not copy it. A writer
may hardcode that path because it lives there; sky.boss ships to machines with no such directory,
and a workspace layout baked into a published tool is the same class of leak as a host name in a
tracked file.

So the richest artifact in the tree is addressed by typing it out in full:

```bash
sb data --from jsonl ~/skyrow.labs/sl-agent-logs/jam-sense/ledger/runs.jsonl
sb follow            ~/skyrow.labs/sl-agent-logs/jam-sense/log/cron.log
```

Both name a machine in a command the operator will save, and the only part that varies between
projects is one path component sky.boss already has in `projects.toml`.

## Shape

Three pieces: a declaration, a resolution, and an address form.

### The declaration — one root, at the top of `projects.toml`

```toml
state_root = "~/skyrow.labs/sl-agent-logs"

[project.jam-sense]
argv = ["jam", "report", "status", "--json"]
```

**One root, not a key per project.** Repeating it in every block rebuilds the hand-maintained table
the slug convention exists to remove, and a per-project override is easy to add later and hard to
take back. The project's own directory is `<root>/<the table's key>` — nothing declares a slug,
because the table key already is one.

**`~` and `$VAR` expand**, through `rollcall._expand`, which the `path` key already uses. The
operator wrote this by hand in their own editor.

### The resolution — environment first, file second, silence third

1. `SL_AGENT_LOGS` in the environment, **the same name the writers honour**, so one knob points the
   producers and the reader at the same scratch directory. That is the whole value of matching it.
2. `state_root` in `$SB_HOME/projects.toml`.
3. Neither → *nothing declared*, which degrades to no state root rather than raising. The rule an
   absent `$SB_HOME` already follows.

**The environment wins, and the case that settles it is a redirected test run.** Point
`SL_AGENT_LOGS` at a scratch directory and the producers write there; if the file won, sky.boss
would carry on reading the real root and report a ledger that nothing was writing to — mismatched,
and silently. The file is the fallback because that is the level the *surface* can reach: `sb ui`
opens a native webview, and a window started from a desktop launcher inherits no shell environment,
so an env-only knob would work in a terminal and silently not in the canvas.

**Resolved at use, never at import.** `SB_HOME` and `SB_STATE` are module constants because they
are sky.boss's own; this one is read from a file the operator edits under a pinned window, so it is
a function and the pinned window picks up the edit on its next tick. It is also the trap
`agent-state.md` names by hand, and the reason it names it: a root frozen at import is a root that
cannot be redirected by a test.

**Which source won is reported, not inferred.** Two levels with no way to see which applied is the
inconsistency this file was worried about — a long-lived `sb ui` holding what was set when it
launched while a fresh shell sees something else, both correct and neither visible.

### The address form — `<project>:<path>`

```bash
sb data --from jsonl jam-sense:ledger/runs.jsonl
sb follow            jam-sense:log/cron.log
```

Read it as scp reads it: *this path, over there*. The part before the colon is a **declared project
name**, and that is what makes this a lookup rather than a guess — a closed set the operator wrote,
exactly like `--from <name>` resolving against declared formats. A prefix that matches no declared
project is not a project reference, and the whole string stays the literal path it always was.

**An existing file always wins.** The literal path is tried first, so a directory genuinely named
`jam-sense:log` resolves to itself. Same precedence `is_file_form` already applies when a bare word
is both an executable and a file: the concrete thing wins, and the operator writes `./name` to be
explicit.

Three ways it fails, each naming the fix:

- **No root declared** → *"no state root; set `SL_AGENT_LOGS` or `state_root` in projects.toml"*.
- **Root declared, this project has no directory, others do** → *"no state directory `jam`; the root
  holds `jam-sense`, `breeze-brain`"*. This is the whole reason to list rather than just report
  absence: an operator who wrote `[project.jam]` for brevity otherwise gets *nothing to follow*,
  the exact sentence a project with no logs yet gets.
- **Root declared and absent, or empty** → say the root is not there. Naming it is the difference
  between a wrong path and a missing machine.

**Derivation is safe here in a way it was not for the writers**, and the seam's own refusal is worth
reading before copying it:

> `STATE_SLUG` is written in rather than taken from the directory name … deriving the slug from the
> checkout would hand each of them a private state root.

Every writer *declares* its slug because derivation was judged unsafe. A writer runs inside one tree
and cannot see the others, so it has no way to check a guess. **A reader sees the whole root**, so
it can derive *and verify* — an asymmetry that means the conclusion does not transfer.

**Does not do:**

- **No per-project root override.** The escape hatch the diagnostic points at, not the mechanism.
  An optional field that is usually redundant gets omitted, so it cannot be the primary answer.
- **Does not write `projects.toml`.** The file is operator-owned and outside every repo. Adding the
  key is a request to the operator; this only reads it.
- **Knows no class names.** `log/`, `ledger/` and the rest are the seam's vocabulary, not sky.boss's.
  The address form takes whatever follows the colon and joins it — a reader that knew `ledger` would
  be reading one workspace's convention rather than a shape.
- **Not a search path.** One root. A list would need precedence rules, and two roots holding the
  same slug is a question nobody has asked.
- **Not a status command.** *How old is each project's newest artifact* is a real question and a
  different feature; this is addressing, not reporting.

## Phases

### Round 1 — the declaration and the resolution (2026-08-29)

- [x] `state_root` accepted as a top-level key in `projects.toml`, with unknown top-level keys
      still named the way unknown tables are.
- [x] `cli/agentstate.py`: `root()` returning the path and which source it came from; resolved at
      use, never at import.
- [x] `directory(slug)` with the three-state diagnostic, including the sibling listing.

### Round 2 — the address form (2026-08-29)

- [x] `<project>:<path>` resolved in `sb data` and `sb follow`, literal path first.
- [x] `is_file_form` in both commands recognises it, so a project reference with no slash is not
      mistaken for a command.
- [x] Every failure names the fix; none of them raise.

## Notes

### 2026-08-29 — round 1, and a suite that was reading the operator's machine

Two things the tests found rather than the design.

**The suite did not isolate `SL_AGENT_LOGS`.** `conftest.py` redirects `SB_STATE` and `SB_HOME` at
import, with a paragraph each explaining why, and this third root had no equivalent — so a run in a
shell exporting it would have resolved the operator's real project directories, and a run without
one would not. Cleared rather than redirected, because *no root declared* is a state these tests
have to exercise; each test that wants one sets it.

**`sb_home` is one directory shared by the whole run.** That is fine for reading an empty home and
wrong the moment a test *writes* a `projects.toml` into it — two of these do, and they polluted the
tests asserting no root is declared. They pass a per-test home instead, which is free because every
function here already takes one. No other test in the suite writes there, so there was nothing
pre-existing to fix.

### 2026-08-29 — round 2, and the failure that kept reappearing in new shapes

The address form was built and then found *three* separate ways to reproduce the exact failure the
Why section is about — a wrong reference reported as something other than a wrong reference. Each
was found by running it, and none was visible in the diff.

1. **`jam:ledger/runs.jsonl` → `no such file: jam:ledger/runs.jsonl`.** An undeclared prefix is not
   a reference, so the string stays a literal path — correct, and it produces a path error naming a
   file that could never exist. `unresolved_hint` adds the reason the other reading did not happen,
   worded as an addition because a genuine path containing a colon is still what was typed.
2. **`jam:runs.jsonl` → `no such command`.** With no separator it never reaches the file reader at
   all, so fixing only the file path would have fixed the slash form and missed this one. The hint
   is on both errors.
3. **`sb follow jam:log/cron.log` → silence, forever.** Waiting on a file that does not exist yet is
   the file form's normal case and the whole reason `sb follow new.log` is legal. For a typo it
   means waiting for a file that will never exist. Warned on stderr rather than refused, because the
   rare genuine colon-named file must still be followable.

**`SB_HOME` is frozen at import, and that shaped the signatures.** `_split`, `is_project_form`,
`resolve` and `unresolved_hint` all take a `home` for the same reason `root` and `directory` do: a
caller that must reach a different home has no other way in, and a test is exactly that caller.
Threading it was not tidiness — the first four address tests failed against the operator's isolated
home rather than the one they had written.

**The canvas resolves before its cwd join**, and the order is load-bearing: a project reference
resolves to an absolute path, where joining first would make `jam-sense:log/cron.log` a relative
path under the window's directory. The canvas is also the reason the file level exists at all — a
webview started from a desktop launcher inherits no shell environment, so an env-only knob would
work in a terminal and silently not in the surface.
