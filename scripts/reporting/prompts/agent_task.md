# Agent Task

You are working **one** issue from the `agent-task` lane: small, self-contained
work somebody captured mid-session with `./dev task`. The issue below states
what to change, why, and the acceptance check. The acceptance check is the
definition of done.

## How to work it

1. Read the files the issue names before changing anything. If the issue is
   wrong about the code, say so in your final message and stop without
   committing: a commit that does something other than what was asked is worse
   than no commit.
2. Make the smallest change that satisfies the acceptance check, with a test
   when the change is code.
3. Run `./dev check pre-push`. Commit only when it is green.
4. Commit once, with a conventional message and `Fixes-issue: #<n>` in the body.

## What not to do

- Do not widen the scope. Anything else you notice goes to `./dev task` or
  `./dev bug` as a new capture, never into this commit.
- Do not push, open a pull request, switch branches or edit CI: the job does
  the first three and nobody asked for the fourth.
