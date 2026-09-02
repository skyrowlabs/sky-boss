# Fundamentals

This is the concept document — the constitution the implementation is subordinate to. Everything
built so far is treated as *evidence about the concept*, not as the concept itself: where code and
this document disagree, one of them is wrong on purpose, and the disagreement is worth a decision
rather than a silent edit. Decisions accrete under **Decisions**, dated, with the reasoning that
earned them; a reversed decision stays visible beside its reversal, same rule as a feature doc's
Notes.

## The concept in one line

> A glanceable surface that keeps the output of commands you care about **current** — so you can
> watch work happen, especially agentic work, without re-typing anything or trusting a stale
> scrollback.

The app observes work; it is not the thing that does the work. That is why the act/observe split
is the first primitive and not an implementation detail.

## The eight primitives

Three groups. Each primitive is a claim, a concrete example, and the design question it forces.
A ✦ marks one with a decision recorded below.

### About commands

1. **The Command** ✦ — an argv plus one bit that cannot be inferred: does it *act* or *observe*?
   `git status` observes; `git push` acts; no parser can tell you which `curl` is. The operator
   asserts the bit by choosing the entry point, and it gates whether refresh is allowed.
2. **The Result** ✦ — one uniform envelope everything arrives in. Verbatim text and structured
   rows are *different contracts*, not different qualities of the same output (see the
   `jam pr list` example below).
3. **The Keyword** ✦ — a name bound to a command, invocable in a few keystrokes. A saved routine
   *inherits* the act/observe bit — and its temporal shape — from the entry point it wraps rather
   than declaring either — otherwise a saved deploy could grant itself a refresh cadence.

### About the surface

4. **The Window** ✦ — output pinned to a place, alive beyond the scrollback. The arrangement
   persists in `$SB_STATE` and restores by nature: observes run fresh, follows return dead.
5. **The Cadence** ✦ — refresh keyed to *attention*, not a wall clock: re-runs while the window
   exists (even minimized), stops when it closes. Nothing survives the last window — that is what
   makes it a scheduler and not a daemon, and crossing that line is only ever done on purpose.
6. **The Layout** ✦ — a named arrangement of windows, openable in one keystroke. Operator
   content: `layouts.toml` in `$SB_HOME`, exported from the canvas, read and never written by sb.

### About liveness

7. **The Follow** ✦ — resident content accrual, two mechanisms behind one verb:
   `follow <path>` runs the native file cursor (stat-aware, rotation-proof, backfill),
   `follow -- <argv>` streams a command that never exits. Dispatch is by argument shape and
   nothing else.
8. **The Rule** ✦ — what keeps a window current, and later, what a window does about its output.
   Begins basic with exactly two rules — **refresh** (re-run a snapshot on cadence) and
   **follow** (hold content open, file or command) — and branches from there in ladder order:
   the delta view (declared keys, honest fallback), then escalation rung by rung, ending at
   opt-in desktop notification. Escalation may leave the surface but never outlives it. The word
   *watch* is reserved for the change-detection branch.

## Decisions

### 2026-08-21 — the Command, settled against two real use cases

Worked against `jam pr list` (a command with two output faces) and
`jam.sense/tmp/reporting/cron.log` (a live agentic-workflow log).

**A saved command is one face: one argv, one contract.** `jam pr list` raw is *authored* output —
a hand-built table whose legend ("⊘ cancelled is NOT a failure") is knowledge, not decoration.
`jam pr list --json` is *data* — bindable fields (`checks.failed`, `next`) that rules can key on.
Preserving the first means passing it verbatim; using the second means never seeing the first.
So they are two saved commands (`prs` structured, `prs-raw` verbatim), not one command with a
toggle. The primitive stays `(name, argv, nature)`; a both-faces toggle can arrive later as sugar
without changing it. Corollary, re-affirmed: the system never parses an authored face into
columns — inferring structure from whitespace is the silently-wrong failure, and a tool with real
structure has `--json`.

**A Follow is an argv that never exits.** The primitive covers `journalctl -f`, `docker logs -f`,
and a streaming agent session. *Superseded in part, same day:* this entry originally routed files
through it too (`tail -F <path>`, "sky.boss never grows a second, file-specific mechanism") —
reversed under *rules begin basic* below: files get **watch**, a native tail-like loop, because the
improvements watch needs are made of file knowledge a spawned tail cannot see. Follow remains the
mechanism for streaming *commands*.

**A dead stream goes dead visibly; restarting it is the operator's click.** When the followed
process exits or errors, the window plainly shows that the stream ended and when. No auto-restart:
the surface never launches a process on its own initiative, which keeps the follow on the observe
side of the same line the Cadence lives behind. `tail -F` already survives log rotation by itself,
which covers the common involuntary death.

What the log taught that a hypothetical would not have (evidence for the Follow and Rule
primitives):

- **Bursty, with long meaningful silences.** "no output until it finishes; ceiling 90 min" — a
  follower sits silent for an hour and a half *while everything is fine*. The surface must
  distinguish "stream alive, nothing new" from "stream dead"; a last-activity clock on the window
  is the feature, not chrome.
- **Lines are not uniform.** Timestamped lines, untimestamped `[isolation]` lines, blank spacers,
  multi-line logical blocks. Rules over a follow are per-line pattern matches that tolerate mess,
  never a parse of the whole.
- **Unbounded.** The window holds a ring buffer of the last N lines; the file remains the
  scrollback of record. Same rule as snapshots (no result renders unbounded), different mechanism.

### 2026-08-21 — the Keyword and the temporal shapes

Worked against the operator's three temporalities: instant commands, long processes, and watching
files for change.

**The Keyword is a name plus a sky.boss argv, and it is already the right shape.** `[tool.jam-prs]`
in `$SB_HOME/tools.toml` wrapping `wrap -- jam pr list --json` makes `sb jam-prs` real — in the CLI,
completions and palette alike. Ratified as-is from the build: the keyword inherits act/observe from
`argv[0]` and cannot declare it. Extended by this round: it inherits its *temporal shape* the same
way — `wrap`/`read` snapshot, `run` snapshot-or-job, `follow` stream — so `follow` becomes the
fourth savable entry point and no new tool field exists to get wrong.

**One execution mechanism; the temporal shapes are policies over it.** Every command is the same
event — spawn an argv, output accrues, maybe it exits. So:

- **A Job is a stream that ends.** Output from raw-output commands (`run`, `read`, `follow`)
  accrues live into the window as it happens; exit stamps a final status. This kills the
  ten-minute black box a long `sb run` is today, using the same plumbing the Follow needs anyway.
- **Duration is discovered, never declared.** There is no "job" flag: a snapshot that turns out
  to take eight minutes simply is one, and the surface shows it accruing either way. The only
  operator assertions remain act/observe and never-exits (`follow`).
- **`wrap` alone stays report-at-exit** — JSON parses only when complete; it shows a
  running-since clock instead. That is its contract, not a limitation.

**Change-watching is a view, not a fourth shape.** Two paths, both riding decided primitives:
event-driven is `inotifywait -m` as a Follow (zero new mechanism); state-driven is any snapshot
on a cadence plus the **delta view** — the window keeps the previous Result and highlights what
is new, changed, or gone between refreshes. Adopted as the Rule primitive's first capability and
deliberately generalized past files: a new PR row highlights the same way a modified file does.
"What changed since I last looked" is the app's mission stated as a rendering rule.

### 2026-08-21 — rules begin basic: refresh and watch

Operator's scoping call, closing the session. Rules start with exactly two, and everything else
branches from them later:

1. **refresh** — re-run a snapshot command on a cadence. Already built; ratified as rule number
   one rather than background machinery.
2. **watch** — continually watch a file for changes, with a cadence feel and the improvements the
   cron.log evidence demanded: a last-activity clock (silence ≠ death), a ring buffer, a visible
   dead state, surviving rotation.

**Corrected the same day: watch is a tail-*like* execution, not `tail -F` spawned.** This entry
first read watch as sugar expanding to `tail -F` under the ratified Follow — "one primitive, two
spellings, zero special cases." The operator corrected it: watch is sky.boss's own read loop over
the file — open, remember the offset, backfill the last N lines into the ring, poll for growth, emit
new lines — not a subprocess wearing a different name. The superseded reading stays visible here
because the reasons to reverse it are the design: owning the loop is what the "improvements" are
made of. sky.boss can *stat* the file, so the liveness clock distinguishes "file untouched since
19:00" from "no new lines matching" — a spawned tail can say neither. Truncation and rotation are
detected by inode and size rather than inherited from tail's flavor. Backfill-then-follow is one
mechanism instead of a flag. And the later branches — delta, conditional highlighting — bind to a
loop sky.boss owns rather than to another process's stdout.

The Follow proper (an argv that never exits — `journalctl -f`, `docker logs -f`, a streaming
agent session) stands unchanged for *commands* that stream. What changed is that files are no
longer routed through it: **watch owns files, follow owns commands.** Two mechanisms after all,
each earning its keep — the earlier zero-special-cases claim traded away exactly the file
knowledge the improvements need.

Sequencing consequence: the delta view and the escalation ladder stay adopted but move behind
these two — branches, not foundations.

### 2026-08-21 — naming: `wrap` becomes `data`; `run` keeps its name

**`wrap` is renamed `data`.** "wrap" named the mechanism; "data" names the contract, and the
contract is what this document says matters. `sb data -- jam pr list --json` reads as what it
promises: parsed data or a failed contract, never carried bytes. Format expansion rides it as
**one option, not a flag per format** — `--from csv`, `--from yaml`, json the unspoken default —
so formats stay mutually exclusive by construction, and each new one arrives only as it earns its
parsing contract. `data` never grows its own `--json` flag: the root owns that spelling for
envelope output, and one flag meaning two things at two levels is a confusion trap. (Decision
entries above predate the rename and say `wrap`; they are left as written.)

**`run` keeps its name.** A `cmd` rename was considered for the acting entry, and a generic
`sb cmd <argv>` door for all foreign commands was **considered and rejected**: one neutral entry
says nothing about whether re-running is a refresh or a scheduler nobody asked for, restoring the
assertion would take an `--acts` flag — a far weaker assertion than a command name — and keyword
inheritance leans on `argv[0]` being a distinct entry point. "run is the one command that acts"
is a sentence that teaches itself. The generic-reference experience already exists where it
belongs: the palette offers anything foreign as `read -- <argv>` — observing by default, the safe
default for something typed casually.

The surface this lands: **`run` acts · `read` / `data` / `follow` / `watch` observe** — one
acting verb, four observing contracts.

### 2026-08-21 — `--refresh`: the terminal is a surface too

**`--refresh <seconds>` on `read` and `data` makes the invocation resident.** Without it, an
invocation runs once, prints, exits — unchanged. With it, the command does not exit: it re-runs
every N seconds and redraws in place, `watch(1)`-style, `q`/`Esc`/Ctrl-C to leave. This came from the
operator's framing — "a run without options is one time; we need a flag that doesn't exit" — and
it is bigger than a launch-time cadence flag: it makes the *terminal* a rendering of the refresh
rule, beside the canvas. One refresh concept, two renderings, the same shape as the
theme's two-renderings rule. The same number drives both surfaces: `--refresh 30` in a terminal
is what `refresh = 30` on a saved keyword gives a pinned window.

**tools.toml's `every` renames to `refresh`** — flag and field share one vocabulary.

**`run` takes no refresh flag, ever.** A deploy re-running itself every 60 seconds is the exact
failure the act/observe split exists to prevent; the absence of the flag on `run` *is* the split,
made visible in `--help`. `follow` and `watch` take none either — they are resident by nature.

**`--from json` is spelled explicitly.** json becomes a named value of `--from` like any peer
format rather than an invisible assumption; a bare `sb data` still defaults to json (it is the
95% case) but json's status is now "default value of an explicit option," not "the assumption."

The full temporal picture: **`run` = once, ever · `read`/`data` = once, or resident with
`--refresh N` · `follow`/`watch` = resident by nature.**

### 2026-08-21 — closing the open questions: Window, Layout, delta, escalation

**The window's arrangement persists; what returns runs by its nature.** Geometry and the window
set live in `$SB_STATE`. Opening the canvas is operator initiative — restoring the desk is not
the surface acting on its own — so a restored `read`/`data` window runs fresh (exactly what its
cadence would do anyway), a `watch` reopens its file, a `follow` returns **dead until clicked**
(a restore is a process launch, and the dead-streams rule already decided that), and a `run`
window does not return runnable. The per-nature table is the act/observe split answering a
question it was never asked — which is what a good primitive does.

**Layouts are operator content.** `layouts.toml` in `$SB_HOME` beside `tools.toml`, read and
never written by sb. Hand-authoring geometry is miserable, so the canvas offers *copy current
arrangement as TOML* and the operator pastes it in — arranging is the canvas's job, owning the
file is the operator's. Last-session restore is state (`$SB_STATE`); a named layout is content —
the same content/state line the home directories already draw. This also answers the parked
Follow question: a layout may declare a follow, and it restores dead-until-clicked like any
other.

**Delta: identity is declared, never inferred.** Rows track across refreshes by an
operator-declared key (`key = "number"` on a keyword) and changed cells highlight. With no key,
the view degrades honestly — whole rows appear and disappear by exact content, no changed-cell
tracking — rather than guessing a key and being silently wrong. Verbatim text compares lines to
the previous run; a watch's arriving lines already are the delta. A highlight lives one cycle:
"changed" means *since the previous refresh*, never a ledger.

**Escalation may leave the surface, never outlive it.** The clarification that made this
decidable: a desktop notification fired while the canvas runs does not break
scheduler-not-daemon — that rule is about nothing surviving the last window, not about staying
mute. The ladder: highlight the line → tint the window → a peripheral canvas badge → per-rule
opt-in desktop notification. Every rung dies with the last window. **Loud is allowed; daemon is
not.**

*2026-08-22 — the first rung landed, in its pre-Rule form: [[highlight]] tints followed lines
by lexical shape (timestamp, tag, URL) with no judgment vocabulary. Operator-declared highlight
rules — the ladder's real first rung — remain the Rule branch's, undesigned.*

### 2026-08-21 — one verb: `follow`

**`follow` fronts both resident forms; `watch` is retired as a command name.**
`sb follow <path>` runs the native file cursor; `sb follow -- <argv>` streams a process. The
evidence was muscle memory: `-f` is literally `--follow` in tail, journalctl, docker and
kubectl — covering files *and* commands — while Unix's own `watch(1)` means periodic re-run,
which is this design's `--refresh`. Two names fighting that history misfired in the operator's
own hands during spec review, which is the cheapest possible place to learn it.

The mechanism split is untouched: the file cursor owns files (stat, rotation, backfill), the
process stream owns commands, and they stay separately specced — this is a surface decision,
not a mechanism one. Dispatch is by argument shape: `--` means process, a bare path means file,
nothing else. `watch` is reserved for the change-detection rule branch, where "watch for
changes" is what it will actually mean. The basic rules now read **refresh and follow**; earlier
entries say watch because it was watch.

### 2026-08-21 — the view and the chrome

Presentation has two layers, and naming them apart is the decision. **The view** is in-band —
how the data itself is drawn (columns, details, later the delta highlights) — owned by the view
contract. **The chrome** is out-of-band — what the surface *knows about* the output: source,
shape, ran-at, duration, countdown, liveness clocks, dead/absent/rotated states, warnings
count. The chrome is **one contract** (a per-shape fact set computed in Python, drawn by both
renderers), not a status line per command — specced as [[chrome]] before the resident commands
could implement it four separate ways. It carries a reserved, mechanics-only `attention` slot,
which is where the escalation ladder's tint and badge will land. Chrome consumes the envelope
and never feeds it: `--json` output is untouched by chrome existing.

### 2026-08-21 — the app documents itself

**Every command carries its complete documentation in its own `--help`:** what it does, the
contract it asserts (acts or observes; snapshot or resident), and at least one runnable example.
The help *is* the operator's documentation. Feature docs under `docs/features/` are the
designer's record of why — a thing the operator never needs to read to use the tool. This is the
resolution of a tension that produced pushback whenever operator docs were proposed as markdown:
the answer was never "no docs", it was that the doc belongs inside the surface it documents.

One string, two renderings — the same theme rule again: the catalog walks the live Click tree,
so the help that serves `--help` in the terminal serves the palette on the canvas, with no second
copy to drift. **Enforced, not aspired to:** a test walks the tree and fails any command whose
help lacks a runnable example, so a future command cannot ship undocumented.

### 2026-08-27 — the label tier: a border token is not a text token

`docs/open.md` carried this as a contrast question — 10.5px `#344050` on `#0b1016`, against the
CLI's measured 3.5:1 floor — and asked whether to *widen the canvas exemption* to cover a whole
tier of labels or lift the tier. **Both halves of the question were wrong, and the measurement
was too.** It is 1.81:1, not the "roughly 2.5:1" the item recorded.

**It is not a contrast dispute. It is a token used outside its role.** `cli/theme.py` defines
`TEXT_3` as *"very dim — structure, not reading text"*, and `BORDER = TEXT_3`. The mockup used
the **border** token as a **text** token. Nothing about the floor, the exemption, or the palette
needs to change to fix that.

**Ruled:** anything meant to be *read* takes `TEXT_2` (`#7a8fa8`, 5.75:1 on the canvas surface —
clear of the CLI floor and of WCAG AA's 4.5:1 for normal text). `TEXT_3` keeps what it is for:
borders, rules, dividers, and the dashed slots that mean *absent*. `QUEUE · 8`, `LAYOUT` and the
on-deck times are reading text and move.

**The exemption is not widened, and the reason matters more than the ruling.** Its stated basis is
that painting a background removes *the unknown terminal background* — which licenses using the
palette at **full strength**. It never licensed using a token outside its role, and stretching it
to cover a label tier would leave the floor meaning nothing. [[header]] records the mark as the
one thing outside the floor and asserts that with a test precisely so the carve-out cannot spread
by reasonable-looking steps. This is one of those steps, declined.

The canvas takes its tokens as CSS custom properties from `css_variables`, so this is a question of
*which* property a rule names — not a new colour, and not a second palette.

### 2026-09-01 — the tower is an observatory, and neither line moves

`docs/open.md` item 10 asked for a dated decision about the scheduler/daemon line, on the grounds
that the flight plan and the tower cross it. **They do not**, and the item was reasoning from a
mockup rather than from what the mockup draws.

**Measured before ruling.** Fourteen of the fifteen job names in `docs/design/ControlTower.dc.html`
are jam.sense's own jobs — `agent-fix`, `sentinel`, `integration`, `docs-guard`, `night-review`,
`implement-ready`, `model-health` and the rest — checked against the 31 rows that project's status
command returns. The fifteenth is `notify_slack`. So every band is drawn over **someone else's**
grid: `IN FLIGHT` is a session that provider started, `ON DECK` is that provider's cron, `COMPLETED`
is that provider's ledger, `OUTPUT` is that provider's logs. The tower is an observatory. It was
never a picture of jobs sky.boss runs.

**Ruled: neither line moves.** *Execution* — nothing survives the last window — is unchanged, and
the tower gives no reason to change it, since a foreign job runs whether or not sky.boss is open
and that is the whole point of watching it. *Federation* — sky.boss keeps no copy of another
project's state — is unchanged, because the tower reads rather than stores.

**Two rules were being conflated under one name, and separating them is the durable half of this.**
§ Cadence above is about **execution**: nothing keeps running. `cli/rollcall.py` is about
**copies**: *no ledger here, no history, no cache*, because a copy of a schedule that agents
rewrite goes stale without announcing it. A record is not a process, and a copy of one's own work
is not a copy of someone else's. "It crosses the daemon line" was doing the work of both sentences
at once, which is why the item could sit unanswered for a fortnight: there was no way to argue with
it. A future proposal has to say **which** of the two it crosses.

**What this does to item 6.** *Job identity that outlives a window* was named as the primitive the
plan and the tower are blocked on. For the tower it is not: three of the four bands have a shipped
or specced source today — `sb agents` ([[agent-sessions]], 2026-09-01), `sb schedule`
([[schedule]], 2026-08-30), and a project's own ledger ([[history]], drafted). Item 6 is neither
closed nor rejected; it is **no longer load-bearing for this screen**, which is a better place for
it to sit than *blocking*. Whatever genuinely needs sky.boss to remember what *it* ran should make
that case on its own.

**Not decided here, deliberately:** whether sky.boss may keep a record of its own runs. That
crosses the **federation** rule and not the execution one; the staleness argument that justifies
federation does not obviously reach it, since sky.boss is the authority for what sky.boss ran; and
`prefs.json` and `tools.toml` mean *stateless* is already a narrower claim than the word. Left
undecided until something wants it, rather than pre-answered here.

*Answered the same day by the decision below — something wanted it within hours. Nothing above is
withdrawn: this decision was about **what the tower requires**, and the tower still requires
neither line moved. What follows is a separate decision to build something the tower never needed.*

### 2026-09-01 — sky.boss may issue a schedule, and systemd is still the daemon

Asked for by the operator, hours after the decision above: a schedule sky.boss **owns**, layered
beside the ones it reads. Ruled yes, and the crossing is deliberate rather than incidental — which
is the condition § Cadence attaches to it.

**Execution is crossed. An installed job fires with no window open.** That is the sentence in
§ Cadence and there is no reading of this feature that avoids it. Recorded here so it is a decision
with a date rather than a drift.

**sky.boss does not become a daemon, and that distinction is the whole design.** systemd is the
daemon. sky.boss generates units and reads them back; it holds no clock, stays resident for
nothing, and supervises nobody — the relationship breeze.brain has to Docker. *Nothing of
sky.boss's own survives the last window* remains literally true. What survives is a `.timer` file,
owned by an init system that was already running.

**§ Cadence keeps its force and gains its missing half.** The rule that only a read may be given a
cadence was never *a repeating write is forbidden* — it is **a window is the wrong owner for one**.
A window is attention-keyed, pauses when you close it, and would make a scheduler out of something
you opened to look at. A job is the right owner: declared in a file, installed one at a time,
deliberately. The canvas's refusal is unchanged and now has a reason it can point at instead of a
prohibition.

**Federation is crossed narrowly, and the argument for it was already written.** `cli/rollcall.py`
keeps no ledger because a copy of *another project's* state goes stale without announcing it. A
record of what sky.boss itself ran is not a copy of anyone's state — sky.boss is its authority.
That is exactly the reasoning left standing above, applied on the day something wanted it.

**Two refusals do not move, and they are what keep this honest.** sky.boss **never writes anyone's
crontab** — the operator deactivates their own entries, and cron is read as opaque busy windows.
And sky.boss **never parses a calendar syntax** in either direction: `OnCalendar` is validated by
`systemd-analyze calendar`, and a fire time is read back from `systemctl --user list-timers` rather
than computed. [[schedule]]'s refusal to parse cron was never about reading; it was about not owning
semantics that belong to something else, and that is unchanged on the writing side.

**The riskiest part is not the scheduler.** It is the window in which a job exists on both sides,
which this design *opens on purpose* by leaving the handover to the operator. So drift read back
from systemd, and an `install` that refuses a collision and names it, are load-bearing rather than
polish. See [[jobs]].

## Open questions

One held deliberately; the concept is otherwise closed and further detail belongs in feature
docs:

- **Governance:** which of skeletor's checks (docs, doc-links, bug capture) this repo adopts now
  that the fundamentals have settled. Deliberately after the specs, not during.

## Parked ideas

Named but not designed. Parked, not promised.

- **Cron/systemd manager, or manager-lite** (operator, 2026-08-21). The *lite* reading fits the
  concept as-is: `systemctl list-timers`, `systemctl status`, `crontab -l` are snapshots on a
  cadence, and a unit's journal is a Follow — a "manager-lite" may be nothing but keywords plus a
  layout. The full *manager* reading (enable/disable/edit units) acts, so it lives behind `sb run`
  like every action, and would need to respect an existing boundary: jam.sense keeps its own
  scheduler, and sky.boss never manages or edits its cron entries.
