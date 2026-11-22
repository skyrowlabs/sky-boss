---
commit_range: v0.3.0..HEAD
generated: "2026-11-22T04:11:48Z"
previous_release: v0.3.0
release: unreleased
status: in-flight
---

# Repository Report

> **Window:** unreleased (since v0.3.0) — `v0.3.0..HEAD` (125 commits, at `b3e374e`)

This window opened at the v0.3.0 tag and is still in flight, so none of it is
in a release yet.

## Metrics

| Measure | Value | Source |
| ------- | ----- | ------ |
| Commits | 125: 77 non-merge, 48 merges | collected data; `git rev-list --count --merges` / `--no-merges` |
| Commits by type | feat 27, chore 21, docs 18, fix 8, test 5 | collected data. These sum to 79. The other 46 are merges with no type |
| Most-changed files | `docs/TODO/command-deck.md` 35 commits; `skyboss/deck.py` 26; `tests/test_deck.py` 23; `.skeletor.json` 13; `CLAUDE.md` and `docs/todo_index.json` 11 each; `README.md` 10 | collected data |
| Tree diff | 143 files, +11,755 / −960 | `git diff --shortstat v0.3.0..HEAD` |
| Test diff | 36 files under `tests/`, +4,459 / −153 | `git diff --shortstat -- tests` |
| Product diff | 22 files under `skyboss/` and `plugin/`, +4,431 / −461 | `git diff --shortstat -- skyboss plugin` |
| `skyboss/deck.py` | 4,571 lines at v0.3.0, 6,592 at HEAD | `wc -l` |
| Tour clip in history | 8 commits of `docs/design/readme-deck-tour.webp` in the window, none since the previous edition | `git log v0.3.0..HEAD -- <path>` |
| Findings in collected data | 0 | collected data |

The collected data has no coverage figure, so none is given here.

## What changed

Items marked *(new)* landed after `806b852`, the HEAD the previous edition
(`6244a59`) was written at.

### The deck

- *(new)* **Profiles and sessions are separate** (5f4b532, round 25). A profile
  is a set of agents in `deck.toml`; a session is one deck, running or not,
  kept in `$SB_STATE/deck/<name>/` with a `session.json` record
  (`skyboss/decksession.py:1`). New sessions are named `sb-<profile>-<n>`
  (`skyboss/decksession.py:110`). A session directory with no record is given
  one, keeping its tmux name (`skyboss/decksession.py:166`, called at
  `skyboss/deck.py:496`). The launcher has three sections: sessions, profiles
  and folders (`skyboss/decklaunch.py`). Deleting a session removes its
  directory (`skyboss/decksession.py:248`) and is refused while it runs
  (`skyboss/deck.py:3407`). Launcher actions tested in ad054e8;
  `tests/test_decksession.py` is new.
- *(new)* **Profiles own their sessions, and a tab menu sets the lead**
  (55f2036): `sb deck tab lead|move` (`skyboss/deck.py:4037`, `:4062`).
- *(new)* **A WATCHERS pane** (19d59c7, round 23, `skyboss/deckwatch.py`). It
  lists the shells, Monitors, sub-agents and daemon jobs a tab left running,
  and never drives one. A Monitor is told from a shell by where its fd 1
  points (43b5845, `skyboss/background.py:128`). `tests/test_deckwatch.py` is
  new (fa9aabe).
- *(new)* **A shortcuts overlay on M-/, and a footer dial** (3830eef, round 26,
  `skyboss/deckkeys.py:1`, `skyboss/deck.py:3837`).
- **Earlier in the window, recorded in the previous edition:** attaching
  reloads the deck (2e35910); hover lighting (a366451); folder browsing
  (0ffbd7c); several decks at once (d546c62); the launcher (dac64fb);
  `brief_file` (30805f5); shell watch (d6a8902); folder trust (010c064); stale
  todos put back (4261045); M-x clearing (092b612, badc0eb); `/deck-tour` and
  the README clip (d014547 to 806b852); 93 command tests (bd8a8d4).

### Fixes

- *(new)* **Trusting a folder keeps a write Claude Code made meanwhile**
  (641755c, closes [#84](https://github.com/skyrowlabs/sky-boss/issues/84)).
  `trust()` reads the file again before replacing it and retries up to three
  times (`skyboss/decktrust.py:37`, `:82`).
- *(new)* **The native canvas no longer waits on NetworkManager** (4191326).
  The shell sets `GIO_USE_NETWORK_MONITOR=base`
  (`skyboss/canvas/shell.py:67`) and drops it from every child.
- *(new)* **The tools plan points at the moved example file** (481abb1, closes
  [#75](https://github.com/skyrowlabs/sky-boss/issues/75)).
- Earlier: `sb agents` names `uds:` addresses (ee6b69e); an unexecutable source
  is a failed read (0bd5c8d).

### Structure and tooling

- **Skeletor**: twelve upgrades in the window, none since the previous edition
  (`.skeletor.json:3` reads `v0.88.0`).
- *(new)* **Dependencies**: the python group (cc338ce) and electron (d13b76b).
- Earlier: this job's commit is published by the runner (01c610c,
  `scripts/reporting/jobs.py:380`); root tidy (47c84c2); v0.3.0 report frozen
  (26bce56).

## Risks

- *(new)* **Deleting a session cannot be undone.** `delete()` calls
  `shutil.rmtree` on the session directory (`skyboss/decksession.py:253`).
  That directory holds its saved tabs, todos, decisions, asks and watcher
  choice, and nothing is backed up first. `tools.toml`, `deck.toml` and
  `.claude.json` are all backed up before a write. The launcher says what will
  go (`skyboss/decksession.py:236`), and a running session is refused. Whether
  a delete should keep a backup is a ruling, so it is not filed.
- *(new)* **The fix for #84 made the race window smaller but did not close it.**
  A Claude Code write that lands after the re-read at
  `skyboss/decktrust.py:82` and before `os.replace` at
  `skyboss/decktrust.py:89` is still lost. Closing that gap needs a lock that
  Claude Code also honours, and nothing here controls Claude Code.
  `DEFAULT_PROJECT` (`skyboss/decktrust.py:24`) still copies the entry shape of
  one Claude Code version.
- *(new)* **WATCHERS depends on Linux `/proc`.** `os.readlink` of
  `/proc/<pid>/fd/1` (`skyboss/background.py:128`) is how a Monitor is told
  from a shell. Where that cannot be read, every watcher shows up as a `SHELL`
  with no file to follow (`skyboss/background.py:125`). It degrades and does
  not raise.
- **Attaching to a deck is an act, and the real tmux path is untested.** An
  attach rebuilds the tool panes and then replays the captured layout
  (`skyboss/deck.py:2550`, `:4284`). Every test of this uses `FakeTmux`. Filed
  as [#110](https://github.com/skyrowlabs/sky-boss/issues/110). Whether attach
  should act at all is a ruling and is not filed.
- **The deck keeps growing in one module.** `skyboss/deck.py` is up 2,021 lines
  in this window, 1,147 of them since the previous edition (5,445 → 6,592).
  Round 25 moved sessions out to `skyboss/decksession.py` but added 1,497
  insertions to `deck.py` itself.
- **A recheck line can join an operator's draft.** Unchanged at HEAD: it is
  typed into any tab in `TELL_AT_ONCE = ("idle", "shell")`
  (`skyboss/deck.py:1392`, `:1453`) on a timer. Needs a ruling.
- **The tour clip's history weight** is unchanged: 8 versions in the window,
  none added since the previous edition. Where it should live is a ruling.
- **This report is published unattended** (`scripts/reporting/jobs.py:380`),
  so a wrong figure here reaches `develop` without a human reading it first.
- *Resolved since the previous edition:* the profile session-name change now
  has a migration (`skyboss/decksession.py:166`); #84 and #75 are closed.

## What is unfinished

`docs/todo_index.json` has an empty ready queue, and no open plan carries a
`queue_order`:

1. [[command-deck]]: `in-progress`, priority medium, 0 open tasks, updated
   2026-11-20. Rounds 23, 25 and 26 are recorded as built.
2. [[deck-tab]]: `planned`, priority medium, 24 open tasks.
3. [[grid-observability]]: `planned`, priority medium, 13 open tasks.
4. [[highlight]]: `in-review`, priority low. Its review is recorded as "pushed
   to develop".
