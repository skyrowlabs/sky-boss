# Repository Report

You are writing `docs/reports/regular/repository-report.md` for the **current
release window**.

## The window

Get it from `./dev docs release-window`. **Never** re-derive it, and never write
"since this last ran" — a window that straddles a release boundary cannot answer
the only question that matters about a finding: *is this in production now?*

Re-stamp only your own report:

```bash
python scripts/docs/release_window.py --apply --only repository-report.md
```

A bare `--apply` re-stamps every anchored report and dirties all of them.

## What to write

Sections, in this order. Each must be **falsifiable**: a claim a reader can check
against the repo, not a mood.

1. **Metrics** — from the collected data. Never hand-count; if a figure is not
   in the data, say so rather than estimating.
2. **What changed** — grouped by subsystem, with the commits that did it.
3. **Risks** — what is more likely to break than it was last window, and why.
4. **What is unfinished** — from the holding tank, in queue order.

## What not to write

- No praise, no summary of your own process, no "the codebase is in good shape".
- No finding without a location. `path:line` or it does not go in.
- No figure you did not receive in the collected data.
- If nothing meaningful changed, **say that in one line**. A report padded to
  look substantial is one nobody reads next week either.

## File what needs work

A risk that needs **work but no decision**, and that your fix policy does not let
you fix, must not live only in the report: next week's edition re-derives it and
nobody does it. File it once — the runner attributes it to this job:

```bash
./dev bug "<title>" --finding … --reproduce … --scope … --acceptance …
./dev task "<title>" --what … --why … --acceptance …
```

`bug` is for something plainly broken; `task` is for everything else.

1. **A refusal is not an error.** The command refuses a title this job already has
   open, and anything past this job's cap of open captures. Leave that finding in
   the report and say it is waiting on the queue.
2. **No acceptance criteria, no filing.** If an agent who has not read this report
   could not finish the work and know it was done, it stays in the report.
3. **Check it is still true at HEAD.** The data above was collected earlier.
4. **Highest consequence first**, when more deserve filing than the cap allows.

Filing routes work to a queue; it changes nothing in the tree, so it does not
widen your fix policy.

## Finish

1. Write the report.
2. Re-stamp it (`--only`, above).
3. Commit on the branch you are on, with no new branch:
   `docs(reports): refresh the repository report for <window>`. Your fix policy
   allows exactly this commit. Then stop: do not push, open a pull request or
   ask about merge settings. If this tree lists the job in `AUTO_PUSH`, the
   runner publishes your commit through an auto-merging pull request after
   you finish; if not, the commit stays local for the operator.
