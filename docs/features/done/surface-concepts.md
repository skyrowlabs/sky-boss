---
slug: surface-concepts
title: The idle state as a place, and the envelope without a second trip
status: complete
created: 2026-08-19
updated: 2026-08-19
agent_value: 3
key_files:
  - cli/tui/launch.py        # the idle screen
  - cli/tui/verbs.py         # view verbs, checked after the Click tree
  - cli/tui/actions.py       # what they do
  - cli/output.py            # Capture keeps the envelopes emit used to discard
  - cli/tui/app.py
---

# The idle state as a place, and the envelope without a second trip

## Why

Two things a design pass over the surface made obvious, both of which had been sitting in plain
sight. The canvas explored four directions; these are the two ideas worth taking, and neither
requires adopting a direction wholesale.

**The idle state is a blank.** Open `tb tui` and you get a banner, one line of key hints, and an
empty transcript with a rail beside it. Everything the surface knows — what is scheduled, what is
watched, what ran last, what you might type — is either offscreen or one command away. The first
thing you do every session is type something to find out where you are.

The design's framing is the useful one: **build the quiet state as a place rather than an empty
transcript.** Nothing new has to be computed. Jobs, watches, lanes and the ledger tail are all
already loaded a second after launch; they are simply not shown until asked for.

**`--json` is a second trip.** Every command returns an envelope — `ok`, `partial`, `data`,
`warnings` — and the surface renders it and throws the structure away. Wanting the underlying
data means retyping the line with `--json`, which runs the command again. For a `check` that is
merely wasteful. For a `run` it is wrong: the second trip is a second execution.

The envelope was in hand and got discarded. That is the whole bug.

## Shape

**Idle is "the transcript is empty", not "nothing is running".** The launch screen shows on
start, and comes back on `^L`. Clearing takes you home, which is a better `^L` than blanking a
pane.

**In the idle state the rail hides**, because the launch screen already says everything the rail
says, with more room to say it. The design's phrase is *no chrome until you type*, and the
alternative — launch screen and rail side by side — would print the watch list twice on one
screen. The rail returns with the first dispatch, which is when the transcript needs a companion
rather than a substitute.

```
 TACKLEBOX
                                                       workstation
   4 jobs · 2 watches · lanes clear · ledger 214 runs

   ● drift      clean          check drift · every 15m · 4m ago
   ● tools      2 stale        check tools · every 30m · 12m ago
   ○ home       can't read     ha-pi not on tailnet

   RECENT
   20:10  asset-drift       partial   0.4s
   18:30  unpushed-audit    ok        11.2s
   12:00  doctor            ok        2.1s

 ────────────────────────────────────────────────────────────────
 tb ▸                                    tb
                                         tackle-box — homebase…
```

**Surface verbs are a small dispatcher in front of the Click tree.** `inspect` is the first one;
[[pinned-watches]] needs `watch` and `unwatch` next. They are view verbs — they change what is
rendered and never what exists — so they are the one category a surface may own without becoming
a second CLI. Anything not recognised falls through to Click unchanged, so no tb command can be
shadowed by accident: the surface's table is checked *after* the real tree, not before.

**The envelope is captured where it is created, not re-derived.** `emit` already holds the
`Result` when it renders it; it appends it to the active capture. `Dispatch` carries them out,
and `inspect` shows the last one as formatted JSON — the same bytes `--json` would have printed,
without running anything. Collected on the capture rather than in a global, so a watch refreshing
on another thread cannot leave its envelope where the foreground will show it.

**Does not do:**

- **No re-running to inspect.** The point is that the second trip disappears. If the envelope was
  not captured, `inspect` says so rather than quietly running the command again — for `run` that
  would be a second execution of a job.
- **No history of envelopes.** The last one per dispatch, not a browsable log. The ledger is the
  durable record; this is a peek at what just happened.
- **No launch screen once you have typed.** It is the empty state, not a dashboard you switch to.
  A pane that persists beside the transcript is [[pinned-watches]]' job.
- **No new data sources.** Everything on the launch screen is already loaded for the rail.
- **The wordmark stays `TACKLEBOX`.** The design system's convention is lowercase `name.suffix`
  with the suffix tinted, and two of the four concepts render `tackle.box` — but the banner was
  asked for in caps, and the launch screen would then say the name twice on one screen. The
  launch screen leads with the status line instead.

## Phases

### Phase 1 — The launch screen

- [x] `#launch` beside `#body` in the middle; shown while the transcript is empty
- [x] Rail and its divider hide with it, restored on the first dispatch
- [x] Status line: host, job count, watch count, lane state, ledger size
- [x] Watch cards: verdict, age, and the definition that produced it
- [x] Recent runs, and a few suggestions of what to type
- [x] `^L` returns to it rather than leaving a blank pane
- [x] Test: the launch screen is visible at start and gone after a dispatch
- [x] Test: `^L` brings it back
- [x] Test: the rail is not shown beside it — the watch list is not printed twice

### Phase 2 — Surface verbs and the envelope inspector

- [x] `cli/tui/verbs.py`: a table of view verbs, consulted only after the Click tree misses
- [x] `emit` appends its `Result` to the active capture; `Dispatch` carries them
- [x] `inspect` renders the last envelope as JSON in the `Expanded` modal
- [x] With nothing captured, say so — never re-run
- [x] Completion offers surface verbs alongside real commands
- [x] Test: `inspect` after a command shows that command's envelope, not a fresh run
- [x] Test: a surface verb cannot shadow a real command
- [x] Test: a watch's envelope on another thread never reaches the foreground inspector —
      covered structurally: envelopes collect on the `Capture`, which is thread-local, and
      `test_concurrent_captures_do_not_post_into_each_other` already pins that

## Notes

Filled in during implementation.

**Shipped 2026-08-19.**

**`idle` could not be read off the transcript, which is where it obviously lives.** The first
definition was `not RichLog.lines`. While the launch screen is up the transcript is
`display: none`, so it has no size, so a write renders no lines — and the surface could never
leave the state it was measuring. It is tracked on a flag instead, set by `write_body`, which is
now the single path anything takes to the transcript. That single path is load-bearing:
`action_last_log` writes without an echo, and that alone was enough to leave the launch screen up
over a non-empty transcript.

**Truncation belongs to Textual, not to Python.** The chrome measured pane widths at call time
and cut strings to fit. That is wrong twice: on the first paint the width is the pre-layout
fallback, and after a resize or a drag it is stale — so the help pane rendered 34-character lines
into a 33-column pane and *wrapped*, which is the one thing the row budget cannot absorb.
`text-wrap: nowrap; text-overflow: ellipsis` in the stylesheet fixes it at the only place that
reliably knows the width. The `_fit` helpers stay, because they cut at a sensible boundary rather
than mid-word; they are now a nicety with a backstop instead of the mechanism.

Related, and the reason it went unnoticed: rewriting `on_resize` to delegate to `refresh_launch`
silently dropped its `refresh_help()` and `tick()` calls. Restored — but the CSS fix is what makes
the class of bug harmless rather than recurring.

**Surface verbs are checked *after* the Click tree, never before.** The tempting order is to
match the surface's own table first; that would let a verb added next year silently shadow a real
command, which is the worst failure available on this surface. `resolve()` returns `None` for
anything Click knows, and a test asserts the two name sets are disjoint.

**The envelope was always there.** `emit` holds the `Result` at the moment it renders it and used
to drop it. It now appends to the active `Capture` — which is already thread-local, so a watch
refreshing beside a typed command cannot leave its envelope where the foreground will read one.
No new machinery, and `--json` stops being a second trip. For `tb run` that second trip would
have been a second execution of the job.

**Deferred deliberately:** the catalog idea from concepts 1b and 1c — the command list shown with
live state, "replaces recall by memory" — is not built. The help pane is the right home for it
and it is a bigger change than these two. Concept 1b is a web app on `localhost:7331`, not a
direction for this surface; if it is ever wanted it is `tb serve`, a different thing.
