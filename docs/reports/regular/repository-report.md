---
commit_range: v0.3.0..HEAD
generated: "2026-11-08T04:11:51Z"
previous_release: v0.3.0
release: unreleased
status: in-flight
---

# Repository Report

> **Window:** unreleased (since v0.3.0) — `v0.3.0..HEAD` (26 commits, at `e2736c3`)



This window opened at the v0.3.0 tag (2026-11-07) and is still in flight. None
of it is in a release yet. Ten of its thirteen non-merge commits are deck work
or its plan. The other three are a skeletor upgrade, a root-directory tidy and
the v0.3.0 report freeze.

## Metrics

| Measure | Value | Source |
| ------- | ----- | ------ |
| Commits | 26: 13 non-merge, 13 merges | collected data; `git rev-list --count --merges` / `--no-merges` |
| Commits by type | feat 6, chore 5, fix 2, docs 2 | collected data. The chore count includes two merge commits titled `chore: merge …` (89d262a, 64d3154). The 11 `Merge …` commits have no type |
| Most-changed files | `skyboss/deck.py` and `docs/TODO/command-deck.md`, 8 commits each; `tests/test_deck.py`, 5; `CLAUDE.md`, 4 | collected data |
| Tree diff | 52 files, +2,071 / −129 | `git diff --shortstat v0.3.0..HEAD` |
| Test diff | 11 files under `tests/`, +429 / −10 | `git diff --shortstat -- tests` |
| Product diff | 8 files under `skyboss/` and `plugin/`, +1,202 / −84 | `git diff --shortstat -- skyboss plugin` |
| `skyboss/deck.py` | 4,571 lines at v0.3.0, 5,179 at HEAD | `wc -l` |
| New product modules | `skyboss/decklaunch.py` 280 lines, `skyboss/shellwatch.py` 199 | `wc -l` at HEAD |
| Findings in collected data | 0 | collected data |

The collected data has no coverage figure, so none is given here.

## What changed

### The deck

- **Several decks at once** (d546c62). A declared profile's deck now runs as
  its own tmux session: its `session` key, or else `sb-<profile>`
  (`skyboss/deck.py:1522`). Each pane is told its deck in `SB_DECK`
  (`skyboss/deck.py:1532`). `sb deck profile list|save|delete` manages
  profiles, and M-r saves the running deck as one. Help text and
  `.env.example` were fixed afterwards (cbdeef2).
- **A launcher before the deck starts** (dac64fb, `skyboss/decklaunch.py`).
  `sb deck` with no `--profile` at a terminal first offers the last deck to
  resume, the profiles, and the agent folders to tick, save or delete. On a
  first run it offers the folders under `roots`. M-r opens the same screen
  inside a deck.
- **A brief can live in a file** (30805f5). `[profile.NAME]` takes
  `brief_file`, read each time a brief is built (`skyboss/deck.py:217`). An
  unreadable one warns at load (`skyboss/deck.py:440`). `brief` and
  `brief_file` together are refused (`skyboss/deck.py:406`).
- **Shell watch** (d6a8902, `skyboss/shellwatch.py`). Once a minute a sweep
  looks for two kinds of shell. One is a wait loop whose `pgrep -f` pattern
  matches only itself. The other is a long unbounded shell left behind by a
  finished turn. Each is noted once in its tab's DECISIONS, and the note closes
  when the shell ends. It never stops a shell or types into a tab.
- **Rebrief on resume, clear or compact** (9e3efbb, `plugin/hooks/hooks.json`).
  The brief and `/deck-connect` now say that anything a tab waits on the
  operator for is a row.
- **Decision popup** made smaller, given a title and a light border (4bbc998,
  `skyboss/theme.py`).
- **A clear takes a notice as read** (badc0eb, `skyboss/todos.py`).

### Structure and tooling

- **Root tidy** (47c84c2). `shell/` moved to `electron/`. `CONTRIBUTING.md`
  and `SECURITY.md` moved to `.github/`. `tools.example.toml` moved to
  `docs/examples/`. `.github/CONTRIBUTING.md` was then marked owned in
  `.skeletor.json` (c655c5a).
- **Skeletor v0.81.2** (8c32676). Ported notes into `docs/DEVELOPMENT.md` and
  `.github/pyright-deps.txt`. The `ci.yml` hunk was an empty port.
- **Release.** The v0.3.0 report was frozen under
  `docs/reports/releases/v0.3.0/` (26bce56).

## Risks

- **A profile's deck changed session name with no breaking marker, and saved
  decks are keyed by session.** At v0.3.0 every profile ran in the one
  configured session, `sb` by default. Since d546c62 a profile without its
  own `session` runs as `sb-<profile>` (`skyboss/deck.py:1529`). Saved tabs
  are looked up by session name (`decksave.load(session)`,
  `skyboss/decksave.py:49`). This report found no fallback to the old name. So
  a profile deck saved under `sb` before upgrading is not found when that
  profile opens as `sb-<profile>`. This report read that from the code and
  did not run it. Scripts that attach with
  `tmux attach -t sb` stop finding profile decks. The commit is a `feat`, so
  the changelog will not list it as a change in behaviour. This needs a ruling
  (migrate, document, or accept), so it is not filed.
- **Shell watch reads the process table with heuristics.** `skyboss/shellwatch.py`
  classifies shells by their `pgrep -f` pattern and by how long they have run.
  `tests/test_shellwatch.py` has 6 tests. A wrong classification costs a false
  DECISIONS row, never a killed process, since the module only writes notes.
- **The deck keeps growing in one module.** `skyboss/deck.py` grew by 608
  lines in this window, after doubling in the last one. Its tests still stub
  tmux: `tests/test_deck.py` replaces `RUNNER`, and
  `tests/test_deck_runtime.py` intercepts `subprocess.run` and `os.execvpe`.
  Running several decks at once (d546c62) is the first change whose subject is
  how tmux sessions interact with each other, and no test runs two real
  sessions.
- **One stale path survived the root tidy.**
  `docs/implementations/commands/tools.md:11` lists `tools.example.toml` in
  `key_files`, and that file now lives under `docs/examples/`. No gate checks
  `key_files` paths. Filed as
  [#75](https://github.com/skyrowlabs/sky-boss/issues/75). A search of the tree
  found no other references to the old `shell/`, root `SECURITY.md` or root
  `CONTRIBUTING.md` paths.

## What is unfinished

`docs/todo_index.json` has an empty ready queue, and no open plan carries a
`queue_order`:

1. [[command-deck]]: `in-progress`, priority medium, 0 open tasks. Every deck
   commit in this window added a round to it. Its frontmatter still reads
   `updated: 2026-11-06` (`docs/TODO/command-deck.md:8`).
2. [[deck-tab]]: `planned`, priority medium, 24 open tasks.
3. [[grid-observability]]: `planned`, priority medium, 13 open tasks.
4. [[highlight]]: `in-review`, priority low, review recorded as "pushed to
   develop".
