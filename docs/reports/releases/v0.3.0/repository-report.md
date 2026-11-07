---
commit_range: v0.2.0..v0.3.0
generated: "2026-11-07T21:57:07Z"
previous_release: v0.2.0
release: v0.3.0
status: released
---

# Repository Report

> **Window:** v0.3.0 — `v0.2.0..v0.3.0` (73 commits, at `e333710`)



This edition closes the window that became **v0.3.0**, the second release cut
by Release Please. The window ran from 2026-11-04 (the v0.2.0 tag, at
`7cd5823`) to 2026-11-07. Almost all of its product work went into the deck
(`sb deck`). The rest was a README rebuilt around the deck and eight skeletor
upgrades, from v0.72.2 to v0.81.1.

## Metrics

All figures came from git over the stamped range. None were estimated.

| Measure | Value | Source |
| ------- | ----- | ------ |
| Commits | 69: 50 non-merge, 19 merges | `git rev-list --count`, `--merges`, `--no-merges` |
| Non-merge commits by type | feat 22, docs 14, chore 9, fix 5 | subject prefixes |
| Deck-scoped commits | 39 non-merge (`deck` or `command-deck` scope): feat 22, docs 12, fix 5 | subject scopes |
| Skeletor-scoped commits | 8, all template upgrades (v0.72.2 → v0.81.1) | subject scopes |
| Tree diff | 119 files changed, +11,080 / −1,286 | `git diff --shortstat` |
| Test diff | 35 files under `tests/` changed, +3,588 / −138 | `git diff --shortstat -- tests` |
| Product diff | 18 files under `skyboss/`, `plugin/` and `README.md`, +4,414 / −379 | `git diff --stat` |
| `skyboss/deck.py` | 2,257 lines at v0.2.0, 4,571 at HEAD | `wc -l` |
| New product modules | `deckasks.py` 330 lines, `column.py` 262, `deckwire.py` 145, `deckplus.py` 136, `background.py` 131, `decksave.py` 94 | `wc -l` at HEAD |
| Coverage floor | 90.59%, unchanged | `tests/coverage_budget.json:18` |
| Breaking-change markers | 0 (no `!` subjects, no `BREAKING CHANGE` footers) | commit messages |

## What changed

### The deck

The deck shipped in v0.2.0 and was reopened for every round of this window.
Its plan moved back from `docs/implementations/surfaces/` to
`docs/TODO/command-deck.md` and is `in-progress`.

- **AGENT LIST.** The right column's panes were retitled AGENT LIST, AGENT
  COMMUNICATIONS, AGENT TODOs and HUMAN DECISIONS (0fd27f3). A session that a
  tab started is nested under that tab. The link comes from the process tree,
  or else from the session id in its scratch path, and an ended session stays
  listed under RECENT (fdf4150). A session's background jobs unfold under it
  too (34fe083, `skyboss/background.py`).
- **HUMAN DECISIONS.**
  - Agents first recorded decisions with `sb deck decide`, in a DECISIONS pane
    (d5e0a8d).
  - Clicking a decision offers its choices and types the ruling into the
    agent's tab (5c9475a). A ruling no longer waits for the tab to read `idle`:
    `shell` takes one at once, `busy` takes one after two minutes, and
    `waiting` never does (370cf37, `BUSY_TELL_AFTER` in `skyboss/deck.py`).
  - The pane became one queue for every ask of the operator (bc86757,
    `skyboss/deckasks.py`). An action row carries its exact command with
    `--run`, which a click asks about once and then runs. `--until` closes a
    row by observation. A notice is a row of its own kind. Hook rows say what
    a tab is waiting on, or that its turn ended on a question. A folded HELD
    line reads unpushed commits, green PRs and open alerts.
  - The tab brief and the `/deck-connect` skill teach every tab to tag its asks
    that way, including `--action` and the `pr:<n>@<sha>` pin (28f4d95). They
    also say that a merge the operator must run goes in as a `--run` row, and
    is never left only in prose (5074b05).
- **Messages between tabs.** A line under the tabs runs from a sender's tab to
  its receivers and then fades (c4c9352). It is drawn when the message is sent,
  holds the sender's hue until the message is received, and then takes the
  receiver's hue. `msg_id` ties the send to its receipt (dfc23f5,
  `skyboss/deckwire.py`). A message that a session absorbed mid-turn is stored
  as a `queued_command` attachment rather than a user entry. Before 3bdc521 it
  never landed a line and never appeared in AGENT COMMUNICATIONS
  (`skyboss/messages.py:116`).
- **Tabs and sessions.**
  - A stopped deck reopens its saved tabs, and each tab resumes its session.
    `--fresh` starts over, and `sb deck save` and `exit` write exactly what is
    open (cebab3e, `skyboss/decksave.py`).
  - A `+` in the bar, or M-n, opens a new agent tab or a terminal tab from
    `roots` in `deck.toml`, and can keep it in the profile (3b4fe61,
    `skyboss/deckplus.py`). This reversed the rule that sky.boss never writes
    `deck.toml`. The edit is a splice, parsed back after a backup.
  - Each tab is boxed, and its ground is lit while the agent works (dd6ae1a).
    Each tab's console takes its agent's colour through a per-agent Claude Code
    theme (a2ae6d8), and colours became the default (5c9475a).
  - The tab row scrolls around the current tab when it overflows (e208683).
- **Layout.**
  - The right column's panes are chosen and ordered with M-s and folded with
    M-c (d5e0a8d).
  - A 2x2 layout was added (5c9475a). The `grid` layout then became free: a
    pane moves between columns by clicking a title bar and then a pane in the
    target column, or with `sb deck column move` (4efc9a9, `skyboss/column.py`).
- **The bar and footer.** The SL mark and wordmark sit at the tab bar's left
  (02c5096), and were redrawn smaller (823d2aa) and then in sextants (e208683).
  The tool panes refresh together and are counted down once in the footer
  (7f41244). One clock moved to the footer (1c29169), and the footer is named
  after the profile (8087c42).
- **Smaller changes.** NEEDS YOU sorts by activity, and `sb deck reload`
  restarts the tool panes without killing one (c289f96). TODOS is ordered by
  recency (f93f35f). M-x clears done todos and decided items alike (823d2aa,
  c9e0c74). A clicked message opens whole in a popup (823d2aa). The bar label
  is no longer cut short (d4cab4a), and a sent message is drawn on the header
  ground (8976796).

### README and scope

- **The README leads with the deck** (7193aae). It opens on a redacted live
  deck and a quickstart, then covers the panes, keys and human decisions, with
  the rest of the CLI after them. It dropped the stale "acts: only `sb run`"
  badge. `docs/design/readme-deck-agents.png` and `readme-deck-decisions.png`
  were added.
- **The canvas stopped being declared a monitoring surface** (faf993c). Act
  versus observe went back to being a property of each command, and fusing the
  canvas with the deck became the long-term goal. `docs/open.md` § One surface
  lists what fusion adds, and [[deck-tab]] was planned as its first step. No
  behaviour changed.

### Structure and tooling

- **Skeletor.** Eight upgrades took the template from v0.72.2 to v0.81.1
  (9558d67, 4e3d7d2, 7ff8d3a, 5a22adc, a51740c, 88ef4fc, 52a855e, ba3e48c).
  - v0.73.0 added an actionlint step to CI, ported onto the flake8 leg
    (9558d67).
  - v0.77.1 introduced the divergence record,
    `scripts/template_divergence_allowlist.yaml`, with eleven entries for files
    whose reason a machine could not state (88ef4fc).
  - v0.81.0 brought green-stamp, the node product gates and
    `tests/test_product_scripts.py`. The eslint job now runs
    `.github/scripts/node-gate.cjs` in place of `npm test` (52a855e). A
    follow-up dropped the eslint block for CI's own helpers (9af5d4f).
- **Release.** v0.2.0 was frozen under `docs/reports/releases/v0.2.0/`
  (d464fb4) and back-merged into `develop` (0d0753f).

## Risks

- **Two defaults changed without a breaking marker.** A stopped deck now
  resumes its saved sessions unless given `--fresh` (cebab3e). Deck tabs are
  coloured by default and write a theme per agent into Claude Code's own theme
  directory unless `deck.toml` sets `themes = false` (a2ae6d8, 5c9475a;
  `skyboss/deck.py:219`). Both commits are `feat`, so the changelog will list
  them, but not as changes to existing behaviour.
- **sky.boss now writes `deck.toml`.** Until 3b4fe61 that file was operator
  content that sky.boss only read. The write is a splice behind a backup, the
  same safeguard `tools.toml` has.
- **The deck doubled again, and still runs no real tmux in the suite.**
  `skyboss/deck.py` grew from 2,257 to 4,571 lines in three days, beside six new
  deck modules. `tests/test_deck.py` replaces `RUNNER` wholesale
  (`skyboss/deck.py:468`), and `tests/test_deck_runtime.py` intercepts
  `subprocess.run` and `os.execvpe`, so no test needs a tmux binary.
- **The message line depends on Claude Code's transcript shape.** The
  mid-turn fix (3bdc521) exists because one delivery path wrote a
  `queued_command` attachment instead of a user entry. Any further change to
  how transcripts record a received message would stop lines landing in the
  same silent way.

## What is unfinished

`docs/todo_index.json` has an empty ready queue, and no open plan carries a
`queue_order`:

1. [[command-deck]]: `in-progress`, priority medium, 0 open tasks.
2. [[deck-tab]]: `planned`, priority medium, 24 open tasks. It embeds the
   running deck in the canvas as a nav tab.
3. [[grid-observability]]: `planned`, priority medium, 13 open tasks.
4. [[highlight]]: `in-review`, priority low.

## Errata

- **v0.2.0 edition, Metrics and Risks.** The frozen v0.2.0 report gave the
  window as 283 commits (250 non-merge, 33 merges), and its Risks section
  repeated 283. Over its own stamped range, `v0.1.0..v0.2.0`, git counts
  **290 commits: 253 non-merge, 37 merges**, which matches the commit count in
  that edition's own window line. The other figures in that table were not
  re-checked.
- **v0.2.0 edition, Risks.** It said this report had not verified whether
  Release Please would bound the first changelog at the v0.1.0 tag. It did.
  The `0.2.0` entry in `CHANGELOG.md` compares `v0.1.0...v0.2.0`.
