---
commit_range: v0.3.0..HEAD
generated: "2026-11-15T04:12:28Z"
previous_release: v0.3.0
release: unreleased
status: in-flight
---

# Repository Report

> **Window:** unreleased (since v0.3.0) — `v0.3.0..HEAD` (91 commits, at `806b852`)

This window opened at the v0.3.0 tag and is still in flight, so none of it is
in a release yet.

## Metrics

| Measure | Value | Source |
| ------- | ----- | ------ |
| Commits | 91: 52 non-merge, 39 merges | collected data; `git rev-list --count --merges` / `--no-merges` |
| Commits by type | feat 22, chore 19, fix 6, docs 4, test 3 | collected data. These sum to 54. The chore count includes two merge commits titled `chore: merge …` (89d262a, 64d3154). The other 37 merges have no type |
| Most-changed files | `docs/TODO/command-deck.md` 23 commits; `skyboss/deck.py` 20; `tests/test_deck.py` 19; `.skeletor.json` 13; `docs/design/readme-deck-tour.webp`, `skyboss/theme.py` and `docs/assets/skeletor-version.svg` 8 each | collected data |
| Tree diff | 125 files, +7,449 / −701 | `git diff --shortstat v0.3.0..HEAD` |
| Test diff | 30 files under `tests/`, +2,994 / −111 | `git diff --shortstat -- tests` |
| Product diff | 16 files under `skyboss/` and `plugin/`, +2,016 / −274 | `git diff --shortstat -- skyboss plugin` |
| `skyboss/deck.py` | 4,571 lines at v0.3.0, 5,445 at HEAD | `wc -l` |
| Tour clip in history | 8 blobs of `docs/design/readme-deck-tour.webp`, 7,211,990 bytes together; 996,948 at HEAD | `git rev-list --objects v0.3.0..HEAD -- <path>` with `git cat-file --batch-check` |
| Findings in collected data | 0 | collected data |

The collected data has no coverage figure, so none is given here.

## What changed

Items marked *(new)* landed after the previous edition of this report (`5cf8c9f`).

### The deck

- *(new)* **Attaching to a running deck reloads it** (2e35910,
  `skyboss/deck.py:2419`). `sb deck` that finds its session running does what
  `sb deck reload` does, then puts the captured window layout back
  (`skyboss/deck.py:3469`).
- *(new)* **The clickable row under the mouse is lit** (a366451,
  `skyboss/resident.py:283`, `tests/test_deck_hover.py`, 10 tests).
- *(new)* **Browse to a folder, and list the git projects under one** (0ffbd7c,
  `skyboss/deckplus.py:90`), from the `+` tab and the launcher.
- *(new)* **A message line to a tab whose transcript did not exist yet now
  fades** (d283073, `skyboss/deckwire.py`).
- *(new)* **`/deck-tour` and a README clip recorded from it** (d014547, then
  583f841 to 806b852). The clip is `docs/design/readme-deck-tour.webp`,
  rendered by `docs/design/render-deck-tour.mjs`. The same commits replaced the
  tab-row mark with a `SKY.BOSS` word block, then removed the tab-row mark
  (f0dd3be, `skyboss/theme.py`, −35 lines).
- *(new)* **Deck commands are covered** (bd8a8d4): 93 tests in
  `tests/test_deck_commands.py`, plus additions to `tests/test_deckasks.py` and
  `tests/test_shellwatch.py` (now 12 tests).
- **Several decks at once** (d546c62). A profile's deck runs as its own tmux
  session: its `session` key, or else `<base>-<profile>`
  (`skyboss/deck.py:1569`). `sb deck profile list|save|delete` manages them.
- **A launcher before the deck starts** (dac64fb, `skyboss/decklaunch.py`).
- **A brief can live in a file** (30805f5, `brief_file`).
- **Shell watch** (d6a8902, `skyboss/shellwatch.py`). Notes a stuck wait loop
  or a long unbounded shell in its tab's DECISIONS; never stops a shell.
- **The deck trusts a new folder before its tab opens** (010c064,
  `skyboss/decktrust.py`). `trust = false` in `deck.toml` turns it off.
- **Stale todos are put back to their tab** (4261045, `skyboss/deck.py:1362`).
- **M-x clears asked rows and says what stayed** (092b612); **a clear takes a
  notice as read** (badc0eb).
- **The primary tab is marked** (123de68, fa57d76); **a dotted folder gets a
  dashed tab name** (ea46108); **rebrief on resume, clear or compact**
  (9e3efbb); **decision popup restyled** (4bbc998).

### Agents and reads

- *(new)* **`sb agents` reports each session's `uds:` address** for a name that
  misses (ee6b69e, `skyboss/agents.py:257`).
- *(new)* **A source that cannot be executed is a failed read** (0bd5c8d,
  `skyboss/data.py:360`). A directory or non-executable argv had raised
  `PermissionError` and taken down all of `sb schedule` and `sb roll-call`.

### Structure and tooling

- **Skeletor**, twelve upgrades in the window: v0.81.2, .4, .5, *(new)* .6, .7,
  .8, v0.83.0, .1, .3, .5, v0.85.0 and v0.88.0 (`.skeletor.json:3` reads
  `v0.88.0`). The new ones add `cli/pr.py` and
  `scripts/check_deleted_paths.py` (8f5b55d), PR-route checks in
  `cli/doctor.py` (cb2dcf4), `scripts/tempdirs.py` (cb2dcf4), and plan
  lifecycle changes in `scripts/docs/plans.py` (3caabdd). Two doctor tests were
  held off the live PR route (ddedf48) and folded back at v0.83.1 (eeaed1f).
- *(new)* **This job's commit is published by the runner**
  (01c610c, `scripts/reporting/jobs.py:380`, `AUTO_PUSH.add("repo-report")`).
- **Root tidy** (47c84c2): `shell/` → `electron/`, `CONTRIBUTING.md` and
  `SECURITY.md` → `.github/`, `tools.example.toml` → `docs/examples/`.
- **Dependencies**: `pytest-asyncio` and `platformdirs` (41d8f3e); `globals`
  (c635937). **Release**: v0.3.0 report frozen (26bce56).

## Risks

- *(new)* **Attaching to a deck is now an act.** Before 2e35910 a second
  `sb deck` from another terminal only attached. Now it asks every tool pane to
  close and reopens it (`skyboss/deck.py:3455`), so attaching from a second
  terminal restarts the panes the first terminal is looking at, and a pane that
  will not close leaves a `partial` result (`skyboss/deck.py:3464`). The layout
  restore (`skyboss/deck.py:3475`) is tested only against `FakeTmux`
  (`tests/test_deck.py:3`), so whether real tmux accepts the captured layout
  after panes are rebuilt has not been run by any test. Whether attach should
  act is a ruling, so it is not filed.
- *(new)* **The tour clip adds about 7.2 MB to a public repo's history in one
  week.** Eight versions of `docs/design/readme-deck-tour.webp` were committed
  in this window, 0.24 to 1.08 MB each (Metrics). Each re-take adds another
  full copy, and history cannot be rewritten without the cost recorded for
  `refs/pull/*`. Where the clip should live (tree, LFS, a release asset) is a
  ruling, so it is not filed.
- **A profile's deck changed session name with no breaking marker, and saved
  decks are keyed by session.** Unchanged at HEAD: a profile without its own
  `session` runs as `<base>-<profile>` (`skyboss/deck.py:1569`) and saved tabs
  are looked up by session (`skyboss/decksave.py:49`), with no fallback to the
  old name found. A profile deck saved before upgrading is not found when that
  profile next opens. Needs a ruling, so it is not filed.
- **The deck rewrites a file another program owns.** Unchanged at HEAD:
  `trust()` reads Claude Code's config at `skyboss/decktrust.py:65` and replaces
  it at `skyboss/decktrust.py:77` with no check between. Filed as
  [#84](https://github.com/skyrowlabs/sky-boss/issues/84), still open.
  `DEFAULT_PROJECT` (`skyboss/decktrust.py:23`) copies one Claude Code
  version's entry shape, and nothing here notices when that shape changes.
- **A recheck line can join an operator's draft.** Unchanged at HEAD: it is typed
  into any `idle` or `shell` tab (`skyboss/deck.py:1301`, `skyboss/deck.py:1362`)
  on a timer, and the deck cannot see a half-written prompt. Needs a ruling, so
  it is not filed.
- **The deck keeps growing in one module, and its tests still stub tmux.**
  `skyboss/deck.py` grew by 874 lines in this window. The 93 new tests in
  `tests/test_deck_commands.py` raise coverage of the command layer, but they
  use the same fake runner; no test runs two real tmux sessions, which several
  decks at once (d546c62) and reload-on-attach (2e35910) depend on.
- **Unattended publication of this report.** Since 01c610c the runner publishes
  this job's commit through an auto-merging pull request
  (`scripts/reporting/jobs.py:380`), so a wrong figure here reaches `develop`
  with no human read. The job's fix policy limits the commit to this one file.
- **One stale path survived the root tidy.**
  `docs/implementations/commands/tools.md:11` still lists `tools.example.toml`
  in `key_files`. Filed as
  [#75](https://github.com/skyrowlabs/sky-boss/issues/75), still open.

## What is unfinished

`docs/todo_index.json` has an empty ready queue, and no open plan carries a
`queue_order`:

1. [[command-deck]]: `in-progress`, priority medium, 0 open tasks. Its
   frontmatter still reads `updated: 2026-11-06` (`docs/TODO/command-deck.md:8`),
   though it was changed in 23 commits of this window, the latest f0dd3be.
2. [[deck-tab]]: `planned`, priority medium, 24 open tasks.
3. [[grid-observability]]: `planned`, priority medium, 13 open tasks.
4. [[highlight]]: `in-review`, priority low, review recorded as "pushed to
   develop".
