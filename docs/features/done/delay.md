---
status: complete
created: 2026-08-22
updated: 2026-08-23
agent_value: 3
key_files:
  - cli/run.py
  - tests/conftest.py
  - cli/helpers.py
  - cli/chrome.py
  - cli/resident.py
  - tests/test_run.py
---

# Once, later — a delayed run you can watch

## Why

From the ideas list: *"future runs (non crontab or systemd), `sb run --delay=[seconds] [cmd]`."*

Taken literally the flag is already two things you have. If it survives your terminal it is a
worse `systemd-run --on-active=300`. If it does not, it is `sleep 300 && cmd`. Neither is worth
a flag.

**What neither gives you is a pending action you can see.** `sleep` shows nothing and dies with
the terminal without saying so; `systemd-run` survives but is invisible unless you go asking
`systemctl`, and it wants a unit for something you are doing once. The thing missing from both
is the ordinary case: *I want this to run in five minutes, I want to watch it happen, and I want
to change my mind.*

That is a thing sky.boss is unusually well placed to draw, because it already draws it. The chrome
contract computes a countdown for every refreshing window (`chrome.countdown()`); the resident
loop already redraws once a second and already leaves on `q`. A delayed run is those two parts
pointed at a command that has not started yet.

## Shape

    sb run --delay 5m -- ./deploy.sh

A resident countdown, then the run, then exactly what `sb run` prints today, then exit.

**Once-later is still once.** This looks like it violates the sharpest rule in the project and
does not, so it is stated here rather than discovered in review. [[refresh]] rules that **`run`
never takes `--refresh`**, and calls it rejected rather than deferred: *re-running a write on a
timer is a scheduler nobody asked for.* That rule is about **cadence** — about a write happening
again, unattended, forever. A delay is not a cadence. The command still runs **once, ever**; the
only thing that moved is when. `--delay` and `--refresh` are mutually exclusive and the error
says why.

**It never survives the surface.** `q`, `Esc` or Ctrl-C during the countdown cancels, and
nothing ran. Closing the terminal cancels. There is no queue, no state file, no unit written, no
process left behind — which is exactly what keeps this a *view of a pending action* rather than
a scheduler. The moment it survives the window it is systemd's job, and `--help` says so.

**The countdown is the honest rendering of waiting**, and it is the same one a pinned window
already wears. `Chrome` has an `act` shape and a `countdown()`; this is a third caller for parts
that exist, not new chrome. The band says what is pending, how long is left, and how to cancel.

**`--json` is compatible, and that is the difference from `--refresh`.** A resident *read*
refuses `--json` because it would emit an endless stream of envelopes onto a pipe that expects
one. A delayed run emits **exactly one envelope**, at the end, as it always did — so the two
compose, the countdown draws on stderr where every band already goes, and stdout stays a single
envelope. A machine that wants to wait five minutes for one result is a reasonable thing to be.

**Only `run` takes it, in this round.** The value is a *cancellable pending write*; a read is
cheap and you can simply run it when you want it. If a delayed read earns itself later it can
have a round.

**Does not do:**

- **No survival, no detach, no `nohup`, no unit generation.** A command that must outlive the
  surface belongs to systemd, and sky.boss will not generate the unit for you — the same line
  [[follow]] draws for streams.
- **No repeat.** `--delay` is not `--refresh` and there is no `--every`. Once, later, once.
- **No absolute times.** `--delay 5m`, not `--at 19:00`. Absolute is a real want and a separate
  argument — a wall clock brings timezones, DST and "that time was twenty minutes ago" with it.
- **No queue and no persistence.** One delayed command per invocation, held in one process.
- **No canvas window**, this round. A delayed *write* in a surface where windows are re-run on
  cadences needs its own think, and the terminal is where the want came from.

## Phases

### Round 1 — the countdown and the flag (2026-08-22)

- [x] **A duration is a shared parser.** `5m`, `90s`, `2h` → seconds, in `cli/helpers.py`.
      [[file-follow]] round 2 needs the identical spelling for `--due`; whichever lands first
      writes it, and the second one uses it rather than agreeing with it by hand.
- [x] **The pending shape in chrome.** The `act` shape carries what is pending and when it fires;
      `countdown()` already answers the rest. Pure, over an injected clock — proving a
      five-minute delay must not cost five minutes of suite.
- [x] **`--delay` on `run`**, drawing through `resident.hold` so `q`, `Esc` and Ctrl-C cancel by
      the same keys that leave every other resident view. Cancelling exits non-zero — nothing
      ran, and a script that cannot tell the difference would deploy on a keystroke.
- [x] **Refused together with `--refresh`**, with a message that names the reason rather than
      the rule. Composed with `--json`: countdown on stderr, one envelope on stdout, proven by
      the purity test that already exists.
- [x] **Help is the doc.** The runnable example, the cancel keys, and the sentence that says a
      command needing to outlive the terminal wants systemd instead.

## Notes

### Round 1 — shipped, and cancellation turned out to be the clock (2026-08-23)

The doc's hardest sentence held: a delay is not a cadence, so `run` taking one is not a reversal of
[[refresh]]. Everything else fell out of that, including `--json` composing where `--refresh` cannot.

**Cancellation needed no flag.** `hold` returns both when the operator leaves and when its tick
budget runs out, and it does not say which — the obvious fix is a sentinel threaded back out of the
frame closure. The better one is to ask the only question that matters afterwards: *did we reach the
moment*. Time was already the source of truth and a flag would have been a second one.

**`transient` was missing and its absence was a lie.** `hold` hardcoded `transient=False`, correct
for a follow — leaving one should leave the tail of the log you were watching. A countdown is the
opposite: its final frame reads `nothing has run yet` and the output of the thing that just ran
prints directly beneath it. One parameter, defaulted to the existing behaviour, with the reason for
both settings written at the site.

**A hidden `--refresh` that exists only to refuse well.** [[refresh]] already ruled `run` never
takes a cadence, and Click answered the flag with a bare *"No such option"* — which teaches nothing
to the person whose next instinct is that `--delay` is the same thing wearing a coat. The option is
hidden, so help and the catalog are unchanged, and the message now names the reason and points at
the flag that does what they wanted. The existing test asserting `"No such option"` was updated
rather than deleted; the invariant it protects (absent from help) is untouched.

**A latent flake, found and mostly fixed.** One suite run failed where the previous had passed, on
an assertion matching a phrase in a rich-click error. The cause is that rich-click wraps into a box:
a phrase can be broken by a newline *and* by the border, so asserting on raw output is a test about
the terminal rather than about the message. Measured — the same tests pass at 80 and fail at 40, 60
and 200. A `said` fixture in `conftest.py` strips the drawing and normalises the whitespace, and
seven tests across four files now read through it. Two remain, both in `test_output.py` and both
genuinely *about* width fitting; they should declare a width rather than borrow one, which is
[[table-views]]' business and is in `ideas.md`.

Worth stating plainly: the suite was width-dependent before this round and nothing had noticed,
because every run happened to be 80 columns.

### Round 1 — drafted, awaiting the word (2026-08-22)

Drafted from the ideas list. The idea arrived as a flag and the useful half was underneath it:
the flag alone is `sleep`, and what is missing from `sleep` and from `systemd-run` alike is
*visibility of a pending action you can still cancel*.

**The rule that looked like a blocker turned out to be the design.** `run` never takes
`--refresh`, recorded as rejected-not-deferred, and the first instinct on reading `--delay` is
that it is the same thing wearing a coat. Writing out why it is not produced the sentence the
whole doc hangs on — *cadence is a write happening again forever; a delay is a write happening
once, later* — and that sentence is also what makes the `--json` behaviour fall out: one
envelope, so no conflict, where a resident read has an endless stream and a real one.

**The parser is shared with [[file-follow]] round 2 on purpose.** Two flags in two docs taking
`15m` is exactly the shape that ends with `2h` meaning two hours in one place and two minutes in
another, and the cost of preventing it is one function.
