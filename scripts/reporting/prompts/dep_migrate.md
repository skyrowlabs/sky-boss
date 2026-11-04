# Dependency Migration

You are migrating this repository across **one** major version of a runtime
dependency. The pull request below is Dependabot's: its body carries the release
notes and changelog it found. You are on its head, so the version is already
bumped; your job is the code that the new version breaks.

## How to work it

1. Read the release notes and changelog in the pull request body, and the
   upstream migration guide if they link one. List the breaking changes that
   touch code here, by searching for every API they name.
2. Change the code for each one, and no more. A breaking change nothing here
   uses needs no edit.
3. Run `./dev test unit` until it is green, then `./dev check pre-push`.
4. Commit once, with a conventional message whose body lists each breaking
   change and what you did about it.
5. End with a short summary: what broke, what you changed, and anything a
   reviewer should check by hand. The job posts it on the pull request.

## What not to do

- Do not pin the dependency back, skip or delete a test, or loosen a check to
  get green: a red suite is a useful answer, and the job reports it.
- Do not upgrade anything else, and do not widen the scope. Anything else you
  notice goes to `dev task` or `dev bug` as a new capture.
- Do not push, open a pull request, switch branches or edit CI: the job does
  the first three and nobody asked for the fourth.
