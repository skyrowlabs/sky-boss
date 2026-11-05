---
commit_range: v0.2.0..HEAD
generated: "2026-11-05T04:03:36Z"
previous_release: v0.2.0
release: unreleased
status: in-flight
---

# Repository Report

> **Window:** unreleased (since v0.2.0) — `v0.2.0..HEAD` (1 commits, at `0d0753f`)



This edition closes the window that became **v0.2.0**, the first release cut by
Release Please. v0.1.0 was the only tag from the tag-versioning era, and the
manifest was seeded at `0.1.0`. The window ran from 2026-08-30 (the v0.1.0 tag,
the day the repo went public) to 2026-11-04.

## Metrics

All figures came from git over the stamped range. None were estimated.

| Measure | Value | Source |
| ------- | ----- | ------ |
| Commits | 283: 250 non-merge, 33 merges | `git rev-list --count`, `git log --merges` |
| Non-merge commits by type | chore 80, docs 79, fix 32, feat 30, ci 11, test 10, refactor 3, build 2, wip 2, style 1 | subject prefixes |
| Skeletor-scoped commits | 89, of which 52 were `chore(skeletor): upgrade` | subject scopes |
| Tree diff | 393 files changed, +55,543 / −3,480 | `git diff --shortstat` |
| Test diff | 123 files under `tests/` changed, +18,893 / −987 | `git diff --shortstat -- tests` |
| New product modules | `skyboss/deck.py` 2,257 lines, `jobs.py` 944, `agents.py` 604, `messages.py` 313, `history.py` 234, `todos.py` 225 | `wc -l` at HEAD |
| Coverage floor | 89.37% recorded (a18e818), then raised to 90.59% (fc55251) | `tests/coverage_budget.json:18` |
| Breaking-change markers | 0 (no `!` subjects, no `BREAKING CHANGE` footers) | commit messages |

## What changed

### Commands that were new in this window

- **`sb deck`.** A tmux controller over agent sessions, with one tmux session per
  agent plus NEEDS YOU, MESSAGES and TODOS panes (`skyboss/deck.py:1`). It was
  first planned and built on 2026-11-04 (2b59c96, 0ea4bc8, b591b78) and reopened
  four times that same day:
  - The controller layout with tabs and layouts (d672d9c, ee1742f).
  - Profiles declared in `deck.toml`, live tab states and a themed bar (09ef614).
  - A key table of its own, an exit, and shortcuts drawn in the bar (0e7e5ee,
    d14a1cf), plus scrolling messages and an outside toggle (ebba8f5).
  - Agent colours taken from the landing page's product hues (04bad70). The brand
    owner ruled this an exception to the canvas's brand-step rule (c7b07eb).
  - Each agent named after its tab and given a startup brief (25b769a), and
    message endpoints identified by session (747fcf5).
  - A todo list per agent in a TODOS pane (f08bdc2, `skyboss/todos.py`).
  - `sb deck brief`, which rebuilds a tab's brief from the live roster (a803c00,
    af5f2ff).
  - The `/deck-connect` skill, shipped as a plugin under `plugin/` and loaded by
    every tab through `--plugin-dir` (813a1bb, `plugin/.claude-plugin/plugin.json`).
- **`sb agents`.** Lists the agent sessions running now, across providers
  (18577b0). It also marks sessions that share a repository as an advisory claim
  (2a4841e), and its `--scope deck|outside|all` option is shared with the deck
  queue (97c15d3).
- **`sb job`.** Jobs that sky.boss issues, with systemd as the daemon. It declares
  a job and reads its state back (4524d0e), runs one without overlapping a lane
  (1437c9a), and generates units while refusing a double install (9b794b9).
- **`sb history <project>`.** A project's own run ledger, newest first (02778c0).

### Commands that existed at v0.1.0 and changed

- **`sb schedule`.**
  - Rounds 8 and 9 rebuilt the screen. It became one screen with hours, a table
    and a timeline (e89c218), one row per job with a span that narrows the whole
    screen (e291de9), and a when-column that never wraps (e234189).
  - sky.boss's own jobs now appear beside the projects' jobs, told apart by clock
    (96b9830).
- **The canvas (`sb ui`).**
  - An agents screen became a fourth nav entry (96a38d9).
  - The native window now allows text selection (348746c).
  - A window body has a right-click menu and ctrl-click links (075dc8e), and these
    also open file paths (37b583f) and executable scripts in the editor (923c44c).
  - Quiet-but-read text stopped using the structure colour `--text-3` (7379269).
- **Highlight.** A count is no longer tinted as a path (541d4d9), and a log can be
  sampled into its distinct shapes (fc381ff).
- **Rendering fixes.**
  - A resident screen frame repaints in place (f3e033c), and a long result draws
    no band inside the residency's own (4b5f629).
  - Warning text is escaped so that brackets are not read as Rich markup
    (b12a30c).
  - A named empty list is zero rows rather than a missing list (438b6fd).
- **The mark and README.** The tower was redrawn as pixel art with a rendered
  README hero (fcb9f3e), and the README was rebuilt as a landing page (ea6ce61,
  e6fa542).

### Structure and tooling

- **Skeletor adoption.** Skeletor components were taken on 2026-09-05 (fc9aeee),
  and the scaffold landed at v0.15.0 on 2026-09-06 (3173f96). The product package
  moved from `cli/` to `skyboss/` so that the scaffold's shell could own `cli/`
  (11fd9c2). Fifty-two upgrade commits then followed the template up to v0.72.2
  (9f1f410). The last upgrade switched the repo from `--versioning tag` to
  Release Please. It added `.github/release-please-config.json`,
  `.github/.release-please-manifest.json`, `VERSION` and the `release-please` job
  (`.github/workflows/ci.yml:514`).
- **Documentation lifecycle.** `docs/features/` was folded into the scaffold's
  `docs/TODO/` → `docs/implementations/<category>/` lifecycle (9bc4a7a), and
  `ideas.md` moved under `docs/research/` (9a2118f).
- **CI.**
  - `CI Gate` became a required context (e91d0c1).
  - CI now runs on direct pushes to `develop` (60e9021).
  - The Python matrix became floor and ceiling, with the floor at 3.12 (dd2384c).
  - Type-checking was added to CI (8a9ef3e), and the commit-style gate checks the
    whole range (280e551).
  - Dependabot auto-merge was first written in-tree (6f96a5e), then replaced by
    skeletor's (f2e40b9).
- **Types.** Pyright was found to be reading the package that the rename had
  emptied. Three commits fixed what it then reported (2c137fc, a4735d7, 65835d5).
- **Publication hygiene.** The host-name audit became a test (11e5255). Two later
  leaks were fixed: one in the file about not naming hosts (80c9991), and one
  where a home path was built rather than spelled (803c9fd).

## Risks

- **Python 3.11 support ended without a changelog entry.** At v0.1.0 the README
  said "Needs Python 3.11+". It now says 3.12+ (`README.md:65`). The change was
  made in a `ci:` commit (dd2384c), and `ci` is a hidden section in
  `.github/release-please-config.json`. The generated v0.2.0 changelog will
  therefore not mention a floor change that a consumer can see.
- **Release Please is unproven here.** No GitHub Release object exists for
  v0.1.0, only the git tag. The config sets neither `bootstrap-sha` nor
  `last-release-sha` (`.github/release-please-config.json`). This report did not
  verify whether Release Please will bound the first changelog at the v0.1.0 tag
  or walk further back. Read the release PR's changelog against this window's
  283 commits before merging it.
- **`sb deck` is the largest module, and the youngest.** At 2,257 lines
  (`skyboss/deck.py`), it was written and reopened four times on one day. Its
  tests replace every tmux call through `RUNNER` (`skyboss/deck.py:13`), so no
  test in the suite runs a real tmux. Its runtime also requires `claude` on the
  child `PATH` (`skyboss/deck.py:783`).

## What is unfinished

`docs/todo_index.json` has an empty ready queue, and neither open plan carries a
`queue_order`:

1. [[highlight]]: `in-review`, priority low.
2. [[grid-observability]]: `planned`, priority medium, 13 open tasks. It covers
   what sky.boss misses about skeletor's agentic grid.
