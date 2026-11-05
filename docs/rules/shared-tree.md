# Shared Working Tree Rules

Applies to anything that runs `git switch`, `git checkout` or commits in the
primary checkout — agents, scheduled jobs, and interactive sessions alike.

## The Rule

**Never change the branch of a tree you did not create.**

The primary checkout is shared. Another agent may be mid-edit in it right now,
and a `git checkout` underneath them destroys uncommitted work **with no error**
— the files are simply gone. It also lands your next commit on their branch.

If you need a different branch, get a different tree:

```bash
dev worktree new <branch>     # its own checkout, its own .env, its own stack
```

## The Three Cases

| You want to                                | Do                                                  |
| ------------------------------------------ | --------------------------------------------------- |
| work on another branch                     | `dev worktree new <branch>` — never switch in place |
| return a shared tree to the base branch    | `reset_to_base()` — it refuses when unsafe          |
| commit in a tree others share              | `dev commit` — never plain `git commit`             |

## Why `dev commit`

pre-commit **stashes every unstaged change in the repo** while its hooks run. In
a shared tree that deletes another agent's in-flight work from disk for the
duration, and silently discards anything they write in that window — including
on files your commit never touches.

`dev commit -m "<msg>" <paths>` runs the same hooks against **only the paths you
name**, then commits with `--no-verify`, so no stash ever happens.

```bash
dev commit -m "fix(worker): stop retrying a rejected job" worker/queue.py tests/test_queue.py
dev commit -m "..." --dry-run <paths>   # run the checks without staging or committing
```

Never `git add -A` or `git commit -a` in a shared tree: stage and commit only
the paths you touched.

## What Enforces It

Advisory records, one refusal, and one guard. Nothing blocks an interactive
`git checkout` — a lock that can refuse the owner's own command is a lock people
learn to route around.

**`scripts/tree_lock.py` records holds.** Two kinds, because they make different
things unsafe:

| Kind    | Taken by                            | Makes unsafe                          |
| ------- | ----------------------------------- | ------------------------------------- |
| `suite` | test runs, PR gates, stack jobs     | writes under mounted paths, **and** the branch |
| `edit`  | `dev commit`, editor sessions       | the branch only                       |

The `edit` hold exists because the incident this rule came from had **no suite
running** — just an editor and a `git checkout`. A clean `git status` is not
evidence that nobody is working here.

**`would_strand(branch)`** turns those records into a refusal reason, or `None`.
It ignores stale records (a crashed holder must never wedge the tree) and our
own pid, and it **refuses on a branch it cannot read** — a false refusal costs
one retry, a false clearance costs somebody's work.

**`dev commit` reads the branch twice** — once before its checks, once
immediately before staging — and refuses if it moved. The checks take tens of
seconds; that window is the whole exposure.

## Refuse, Don't Warn

A job that declines records red and skips a cycle. Nothing you were doing stops.
A job that warns and proceeds produces a **verdict**, and a wrong verdict is
read as a right one — the two outages behind this rule both had a scheduled job
grade whatever branch the tree happened to be sitting on and report green while
the real base branch was failing. Both errors flattered the base branch, which
is the direction that ships something broken.

## If a Job Refuses

```bash
dev worktree holders     # who is holding the tree right now
```

- **A live holder** — wait, or use a worktree. That is the mechanism working.
- **A stale holder** (its pid is gone) — already ignored, and swept before the
  next acquire. One that persists is a bug worth capturing.
- **Uncommitted work in the tree** — it belongs to somebody. Never
  `git checkout -- .` or `git stash` it away to unblock a job. An unattended run
  that resolves an anomaly by deleting the evidence is worse than one that stops.
