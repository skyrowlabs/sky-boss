# Agent Fix

You are fixing **one** defect from the `agent-bug` lane: something found
mid-session and captured with `./dev bug`. The issue below gives the finding,
an exact reproduction, the scope and the acceptance check.

## How to work it

1. Run the reproduction first. If it does not fail, say so in your final message
   and stop without committing: a fix for a defect you could not see is a guess.
2. Write the failing test, then the fix. The test is what stops it coming back.
3. Stay inside the issue's scope. What it calls out of scope stays out.
4. Run `./dev check pre-push`. Commit only when it is green.
5. Commit once, with a conventional `fix:` message and `Fixes-issue: #<n>` in
   the body.

## What not to do

- Do not fix a second defect you noticed. File it with `./dev bug` and leave it.
- Do not push, open a pull request, switch branches, or weaken a test or a
  gate to make the suite pass. The job opens the draft PR, and a person reviews it.
