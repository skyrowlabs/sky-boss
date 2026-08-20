---
slug: surface-panes
title: Panes, progressive disclosure and watched conditions
status: complete
created: 2026-08-19
updated: 2026-08-19
agent_value: 3
key_files:
  - cli/output.py            # thread-local capture; the concurrency fix lives here
  - cli/watch.py             # the read-verb-only rule, enforced at load
  - cli/tui/help.py          # help read off the Click tree
  - cli/tui/app.py           # panes, rail, Separator, Expanded
  - watches/_template.yaml
---

# Panes, progressive disclosure and watched conditions

## Why

The surface currently spends ten of its rows on a single stacked column: input, completions,
lanes, progress, and the ledger tail, all in one strip above — now below — the transcript. That
column mixes three things with completely different lifetimes. The input and its completions are
about *the line being typed right now* and are gone a second later. Lanes and progress are *live
machine state*. The ledger tail is *history*. Stacking them means the fast-moving thing and the
slow-moving thing compete for the same rows, and the transcript pays for all of it.

Three specific gaps this closes:

**Nothing explains a command while you type it.** Tab completion produces a bare list — `list
log` — which tells you a verb exists but not what it does or what it takes. The information is
already in the tree; `tb auto log --help` will print it, but that costs a dispatch, scrolls the
transcript, and answers a question you had mid-line.

**Long command lines run out of room.** `run asset-refresh --lane committing --timeout 300` is
fifty characters. The input needs width more than anything else in the region does.

**There is no way to watch a condition.** `tb check drift` answers "is this machine still what
its inventory says" once, when asked. The whole reason the surface exists is that a one-shot
command can only report in the past tense — the same argument that produced the lane strip
applies to every `check`. A condition you care about should be able to sit on screen.

## Shape

Three regions, each holding one lifetime of information.

```
 TACKLEBOX                                            workstation
─────────────────────────────────────────────────┬──────────────────────
 ▸ check drift                                   │ LANES
 ● check  3 rows                                 │ · read-only
 …transcript…                                    │ ● committing  refresh
                                                 │
                                                 │ NOW
                                                 │ ▰▰▰▱▱▱▱  run doctor
                                                 │ 2.0s / ~7.0s  (1 q)
                                                 │
                                                 │ WATCH
                                                 │ ● tools     2 stale 4m
                                                 │ ● drift     clean   4m
                                                 │ ⚠ unpushed  can't read
                                                 │
                                                 │ RECENT
                                                 │ 20:10 asset-refresh ok
─────────────────────────────────────────────────┴──────────────────────
 tb ▸ check dr                          │ check drift
 drift                                  │ Compare this machine against
                                        │ its inventory record.
                                        │ --section  Limit to one or…
```

**The region splits 2fr / 1fr, input on the left.** The input gets the larger share because a
command line is the longest string on the surface; the help pane is narrow on purpose and leans
on truncation. Left holds the input on its bottom row with candidate names above it — tab
completion keeps its adjacency to the cursor. Right holds help for whatever the line resolves to.

The region drops from ten rows to six, returning four rows to the transcript.

**Help is read off the real Click tree, never described again.** `complete._resolve()` already
walks the tree, and resolving plus reading every param costs **0.4 µs** — 2,000 in 0.8 ms. That
is cheap enough to run on `Input.Changed` on the event loop, with no thread and no debounce. A
group renders its subcommands with their one-liners, a command renders its short help and its
params with theirs. This is the third consumer of the rule that already governs dispatch and
completion: the surface keeps no command table, so it cannot drift from the CLI.

**The rail is a slim column right of the transcript**, holding what the region gave up plus a new
`WATCH` section. It auto-hides below a terminal width threshold rather than squeezing the
transcript — output is the thing the surface is for.

**A watch is a `check` or `info` command, an interval, and a rendered line.** It may never name
`run`. That restriction does two jobs, and the second is the load-bearing one:

- A watch that could invoke `run` would be a scheduler that never touches the ledger, which
  breaks the property the whole taxonomy exists for. Scheduling is `auto`'s job.
- **It is what makes the concurrency safe.** A watch has to refresh without queueing behind the
  line you are typing, which means a second dispatch running concurrently with yours. That is
  only safe because a read verb cannot take a lane lock or mutate state. Read-only is not a
  precaution bolted on afterwards; it is the precondition for the whole design.

Watches need no per-watch code, because every command already returns the same envelope. `ok` /
`partial` / `warnings` and a row count is enough to render any check that exists or will exist.

**Progressive disclosure is chrome-only.** Everything in the panes truncates to fit and offers a
clickable `…` that expands — into a taller pane where there is room, into a `ModalScreen` where
there is not. This must not extend to the transcript: `RichLog` is constructed `markup=False`
precisely so captured command output is never parsed as markup, and a tool that printed
`[/home/x]` would otherwise lose it. Chrome therefore uses Textual `Content` markup; the
transcript keeps Rich `Text`.

**Separators are draggable.** Textual 8.2.8 ships no splitter widget, so this is hand-rolled from
`capture_mouse()` / `release_mouse()` and `MouseMove.delta_x` against a reactive width, clamped so
neither side can be dragged out of existence.

**Does not do:**

- **No watch may write.** No `run`, no arbitrary argv, no shell. If a watch could take a lane the
  concurrent refresh above would be unsafe, and `tb run` would stop being the only door that
  writes.
- **No second scheduler.** Watches refresh while the surface is open and stop when it closes.
  Anything that must run whether or not you are looking at it is a job — that is `tb auto`.
- **No progressive disclosure in the transcript.** See above; `markup=False` is load-bearing.
- **No per-check rendering code in the rail.** A watch that needs bespoke formatting is a sign
  the envelope is missing a field, and the fix belongs in the command.
- **No layout persistence** in this feature. Dragged separators reset on restart; remembering
  them means a config file and a schema, and it should wait until the defaults are known to be
  wrong.
- **No theme switching.** One palette, per CLAUDE.md.

## Phases

### Phase 1 — The width fix

`tb --help` renders at 80 columns inside the surface no matter what width is passed. rich-click
builds a Console of its own; `capture()` catches its bytes through `redirect_stdout` but never
sizes it, and setting `rich_click.WIDTH` / `MAX_WIDTH` does not take. Setting `COLUMNS` inside
`capture()` does — verified: `COLUMNS=46` yields a widest line of exactly 46.

Invisible today, because the transcript is wider than 80 anyway. It becomes clipping the moment
the rail narrows the pane, since `RichLog` is `wrap=False`. So it lands first, alone.

- [x] Set `COLUMNS` (restoring it after) inside `capture()` in `cli/output.py`
- [x] Test: `--help` captured at width N has no line longer than N
- [x] Test: `COLUMNS` is restored afterwards, including on the exception path

### Phase 2 — Split the region

- [x] Region becomes a `Horizontal`: `#inputpane` 2fr, `#helppane` 1fr, separator between
- [x] Shrink `REPL_ROWS` 10 → 6 and rebuild the row budget; the assert stays — **moved to Phase
      3**, where the stats actually leave the region; shrinking first would have clipped them
- [x] Input bottom-aligned in the left pane, candidates above it
- [x] `cli/tui/help.py`: resolve a partial line to its help view off the Click tree
- [x] Group → subcommands with one-liners; command → short help plus params with theirs
- [x] Wire to `Input.Changed`, on the event loop, no thread
- [x] Truncate to the pane width (plain `…` for now; Phase 5 makes it clickable)
- [x] Test: help for a partial line names the resolved command, not the typed prefix
- [x] Test: the help view is derived from the tree — a command added to a group appears with no
      change to `help.py`

### Phase 3 — The rail

- [x] `#rail` right of the transcript, fixed width, sections `LANES` / `NOW` / `RECENT`
- [x] Restack the progress row for a narrow column — bar, label and timing on separate lines
- [x] Move lanes, progress and updates out of the region
- [x] Auto-hide the rail below a threshold terminal width
- [x] Test: geometry — rail right of the transcript, transcript still starts under the banner
- [x] Test: below the threshold the rail is hidden and the transcript takes the full width

### Phase 4 — Watches

- [x] Watch definitions versioned in-repo under `watches/*.yaml`, keyed by `hosts:`
- [x] Reject at load time any watch naming a verb outside `info` / `check`, with a clear error
- [x] Refresh on a per-watch interval, on a thread, off the dispatch queue
- [x] Render from the envelope alone: outcome, a count, and staleness
- [x] A watch that fails to run reads `can't read`, never `clear`
- [x] Test: a watch naming `run` is refused at load
- [x] Test: a watch whose command raises renders unreadable rather than ok
- [x] Test: a watch refresh does not block a concurrent dispatch

### Phase 5 — Truncation and progressive disclosure

- [x] Chrome renders through Textual `Content`; the transcript stays Rich `Text`
- [x] Truncated chrome ends in a clickable `…` (`[@click=…]`, verified working)
- [x] Expand in place where the pane has rows; `ModalScreen` where it does not
- [x] `Tooltip` on truncated rail entries
- [x] Test: the transcript is still `markup=False` and renders literal `[…]` unharmed
- [x] Test: clicking the ellipsis reveals the full text

### Phase 6 — Movable separators

- [x] A `Separator` widget: `capture_mouse` on `MouseDown`, width from `MouseMove.delta_x`,
      release on `MouseUp`
- [x] Clamp both sides to a minimum width
- [x] Cursor/hover affordance so it reads as draggable
- [x] Test: a simulated drag moves the boundary and respects the clamp

## Notes

**Watches were removed on 2026-08-20.** Everything below about watched conditions — the rail's
WATCH pane, `watches/*.yaml`, the read-verb restriction — described what was built and is kept as
that record. It is not the current surface. `tb check` and `tb info` were the only groups a watch
could name, and removing them left no valid watch command; see Round 2 of the `command-taxonomy`
doc. The rail keeps LANES, NOW and RECENT.


**Superseded 2026-08-20 by [[operator-home]].** The conclusion below held; the location did
not. Watch definitions are still versioned rather than loose config, and still keyed by `hosts:`
— they simply live in `$TB_HOME/watches/`, which is the operator's own git repository, rather
than in this one. The reasoning survived the move intact; what changed is *whose* repo.

**Decided 2026-08-19 — watches are versioned in-repo**, under `watches/*.yaml`, not in
`~/.config/tb/`. The `sites.toml` precedent argued for machine-local, since workstation and laptop
would not watch the same things — but that is what a `hosts:` key is for, and it does not
outweigh the convention this repo already set: inventory and job definitions are systems of
record whose git diff is the maintenance log. A watch list is the same kind of thing. Machine
divergence is a field, not a file location.

**Scope, this pass:** phases 1–3 only. Watches, disclosure and draggable separators stay drafted
until the layout has been used.

**Watches are the natural split point** if this doc gets long. Phase 4 depends on the rail from
Phase 3 but nothing after it depends on Phase 4, so it can be lifted into its own feature doc
without disturbing the rest.

**Verified before writing this, not assumed:** `[@click=app.action]` markup fires in a `Static`;
`ModalScreen`, `Tooltip` and `Collapsible` all exist in Textual 8.2.8; `capture_mouse` /
`release_mouse` and `MouseMove.delta_x` exist; there is **no** built-in splitter widget; and the
`COLUMNS` fix for the rich-click help width works.

**Shipped 2026-08-19: phases 1–3.** Phases 4–6 remain unchecked and the doc stays `active`.

**The `COLUMNS` fix was worth landing alone.** It is a one-line change that reads like a nicety
and is not: without it `--help` renders at Rich's 80-column default, and the moment the rail
narrowed the transcript that became clipping rather than merely wasted space, because `RichLog`
is `wrap=False`. Confirmed the test is real by neutralising the fix — the same capture measures
80 columns at a requested width of 46.

**The help pane descends one step further than `resolve` does.** `resolve` only steps into words
that are already whole subcommands, so `check dr` stopped at the group and explained `check` on
exactly the keystroke where you want `drift`. `_descend` follows an *unambiguous* prefix one step
on, and deliberately refuses when two subcommands match — guessing between `drift` and a
hypothetical `drain` would present a coin toss as a fact.

**The root group is called `cli`.** Click takes a group's name from the function it decorates, so
the help pane titled the root `cli` — the package it lives in, which appears nowhere the user can
see. Special-cased against the imported root object rather than by string, so renaming the
package cannot silently reintroduce it.

**The region shrink moved from Phase 2 to Phase 3.** Shrinking to six rows while lanes, progress
and the feed were still in the region would have clipped them for one commit. Each phase has to
leave the repo working, so the split landed at ten rows and the shrink rode along with the move.

**The old row-budget assert did not survive, and should not have.** It summed the region's parts
against a constant ten, which was right while the region held everything. The rail's height comes
from the terminal, so the equivalent invariant is now just the region's own three parts against
six. `test_the_region_row_budget_adds_up` replaces `test_the_region_is_exactly_ten_rows`.

**Progress needed real restacking, not just truncating.** Bar, label and timing shared one line
on the wide strip. In 31 columns they cannot, so each takes a row — which incidentally gave the
job name room to be read instead of being cut off after four words.

**`^D` with text in the input does not quit**, which is correct readline behaviour and cost a
confusing `exit 124` in a pty smoke test before it was recognised as the feature it is. Any
future scripted smoke test has to clear the line with `^C` first.

**Phases 4–6 shipped 2026-08-19, basic versions.**

**The concurrency claim was wrong when written, and phase 4 proved it.** The spec argued that a
watch is safe to run beside a typed command because a read verb cannot take a lane lock. True,
and not sufficient. `capture()` swapped *module globals* and `sys.stdout`, which was safe only
while the TUI's queue guaranteed one dispatch at a time — the exact guarantee watches were
designed to break. Measured, not theorised: four concurrent dispatches, and two came back with
zero captured characters because the other two had stolen their buffers.

Fixed by moving the two consoles to a `threading.local()`, reached through `_out()` / `_err()`.
`sys.stdout` has no per-thread version, so the redirect stayed process-global and became
opt-out instead: the foreground dispatch keeps it, because it is the one that can render
`--help`, and a watch passes `redirect=False`. That is only safe because a watch may not run
`--help` — refused at load, which is a real rule rather than a note, since rich-click's own
console is exactly what the redirect exists to catch.

The lesson worth keeping: **the lane lock was never the only shared state.** Anything that
serialises access to a process-wide resource is load-bearing, and the output contract's single
console was one.

**A watch is not restarted while it is still running.** `check tools` shells out to half a dozen
CLIs and can outlast its own interval; without the guard it would stack copies of itself.

**Exit codes carry the whole verdict**, so nothing parses `--json`. 0 and 3 are verdicts, 1 and 2
mean the check never reached one — and the second group renders `can't read`, never `clear`. That
is the home group's rule generalised, and the test enumerates all five outcomes rather than
spot-checking, because collapsing those two is the failure the whole section exists to avoid.

**Progressive disclosure landed as a pane click, not a clickable ellipsis.** The verified
`[@click=…]` markup works, but using it means rendering all chrome through Textual `Content`
instead of Rich `Text` — a rewrite of every renderer for a smaller target. Clicking anywhere in
a truncated pane opens the `ModalScreen`, which is most of the value for a fraction of the
change. `Tooltip` was skipped for the same reason; the modal covers it.

**Widget `DEFAULT_CSS` parses in a scope with no `$tb-*` bound.** `Separator` and `Expanded` had
to have their rules moved into the app's stylesheet, which is where the palette is. Otherwise the
only way to style them would be a literal hex, which the theme test forbids — correctly.

**`styles.width` sets the outer box; `size` reports the content box.** Reading the wrong one made
every drag silently subtract the rail's padding, so the clamp settled two columns below the floor
it named. `outer_size` on both sides fixed it.

**Dragging is not persisted**, as scoped. The rail's divider hides with the rail below the width
threshold — a handle for a pane that is not there is a column of transcript spent on nothing.

**The input moved to the top of the region, 2026-08-19.** The region stays at the foot of the
screen — that part of [[surface-design]]'s reversal holds, and for the reason recorded there.
Inside the region it was wrong. Everything else in the region *describes* the line: candidates
hang off it, help explains it. Putting the line last meant its own subordinate detail sat above
it, and the help pane's title floated four rows clear of the command it was titling.

With the input on the region's first row the two panes line up: `tb ▸ check drift` on the left and
`drift` on the right, on the same row. That alignment is now asserted rather than left to look
right by accident — `test_the_input_is_the_first_row_of_the_region_not_the_last` checks
`#helppane.y == #prompt.y`.

**A test was lost between being written and being committed.** The original geometry test named
the input as the screen's last row; a later block replacement in the same file, anchored on two
function names it happened to sit between, removed it before it was ever committed. It never
appears in git history, so nothing regressed — but the coverage was reported as existing while
it did not. Two replacements now stand in its place. The lesson is about the edit, not the
layout: anchoring a wholesale replacement on surrounding function names silently eats anything
that moved in between.
