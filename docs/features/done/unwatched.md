---
status: complete       # round 1 built 2026-08-30; round 2 not scheduled
created: 2026-08-30
updated: 2026-08-30
agent_value: 2
key_files: [cli/resident.py, cli/data.py, cli/read.py, cli/filefollow.py, cli/output.py, cli/chrome.py]
---

# Unwatched — what a resident command can say with no band to say it in

## Why

Three of sky.boss's commands are **resident**: they hold the terminal, redraw a frame, and end when
the operator leaves. Off a terminal there is no frame — [[follow]] degrades to verbatim lines and
[[refresh]] round 4 emits NDJSON — and both of those rulings were about *what the body is*. Neither
answered the two things the **band** was doing.

`docs/open.md` § *Where a follow ends* holds both, and they are the last unblocked items in it:

- **When does it stop?** *"Resident-by-nature has no natural end off a terminal. Today it runs until
  killed, which is right for `tail -f` and wrong for a script that wants the backfill and out.
  `--ticks` exists in the suite; nothing exposes it."*
- **How does it say late?** `--due` exists precisely so *quiet* and *dead* are different words. It
  reaches `chrome_.cursor` and lands in the band — and off a terminal the band is suppressed, so the
  one flag whose entire purpose is to break a silence is itself silent.

**Round 4 of [[refresh]] made the first one pressing rather than theoretical.** `sb data --refresh`
now produces a machine-readable stream down a pipe, and there is no way to stop it. The README
documents `| head -3`, which works and is a shell workaround standing in for a missing flag — the
consumer terminates the producer by breaking its pipe.

## Shape

**`--ticks N` on `data` and `read`, meaning N completed refreshes, then exit 0.** Valid only
alongside `--refresh`; on its own it is a usage error, because a command that runs once already
stops after one.

**`--ticks` is deliberately *not* on `follow` in round 1, and the reason is the round's main
finding.** A tick is not one thing in this codebase:

| loop | what one tick is |
|---|---|
| `resident.loop` (`data`/`read` on a terminal) | one poll turn — `keys.TICK`, **one second** |
| `resident._turn` (`follow`, both forms) | the same: one second |
| `output.resident_ndjson` (`data` down a pipe) | one **snapshot** |

So the word already means *seconds* in three places and *records* in the fourth. Shipping it as a
flag without settling that would give `sb data --refresh 30 --ticks 3` two different meanings —
three seconds on a terminal, three refreshes in a pipe — for the same command, which is the *wrong
but looks right* failure in its purest form. **The flag counts refreshes on every path**, and the
poll bound keeps the name `ticks` only inside the suite where it already lives.

A follow has no refresh to count. What a script actually wants from one is *the backfill and out*,
which is one pass rather than N of anything, and a time bound is a different feature again. Named in
Phases as round 2 rather than guessed at here.

**A lapsed `--due` says one line on stderr, once.** `chrome._late` already computes the word from
`(state, last_line_at, due, now)`; off a terminal the same function is asked and the answer is
printed rather than drawn. Once per lapse, not once per second — a line every second is the noise
that makes an operator stop reading stderr.

**stderr, and that is what disposes of the objection this inherited.** [[follow]]'s non-TTY ruling
promised *verbatim log output*, and a line that is not log output would break it — on stdout. On
stderr, stdout stays byte-identical for a consumer piping it, and the sentence lands on the channel
that already carries every other thing sky.boss says about a stream. The same split that keeps
warnings off stdout, and the same one [[refresh]] round 4 used for the same reason.

**A declared threshold is not a judgment.** The verbatim rule was chosen partly to have no opinions,
and *late* looks like one. It is not: `--due 15m` is a number the **operator** wrote, and reporting
that it has elapsed is arithmetic on their own declaration. sky.boss computing lateness nobody asked
for would be the judgment — which is why there is still no `--due` default and none is proposed.

**Does not do:**

- **No `--ticks` on `follow`** in round 1. See above; it is round 2 and it is a different question.
- **No time bound anywhere.** `--for 30s` is coherent and is not this — a wall-clock ceiling on a
  read is the shape [[open]] item 8 already ruled belongs to a supervisor.
- **No `--due` default, and no lateness sky.boss invented.** The flag stays opt-in.
- **Nothing new on stdout.** Both halves of this land on stderr or on the exit; a consumer's bytes
  are unchanged.
- **No exit-code vocabulary for "ended because ticks ran out".** It is exit 0: the command did what
  it was asked. A distinct code would be a verdict on a normal ending.

## Phases

### Round 1 — a bound you can ask for, and a lapse you can hear (2026-08-30)

- [x] `resident.loop` gains a **completed-run** bound, distinct from its one-second poll `ticks`.
- [x] `--ticks N` on `data` and `read`, refusing without `--refresh`, exit 0 when it lapses.
- [x] It means the same N on the terminal path and the NDJSON path — asserted by a test, since that
      equivalence is the whole reason the flag is safe to ship.
- [x] A file follow off a terminal prints one stderr line when `--due` lapses, and one only.
- [x] `sb follow` still refuses `--ticks`, naming round 2 rather than pretending it is unsupported.

### Round 2 — the backfill and out (not scheduled)

What a script wants from a follow is one pass over what is already there, not N of anything. That is
close to `sb data <path>` and differs in exactly two ways — the ring limit and the highlight ruleset
— so the question to answer first is whether it is a flag on `follow` at all, or whether `data`
grows the two things that are missing. Do not open this by adding `--ticks` to `follow` because the
word was already there.

## Notes

### 2026-08-30 — round 1, executed

**The finding was in the first ten minutes and it changed the design.** The plan was "expose the
`--ticks` that already exists". It exists four times and means two things: `keys.TICK` is `1.0`, so
`resident.loop` and `resident._turn` count **seconds**, while `output.resident_ndjson` counts
**snapshots**. Exposing the word as written would have shipped `sb data --refresh 30 --ticks 3` as
three seconds on a terminal and three refreshes in a pipe — one flag, one command, two answers.
`loop` gained a separate `runs` bound instead, and the flag maps to `runs` on both paths with a test
asserting the two agree. **That equivalence is the whole reason the flag is safe to ship**, so it is
tested directly rather than left as a property of the wiring.

**`--ticks` without `--refresh` is refused rather than ignored**, and the reason is this repo's
usual one: ignoring it *looks* honoured, because a single read does stop after one. A flag that
changes nothing and says nothing is the silence, arriving through an argument parser.

**The lapse line asks `chrome_.cursor`, not a private reimplementation.** `_late` was right there
and tempting; going through the same function the frame calls is what makes the piped sentence and
the drawn band structurally unable to disagree about the same file. That is the shape [[open]]
recommended from the diagnosis — *use the check that was already there for the thing it was actually
telling you* — and it cost nothing to follow.

**Two things only running it found.** Rich wraps to an 80-column default off a terminal, so the
first version broke a long path across three lines: legible nowhere, uncopyable from a log, and the
path is the one thing the sentence must carry intact. `soft_wrap=True`. And the once-per-lapse flag
has to **reset on recovery**, or a file that goes quiet, recovers, and goes quiet again reports the
first lapse and silently swallows the second — which is the bug this feature exists to prevent,
reintroduced by the fix for its noise.

**A near miss worth recording.** `cat >> tests/test_file_follow.py` created a *new* file rather than
appending to the existing `tests/test_filefollow.py` — two plausible spellings, one of them real,
and `>>` does not care. It was caught by `git status` showing an untracked file, not by the suite,
which passed: the new file had no imports and pytest collected it as zero tests. **A test file that
collects nothing passes**, which is the same shape as everything else in this doc.
