---
slug: operator-home
title: The product and the operator's content, separated
status: active   # phases 1-4 done; phase 5 is a separate session
created: 2026-08-20
updated: 2026-08-20
agent_value: 3
key_files:
  - cli/helpers.py           # TB_HOME, and the three-homes rule
  - cli/home.py              # the scaffold
  - templates/               # shipped scaffolding
  - tests/conftest.py        # the suite never reads the real home
  - tests/test_operator_home.py
  - README.md
---

# The product and the operator's content, separated

## Why

This repo currently holds two things that belong to different owners, in the same tree, in the
same git history. `cli/`, `tests/`, `docs/` and `tb` are the tool. `inventory/`, `jobs/` and
`watches/` are **jeston's**, and nobody else could ever use them.

That is not a tidiness problem. It is a leak:

```yaml
# inventory/workstation.yaml — committed
derived:
  tailnet_ip:   100.64.0.1                  # redacted; the real file has the real one
  tailnet_name: device.tailnet-name.ts.net
  board:        <make and model of the board>
```

**Sharing tackle-box today means sharing a tailnet address**, and it is one `git remote add` away
from being public. Everything else about making this a general tool is a nice-to-have; this part
is a defect that exists now, with one user.

The coupling is remarkably small. Three lines:

```python
cli/assets.py:505   INVENTORY_DIR = PROJECT_ROOT / "inventory"
cli/jobs.py:33      JOBS_DIR      = PROJECT_ROOT / "jobs"
cli/watch.py:33     WATCHES_DIR   = PROJECT_ROOT / "watches"
```

## Shape

**Three homes, one rule each — who authored the bytes.**

| Where | Holds | Authored by | Versioned |
|---|---|---|---|
| `~/tackle-box/` | code, tests, docs, templates | the project | this repo |
| `~/.tackle-box/` | inventory, jobs, watches, config | **you** | its own git repo |
| `~/.local/state/tb/` | run ledger, logs | the machine | never |

`$TB_HOME` overrides the middle one; it defaults to `~/.tackle-box/`.

**Not `~/.config/tb/`,** which is where CLAUDE.md's table currently points and where the unused
`CONFIG_DIR` constant aims. XDG's config directory is for configuration, and this is a *worktree*
— a git repo you will `cd` into, edit and commit in, and a machine record whose diff is the
maintenance log. Being buried in `~/.config/` makes that awkward. The cost is that
`~/.tackle-box/` and `~/tackle-box/` differ by one character, which will eventually bite in a
script or a tab-completion; the names are worth keeping in mind rather than the arrangement worth
changing.

**The ledger does not move.** It is the one thing here the machine writes rather than a person,
it appends on every run, and putting it in the content repo would make `git status` useless
within a day. `~/.local/state/tb/` keeps its existing reasoning intact.

**The git-diff-as-log property survives.** CLAUDE.md justifies keeping inventory and job
definitions in the repo because *the git diff is the maintenance log*, and that is still true —
they remain versioned, in a repo of their own. The same goes for the watches decision taken while
specing [[pinned-watches]]: in-repo beat a loose `watches.toml`, and it still does. Only the
repository changes.

**Absent home degrades, it does not crash.** A fresh clone has no `~/.tackle-box/`. Commands that
need it warn in yellow on stderr and return an empty result — the rule the output contract
already sets for absent config — and name the scaffold. `tb check tools` never needed it and goes
on working.

**Scaffolding writes, so it goes through `tb run`.** An internal task, `init-home`, creates the
tree and copies the templates. It is ledgered like anything else that changes the world, and it
refuses to overwrite a home that already exists.

**Templates are product, not content.** The three `_template.yaml` files move out of the content
directories and into `templates/` in this repo, where they are shipped, reviewed and versioned
with the code that reads them.

**Does not do:**

- **No fallback to in-repo content.** If `~/.tackle-box/inventory/` is missing, tb does not
  quietly read `./inventory/`. Two sources of truth for a system of record is worse than none,
  and the failure mode — editing one and having tb read the other — is silent.
- **No auto-init.** A first run does not create the home on your behalf. Writing without being
  asked is precisely what `tb run` being the only door exists to prevent, and a scaffold that
  fires from a read command would be a write path with no ledger entry.
- **No secrets in `TB_HOME`.** Unchanged and non-negotiable: external CLIs keep their own
  authentication and tb is never in the credential path. A directory that is now obviously
  "yours" is exactly where someone would be tempted to put a token.
- **No profiles.** One home per machine. Multi-host or multi-profile switching is the
  context-switching idea CLAUDE.md already rejected, arriving by a different road.
- **No moving the ledger or the logs.** See above.
- **No docs reorganisation.** `docs/features/` is uniformly build record. The thing actually
  missing from the product is a README, which this adds; whether the feature docs then want
  subfolders is easier to answer afterwards and may answer itself.

## Sequencing, and what this is a prerequisite for

Decided 2026-08-20. This split is the first step of three, and the order is not arbitrary.

1. **This feature** — product and content separated, so there is a clean thing to publish.
2. **Start a fresh history.** `git rm` moves `inventory/` out of the *working tree* and leaves it
   in `git log -p` forever, so a repo published without dealing with this ships the tailnet
   address regardless of what the split did.
3. **Move to `~/src/tackle-box`**, then add the remote.

**Fresh history rather than `git-filter-repo`, decided 2026-08-20.** Both work; the difference is
what you are left holding. filter-repo leaves you *verifying* that a rewrite caught everything —
across packfiles, reflogs, and anything the `--path` filter did not name. A fresh `git init` has
nothing to catch. At 38 hours and 55 commits that is not a trade worth agonising over.

What it costs, measured rather than assumed: commit messages total 9,801 words against 26,004 in
`docs/features/`, and the surprises are deliberately mirrored into **Notes** as they happen — the
docs are the primary record and the commits are the echo. The three docs citing a SHA
(`95a871a`, `57b0e19`) break under *either* option, since filter-repo rewrites every SHA too.

Checked before deciding, because it would have forced filter-repo's hand: **no machine detail
appears in any commit message** — no tailnet address, no `.ts.net` name, no MAC, no LAN IP. Only
the bare hostname `workstation`, which the README states openly. A `--path` filter would therefore
have been sufficient; it is simply more machinery for the same result.

The old history is bundled at `~/tackle-box-history.bundle` (313K, all 55 commits), verified by
cloning from it rather than by trusting `bundle create`. Two documents exist only there —
`tidy.md` and `workstation-baseline.md` — and both turned out to be superseded rather than lost:
respec'd into `locations.md` and `machine-baseline.md`, measurements and all. So the bundle is
insurance, not a rescue.

To be accurate about what is at stake: a tailnet address is CGNAT space routable only inside the
tailnet, and it is not a credential. What is actually exposed is the tailnet DNS name, the machine
names and the hardware — infrastructure detail nobody would publish deliberately.

**The move reverses a decision CLAUDE.md states outright:** *"It lives at `~/tackle-box` —
deliberately outside `~/src`, because it is not a product."* Adding a remote and making it
shareable is what retires that premise. It also collapses `unpushed.DEFAULT_ROOTS` from two roots
to one, since `SCAN_DEPTH = 2` finds `~/src/tackle-box` on its own — so `tb check
unpushed` starts watching tackle-box itself, which is correct.

Four things anchor to the old path and must be repaired after the move: the `~/.local/bin/tb`
symlink, eight generated systemd units carrying `WorkingDirectory=`, the fish completions, and
`DEFAULT_ROOTS`. The CLI itself needs no change — `PROJECT_ROOT` derives from `__file__` and the
wrapper resolves its own symlink, which is the whole point of that rule.

## Phases

### Phase 1 — `TB_HOME` and the seam

- [x] `TB_HOME` in `cli/helpers.py`: `$TB_HOME` if set, else `~/.tackle-box`
- [x] Repoint `INVENTORY_DIR`, `JOBS_DIR`, `WATCHES_DIR`
- [x] Fold the unused `CONFIG_DIR` into `TB_HOME` so there is one home, not two
- [x] An absent home warns once on stderr and yields nothing, rather than raising
- [x] Test: with `TB_HOME` pointed at an empty dir, every read command still exits cleanly
- [x] Test: nothing reads `PROJECT_ROOT / "inventory" | "jobs" | "watches"` any more

### Phase 2 — Templates and the scaffold

- [x] `templates/{inventory,job,watch}.yaml` in this repo; remove the `_template.yaml` copies
- [x] `init-home` in the `tb run` registry: create the tree, copy templates, print what it made
- [x] Refuse rather than overwrite an existing home
- [x] Test: scaffolding an occupied home is refused, and nothing is written
- [x] Test: a scaffolded home loads with no errors from every loader

### Phase 3 — Migration

- [x] Move the nine live files to `~/.tackle-box/`
- [x] `git rm` them here; `git init` and a first commit there
- [x] `.gitignore` the three names in this repo, as a backstop against a stray recommit
- [x] Rewrite `test_the_shipped_watches_load` — there are no shipped watches now; the templates
      are what must parse
- [x] Verify end to end: `tb info assets`, `tb check drift`, `tb auto list`, `tb tui`

### Phase 4 — Read as a product

- [x] `README.md`: what tb is, install, first run, where your content lives
- [x] CLAUDE.md § Where things live rewritten to the three homes and the authorship rule
- [x] CLAUDE.md's `~/.config/tb/` references corrected
- [x] CLAUDE.md's "deliberately outside `~/src`" reversed, with the reason it expired

### Phase 5 — Publishable (separate session)

Left for a session that is not running inside the directory being moved. Steps 2 and 3 are the
only destructive ones and neither is safe from a shell whose cwd is the repo.

- [x] Bundle the old history to `~/tackle-box-history.bundle`, verified by cloning from it
- [ ] Move to `~/src/tackle-box`
- [ ] `rm -rf .git && git init`, one commit — a fresh history with nothing to scrub
- [ ] Repair the four anchors: `~/.local/bin/tb` symlink, the eight generated systemd units
      (`tb auto install`), fish completions, and `unpushed.DEFAULT_ROOTS`
- [ ] Read the working tree once for anything that should not be published — `.env` is
      gitignored, which is a reason to look rather than a reason to assume
- [ ] Add the remote, push

## Notes

Filled in during implementation.

**Phases 1–4 shipped 2026-08-20. Phase 5 — history rewrite, move, remote — is deliberately left
for a session not running inside the directory being moved.**

**The leak was already in history, which is the fact that shapes everything after this.**
`git rm` moves a file out of the working tree and leaves every past version in `git log -p`.
`git log --all -S <the address>` finds commit `95a871a`, so publishing without a rewrite ships
the address regardless of what this feature did. That is why Phase 5 exists and why it comes
before the remote rather than after.

**`relative_to()` raises rather than degrades.** `cli/assets.py` reported a seeded record as
`path.relative_to(PROJECT_ROOT)`. The moment the path moved under `TB_HOME` that became a
`ValueError` on a success path — the kind of breakage that only appears when the command
succeeds. Found by reading the remaining `PROJECT_ROOT` uses after repointing the constants,
not by a test; the guard test now forbids the pattern that produced it.

**`WorkingDirectory={PROJECT_ROOT}` in the generated systemd units is correct and stays.** Units
run `tb`, which lives in the repo. It is the one remaining `PROJECT_ROOT` use in `cli/jobs.py`
and it is not an oversight.

**The suite was reading the operator's machine.** Two tests loaded the real `jobs/` and
`watches/` and asserted they were non-empty — which is a test whose result depends on whose
machine it runs on. They passed here and would have failed on any fresh clone. `tests/conftest.py`
now points `TB_HOME` at a temp directory before anything imports `cli`, which it must, because
`TB_HOME` resolves at import. One of the two tests turned out to be checking a rule the parser
already enforces; it now tests the parser instead of the operator's files.

**A scaffolded home is quiet because the loaders skip `_template.yaml`.** The underscore
convention already existed for exactly this and it is what makes a first run print nothing
alarming rather than a parse error per directory.

**`init-home` refuses an occupied home rather than merging.** Overwriting is the one action here
that could destroy an irreplaceable machine record, and "it was already there" does not say what
the caller intended.
