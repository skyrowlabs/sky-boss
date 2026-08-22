---
status: complete
created: 2026-08-21
updated: 2026-08-21
agent_value: 3
key_files:
  - cli/chrome.py
  - cli/resident.py
  - cli/canvas/server.py
  - cli/canvas/static/app.js
  - tests/test_chrome.py
  - tests/test_canvas_stream.py
---

# Chrome — what a window knows about its output

## Why

Two presentation layers exist in this design and only one of them has a home. **The view** is
in-band — how the data itself is drawn — and it is owned by [[table-views]] and `cli/view.py`.
**The chrome** is out-of-band: everything the surface *knows about* the output that the output
itself does not say. The source argv or keyword. The temporal shape. When it ran and how long it
took. The countdown to the next refresh. The liveness clock. The exit that made a stream go
dead. The warnings count. Nothing owns this set, and the specs now in flight are about to
scatter it: [[refresh]] adds a running-since clock and a countdown, [[follow]] adds a last-line
clock and a dead state, [[file-follow]] adds a stat clock, a size, and rotation announcements —
four status-line implementations, in two renderings each, written separately. That is the exact
drift the one-source pattern everywhere else here exists to prevent: one palette in `theme.py`,
one view heuristic in `view.py`, one catalog off the live tree. The chrome deserves the same
treatment before it diverges, not after.

It also gives the Rule primitive its landing site in advance. The escalation ladder's first
rungs — tint the window, badge it — are chrome reacting to a rule. If the chrome is one
contract, escalation later changes one thing; if it is four status lines, escalation is a
four-file retrofit.

## Shape

**The chrome is a fact set, computed once in Python, drawn twice.** A pure structure in
`cli/chrome.py`, assembled from what the envelope says (`ok`/`partial`, duration, warnings) plus
what the surface knows (interval, last run, liveness, ring occupancy). Both renderers — the
terminal's status lines and the canvas window's title bar and footer — draw what they are told,
exactly as they do for a view. The deciding half lives where pytest reaches it; neither renderer
grows an opinion.

What a window wears, by temporal shape:

| Shape | Chrome facts |
|---|---|
| snapshot, one-time | source · shape · ran-at · duration · ok/partial/failed · warnings count |
| resident refresh | the above · interval · countdown to next run · running-since while in flight |
| process stream | source · last-line clock · ring occupancy · **dead** (exit code, when) |
| file cursor | source · last-write clock (stat) · size · ring occupancy · absent / rotated / quiet |
| act (`run`) | source · ran-at · duration · exit — stamped once, never a countdown |

Sketch of the two renderings, same facts:

```
┌ jam-prs · data · refresh 30s ─────────── ⟳ next in 12s ┐
└ ok · 0.4s · ran 19:04:12 · 1 warning ──────────────────┘

┌ cron.log · follow ─────── quiet 3m · last write 19:01 ─┐
└ 198 KB · showing last 200 ─────────────────────────────┘
```

**The countdown rule is inherited, not re-decided.** [[canvas]] already ruled that a progress
bar shows time to the next refresh and nothing else — a running subprocess has no percentage,
and a bar that animates to look busy is decoration reading as information. The chrome contract
feeds that bar the same `interval` and `last_run` it reads today; the label-clock throttling
trade-off recorded there stands.

**An `attention` slot, reserved and mechanical.** The chrome carries one state field —
`running · ok · partial · failed · dead · quiet · absent · rotated` — populated only by
*mechanical* facts in this round. No judgments: "dead" is an exit code, "quiet" is a stat
comparison, and neither involves reading the output. This is the slot the escalation ladder's
tint and badge will occupy when the Rule branch arrives; reserving it now is one field, and it
is the difference between escalation landing in a contract and landing in a retrofit.

**Chrome consumes the envelope; it never feeds it.** `ok`, `duration` and `warnings` are already
envelope facts and stay so. Everything surface-side — clocks, countdowns, occupancy — stays
surface-side. Nothing chrome-shaped enters `data` or the envelope, so `--json` output is
untouched by this feature existing, byte for byte.

**Does not do:**

- **No spinners, no percentages, no busy animation.** The [[canvas]] argument, restated once:
  decoration that reads as information.
- **No rules, no thresholds, no judgments.** The attention slot is populated by mechanics only.
  Conditional states (a rule matched, a value crossed a line) are the Rule branch's to add.
- **No operator configuration.** Chrome is uniform per shape — no flags to hide it, reorder it,
  or extend it. A knob here would be a third rendering to test. If a real need appears, argue it
  as its own round.
- **No new envelope fields.** Stated above; a test holds the line.

## Phases

### Round 1 — one contract, two renderings (2026-08-21)

- [x] **The facts, pure.** `cli/chrome.py`: the per-shape fact set assembled from envelope +
      surface state over an injectable clock. Tests cover every shape and every mechanical
      attention state; no real time anywhere.
- [x] **The terminal rendering.** Status lines for the one-time and resident forms; [[refresh]]'s
      resident loop renders through it from birth rather than growing its own.
- [x] **The canvas rendering.** Title-bar and footer band from the same facts; the existing
      progress bar re-pointed at the contract's `interval`/`last_run` unchanged in behavior.
- [x] **The envelope boundary test.** An envelope produced with chrome active is byte-identical
      to one produced before this feature existed.

## Notes

### Round 1 — written as spec, from spec review (2026-08-21)

Born from the operator's question during review of the first three specs: can output be
"reimaged" — portrayed in a window annotated with additional info, metadata, timers. The answer
was that the design already implied the layer and three specs were about to implement it three
ways. Consolidated here *before* divergence — the cheapest moment — on the same argument that
put the view heuristic in Python and the palette in one file. Build order places this right
after [[refresh]], which creates the first resident terminal rendering to hang it on;
[[follow]] and [[file-follow]] then render through it rather than migrating onto it.

### Round 1 — executed (2026-08-21)

The first two phases were pulled *inside* [[refresh]]'s execution, between its renames and its
`--refresh` phase, so the resident loop rendered through `status_lines` from birth. What the
execution argued back:

- **The transport was already the right seam.** The canvas never shipped bare envelopes — the
  runner's `Run.to_dict()` wraps one — so `chrome` attaches beside `envelope` in the frame and
  the run response, and the envelope inside stays byte-identical without any migration. The
  boundary test pins the envelope's exact key order instead of asserting a negative.
- **The watcher's monotonic clock never ships.** `last_run` in the contract is stamped in epoch
  seconds at result time — the same moment the page stamped `ranAt` before — because a
  monotonic reading means nothing to another process. The bar reads the contract's number with
  identical behavior, falling back to the local stamp for a window that has not heard from the
  server yet.
- **`acts` comes through the catalog at assembly time**, never from `argv[0] == "run"` alone —
  a saved tool's first word is its own name, and the catalog is the one place that knows what
  it expands to. Same inheritance rule as the cadence control, applied a third time.
- The cursor constructor takes the *loop's* state verbatim and refuses any word outside its
  vocabulary — chrome carries verdicts, it never re-derives them, and the ValueError is what
  keeps a future caller from inventing a tenth attention word without meeting this doc first.
