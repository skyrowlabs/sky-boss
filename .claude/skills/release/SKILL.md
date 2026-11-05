---
name: release
description: Cut a release — drive the integration branch to a tagged release as a phased state machine across multiple turns. Preflight every gate locally, sweep docs and close the report window, open and babysit the release PR, stop for the human to merge, then freeze the reports and back-merge. Use when the user says "cut a release" or "ship it".
---

# /release — Release Train

Drives `develop` → tagged release on `main`. It is a **state
machine across turns**, not one long run: each phase ends at a checkpoint you
report, and Phase D stops entirely for a human.

**It never merges a release pull request itself** — and in a two-branch tree
there are two, below.

---

## Phase A — Preflight

Run every gate the release PR will run, locally, against the tree being shipped.

```bash
git fetch origin develop
git status --porcelain           # must be clean — a dirty tree grades the wrong thing
git rev-parse HEAD origin/develop   # must match
dev check pre-push
```

**Refuse to proceed if HEAD is not `origin/develop`.** A release gate run
against whatever branch the shared tree was sitting on reports a verdict about
the wrong code — and the error always flatters the branch being shipped, which
is the direction that ships something broken.

Report the gate table. Red → stop; name the gate and what is failing.

## Phase B — Docs and reports for the closing window

The window that is about to close is `<previous tag>..HEAD`. Get it from one
place:

```bash
dev docs release-window
```

1. Spawn the documenter with `--mode=repository-report --release=<the new tag>`
   so each in-flight report's prose describes the closing window in the past
   tense.
2. `dev docs index` — the tank and archive indexes must be current.
3. `dev check docs` — links, refs, tables, anchors.
4. Commit as one `docs:` commit.

## Phase C — Open the release PR and babysit it

```bash
gh pr create --base main --head develop \
  --title "chore(release): <version>" --body "<the changelog Release Please will generate>"
```

The title becomes the merge commit's message, and Release Please reads it as one
more commit. `chore` is a hidden section, so it adds nothing to the changelog; a
`fix(...)` title appeared in sky.boss's 0.2.0 changelog a second time.

A PR into the release branch runs **everything**. Watch it; fix what breaks; push
fixes to `develop`. Report when every check is green.

## Phase D — STOP. The human merges, twice.

Report that the PR is green and ready, with its number and URL. **Do not merge
it.** Admin enforcement is deliberately off on the release branch precisely so
this step is a human's.

**That merge does not publish anything.** It is a push to `main`,
and on that push the release job opens a **second** pull request — Release
Please's own, titled `chore(main): release <version>`, from
`release-please--branches--main`, authored by whichever App or
token the release job used, carrying the version bump and the changelog. The tag
is published when *that* one merges.
Watch for it, report its number and URL, and stop again: it is a human's merge
for the same reason. This phase used to end at "watch for the tag", which reads
as though the first merge produces one; no release pull request had ever opened
in a tree scaffolded from here, so nothing showed the gap.

## Phase E — Close the window

Once the tag lands:

```bash
dev docs freeze-release --tag <tag>   # archive editions, re-anchor regular/, rebuild the index
```

Then back-merge, so `develop` carries the release commit and the next
release PR does not re-propose it:

```bash
git switch develop && git merge --no-ff main
```

Report: tag, what shipped, where the frozen editions went, and anything left
open.

---

## Rules

1. **One phase per turn.** Each ends at a checkpoint you report; the user
   decides whether to continue.
2. **Never merge any release pull request.** Phase D says how many there are.
3. **Never hand-edit `CHANGELOG.md` or `VERSION`.** Release Please owns both.
4. **Never edit a frozen report edition.** Corrections go in an `## Errata`
   block on the current in-flight edition.
5. **A red gate stops the train.** Do not proceed "to see if CI agrees" — CI
   agreeing would only mean two runs of the same wrong thing.
