# Contributing

Thanks for looking. This is a young project and the design is still moving, so the most useful
thing you can do before writing code is read [`CLAUDE.md`](CLAUDE.md) — it is the guide for both
the humans and the agents working here, and it records *why* things are the way they are, including
the decisions that were reversed.

## Setup

```bash
git clone https://github.com/skyrowlabs/sky-boss && cd sky-boss
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
npm ci                                   # eslint and the frontend test runner
```

Python 3.11 or newer. `.venv` at the repo root is not optional: the `sb` wrapper prefers it, and
`tests/test_readme.py` runs the README's own examples through that wrapper with `PATH` pinned.

## The three checks

```bash
.venv/bin/python -m pytest -q     # the whole suite, under ten seconds, no network
npm run lint:check                # eslint, --max-warnings=0
npm test                          # node --test, the frontend's pure half
```

CI runs all three, plus pytest on 3.11 through 3.14. There is no gate job and no `paths-ignore` —
the suite is cheap enough that deciding whether to run it would cost more.

To work on the surface, `sb ui --no-browser --port 8765` and point a browser at it. Live reload
rides the session stream, so a CSS edit swaps in place and every window keeps its state. Only a
change to Python needs a restart.

## What will get a change sent back

These are not style preferences. Each one is load-bearing and most have a test:

- **`sb run` is the only command that acts. Everything else reads.** A command that wants to both
  read and write is two commands. The canvas reads this line to decide whether a window may be
  given a refresh cadence — re-running a read is a refresh, re-running a write is a scheduler
  nobody asked for.
- **Commands return data; they never print.** Everything goes through `cli/output.py` and the
  `Result` envelope. A command that prints prose has to be written twice, because the surface is a
  second consumer of that envelope.
- **sky.boss never parses human output.** `sb data` takes JSON. `sb read` shows what a command
  printed, verbatim, and says so. There is no flag that guesses.
- **No hex outside `cli/theme.py`**, in any language — a test scans `.py`, `.css` and `.js`. Tints
  are `color-mix` against an injected role.
- **The wordmark in prose, the command in code spans.** The project is **sky.boss**; `sb` is what
  you type, and it appears only inside backticks. `tests/test_naming.py` checks this.
- **No host name, home directory, or routable address in a tracked file.**
  `tests/test_publication.py` checks the shapes of those; see its docstring for why it cannot check
  the names.
- **Bound every wait, and inject the clock.** Proving a five-second cadence should not cost five
  seconds of suite.

## Docs are part of the change

A feature gets one document at `docs/features/<slug>.md`, from first sentence to done, and it moves
to `docs/features/done/` when it lands. Sections are **Why** · **Shape** (including an explicit
*"Does not do"*) · **Phases** · **Notes**.

Two rules about those documents:

- **Expand the existing doc rather than adding a new one.** A change, a new capability, or a defect
  worth designing around is a new *round* in the doc that already owns the feature. A directory
  where four files describe one thing and none is the one to read is the failure this prevents.
- **Notes accretes, never rewrites.** One dated entry per round. A superseded argument left visible
  beside its reversal is the most useful thing in one of these files.

Cross-document links are `[[slug]]`, never relative paths — including in code comments, because a
path breaks the moment that feature reopens. `tests/test_docs.py` checks that every slug resolves.

`docs/open.md` is what is decided-to-build but not decided-how; `docs/ideas.md` is *should we build
it*; `docs/design/fundamentals.md` is the constitution and settles the primitives.

## Commits and pull requests

One logical idea per commit, with all of its files. Conventional-commit subjects
(`feat(scope):`, `fix:`, `docs:`, `ci:`) — the log already reads that way. There is no commit-msg
hook, because a git hook is not cloned with the repository and could not reach you anyway.

**Cut your branch from `develop`, and open the pull request against `develop`.** `develop` is the
integration branch and the default here; `main` is what has been released. A change reaches `main`
only by `develop` merging into it, so a pull request targeting `main` is almost always a mistake —
say so in the description if you meant it.

Draft it while you iterate and mark it ready once you believe it is green; CI runs either way, on
pushes to the branch and on the pull request. The branch is deleted automatically when the pull
request merges. Merges are merge commits — squash and rebase are both off, because a branch here
is *one logical idea per commit* and squashing throws away the half of that which is the reasoning.

Say what you *ran* and what it *said*, not that it should work. If part of a change is unverified,
say which part — that is more useful than a confident summary, and it is the same rule this
project applies to its own output.

## Reporting a bug

The most valuable bug reports here describe the difference between what a command printed and what
you concluded from it. This project's most common defect class is *worked fine, told nobody*: a
command that runs perfectly and renders nothing, leaving you unable to tell absence of output from
absence of event. If something was silent when you expected it to speak, that is a bug, and it is
the one worth reporting.

Security problems go through [`SECURITY.md`](SECURITY.md), not the issue tracker.
