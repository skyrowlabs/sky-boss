# Agentic Automation

The project's **self-maintenance system**: registered jobs that watch the repo,
form a judgement about what they find, and act on it.

Each job pairs a **deterministic collection stage** (stdlib Python, no
dependencies, same answer twice) with an **agentic triage stage** — a headless
agent that reads the collected data, makes the calls a script cannot, writes a
report, and commits it.

The separation is the design. A job that skips collection and asks an agent to
go and look produces a different answer every night, and none of them are
reproducible.

---

## The live schedule

The schedule is **generated from one registry** —
[`scripts/reporting/jobs.py`](../scripts/reporting/jobs.py) — and rendered by
`dev report cron --print`. That registry is the source of truth for the crontab,
the `dev report` subcommands, and the status viewer, so those three cannot drift
apart (`tests/test_reporting_jobs.py` asserts it).

```bash
dev report cron --print    # emit the block for `crontab -e`
dev report cron --install  # replace this tree's block; every other line is kept
dev report cron --check    # does the LIVE crontab match the registry?
dev report watch           # what ran recently, and what it decided
```

**Any table in this document is documentation; the registry is the system.**
Never hand-copy a schedule from prose into a crontab, and remember that
*registered* is not *installed in your crontab*. When the two disagree,
`cron --check` tells you which one your machine is actually following.

## The lane drainers, and standing down for free

`agent-task` and `agent-fix` work the capture lanes `dev task` and `dev bug`
file into: one issue per run, oldest first, on a branch named
`agent/<lane>/<issue>`, opened as a **draft** pull request for a person to
review. Both live in `scripts/reporting/drain.py`, and they ship switched off in
`scripts/reporting_schedule_allowlist.yaml`. Turning one on means deciding who
reviews its pull requests.

Most nights a lane is empty, so the empty check runs before any agent and costs
a `gh issue list`. An empty lane is `declined`, with a ledger row and a
heartbeat; a lane GitHub could not answer for is `failed`, because "I could not
look" is not "empty". An issue that already has an open draft from its drainer,
or that has failed three times, is skipped. The attempt count is a marker comment
on the issue itself.

`dep-migrate` drains a different queue, and it also ships switched off.
`dependabot-auto-merge.yml` merges patches, minors and dev-tool majors itself,
and labels a runtime major it holds `dependabot-runtime-major`. Each night the
job takes the oldest one, branches from Dependabot's head as
`agent/migrate/<pr>`, and has the agent migrate the code, capped at
`--max-turns`. Then the job runs `dev test unit` itself. Green opens a draft
pull request linking Dependabot's, which stays open. Red opens nothing: it
comments the agent's notes on Dependabot's pull request and labels it
`migration-failed`. A bump that needs no change is labelled
`migration-not-needed`. Either label takes the pull request out of the queue.

Every agent runs as a **seat**, one of `SEATS` in `scripts/reporting/jobs.py`.
The generated cron block sets `SB_SEAT`, and `cron --check` is
red without it. `personal`, the only seat shipped, is whoever is logged into
`claude` and `gh` on the host. An automation seat names the variables holding
its Claude and GitHub tokens, and refuses to run when they are unset rather than
falling back to `personal`. Each ledger row records the seat that ran.

Every job starts `schedule_offset()` minutes after its slot, from a hash of the
checkout's path, so checkouts sharing one host's crontab do not all start at
once. Set `SCHEDULE_OFFSET_PINNED` in `jobs.py` to choose it, or 0 to turn it off.

`dev report <key> --dry-run` runs any job's deterministic stage, says what
the agent stage would do, and records nothing.

`overnight` has no agent. Every night it writes `tmp/reporting/overnight.md`:
what failed, what is overdue, or that the night was idle, because "no digest"
reads the same as "the jobs died".

`dev report status --json` is the machine view: every job's last result,
its age, whether it is overdue against its cron schedule, and its next run.
sky.boss reads that envelope, so adding a tree there is a `projects.toml` entry.

## The grid is load-bearing

Two rules generate it, and both are about a resource nothing locks: **one shared
working tree**.

1. **Only one committing job in flight at a time.** Nearly every job spawns an
   agent that edits and commits the same tree, and several regenerate the same
   derived docs. Run concurrently, they race on git and on those files — and the
   loser's work vanishes with no error. Jobs that commit nothing may share a
   window.

2. **Weekly work is partitioned by weekday.** One lane per weekday, sized at
   several times the observed run length. The margin is the point: a block sized
   to today's runtime is a bet that runtime never grows, and it leaves no room
   for the next job. Scheduling as a mutex only works while somebody re-derives
   the whole grid each time a job is added — and that is exactly what stops
   happening.

The nightly spine is a **pipeline**: agents commit → a gate checks what they
committed → a repair job fixes what the gate found → a digest reports the night
as a closed set. Putting the heavy agents *after* the gates would leave every
agent commit ungated until the following night.

## Detection latency should match consequence latency

This is the rule that decides where a check belongs. Nothing on the integration
branch reaches a user until a release, so **a check belongs on a nightly (or on
the release train) unless its cost grows before then**. Two kinds of thing do
grow, and stay fast:

- A **whole-project** gate, where one error blocks every commit repo-wide.
- **Security advisories**, where the window is the exposure.

Everything else is detection at ≤24h, and that is a deliberate trade, not a gap.

## A job that cannot answer correctly declines

`declined` is a first-class outcome, distinct from `failed`. A job that finds the
tree on the wrong branch, or holding somebody's uncommitted work, **stands down,
records why, and still pings its heartbeat** — because a job that executed and
chose not to answer must stay distinguishable from a dead cron.

**Refuse, don't warn.** A job that declines costs you a cycle and nothing else. A
job that warns and proceeds produces a **verdict**, and a wrong verdict is read
as a right one. The two outages behind this rule both had a scheduled job grade
whatever branch the shared tree was sitting on and report green while the real
base branch was failing — and both errors flattered the base branch, which is
the direction that ships something broken.

## Two rails on the outcome record

Enforced once, in [`run_ledger.py`](../scripts/reporting/run_ledger.py), so a new
job cannot forget them:

- **A job whose agent never ran must not report `ok`.** A collection stage that
  succeeded and a triage stage that never started look identical from outside,
  and the second is a job that has quietly stopped working.
- **A red gate may not report `ok`.** A job that finds a problem and records
  success has inverted its own purpose.

## Remediation — what a job may fix itself

Every job carries a `fix_policy`, and it **defaults to `none`**. A job added
without thinking about blast radius gets no autonomy rather than inheriting
whatever the entry above it had.

| Policy       | May                                                          |
| ------------ | ------------------------------------------------------------ |
| `none`       | Report only; never write to the repo                         |
| `own-report` | Write and commit its own report file, nothing else           |
| `docs`       | Repair generated docs and commit them                        |
| `code`       | Open a pull request; never merge, never push to a protected branch |

The policy is passed to the agent **explicitly** in its prompt — an agent that
does not know its blast radius will pick one. What exceeds the policy is
escalated as a finding, not acted on: an unattended change nobody authorised is
worse than a finding nobody acted on.

## Which agent runs the triage stage

The collection stage is deterministic Python with no dependencies. Only triage
shells out, through one argv template:

```bash
# the default, and the only invocation tested here
SB_AGENT_CMD='claude -p {prompt} --permission-mode acceptEdits --output-format json'
```

`--output-format json` is what puts `cost_usd`, `num_turns` and `tokens` on each
ledger row. An agent that prints anything else still runs; its rows carry
`null` there, which reads as "not measured" rather than as free.

`{prompt}` is replaced with the whole prompt and the argv is executed directly,
never through a shell — so `codex exec {prompt}` and
`aider --yes --message={prompt}` both work as shapes.

**There is deliberately no table of supported agents.** Nothing in this
repository can test one, and an adapter that is subtly wrong fails unattended at
03:15, which is the one place the failure is invisible. Before pointing this at
something else, satisfy the contract in `scripts/reporting/agent_runner.py` —
above all: **exit non-zero unless the agent actually did the work.** The ledger
records `ok` on a zero exit, and its central rail is that a job whose agent
never ran must not report `ok`. An agent that exits 0 after refusing the task
inverts that rail, and the ledger then reports health it has no evidence for.

A template with no `{prompt}` token is refused rather than run: an agent invoked
with no instruction starts, does nothing, and exits 0 — the failure that looks
most like success.

## cron does not give you your login PATH

A job that works in your shell and not under cron is almost always this, and it
fails by not finding an interpreter — which reads as a broken job rather than a
broken environment. The generated crontab block sets `PATH` explicitly for
exactly this reason; `tests/test_reporting_jobs.py` asserts it still does.

---

## Adding a job

1. Add a `Job(...)` entry to `scripts/reporting/jobs.py`. **Decide its
   `fix_policy` explicitly**, and if it writes a report, its `findings_sink`:
   where a finding goes that the job may not fix. Name the prompt file after the
   module (`prompts/<module>.md`) — that is how the policy is resolved.
2. Write `scripts/reporting/<module>.py` with a `main()`: deterministic
   collection, then `agent_runner.run_triage(<key>, collected)`. Shell out
   through `scripts/reporting/shellout.py`: cron's `PATH` can lack the tool,
   and a bare `subprocess.run` then raises instead of returning a code.
3. Write `scripts/reporting/prompts/<module>.md`. State what **not** to write as
   explicitly as what to write — an unconstrained report is padded to look
   substantial and is not read next week either.
4. Add its heartbeat variable to `.env.example`.
5. If it writes into `docs/reports/regular/`: **seed the report file** and add
   its filename to `ANCHORED_REPORTS` in `scripts/docs/release_window.py`, so
   the window is stamped and the release freeze archives it. Then have the
   prompt re-stamp **only** that report (`--apply --only <name>.md`) — a bare
   `--apply` dirties every anchored report, and a job that then commits just its
   own leaves the rest claiming a refresh that never happened.
6. If it should not be scheduled yet, add it to
   `scripts/reporting_schedule_allowlist.yaml` **with a reason**. Otherwise
   re-run `dev report cron --install`.

Steps 1–5 are cross-checked by `tests/test_reporting_jobs.py`, and step 2's
shell-outs by `tests/test_reporting_shellout.py`. Only step 6's
crontab half is unenforceable from here — it is a change to a crontab on a host
this repo cannot see.

---

## What this is not

It is not a replacement for review, and it is not a way to get more work done
unattended. It is a way to make the repo's **slow-moving problems visible on a
schedule** — the ones nobody would ever choose to look for on a Tuesday, and
which are therefore found by accident, late, or never.
