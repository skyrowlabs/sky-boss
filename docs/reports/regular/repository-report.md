---
commit_range: v0.3.0..HEAD
generated: "2026-11-08T17:49:43Z"
previous_release: v0.3.0
release: unreleased
status: in-flight
---

# Repository Report

> **Window:** unreleased (since v0.3.0) — `v0.3.0..HEAD` (47 commits, at `5cf8c9f`)





This window opened at the v0.3.0 tag and is still in flight, so none of it is
in a release yet.

## Metrics

| Measure | Value | Source |
| ------- | ----- | ------ |
| Commits | 47: 24 non-merge, 23 merges | collected data; `git rev-list --count --merges` / `--no-merges` |
| Commits by type | feat 10, chore 9, fix 4, docs 3 | collected data. The chore count includes two merge commits titled `chore: merge …` (89d262a, 64d3154). The other 21 merges have no type |
| Most-changed files | `skyboss/deck.py` and `docs/TODO/command-deck.md`, 14 commits each; `tests/test_deck.py`, 9; `CLAUDE.md`, 6; `.skeletor.json`, 4 | collected data |
| Tree diff | 78 files, +2,987 / −393 | `git diff --shortstat v0.3.0..HEAD` |
| Test diff | 16 files under `tests/`, +675 / −23 | `git diff --shortstat -- tests` |
| Product diff | 11 files under `skyboss/` and `plugin/`, +1,584 / −133 | `git diff --shortstat -- skyboss plugin` |
| `skyboss/deck.py` | 4,571 lines at v0.3.0, 5,322 at HEAD | `wc -l` |
| New product modules | `skyboss/decklaunch.py` 280 lines, `skyboss/shellwatch.py` 199, `skyboss/decktrust.py` 90 | `wc -l` at HEAD |
| Findings in collected data | 0 | collected data |

The collected data has no coverage figure, so none is given here.

## What changed

### The deck

- **Several decks at once** (d546c62). A declared profile's deck runs as its
  own tmux session: its `session` key, or else `<base>-<profile>`
  (`skyboss/deck.py:1562`). `sb deck profile list|save|delete` manages
  profiles. Help text and `.env.example` were fixed afterwards (cbdeef2).
- **A launcher before the deck starts** (dac64fb, `skyboss/decklaunch.py`).
  `sb deck` with no `--profile` at a terminal first offers the last deck to
  resume, the profiles, and the agent folders to tick, save or delete.
- **A brief can live in a file** (30805f5). `[profile.NAME]` takes
  `brief_file`, read each time a brief is built (`skyboss/deck.py:220`).
- **Shell watch** (d6a8902, `skyboss/shellwatch.py`). A sweep notes a stuck
  wait loop or a long unbounded shell once in its tab's DECISIONS. It never
  stops a shell or types into a tab.
- **The deck trusts a new folder before its tab opens** (010c064,
  `skyboss/decktrust.py`, `skyboss/deck.py:2517`). It sets
  `hasTrustDialogAccepted` for that folder in Claude Code's config, after a
  backup. `trust = false` in `deck.toml` turns it off.
- **Stale todos are put back to their tab** (4261045, `skyboss/deck.py:1323`).
  An open todo unchecked for `todo_stale` (default 6h, `skyboss/todos.py:45`)
  reads stale, and the deck types one recheck line into its tab.
- **M-x clears asked rows and says what stayed** (092b612,
  `skyboss/todos.py:276`, `skyboss/todos.py:292`).
- **The primary tab is marked** (123de68, then fa57d76 moved the star after
  the name, `skyboss/agents.py`). `/deck-connect` run in the primary sends each
  live tab one line (`plugin/skills/deck-connect/SKILL.md`).
- **A dotted folder gets a dashed tab name** (ea46108,
  `skyboss/deckplus.py:41`). `[agent.skyrowlabs.com]` had parsed as a nested
  table, and keeping that tab was refused.
- **Rebrief on resume, clear or compact** (9e3efbb, `plugin/hooks/hooks.json`).
- **Decision popup** made smaller, given a title and a light border (4bbc998,
  `skyboss/theme.py`).
- **A clear takes a notice as read** (badc0eb, `skyboss/todos.py`).

### Structure and tooling

- **Root tidy** (47c84c2). `shell/` moved to `electron/`. `CONTRIBUTING.md`
  and `SECURITY.md` moved to `.github/`. `tools.example.toml` moved to
  `docs/examples/`. `.github/CONTRIBUTING.md` was then marked owned (c655c5a).
- **Skeletor v0.81.2, v0.81.4 and v0.81.5** (8c32676, 2cb03a0, 9426c65).
  v0.81.4 moved coverage's data file to `tmp/.coverage`
  (`scripts/check_coverage_budget.py`). v0.81.5 made a job that names an
  artifact `failed` when neither HEAD nor the artifact moved
  (`scripts/reporting/agent_runner.py`, `docs/AGENTIC_AUTOMATION.md`).
- **Dependencies.** `pytest-asyncio` and `platformdirs` in
  `requirements-dev.txt` (41d8f3e); `globals` in the npm tooling group
  (c635937).
- **Release.** The v0.3.0 report was frozen under
  `docs/reports/releases/v0.3.0/` (26bce56).

## Risks

- **A profile's deck changed session name with no breaking marker, and saved
  decks are keyed by session.** At v0.3.0 every profile ran in the one
  configured session. Since d546c62 a profile without its own `session` runs as
  `<base>-<profile>` (`skyboss/deck.py:1562`), and saved tabs are looked up by
  session name (`skyboss/decksave.py:49`). This report found no fallback to the
  old name, read from the code and not run. A profile deck saved before
  upgrading is therefore not found when that profile next opens, and scripts
  that attach to the old session name stop finding it. The commit is a `feat`,
  so the changelog will not list it as a change in behaviour. This needs a
  ruling (migrate, document, or accept), so it is not filed.
- **The deck now rewrites a file another program owns.** `trust()` reads
  Claude Code's config at `skyboss/decktrust.py:65` and replaces the whole file
  at `skyboss/decktrust.py:77`, with no check between them, while other tabs
  may be running. A write landing in that gap is lost. The exposure is small: it
  applies only when a folder is first trusted. Filed as
  [#84](https://github.com/skyrowlabs/sky-boss/issues/84). Separately,
  `DEFAULT_PROJECT` copies the entry shape of one Claude Code version
  (`skyboss/decktrust.py:22`), and nothing here notices when that shape changes.
- **A recheck line can join an operator's draft.** The recheck is on by default
  and is typed into any `idle` or `shell` tab (`skyboss/deck.py:1350`,
  `skyboss/deck.py:1356`). The deck cannot see a half-written prompt. The plan
  already records this exposure for rulings
  (`docs/TODO/command-deck.md:1100`), but rulings follow an operator's action,
  and a recheck arrives on a timer. Each recheck also starts an agent turn.
  Whether the default should change is a ruling, so it is not filed.
- **The deck keeps growing in one module, and its tests still stub tmux.**
  `skyboss/deck.py` grew by 751 lines in this window. `tests/test_deck.py:3`
  states that no test there runs tmux, and `tests/test_deck_runtime.py:4`
  intercepts `subprocess.run` and `os.execvpe`. Several decks at once (d546c62)
  depends on how tmux sessions interact, and no test runs two real sessions.
- **Shell watch reads the process table with heuristics.**
  `skyboss/shellwatch.py` has 6 tests in `tests/test_shellwatch.py`. A wrong
  classification costs a false DECISIONS row, since the module only writes
  notes.
- **One stale path survived the root tidy.**
  `docs/implementations/commands/tools.md:11` still lists `tools.example.toml`
  in `key_files`. Filed as
  [#75](https://github.com/skyrowlabs/sky-boss/issues/75), still open.

## What is unfinished

`docs/todo_index.json` has an empty ready queue, and no open plan carries a
`queue_order`:

1. [[command-deck]]: `in-progress`, priority medium, 0 open tasks. Its
   frontmatter reads `updated: 2026-11-06` (`docs/TODO/command-deck.md:8`),
   though commits on 2026-11-08 added rounds to it (4261045, ea46108, 092b612).
2. [[deck-tab]]: `planned`, priority medium, 24 open tasks.
3. [[grid-observability]]: `planned`, priority medium, 13 open tasks.
4. [[highlight]]: `in-review`, priority low, review recorded as "pushed to
   develop".
