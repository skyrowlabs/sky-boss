---
status: active
created: 2026-08-20
updated: 2026-08-28
agent_value: 3
key_files:
  - cli/helpers.py
  - cli/run.py
  - cli/read.py
  - cli/data.py
  - cli/follow.py
  - cli/stream.py
  - cli/canvas/runner.py
  - cli/canvas/server.py
  - tests/test_run.py
---

# The subprocess boundary — what a command sky.boss runs inherits

## Why

**sky.boss stands between a tool and a terminal, and every round here is about what that costs.**
The first was contamination — sky.boss handing a child its own bootstrap. The three since are
absence: a child drawn narrow because it could not ask the display how wide it was (round 2),
arriving late because a pipe buffered it (round 3), and saying nothing at all because it asked
whether it had a terminal and the honest answer was no (round 4). The last is the one with no
symptom, and it is why this doc did not close after round 3.

sky.boss hands every command it spawns its own bootstrap environment. Measured, from an unrelated
directory:

```
$ cd /tmp && sb run -- python3 -c "import cli; print(cli.__file__)"
   <repo>/cli/__init__.py

$ cd /tmp && python3 -c "import cli"
   ModuleNotFoundError: No module named 'cli'
```

The second line is what should happen. The first is sky.boss putting its own package on a foreign
tool's import path, from anywhere on the machine.

The cause is not a mistake so much as an unexamined inheritance. The `sb` wrapper exports two
variables so that `python -m cli` resolves against the repo rather than against whatever directory
you happen to be standing in:

```bash
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONSAFEPATH=1
```

Both are load-bearing and neither is wrong — `CLAUDE.md` § CLI setup explains at length why
`PYTHONSAFEPATH=1` exists, and it has already prevented one silent bug. What nothing decided is
that a *child* should get them. `subprocess.run` inherits the parent environment by default, so
every `sb run`, every `sb wrap`, and every watcher refresh runs its command with sky.boss on
`PYTHONPATH`.

**This was found by manually testing the thing it masks.** `sb wrap -- jam pr list --json`
succeeded from inside this repo without `--cwd`, and it should not have: run directly, `jam` fails
there. The leak was making it work.

Following that down turned up a second thing worth recording, in a different repository. jam's
wrapper does not set `PYTHONSAFEPATH`, so `python -m cli` prepends the current directory to
`sys.path` and **any directory containing a `cli/` package shadows jam's own**:

```
jam from sky-boss (has a cli/ package):       exit=1
jam from /tmp (no cli/ package):             exit=0
jam from sky-boss, PYTHONSAFEPATH=1:          exit=0
```

The error it printed — `missing required Python dependencies` — is sky.boss's own message from
`cli/__init__.py:18`. jam was running sky.boss's CLI. That is jam.sense's bug to fix and this
document does not propose fixing it here, but it is the reason `--cwd` genuinely is needed for jam,
and it is **not** the reason `CLAUDE.local.md` currently records. That note says jam resolves
`.venv` against the cwd; it has not done so for some time — its wrapper uses `realpath
"${BASH_SOURCE[0]}"` and is cwd-independent.

The two together are the worst case: sky.boss's leak silently repairs jam's shadowing, so the argv
that works today is the argv that breaks the moment either bug is fixed.

## Shape

**A command sky.boss spawns gets the operator's environment, not sky.boss's.**

One helper in `cli/helpers.py`. It began as a scrub and has grown two narrow additions and one
declaration, in that order, each argued in its own round:

```python
BOOTSTRAP = ("PYTHONPATH", "PYTHONSAFEPATH")

def child_env(
    columns: int | None = None,          # round 2 — the display's width
    *,
    stream: bool = False,                # round 3 — PYTHONUNBUFFERED
    extra: dict[str, str] | None = None,  # round 4 — the operator's --env, applied last
) -> dict[str, str]:
    """os.environ minus the variables sb's own wrapper set, plus what a
    terminal would have given the child, plus what the operator declared."""
```

Used by everything that spawns: `run_command`, `sb run`, `sb wrap`, and the canvas runner.

**The order is the argument.** sky.boss removes only what it added to boot (round 1), adds only
what it can state truthfully because it *knows* it (rounds 2 and 3), and lets the operator overrule
all of it (round 4) — because what a tool would have printed to a terminal is a fact about the
tool, not about sky.boss.

**Why those two and nothing else.** They are exactly what `sb` exports and nothing else on the
machine sets them for this purpose. `PATH` is emphatically *not* on the list — the wrapper prepends
its venv's `bin` to it, and stripping that would be sky.boss deciding which `python3` a foreign tool
should find, which is the operator's business and not sky.boss's. Scrubbing is for variables that
exist only so sky.boss can boot.

**The canvas runner scrubs too, even though it spawns `sb` itself.** The wrapper re-establishes
both variables on the way in, so nothing is lost — and it *appends* to any inherited `PYTHONPATH`,
so without scrubbing a nested invocation accumulates the repo path twice. Scrubbing makes the
child's environment identical whether it was reached from a terminal or from a watcher.

**The test is the demonstration, not a mock.** `sb run -- python3 -c "import cli"` must fail from a
directory that is not the repo, exactly as a plain shell fails. That asserts the property an
operator would check by hand rather than the mechanism, so a future change to *how* the wrapper
bootstraps cannot quietly satisfy it.

**Does not do:**

- **Does not sanitise generally.** Not a clean-room environment, not an allowlist, no `env -i`. A
  wrapped tool needs `HOME`, `PATH`, `SSH_AUTH_SOCK`, its own `*_TOKEN`s and everything else the
  operator's shell would have given it. The two variables removed are the two sky.boss added.
- **Does not touch `PATH`.** See above.
- **Does not fix jam.** `CLAUDE.local.md` gets its note corrected, because a wrong reason recorded
  is worse than no reason, but jam.sense's wrapper is jam.sense's to change.
- **~~Does not add a `--env` flag.~~ Reversed in round 4 (2026-08-28).** The original reasoning
  stands as written — *nothing has asked to set a variable for a wrapped command; if it does, that
  is a separate round and it should be argued on its own.* Something asked, and it is argued in
  round 4 rather than by amending this line.

## Phases

### Round 1 — stop leaking the bootstrap (2026-08-20)

- [x] `BOOTSTRAP` and `child_env()` in `cli/helpers.py`.
- [x] `run_command`, `sb run`, `sb wrap` and `cli/canvas/runner.py` all use it.
- [x] A test that `sb run -- python3 -c "import cli"` fails from outside the repo, and one that
      `PATH` and ordinary variables survive.
- [x] Correct `CLAUDE.local.md`'s account of why `jam` needs `--cwd`, and add the scrub to
      `CLAUDE.md` § Conventions.

### Round 2 — the display's width (2026-08-22)

Reported by the operator: *"`sb follow -- jam report watch --follow` is not showing me the same
as when I run the command outside of sb."* True, and measurable.

**A tool lays out by asking its stdout how wide the terminal is.** Under sky.boss that stdout is a
pipe, so the tool falls back to its own default — 120 columns for the tool in question — and
truncates every longer line, in a 150-column terminal that had the room. sky.boss was silently
narrowing the thing it exists to show you.

Measured rather than argued. Running the same bounded command both ways and diffing the child's
own bytes:

```
direct, in a 150-column terminal :  74 lines, max width 150
through sb, with COLUMNS passed  :  74 lines, max width 150   ← byte-identical
through sb, without              :  74 lines, max width 120   ← every long line loses its tail
```

**So `child_env()` gains the one thing it adds rather than scrubs.** Round 1's rule was *scrub what
sky.boss added to boot and nothing else*; this is a deliberate, narrow exception, and it earns the
exception by making sky.boss **transparent**: the child draws for the display it is actually being
drawn on, which is what it would have done had sky.boss not been in the way.

**Only where the output is displayed as text.** `run`, `read` and `follow` pass the terminal's
width; **`data` never does.** Its bytes are parsed, a width is an instruction to lay out for a
display, and a tool that wrapped its JSON to fit would hand back a corrupted document rather
than a narrower one. The canvas passes nothing either — a browser window's character width is
not a number the server knows.

**And only when there is a display.** Piped output has no width worth claiming: the consumer may be
a file, and a tool wrapping to a number sky.boss invented is worse than one using its own default.

**`LINES` is deliberately not set.** A tool that thinks it knows the height may decide to
paginate, and a pager inside a held-open stream is a hang.

**Does not do:**

- **No pty.** The remaining difference between the two runs is *colour*: a tool that colours its own
  output does so only when stdout is a terminal, and neither `FORCE_COLOR` nor `CLICOLOR_FORCE`
  moved the one measured here. Giving the child a pty would restore it and is refused by [[follow]]
  — "line streams, not a pty" — and sky.boss now paints its own semantic colour through
  [[highlight]], which would fight it. Recorded as measured, not assumed.
- **No width for `data`, ever.** See above.
- **No terminal *type*.** `TERM` is the operator's and is passed through untouched, as every other
  variable is.

- [x] **`child_env(columns)`**, set only when a width was given.
- [x] **The display paths pass it** — `follow` from its console, `run` and `read` from theirs,
      and only when sb's own stdout is a terminal.
- [x] **Tests**: a child sees the width, a child without a display sees none of sky.boss's, the
      operator's own `COLUMNS` still passes through, `LINES` is never set, and `data` never
      passes a width at all.

### Round 3 — a stream stuck in the child's buffer (2026-08-22)

Found while answering *"is this command showing the bottom of the file?"* — it was, but the
investigation turned up a defect that had nothing to do with the question and everything to do
with what `sb follow` is for.

**A pipe makes a child's stdout block-buffered.** A tool printing a line a minute writes into an
8 KB buffer; nothing reaches sky.boss until it fills or the process exits. Measured with a child
printing every 0.8s:

```
plain pipe          first line at t+5.1s   — all six at once, at exit
PYTHONUNBUFFERED=1  first line at t+0.3s
stdbuf -oL          first line at t+5.1s   — no help: Python's text layer is not libc stdio
```

For a command that is *expected not to exit*, "you see it when it dies" is the feature inverted.
The same tool run in a terminal is line-buffered and shows every line as it lands, which is
exactly the difference the operator kept noticing.

**So a streaming spawn sets `PYTHONUNBUFFERED=1`,** by the same reasoning round 2 used for
`COLUMNS`: sky.boss is standing between a tool and a terminal, and its job is to be transparent
about what the terminal would have given it. It is set only on the streaming paths — a buffered run
collects everything at exit anyway, so there is nothing to un-delay.

**It is Python-specific, and that is stated rather than dressed up.** The general fix is a pty,
which [[follow]] refuses by name; `stdbuf -oL` was tried and does nothing for a Python child.
What this covers is every tool in this family — sky.boss's siblings are all Python — and it costs a
non-Python child nothing. A non-Python tool that block-buffers its own output is still capable
of arriving late, and the honest answer there is that the tool should flush.

**Does not do:**

- **No pty**, still. See round 2 and [[follow]].
- **No argv wrapping.** Prefixing `stdbuf -oL` would make `sb run` something other than what the
  operator typed, and [[follow]]'s rule is argv only, unchanged. It also does not work for the
  case at hand.

- [x] **`child_env(columns, stream=True)`** sets it; the streaming spawns pass it.
- [x] **Tested against the mechanism**, not a stopwatch: a child that has printed and not exited
      has its line already, which is precisely what was false before.

### Round 4 — the tty verdict (2026-08-28)

Reported by the operator, watching a two-hour `jam report agent-task` accrue on the canvas:
*"the log that is written is ahead of ours."* It was, it was not going to catch up, and nothing
was late or dropped.

**A tool that decides what to print by asking whether it has a terminal says less into a pipe.**
jam's reporting funnel, `cli/report.py:91` in that repo:

```python
def _echo_to_stdout() -> bool:
    ...
    return sys.stdout.isatty()
```

Under sky.boss that stdout is a pipe, so the funnel wrote every module line to its own transcript
and echoed **none** of them. Measured, with jam's stdout faked as a pipe:

```
JAM_TRANSCRIPT_STDOUT unset  ->  echoes to stdout: False   (what the window got)
JAM_TRANSCRIPT_STDOUT=1      ->  echoes to stdout: True
```

Fourteen queued issues, the handoff line, the per-issue outcomes: all of it in a file, none of it
in the window. What reached the window was the four lines the funnel says on its own behalf.

**This is a third failure mode, not a variant of the first two.** Round 2 was output drawn *narrow*;
round 3 was output arriving *late*. Both are the child saying the same thing differently. This one
is the child **not saying it at all** — and absent output looks exactly like a job that is quietly
working, which is the "wrong but looks right" failure the canvas keeps finding new spellings of.
There is no symptom to notice: the window is alive, the chrome is honest, the exit code will be
correct, and the content is simply missing.

**And it is where transparency runs out.** Rounds 2 and 3 both turned on sky.boss knowing something
the child could not see for itself — sky.boss *has* a terminal, so it knows the width; a pipe *is*
block-buffered, so it knows the delay. Neither was a guess. sky.boss does not and cannot know what
a given tool would have printed to a terminal. Only the tool's author does, and they wrote it down
as an environment variable. So the answer is not a fourth variable sky.boss sets on its own
initiative, and not a pty. **It is a declaration, by the operator, in the argv.**

**`--env NAME=VALUE`, repeatable, on every command that spawns** — `run`, `read`, `follow`, `data`.

```
sb run --cwd ~/src/jam.sense --env JAM_TRANSCRIPT_STDOUT=1 -- jam report agent-task --limit 2
```

`child_env()` gains an `extra` mapping, applied last, over everything — including `COLUMNS` and
`PYTHONUNBUFFERED`. The operator's declaration is the most specific statement about this child that
exists, so it wins over sky.boss's two automatic ones; a tool whose author says
`PYTHONUNBUFFERED` breaks it must be able to say so.

**A saved tool needs no new key.** A tool is a name plus a *sky.boss argv*, and `cli/tools.py`
re-invokes the real command with `tool.argv[1:]`, so `--env` rides in exactly as `--cwd` does. An
`env` field in `tools.toml` would be a second way to say the same thing, negotiating with the flag
the way `refresh` and `highlight` have to — and those two negotiate because they are *inherited*
per-invocation defaults. This is not.

**Why not `env NAME=VALUE` in the argv, which works today with no code.** Because it makes sky.boss
describe the wrong program. Measured against the running bench:

```
sb run -- env JAM_TRANSCRIPT_STDOUT=1 jam report agent-task
  ✓ env resolves   /usr/bin/env        ← preflight now vouches for /usr/bin/env
```

`resolve_run`'s `foreign[0]` becomes `env`, so the window title, the `runs` column in `sb tools`
and the bench's binary check all name the wrapper instead of the tool. A workaround that costs the
surface its ability to say what it is running is not the answer, however few characters it is.

**Nothing is warned about.** Rounds 2 and 3 set variables silently, and this one is *in the argv* —
visible in the window title, in `sb tools`, in the saved block. A banner saying "this child's
environment was modified" would announce what is already on the screen.

**Does not do:**

- **No pty.** Fourth refusal, and the reasons have only accumulated: [[follow]] refuses it by name,
  round 2 refused it for colour, round 3 for buffering. A pty would fix this whole class at once
  and bring back everything the earlier rounds refused it for — the tool's own colour fighting
  [[highlight]], a pager inside a held-open stream, and control sequences the ring and the browser
  renderer would both have to interpret.
- **Does not know about any tool.** No table of known programs and the variables they want. That
  would put jam's name in sky.boss's source, and which projects exist is `projects.toml`'s
  business — operator-owned, outside the repo, and never written by sky.boss ([[roll-call]]).
- **Does not infer.** sky.boss will not notice that a run printed suspiciously little and offer to
  re-run it verbosely. Same rule as [[text-reads]]: the operator asserts, sky.boss does not guess.
- **Not a credential path.** A `--env` value is written verbatim into `tools.toml`, read back by
  `sb tools`, and drawn in a window title. It is for *behaviour* variables. Anything secret is
  already inherited from the operator's own environment, which is round 1's whole design and the
  reason `sb secrets` is rejected in `CLAUDE.md` § Scope. The help text says so; nothing scans a
  value to guess whether it is one.
- **Does not unset.** `--env NAME=` sets a variable to empty, which is a different thing from
  removing it. Nothing has asked to remove one, and `BOOTSTRAP` remains the only removal sky.boss
  performs.
- **Does not read `.env`.** A file changes what a command does without appearing in what the
  operator typed.

- [ ] **`child_env(columns, *, stream, extra)`** — `extra` applied last, over sky.boss's own two.
      A test that it wins over both.
- [ ] **`--env NAME=VALUE` on `run`, `read`, `follow` and `data`**, repeatable. A value with no
      `=` is a usage error naming the offending token, not a silently ignored flag.
- [ ] **The canvas accounts for it.** `Job` carries `env` and `resolve_run` accepts `--env`;
      likewise `resolve_follow`. Without this an accruing window silently falls back to
      `snapshotRun` — a flag is opted **in** to accrual, never out of it ([[follow]] round 4), so
      an unaccounted flag is a long act back under the watcher's ceiling.
- [ ] **The bench composes it** — a repeatable `--env` row beside `--cwd` in the draft, and
      preflight keeps resolving the *tool*, which is the check the `env` workaround loses.
- [ ] **Docs**: `CLAUDE.md` § Conventions gains the sentence that a tool gating output on
      `isatty()` is the operator's to declare, and the README example.

## Notes

### Round 1 — found by testing something else (2026-08-20)

The fix is six lines and was never in doubt. What is worth recording is how it was found, because
no test would have caught it and no amount of reading would either.

The task was a manual check of `sb wrap -- jam pr list --json` — the feature's own driving case,
after it had already shipped and passed 191 tests. The first command run was the *failure* case,
`wrap` with no `--cwd`, expected to fail because running `jam` there fails. It succeeded. Two
levels down from that surprise were two separate bugs in two different repositories, each of which
had been hiding the other:

- sky.boss handed every subprocess its own `PYTHONPATH` and `PYTHONSAFEPATH`.
- jam's wrapper does not set `PYTHONSAFEPATH`, so any directory holding a `cli/` package shadows
  jam's own — and sky.boss's leak was supplying the missing variable.

Neither is visible from inside its own repository. sky.boss's suite passes with the leak, because
every test that spawns anything spawns something that does not care. jam works everywhere its author
runs it. **They only appear where the two meet**, which is a place only a person standing in one
repo running the other's binary ever stands.

The scar tissue in `CLAUDE.md` § CLI setup is about exactly this class — a relative `PATH` entry
re-resolving against a child's cwd, 112 tests failing from a tmp dir, systemd units silently written
with the wrong `WorkingDirectory`. It records the lesson as a rule about *sky.boss's own* bootstrap.
What it had not extended is the other direction: sky.boss's bootstrap is also something sky.boss
*exports*, and a variable that is load-bearing for the parent is contamination for the child.

**The wrong reason was recorded, which is worse than none.** `CLAUDE.local.md` said `jam` needs
`--cwd` because its wrapper resolves `.venv` against the cwd. That was presumably true once; jam
now resolves it through `realpath` and is cwd-independent. A note like that is not merely stale —
it actively stops the next person looking, because the question already appears answered. Corrected
in place, with the measurements.

**The argv did not change, and that is the point.** `--cwd ~/src/jam.sense` was already
what the tool declared, and it is still right — it just now works for the reason the operator
thought it did rather than by accident of an inherited variable. The state before this round was
the dangerous one: the argv that worked was the argv that would break the moment *either* bug was
fixed, in either repository, by anyone.

**What is not fixed.** jam's wrapper still lacks `PYTHONSAFEPATH`, so `jam` still fails when run
from any directory containing a `cli/` package. That is jam.sense's to change, and `sb wrap`
without `--cwd` now fails honestly there instead of quietly working.

### 2026-08-21 — the words moved; the history stays (supersession)

`wrap` was renamed `data` and the `every` field renamed `refresh` — hard renames, no aliases;
see [[refresh]]. This doc predates the rename and its prose says `wrap` because it *was*
`wrap`; that is history being accurate, and nothing above has been scrubbed.

### Round 2 — executed (2026-08-22)

**The bug report was precise and the first measurement was not.** Comparing the two runs by maximum
line width said "301 versus 150", which looked like sky.boss producing wider output — until the
301-character lines turned out to be **sky.boss's own chrome band**, joined across frames by the
bare carriage returns an in-place redraw uses. The comparison harness was measuring itself.
Splitting on `\r` as well as `\n`, and excluding sky.boss's chrome, made the real difference
visible: the child truncating at its own default.

**What settled it was diffing the child's bytes rather than the rendered screen.** Running the
same bounded command under a pty and under `ChildStream`, with and without the width, gives
`A == B` exactly — a one-line assertion that the fix makes sky.boss transparent, and one that no
amount of looking at two screenshots could have produced.

**The colour difference is real, measured, and deliberately left alone.** The tool emits cyan,
green and yellow when its stdout is a terminal and nothing at all when it is a pipe; neither
`FORCE_COLOR` nor `CLICOLOR_FORCE` changes that. Only a pty would, which [[follow]] refuses by
name — and sky.boss now has its own semantic tinting through [[highlight]], so restoring the tool's
would put two colour schemes on one line. Worth stating plainly rather than leaving as a
surprise: **under sky.boss, the colours you see are sky.boss's, and the layout is the tool's.**

**One more thing the tests had to be talked out of claiming.** The first version asserted that a
child sees *no* `COLUMNS` when sky.boss passes none — and it failed, because the process running the
suite exports one. That is not a bug, it is round 1's rule working: the environment is the
operator's, and sky.boss scrubs only what it added to boot. The contract is narrower than the first
assertion and is now written as it actually is — **sky.boss adds no width of its own, and overrides
an inherited one only when it has a display to describe.**

### Round 3 — executed (2026-08-22)

**The reported symptom and the found defect were different problems, and separating them was
the work.** The operator asked whether `sb follow` was showing the bottom of the stream. It was
— the final frame is identical to the same command's own final frame, line for line — and the
stale-looking rows came from the followed tool's own replay window. But reproducing that
question required watching a child emit lines slowly, and *that* is where the buffering showed
up: not the thing asked about, and a real defect in the one command whose whole purpose is to
show output as it happens.

**Worth keeping as a habit:** the answer to "is it showing the latest?" was obtained by diffing
sky.boss's final painted frame against the tool's own, rather than by reasoning about the ring. The
ring was never the suspect it looked like — `--lines 2000` had already been tried and changed
nothing, which was the clue that the missing lines were not missing from sky.boss at all.

### Round 4 — drafted (2026-08-28)

**The report was "the window is behind" and nothing was behind.** The first three suspects were all
wrong and all plausible, which is worth recording because each is a real defect this repo has
already had: the ring dropping lines (round 3's investigation), block buffering (round 3's actual
find), and the accrual frame loop shipping late. Ruled out by measurement rather than by reading —
`PYTHONUNBUFFERED=1` was verified present in the *live* process's `/proc/<pid>/environ`, and
`follower_frames` ships incrementally off `child.fresh(follower.shipped)`.

What found it was reading the foreign tool's source instead of sky.boss's. jam prints
`— handing to 'claude' (no output until it finishes; ceiling N min)…`, which explained the silence
so well that it nearly ended the investigation at the right answer to the wrong question: the
silence was genuine, *and* the four lines around it were a tenth of what the log held.

**The measurement that settled it is a table of one function's return value**, jam's
`_echo_to_stdout()` with `sys.stdout` faked as a pipe. Two rows, no timing, no subprocess. Cheaper
than any of the three transport experiments that preceded it and the only one that could have
distinguished "sky.boss lost the lines" from "the tool never sent them" — the distinction the whole
round turns on.

**The workaround was measured too, and that is what killed it as the answer.** `sb run -- env
VAR=1 jam …` runs correctly, and the bench then reports `✓ env resolves /usr/bin/env`. A surface
whose checks vouch for `/usr/bin/env` while the operator reads them as vouching for `jam` is worse
than one that offers no check — the same argument that made a palette which cannot drift the first
rule of the canvas. Recorded against the day someone reaches for the two-word fix.

**Round 1's `--env` refusal is reversed, not deleted.** It ended *"if it does, that is a separate
round and it should be argued on its own"* — which is exactly what happened, four rounds and eight
days later. A refusal that names the condition for its own reversal is the most useful kind, and
striking it through beats editing it into agreement.
