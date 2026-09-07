---
title: Adopting skeletor as a scaffold
slug: skeletor-adoption
category: tooling
agent_value: 3
completed: 2026-09-06
updated: 2026-09-06
tags: [skeletor, scaffold, ci]
summary: Converts sky.boss from a skeletor component consumer into a scaffolded tree, and records what a fork can and cannot learn about itself.
created: 2026-09-06
key_files: [.skeletor.json, skyboss/, cli/]
---

# Adopting skeletor as a scaffold

## Why

sky.boss is a **component consumer**: nine files taken one at a time, recorded in
`.skeletor-components.json`, with no `.skeletor.json` and therefore no
`skeletor-upgrade`. That mode has a ceiling, and [[open]] has been circling it for
two weeks. The ceiling is not that upgrading is manual — it is that **a component
consumer is never told a gate exists.**

That was measured rather than argued. On 2026-09-06 a dead `import os` in
`scripts/paths.py` turned out to be an instance of a class: a scaffolded tree
receives skeletor's `ci.yml` alongside its scripts, and that workflow runs
`flake8 --select=E9,F63,F7,F82,F401`. This tree took the scripts and no workflow,
because a workflow is the least portable thing in a template. **The artifact
arrived; the check that kept it honest upstream did not.**

> Adoption granularity and safety granularity are different. A file is
> adoptable; the invariant that made it correct may not be.

The tidiest instance is not the import. `skyboss/canvas/shell.py` has carried two
`# noqa: F401` annotations since 2026-08-20 — correct suppression syntax, written
by somebody who knew the rule, for a linter that has never run in this repo.
**The convention travelled and the enforcement did not**, and a reader of that
file would reasonably conclude it was covered.

Scaffolding does not fix that by magic. What it buys is one thing: a
`.skeletor.json` that makes `skeletor-upgrade` possible, so the next invariant
skeletor writes arrives *with* its gate instead of being copied without one.

## Shape

**Scaffold at `--tier core`, `--versioning tag`, `--cli dev`, from tag `v0.15.0`.**

The one structural change, and everything else follows from it:

| | Before | After |
|---|---|---|
| Product package | `cli/` | `skyboss/` |
| Product CLI | `./sb` | `./sb` (unchanged) |
| skeletor's shell | — | `cli/`, run by `./dev` |

**Why the product moves rather than the shell.** skeletor's package path is
hardcoded `cli/` — `--language` says so outright: *"cli/, scripts/ and tests/ are
python and ship at every tier"*. There is no `--package` flag; sky.boss named one
as the precondition for adoption in `fc9aeee` and it still does not exist.

So one of the two has to move, and the measurement settles which. Scaffolding
over the tree as-is overwrites **21** files including `cli/__init__.py`,
`cli/helpers.py`, `cli/__main__.py` and `sb` — the product's spine. Renaming the
product first drops that to **17, none of them product code.**

The four that disappear are not merely four merge points. Keeping our
`cli/__init__.py` means every future `skeletor-upgrade` three-way merges *a dev
shell's root group into a product's root group*, forever, on the most-edited file
in the repo. They are not the same kind of file and never will be. The rename
buys clean merges in perpetuity, which is the whole point of adopting.

**`--cli dev` keeps the act/observe split intact by construction.** skeletor's
`cli/__init__.py` auto-registers by discovery: any module in the package
exporting a Command lands on the root group. Had both lived in one package,
`check`, `docs`, `bug` and `test` would be top-level commands on `sb` — and
`/api/catalog` walks the real Click tree, so they would appear in the canvas
palette as launchable windows. Four dev **acts** on a surface whose whole
contract is that only a read may be given a cadence. Two wrappers, two roots,
no adjudication needed.

**Does not do:**

- **No `agentic` tier.** It ships a crontab and reporting jobs. This repo has
  `sb job` on systemd and a standing rule that it does not own another repo's
  scheduler; a second one installed by a template is that rule broken quietly.
- **No `governed` tier.** dependabot, CODEOWNERS and issue templates already
  exist here from going public, and `coverage-nightly.yml` needs `pytest-cov`,
  which is not a dependency. A gate that cannot run is what `d71deeb` removed.
- **No Prettier**, kept from `docs/rules/javascript.md`. `htm` is a
  template-literal parser, so a `/* … */` inside a tag is parsed as attribute
  text and **silently removes that element's children** without throwing. A
  formatter that reflows those templates is that bug with write access.
  skeletor's own `SETUP_GUIDE.md` cites this refusal as its worked example of a
  rule that is true there and wrong here.
- **No `AGENTS.md`.** `CLAUDE.md` is this repo's single guide and the thing every
  session reads first. Two files claiming that role is the drift this repo spends
  most of its effort preventing.
- **No history rewrite** and no re-recording of what the components already say.
  `.skeletor-components.json` stays: it records what was taken before there was a
  manifest, and deleting it would make nine files look scaffolded that were not.
  *(Reversed in round 8 — the scaffold manifest turned out to track all eleven of
  those files itself, at a newer ref, so nothing was lost by deleting it.)*

## Phases

### Round 1 — the rename (2026-09-06)

Independent of skeletor and correct on its own terms; a scaffold that lands on a
half-renamed tree is unreviewable.

- [x] `cli/` → `skyboss/`, 494 import sites, 39 config references, 313 prose
      references, and the `sb` wrapper's `python -m`.
- [x] Suite green, both gates green, eslint green, and `sb` exercised for real —
      not only imported.

### Round 2 — the scaffold (2026-09-06)

- [x] `skeletor-new --force --cli dev --tier core --versioning tag` from `v0.15.0`.
      108 files written, 17 overwritten, `.skeletor.json` recording `v0.15.0`.
- [x] Review the printed overwrite list file by file. Nine kept, eight taken.
- [x] Baseline the ratchets at what was inherited, never at zero.
- [x] `./dev` runs; `sb` unchanged and verified from outside the repo.

### Round 3 — suites and CI (2026-09-06)

**16 inherited tests are red and they are all one thing.** skeletor's CI model is
marker-selected suites — a `gate` job, then `unit`, `integration` and `ui` jobs
each running `pytest -m <marker>` — and `tests/test_ci_runs_every_suite.py` scans
the workflows for those selections. sky.boss has **no markers at all**: 1485
tests in one flat suite that CI runs whole.

- [x] Backfill markers. This is the work, not overhead — it is the first time
      anyone writes down which of these tests need a stack up.
- [x] Restructure `ci.yml`. **This is the step with a consequence outside the
      repo.** Branch protection on `develop` *and* `main` requires exactly
      `eslint`, `pytest 3.12`, `pytest 3.14` — read from the API, not assumed.
      skeletor's `ci.yml` names its jobs `CI Gate`, `Lint & Types`,
      `Unit Tests (host-side)`. Adopting it wholesale means those three contexts
      never report again, and a context no job reports blocks every pull request
      for ever, on both branches. Either the merged workflow keeps producing all
      three names, or branch protection changes in the same sitting.
- [x] Land any new gate as a non-required check first — `verdict` is added and
      required by nothing.

### Round 4 — the lint backlog (2026-09-06)

`./dev check pre-push` is green on flake8, output discipline, docs, commit
subjects, unit tests and the skip budget. Three gates are red and none of them
is a test:

| Gate | Red on | Shape |
|---|---|---|
| `black` | 51 files — 20 `skyboss/`, 30 `tests/`, 1 `docs/` | **done** |
| `isort` | import ordering | **done** |
| `pyright` | 259 errors | **open** — a typing backlog, not a formatting one |

Every one is **ours**; the scaffolded files arrive conforming. This is the state
`SETUP_GUIDE.md` predicts — *"the shell assumes a green tree; an existing repo is
not green"* — and it is deliberately not fixed in the same commit as the
adoption. Reformatting 51 files is a decision about the repo's style, not a
consequence of scaffolding, and burying it inside an adoption diff would make
both unreviewable.

## Notes

**2026-09-06 — why this reverses a decision, and what changed.**

sky.boss ran this procedure once before and declined. The measurement is recorded
in skeletor's own `SETUP_GUIDE.md`: *twelve permanent merge points against
seventeen one-line declines.* Re-measured today against the tree as it now stands,
the figure is **21 overwrites**, so the cost has not improved — it grew.

What changed is not the cost. It is that the *reason* for the cost became
visible: the `# noqa: F401` finding showed that a component consumer cannot
discover an invariant it did not take, and the twelve merge points were always
the wrong number to be looking at. The right one is the count of gates this tree
believes it has and does not.

**The decision that was never available before is the rename.** The earlier
evaluation treated `cli/` as fixed and measured what a scaffold would do to it.
Moving the product out was ruled out in `fc9aeee` on the ground that it meant
"a package rename across 494 import sites" — true, and it was measured today
rather than estimated: a crude four-pass sweep in a scratch clone reached
**1267 of 1283 tests passing**, with the residue being string paths and
subprocess invocations. Mechanical, bounded, and reviewable in an afternoon.
The number that blocked this was never checked.

**A synthesised `.skeletor.json` was considered and is not an option**, on
skeletor's own ruling in `bin/skeletor-components`: `cross_check` compares the
manifest against the base *render*, never against the tree, so a synthesised one
passes trivially and the upgrade then three-way merges against an ancestor that
never existed. `git merge-file` does not refuse a fictional base. **The clean
merges are the damage**, written silently under `✅ merged cleanly`. There is no
retrofit; there is only scaffolding for real.

**Scaffolded from the tag, not from `HEAD`.** skeletor is five commits past
`v0.15.0`, clean and pushed, so `b8c337b` would have been resolvable. The tag was
taken anyway, for two reasons: `SETUP_GUIDE.md` step 0 says to, noting sky.boss
got this wrong on its first attempt; and Jeston's standing policy as of today is
to upgrade on a minor or above and never for a patch alone, which makes the tag
the unit of decision. Taking the tag also makes the first `skeletor-upgrade` a
real exercise of the mechanism this whole change exists to acquire, rather than a
no-op.


**2026-09-06 — Round 2 landed, and what the red tests actually mean.**

`--force` overwrote 17 files. Nine were kept and eight taken, and the two
decisions worth recording are the ones that went the *opposite* way to the plan.

`tests/conftest.py` was **merged, not chosen.** skeletor's version has the CI
gate helpers the newly-scaffolded tests import; ours has the `SB_STATE`,
`SB_HOME` and `SL_AGENT_LOGS` redirects that keep 1485 tests off the operator's
real directories. Taking either whole would have been wrong, and taking
skeletor's is precisely the silent loss `SETUP_GUIDE.md` says this repo already
suffered once.

`scripts/paths.py` was **taken whole, retiring a divergence rather than
carrying one.** The plan assumed we would keep our trimmed copy. Both reasons
for the trim had expired: the docs-lifecycle constants named directories that
did not exist and now do, and `STATE_ROOT_DEFAULT` was a hardcoded workspace
layout under the operator's home when it was cut — it is `~/.local/state/…`
upstream since v0.9.0. Keeping the trim would have been a permanent merge point
maintained for a reason that stopped being true. It also *unblocked* `./dev`,
which cannot import `cli/docs.py` without `IMPL_DIR`.

This reverses the recorded line that sky.boss has no `SB_STATE_ROOT` and never
will. It has one now, at the scripts layer, distinct from the `SB_STATE` that
`skyboss/helpers.py` owns. The old ruling was made against a default that leaked
a home layout into a public repo; that default is gone.

**Two gates found each other, which is the argument for adopting in one line.**
Our own `test_publication.py` failed on skeletor's
`scripts/check_source_doc_refs.py`, whose comment named two home-anchored build
directories while explaining false positives from matching absolute paths. They
identify nobody, so it was one; reworded there, and worth sending upstream since
every adopter with a publication gate will hit it. Note this paragraph had to be
reworded too — the first draft quoted the literals and tripped the same gate,
which is the shape `test_naming.py` already masks code spans to avoid: **a gate
cannot tell prose about a pattern from the pattern.** And skeletor's
`cli/helpers.py` broke *our* `test_imports.py`, because it re-exports eleven
names through `__all__` and this tree had no `__all__` when that gate was
written. pyflakes counts an `__all__` entry as a use; ours did not. Fixed, and
re-verified against flake8 — both now report zero across the merged tree.

That is the thing a component consumer cannot buy: neither gate could have found
the other while the two halves lived in different repositories.


**2026-09-06 — Round 3, and the two-configs bug it surfaced.**

The sixteen went green without a single test being weakened, and the route
through each is worth keeping because four of them were the *instrument* rather
than the tree.

**Markers.** 37 files got `pytestmark = [pytest.mark.unit]`. `integration` and
`ui` are declared `scheduled=False, unscheduled="empty"` — true here, and the
reason expires by itself the moment one test carries either marker. Nothing was
marked to make a gate quiet.

**`ci.yml`.** A `gate` job, `ready_for_review`, marker selection, and a `verdict`
job that `needs: [gate, test, lint]`. That last one exists because
`test_pre_push_covers_ci.py` derives *blocking* from `needs:` — with no edge
pointing at them, the pytest matrix and eslint were invisible to the scan, which
found nothing and had nothing to hold `pre-push` against. **A gate nobody
depends on is not a gate.**

The reversal to state plainly: this file used to argue there was no cost gating
and that it was deliberate. The `gate` job now exists and **still gates
nothing** — the three contexts branch protection requires must never report
`skipped`, because branch protection accepts that and the PR merges having
proven nothing. The verdict job consumes `full_suite` to *report* it. That is
one assertion passing on a technicality and it is said out loud in the workflow
rather than left to be discovered.

**Three false positives, all in skeletor's gates, all reported rather than
worked around silently:**

1. `test_setup_blocks_agree.py` scans CI with `pip install\s+-r\s+(target)`,
   anchored on `pip install`, so it captures only the **first** `-r` on a
   command. Three targets on one line read as one, and the gate said CI never
   installs the toolchain it does install. Split one per line.
2. `test_docs_name_real_paths.py` and `test_docs_name_live_code.py` read
   `docs/features/done/` as a description of the tree as it is now. It is a
   dated archive — this repo's rule is that such docs are never scrubbed — so it
   is appended to `NARRATIVE`, which is the extension the template documents,
   *as an append*, because editing the tuple conflicts on every upgrade and an
   append is line-disjoint forever.
3. `check_source_doc_refs.py` flagged `docs/plan.md` and
   `docs/AGENTIC_AUTOMATION.md` in `skyboss/highlight.py` and its tests. Those
   are **highlighter fixtures**: the module tints by shape, so its samples must
   contain path-shaped text to prove a path gets tinted. Exempted in
   `.validate-ignore`, which names test fixtures as legitimate. Pointing them at
   real documents would be worse — the fixture would then depend on a document
   existing for a reason unrelated to what it tests.

**And one real bug, found only by running the shell rather than the suite.**
`pytest -q` was green at 1500 while `./dev test unit` reported **8 failures**:
every `async def` in the canvas suite was collected and not run. `tests/pytest.ini`
is a second config that wins once `tests/` is passed as a path, and it had no
`asyncio_mode`. Root `pytest.ini` had been folded into `pyproject.toml` — itself
because two config sources meant `--strict-markers` and the marker registry were
inert from the moment the scaffold landed — and this third copy was missed.

> **A config that only applies on one invocation is only tested by that
> invocation.** Both commands were "run the tests" and only one of them ran them.

That is the same class as everything else this week, and the suite could not
see it: it *was* the thing being mis-run.


**2026-09-06 — Round 5: the first upgrade, which is what this was all for.**

`v0.15.0` → `v0.16.0`, from a clean clone pinned at the tag rather than from the
sibling checkout, which carries an untracked file and is another session's.

**One conflict, and it was the expected one:** `ci.yml`, hand-merged in round 3
to keep three branch-protected context names reporting. The upgrade left it
alone, wrote the template's diff to `tmp/upgrade/`, and **did not advance the
base** until it was ported — which is the behaviour that makes the mechanism
worth having. It also correctly did **not** restore `.github/CONTRIBUTING.md`,
deleted in round 2 as a duplicate of the root one: a deletion is a decision, and
it is reported as standing state every run instead of being silently re-made.

**Half the patch did not apply, and reporting that as "not applicable" would
have been the failure this whole adoption exists to prevent.** v0.16.0 converts
a flake8 step from `continue-on-error:` to `|| true` — and this workflow had no
flake8 step at all. The gate was simply missing, while `dev check lint` ran it
locally and looked green. So the blocking set is now a CI step here, pinned to
one matrix leg because the rule set is a property of the source rather than of
the interpreter — running it on both is dream-doll's eslint-twice, one file over.

The **informational** step beside it upstream is deliberately not taken. That is
the complexity pass, and it is the thing `v0.16.0` exists to fix: *a channel
whose severity does not mean what it says*. This repo has no complexity budget
to report against, so taking it would import a miscalibrated surface and nothing
else. Taking half a patch on purpose is only honest if the half you drop is
named — that is what this paragraph is.

The other half applied and was worth having: `actions/setup-node` was on `@v5`
where the template moved `@v4` → `@v7`. Checked against the action's own tags
rather than assumed — `v7.0.0` is current — so this tree was two majors behind
on a pin nobody was looking at. **An adopter can be current on the template and
stale on the tools**, which is the workspace's framing of exactly this, and it
argues for `skeletor-check-pins` being run on a cadence rather than at upgrade
time.

---

### Round 6 — 2026-09-06: a standing conflict, and the ruling made in advance

`bin/skeletor-upgrade --dry-run` against skeletor HEAD, run read-only from this
tree, reports **two** files that would conflict and be left alone:

```
❌ 2 file(s) that differ from the template — merge conflicts, LEFT ALONE
   · .github/workflows/ci.yml
   · scripts/docs/release_window.py
```

The first is expected and permanent — `ci.yml` is hand-merged here to keep three
branch-protected contexts (`eslint`, `pytest 3.12`, `pytest 3.14`) reporting
under names the template does not use. Nothing to decide.

**The second is new, and it is worth recording because a future session will
otherwise re-derive it from a conflict marker.** `scripts/docs/release_window.py`
ships at `core` and is manifest-tracked (`.skeletor.json`, 108 files). This tree
edited it — a refusal against a shallow clone, because `window()` silently
returned a well-formed range describing zero commits and `--apply` would stamp
that into every report. skeletor made **the same fix upstream, independently,
the same afternoon**, after this tree reported the finding. So the conflict is
two correct edits to one region, not a divergence of intent.

**The ruling, made now rather than at the merge: take the template's whole.** It
is the template's file, theirs is the maintained copy, and the guard is the same
guard — keeping a local variant of a fix that has landed upstream is how a tree
acquires a conflict it re-resolves at every release for no gain. The one thing
to *check* rather than assume when porting is that their version refuses on the
entry points that reach `window()` and not on `--check`, which validates
frontmatter shape and never calls it. Measured here before the fix:

| clone | `commit_range` | `commits` |
|---|---|---|
| full | `v0.1.0..HEAD` | 63 |
| `--depth 1` | `<sha>..HEAD` | **0** |

**And the reason the local fix was still right to make.** v0.17.0 is untagged
with no date, and a tree cannot wait on an unreleased fix for a live silent
failure. The cost of being early is exactly one hand-port, named here, against
an unbounded window of a report claiming a range it does not describe. That is
the trade, and it is the one to make again.

The general shape, which is not this file's: **a finding sent upstream becomes a
conflict downstream if you also fix it locally.** Worth the conflict when the
failure is silent, not worth it when the failure is loud — a loud one can wait
for the release, because you will know if it fires.

---

### Round 7 — 2026-09-06: the ruling on skeletor's job graph, which is no

skeletor's pending v0.17.0 adds a `node:` job and a `release-please: needs: […,
node, …]` edge that gates on it. Two edits that must move together. This tree
takes `ci.yml` as a three-way merge rather than a replacement, so the pair does
not arrive atomically, and the question put to us was whether we want the graph
at all.

**We do not.** Three reasons, each checked rather than assumed.

**We version by tag, so the `release-please` half has no landing site and should
not have one.** `.skeletor.json` records `--versioning tag`, there is no
`release-please-config.json`, and no workflow mentions it. The template ships
the job even for a tag tree, where it emits a `::notice` reading *not configured
here — this repository versions by git tag* and reports success.

**An earlier version of this paragraph called that "noise on every push
forever". That was wrong and the error is worth leaving visible**, because it
was made the same way this round has been diagnosing all afternoon: sourced from
a *comment* beside the job (*"it runs, it reports, it has nothing to do"*) and
from the workspace guide, rather than from the job body. The body carries a
job-level guard —

```yaml
if: github.event_name == 'push' && github.ref == 'refs/heads/{{RELEASE_BRANCH}}'
```

— so it runs on pushes to the release branch only. Here that is `main`, which
receives merges from `develop` when a release is cut, so the true frequency is
*per release*, not per push.

**And the retraction needed a retraction of its own, which is the more useful
half.** "That was wrong" is stated flatly above and is only wrong *here*. The
guard turns entirely on whether the base branch and the release branch are the
same ref: where they differ, as they do in this tree, it excludes everything
that is not a release; where they are both `main`, it excludes pull requests and
nothing else, so the job does fire on every merge and the original sentence
holds. Derived from the guard rather than from a survey — a fleet census of who
is in which position belongs to the workspace, not to this file.

So the same two-flag conjunction that produced this whole round — `--versioning`
against `--base-branch`, a mechanism inert because of a branch nobody works on —
decides the cadence too, one field over. **A claim about a scaffolded tree is
almost never about scaffolded trees.**

The wrong figure was also the more critical one, and it had been relayed to the
fleet and generalised to three trees before anyone checked. The claim it was
supporting needs none of it: a job that can never do anything in a tag tree is
one we have no reason to take, at any cadence, on any branch layout.

**The `node:` half fixes a defect this tree does not have.** Its own comment
upstream says why it exists: *"only the python half was ever run by CI — so a
`--language node` tree lint-checked its product on the author's laptop and
nowhere else."* Ours does not. The `lint` job runs `npm ci`, `npm run
lint:check` and `npm test`, and has since the frontend got a runner.

**And taking it would cost a branch-protection edit for nothing.** That job
produces the required context **`eslint`**. Splitting node work out of it either
duplicates the npm steps across two jobs or empties the one that carries the
name. A required context is *named, not discovered*, so the second reading means
editing protection on `develop` **and** `main` in the same sitting, with a
window in which a required context reports nothing and every pull request blocks
forever. That hazard is already the first thing this workflow's header warns
about.

#### What declining costs, measured rather than assumed

Planted the reverse partial take — a `node:` job that runs with nothing in
anyone's `needs:` — and ran everything:

```
19 CI-shape tests            pass
dev check pre-push, 6 gates  pass
```

**Nothing here reports it.** A job that runs and gates nothing is green forever,
which is *worked fine, told nobody* wearing a workflow's clothes. So the ruling
above is not free, and the honest form of it is: we decline the graph *and* we
cannot currently detect having taken half of it by accident.

#### The gate that would close it cannot be written here, and that is the finding

The obvious assertion is *every job must be in some job's `needs:`*. It is
false, and the reason is structural rather than an oversight:

| workflow | terminal jobs — nothing needs them |
|---|---|
| `ci.yml` | `verdict` |
| `docs-validation.yml` | `validate` |
| `pr-draft-discipline.yml` | `advise` |

A planted `node:` that gates nothing is **structurally identical** to `validate`
and `advise`, which gate plenty. The fact that separates them — *which contexts
branch protection requires* — is not in any file: it is
`["eslint","pytest 3.12","pytest 3.14"]` read from the GitHub API, and this
suite is deliberately network-free.

So this is the workspace's *unit of observation* argument arriving on a new
face. `test_workflow_job_graph.py` can say a `needs:` names a job that does not
exist, because both halves are in the file. Nothing in the tree can say a job
gates nothing, because **gating is a relationship between the workflow and the
account**, and a tree sees one. A repo that is entirely green ships a job that
blocks nobody, and the only instrument that sees it is somebody reading branch
protection.

Declining to ship a fuzzy predicate rather than declining to look: an in-tree
declaration of the required contexts would be a second belief about a value that
lives elsewhere, and it would go stale silently — which is the failure this
whole round is about, installed on purpose.

---

### Round 8 — 2026-09-06: the components manifest goes, and round 2 was wrong to keep it

Round 2 ruled that `.skeletor-components.json` stays, on the reasoning that
*"deleting it would make nine files look scaffolded that were not."* That was
wrong, and the measurement is one line:

```
files in BOTH manifests: 11        component-only: none
```

Every file it tracked is also in `.skeletor.json`, at **v0.16.0** — newer than
every component pin, which are v0.7.0, v0.10.2 and `v0.15.0-2-g2b64bf9`. Nine of
the eleven match the v0.16.0 record byte-for-byte. The two that do not
(`scripts/paths.py`, `scripts/check_skip_budget.py`) are ours by decision and
recorded as such. So the files were not "made to look scaffolded" by deleting
it — **they are scaffolded, and have been since the scaffold landed.**

**And keeping it was not neutral, which is why this is a fix rather than a
tidy.** `skeletor-components report` answered from the older pin and called
three files *moved upstream* — `output.py`, `check_commit_subjects.py`,
`conventional-commit-check.sh` — when the scaffold already held every one of
those moves at v0.16.0. Nothing was stale; the reporter was answering a question
that had been superseded, and it was the louder of two manifests. That verdict
was relayed to the operator as "three clean takes available" before anybody
compared the two files.

Not silence, but **a confident answer to a superseded question** — this repo's
own *worked fine, told nobody* with the polarity turned over. Reported upstream;
skeletor is making `record` refuse a path `.skeletor.json` already tracks, and
`report` name the overlap rather than answer from the older pin. Their own
finding on it is sharper: `bin/skeletor-components` writes three paragraphs about
`.skeletor.json` in its module docstring and **never opens the file**, so the two
manifests have no relationship in code at all.

Four references updated with it, none of them code: this doc's frontmatter and
its round-2 note, `ci.yml`'s comment above the gate steps, and an entry in
[[ideas]] whose premise was *"sky.boss has no `.skeletor.json` and will not"* —
false in both halves as of yesterday, and left visible rather than deleted
because the idea it supports is still good and now needs a different example.

---

### Round 9 — 2026-09-06: v0.17.0, and the divergence the tool forgets once you tell it

`v0.16.0` → `v0.17.0`, run the way round 5 established: from a clone pinned at
the tag, using **that clone's own binary**. `--from-dir` overrides the *base*,
not the target — the target is whichever checkout the binary lives in — and
pointing this tree's binary at the pinned clone produced sixteen *"manifest
disagrees with the base it names"* refusals before that was understood. The
refusal was correct and the reading of it was not.

Eleven files merged, three added, one clean auto-merge, one standing deletion
correctly not restored.

**The three added files are the round this tree argued for and they do not
close it.** `test_ci_job_conditions.py` and `test_ci_job_settings.py` hold a
workflow's jobs to conditions and settings; `test_commit_vocabulary.py` holds
the subject vocabulary to one home. None can find what round 7 named as
unfindable — a job that runs and gates nothing — because the separating fact is
which contexts branch protection requires, and that lives in the GitHub API
against a suite that is network-free by design. Three gates arriving for a
question is not the question being answered, and the gap is worth restating
rather than letting the file count imply otherwise.

**`release_window.py` resolved by taking the template's version whole**, per the
ruling round 6 made before the upgrade ran. Ours was a shallow-clone refusal and
theirs covers it. Four arms measured rather than reasoned about: full/bare `0`,
full/`--check` `0`, shallow/bare `1`, shallow/`--check` `0`.

**`ci.yml` left alone**, per round 7.

#### The parity gate shipped unsatisfiable, and this is the first tree that could tell

`test_marker_coverage.py` was widened the same day to compare **every** key
across `tests/pytest.ini` and `pyproject.toml` by value, where it had compared
`markers` alone. The widening is right and the reason for it is this repo's own:
a key in one file and not the other is exactly the `asyncio_mode` case round 4
hit, and it is invisible to a check that compares only shared keys.

`pythonpath` and `testpaths` cannot be compared that way. **Both resolve against
rootdir, and rootdir is the directory holding the config pytest found**, so the
two files necessarily spell the same two paths differently. Measured both ways:

```
pytest tests/…   →  rootdir: …/sky-boss/tests,  configfile: pytest.ini
pytest           →  rootdir: …/sky-boss,        configfile: pyproject.toml
```

So `pythonpath = ..` / `testpaths = .` in one file and `pythonpath = ["."]` /
`testpaths = ["tests"]` in the other are the *same two directories*, and textual
identity is the wrong assertion for them. There is no assignment that satisfies
the gate while both files stay correct. Deleting the inner file gives the right
rootdir and breaks eight other tests.

Resolved by exempting those two keys from the **value** comparison and keeping
them in the **presence** comparison — presence is the half that catches the case
the widening exists for. A new standing divergence on a scaffold-tracked file,
created hours after the check shipped, and reported upstream: this tree sets
either key in both files, which is very likely why nobody had hit it.

#### What `--ported` costs, which is not in its description

`--ported` advances the recorded base, and the base is what the next three-way
merge diffs against — so recording the *template's* v0.17.0 hash for a file we
deliberately did not take is correct, and the manifest says as much in its own
header (*"records how this tree was rendered"*). The next upgrade will apply the
v0.17.0→v0.18.0 patch onto our divergent file, which is what we want.

The cost is what the tool says afterwards:

```
before:  ❌ 2 file(s) that differ from the template — merge conflicts, LEFT ALONE
after:   ✅ already current with skeletor @ v0.17.0 — nothing to carry over
```

**Two deliberate divergences went from reported-every-run to invisible**, and
the asymmetry is with a deletion three lines above them in the same output:

```
⏭️  1 file(s) skeletor wrote and you deleted — NOT restored
   Recorded in the manifest, absent from the tree: a decision you made, which
   an upgrade does not re-make for you. Standing state, reported every run.
```

A deletion is standing state. An edit is not, once ported — and yet *disk hash ≠
base hash* is exactly as computable after `--ported` as before it, and it means
the same thing both times: **this tree has edited a file skeletor wrote.** The
tool's own argument for reporting the deletion applies unchanged.

The consequence here is that `docs/features/skeletor-adoption.md` is now the
**only** record that `ci.yml` and `test_marker_coverage.py` are ours by
decision. That is this adoption's founding complaint arriving on the instrument
itself: *a component consumer is never told a gate exists* becomes *a scaffolded
consumer is never told a divergence exists*, and in both cases the remedy the
tree reaches for is a doc, which is the thing that goes stale. Reported upstream
alongside the parity finding.

#### Pre-made ruling for the next upgrade: drop the exemption, take theirs whole

Both findings above were built upstream the same evening they were sent, and
neither is tagged yet — so this is written now, while the reasoning is live,
rather than rediscovered by whoever runs the next upgrade. Round 6 did this for
`release_window.py` and it is the reason that conflict took one decision instead
of an investigation.

**skeletor fixed the parity gate by comparing meaning rather than by exempting.**
Two tables: `_ARGS_KEYS` splits `addopts`, `norecursedirs`, `testpaths` and
`pythonpath` on any whitespace, and `_ROOTDIR_RELATIVE` resolves `testpaths` and
`pythonpath` against **the owning file's** rootdir before comparing. That is the
more faithful of the two shapes and it is the one this round declined to build,
on the grounds that it needed the gate to know each file's rootdir — which was a
judgement about effort, not about correctness, and they spent the effort.

Checked against our values without needing their code, because it is arithmetic:

```
pythonpath   tests/..        → <root>        vs  <root>/.       → <root>       ✓
testpaths    tests/.         → <root>/tests  vs  <root>/tests   → <root>/tests ✓
```

So **our pair passes their gate unchanged**, and the local exemption
(`_ROOTDIR_RELATIVE` in `tests/test_marker_coverage.py`, with the note that
argues for it) is to be **deleted** at the next upgrade rather than merged
forward. Take the template's file whole. The exemption stopped comparing; theirs
starts comparing the right thing, and keeping ours would preserve a blind spot on
purpose.

One thing worth carrying rather than dropping with it: their `_ROOTDIR_RELATIVE`
is a hand-kept table, and they justify it rather than smuggling it — pytest's own
registry types `norecursedirs` and `testpaths` **identically as `args`**, so
nothing in the schema separates basename globs from rootdir-relative paths. It is
knowledge about another tool that no predicate over the tree can derive, which is
the one kind of list worth keeping, and it is checked against pytest on every run.

**And the second finding removes the reason this paragraph has to be load-bearing.**
Their fix to `--ported` reports an edited file as standing state every run:

```
📝 2 file(s) skeletor wrote and you have edited — standing state
   · .github/workflows/ci.yml
   · tests/test_marker_coverage.py
```

Computed before anything is written — after the loop it would be lowest on the
runs that changed the most, which is wrong in the reassuring direction. So the
next upgrade will *name* both divergences without anybody having found this doc.
That is the right relationship between the two: **the tool raises the question and
the doc holds the answer**, where until tonight the doc had to do both and was the
only thing that could go stale.

---

### Round 10 — 2026-09-06: v0.18.0, and a clean merge that was not a correct one

`v0.17.0` → `v0.18.0`, from a clone pinned at the tag, using that clone's binary.
Eight untouched files updated, four merged cleanly, one conflict left alone, one
standing deletion not restored. The ruling written at the end of round 9 was
executed as written: **the exemption is gone and the template's
`test_marker_coverage.py` is taken whole.**

Round 9's finding 2 is live and reports more than it was asked for:

```
📝 24 file(s) skeletor wrote and you have edited — standing state
```

Twenty-four, not the two that were merge conflicts — every scaffold-tracked file
this tree has edited. That is the right answer to the question and a larger
number than the request implied, which is the correct direction for a report to
be surprising in.

#### A clean three-way merge produced a file with two definitions of one constant

`tests/test_marker_coverage.py` came back in the **merged cleanly** list. It was
not correct. skeletor's fix adds `_ROOTDIR_RELATIVE` near the top as a `set`,
beside the `_normalise` that resolves against the owning file's rootdir; our
exemption defined `_ROOTDIR_RELATIVE` as a `frozenset` seventy lines lower. The
two edits never overlapped textually, so git merged both, and **Python kept the
later one**:

```
_ROOTDIR_RELATIVE is frozenset frozenset({'testpaths', 'pythonpath'})
```

Ours. So their normalisation was live code that nothing called, and the
comparison still skipped both keys. **Five tests passed on it.** A gate doing
strictly less than it reports, arrived at by a merge that reported success —
this repo's *worked fine, told nobody* reached through version control rather
than through code.

The general rule, which is not specific to this file:

> **A clean merge is a statement about text, not about meaning.** Two edits that
> add a module-level name in different regions never conflict, and the second
> definition silently wins. Where an upgrade merges cleanly into a file you had
> edited *for the same reason the upgrade exists*, expect a duplicate rather than
> a resolution.

Taking the file whole removed it. Checked afterwards by parsing all four cleanly
merged Python files for duplicate top-level names — none remained.

#### The pass was then verified, because a pass on a file you just replaced is not evidence

Planting real drift (`testpaths = ["scripts"]` in `pyproject.toml` alone):

```
set in both, different: ['testpaths']   → 1 failed
```

and our genuine pair still passes, because `tests/..` and `<root>/.` resolve to
one directory and `tests/.` and `<root>/tests` resolve to another. The gate is
comparing, not skipping. *Prove the instrument can see one before believing it
saw none* — the practice this repo already had, applied to somebody else's fix.

#### The new scanner found dead configuration here on its first run

`test_no_job_fetches_history_the_scan_cannot_explain` failed on `ci.yml:gate`
and `ci.yml:test`. The relayed guidance was that this tree was *"the one where
that finding does not apply"* — which was a prediction about a file the writer
had not read, and it was wrong in both jobs. Reconciled against the render, as
usual, and the two causes are different:

**`test` was a blind spot in the scan.** Its `_DASH_M` is `-m\s+(?P<marker>\w+)`
and this fork ran `-m "unit"`. `\w` does not match a quote, so the job's real
dependency — the unit suite refuses a shallow clone — was invisible. The quotes
were our own divergence (the template writes `-m unit`), so they are gone, which
converges rather than diverges. **The pattern still needs widening upstream**: a
compound selector like `-m "unit and not slow"` *must* be quoted, so any adopter
writing one is unreadable to this scan. Reported.

**`gate`'s depth was genuinely dead, which is the scanner working.** Nothing in
that job reads git: `docs-only.cjs` classifies through the GitHub API, and the
three structural checks touch no history. It carried `fetch-depth: 0` because
the *template's* gate runs the commit-subject read over the PR range — and this
fork does not run that step at all. So the line was kept alive by a header
comment describing a caller that is not in the file. Both are fixed: the depth
is gone and the comment now says which job needs history and why.

> **Configuration justified by a comment rather than by a caller survives every
> reader and fails only to a question.** Nobody reading `ci.yml` would have
> doubted a `fetch-depth: 0` with a paragraph above it explaining the need. It
> took an instrument that asked *which caller* rather than *is there a reason*.

**One gap is left open deliberately, because it is a policy change rather than
an upgrade.** This fork runs no commit-subject check in CI. The local
`commit-msg` hook binds whoever has it installed; the template's `gate` step is
what binds a pull request from someone who does not. Restoring it means
restoring `gate`'s `fetch-depth: 0` in the same edit, which the new comment
there says. Not taken here — it changes what gates the branch, and that is the
operator's call rather than an upgrade's.

#### The declined `ci.yml` patch turned out to be a no-op

Round 7's decline stands, and the reason has changed. The whole v0.18.0 patch
for this file is the matrix and the context rename — `name: pytest ${{
matrix.python }}`, `strategy.matrix.python`, `python-version: ${{ matrix.python
}}` — every line of which this tree already had, having built it independently
when it asked for the feature. So there was nothing to port, and the branch
protection edit the release warns adopters about costs this tree nothing. That
was checked against the remote rather than against the release note.

---

### Round 11 — 2026-09-06: v0.19.0, and the fork turning out to be the defence

`v0.18.0` → `v0.19.0`. One file updated, one standing conflict, nothing else:
`tests/test_ci_job_conditions.py`, a docstring that went stale inside one
release because the behaviour it described was qualified underneath it. No
action here beyond taking it.

Two things were checked rather than accepted, and both were relayed as *nothing
owed*.

**The `store_true` manifest bug does not touch us.** v0.19.0 fixes
`manifest_args` recording a flag as `--reproducing False`, which renders a fresh
scaffold permanently unupgradable. The relay said the fleet was clear. Verified
against our own record rather than trusting it — no bare `True`/`False` token in
`.skeletor.json`'s `args`. It holds.

The gate that was green throughout that bug is the interesting half, and it is
this repo's own rule arriving at a generator: all four of its checks asked
*which flags reach the record*, and none asked whether the record **parses
back**. A record that does not parse is indistinguishable in consequence from a
record that is missing an entry. It now replays the record through the parser
and — the part worth copying — **names the eleven flags it could not move**,
those being exactly the ones it proves nothing about. *A check that cannot speak
for something says so, rather than letting green imply coverage.*

**The gating change cannot reach our required contexts, and the reason is the
fork.** The docstring's subject is `docs-only.cjs` returning `fullSuite: false`
for a ready pull request carrying code, which in the template leaves the node
steps ungated because they live at the end of a `full_suite`-conditioned `lint`
job. The relay flagged it as ours to care about first, since this is the only
tree with protection on both branches.

Measured instead of reasoned about: in this fork the `eslint` job and the
`pytest` matrix carry **no `if:` at all**. Neither is gated on `full_suite` or
`docs_only`, so no classification change can make a required context report
`skipped` — which branch protection accepts, and which is the failure the whole
condition family risks. The header comment claims exactly this and it is now
checked rather than believed.

> **Round 7 declined the template's job graph on cost, and the decline turns out
> to have bought the immunity.** That is worth stating without over-claiming it:
> the decline was not made for this reason and does not become better reasoned
> in hindsight. A fork is not a safety property. What is true is narrower — a
> tree that diverges from a mechanism is outside the blast radius of changes to
> it, and it pays for that by being outside the fixes too.

The standing `ci.yml` conflict is expected every run and is not a regression.

#### One thing the manifest now records that is not true

`--python-ceiling 3.12` is in `args`, added when v0.17.0 gave the flag a default
of `--python`. This tree's matrix is `['3.12', '3.14']` and has been since
before the flag existed. So the recorded render would produce a one-leg matrix
where the tree runs two.

It costs nothing today — `ci.yml` is declined, so the base render's matrix never
reaches the file — and it is not hand-editable: the manifest says *do not
hand-edit*, and a value invented here is a second opinion about how the tree was
rendered. Raised with skeletor rather than fixed, because the question is
whether amending a recorded argument has a supported route. Recorded here so the
next reader does not have to rediscover that the manifest and the workflow
disagree on purpose.

---

### Round 12 — 2026-09-06: v0.20.0, and a coverage reduction that is zero here

`v0.19.0` → `v0.20.0`. Two untouched files updated
(`.github/scripts/docs-only.cjs`, `tests/test_ci_job_conditions.py`), the
standing `ci.yml` conflict, nothing else.

It arrived flagged as a **coverage reduction aimed at this tree** — a docs-only
pull request into the release branch used to earn the full suite in a
two-branch tree and now earns gate-only, and this is the only tree in the fleet
with protection on both branches. The advice was to read the consequence off a
real run rather than off the message. The consequence is readable off the file,
and it is nil.

**Measured, not reasoned about.** `docs-only.cjs` is executable standalone, so
the whole truth table was run against this tree's real `develop`/`main` render
before and after the upgrade. Exactly two rows move:

```
draft docs-only → develop   docsOnly false → TRUE    fullSuite false (unchanged)
docs-only       → MAIN      docsOnly false → TRUE    fullSuite TRUE → false
```

The first is node-zero's bug fix — the draft test used to sit above the
classifier, so marking a docs-only draft *ready for review* **de-escalated** it,
which is the one transition that exists to escalate. The second is the flagged
row. `release-please → MAIN` is unchanged at `fullSuite: true`, confirming that
`VERSION` and `.release-please-manifest.json` fall outside `DOC_PATTERNS`.

**And neither reaches a job here.** The classifier's verdict gates nothing in
this fork:

```
gate     no if:, no needs:            always runs
test     needs: gate, no if:          pytest 3.12 / pytest 3.14
lint     needs: gate, no if:          eslint
verdict  if: always()
```

The only `if:` in the workflow is `always()`, and `full_suite` reaches exactly
one consumer — an `echo` in `verdict`, which reports it and does not act on it.
So no required context can report `skipped`, and the coverage delta in this tree
is **zero rows**, not one.

> **A change can be correctly identified as landing on you and still have no
> consequence for you, and the two questions have different owners.** Which row
> of a classifier moves is a fact about the template. Whether a moved row
> reaches a job is a fact about this fork. Three relays in a row have got the
> first right and the second wrong, in the same direction each time — assuming a
> fork diverges *away* from a finding, when a fork is usually exactly where one
> lands. This is the case where it genuinely did not.

That is round 11's sentence collecting its other half. The decline put this tree
outside the reorder's cost **and** outside its improvement: a genuinely
docs-only pull request here still pays for the full suite, which the template
now avoids. Nobody should read the zero as a win.

#### `--set-arg` shipped, and the design changed under review

The verb asked for in round 11 exists. It is **not** what was first proposed —
amending the record and re-deriving every hash — and skeletor's reason for
abandoning that is worth keeping:

> An amendment that changes nothing is accepted; one that changes something
> cannot be. The record was never wrong. **What an adopter wants is not a
> corrected past but a different future.**

So it amends the *head* render's arguments, and the difference then arrives as an
ordinary template change — untouched file replaced, edited file merged,
**declined file still declined**. Which costs round 7's ruling nothing, and
means the `--python-ceiling 3.12` discrepancy is fixed by taking a future
upgrade rather than by rewriting this tree's history. Not exercised yet; there is
nothing to spend it on while `ci.yml` is declined.

The review this tree gave it is recorded because one finding survived into the
shipped design: `PYTHON_MATRIX` reaches exactly one template file, and that file
is the declined one, so the consequence-check justifying a valued flag over a
bare assertion could never fire for the adopter who asked for the flag.

---

### Round 13 — 2026-09-06: the gap round 10 left open, closed on the operator's ruling

Round 10 ended with one item deliberately not taken: *this fork runs no
commit-subject check in CI*, and restoring it changes what gates the branch,
which is not an upgrade's call. Jeston ruled it in. It is closed, and two of the
three decisions in closing it went against the obvious choice.

**The obvious script was the wrong one.** The template runs
`check_commit_subjects.py` in `gate`, so copying that step across is the
one-line answer. It would have been a step that never looks at anything: that
script reads its vocabulary out of a `release-please-config.json`, and a
`--versioning tag` tree has none, so it self-guards and exits 0 on every commit
forever. (Named without its directory on purpose, as round 7 names it: the
sentence is about the file's *absence*, so spelling it as a path would be a
citation to something no reader can open — which `test_docs_name_real_paths.py`
objects to, correctly, and which is how this paragraph was caught.) Measured before writing anything —

```
$ python scripts/check_commit_subjects.py --range HEAD~5..HEAD
⚠️  no changelog-sections in .github/release-please-config.json — nothing to check against
exit=0
```

— which is the *job that gates nothing* from round 7, reinstated by hand and
wearing a template's authority. The rule this tree keeps meeting: **a check
copied from a tree that has the contract does not acquire the contract.**

So the instrument is `scripts/hooks/conventional-commit-check.sh`, the
`commit-msg` hook, which in a tag-versioned tree is the only one of the two that
*can* fail. `scripts/check_commit_style.py` runs it over a range. It contains no
vocabulary of its own and shells out to the hook per commit, so a range check
and a local commit cannot disagree — the hook's own comments record a hardcoded
list that drifted from the config and let a `style(lint):` subject pass locally
and fail in CI, which is the failure a second copy here would reproduce.
**The hook owns the rule; the script owns the range.**

**It found four real violations in its own tree on the first run**, all from the
day it was written, all on `develop`:

```
4 of 6 commit(s) in HEAD~6..HEAD fail the hook
  · subject is 73 chars (max 72)   ... 74 ... 75 ... 78
```

And the cause is the gap itself, confirmed rather than assumed:
`.git/hooks/commit-msg` **does not exist in this checkout** — no hooks are
installed at all, so the rule had never run here on any commit.

**Not a documentation gap, and worth saying so before somebody goes to fix
one.** `.venv/bin/pre-commit install --install-hooks` is in `AGENTS.md`,
`CONTRIBUTING.md` and `docs/DEVELOPMENT.md`, and `tests/test_setup_blocks_agree.py`
holds those three copies together. The instruction was present, correct and
guarded the whole time; it had simply not been run here. Which is the evening's
own rule from the other side — *a disobeyed instruction is not a falsified one*
— and it decides the remedy: run the step, do not edit the docs. Installed
2026-09-06, verified by feeding the hook a 76-character subject and watching it
exit 1. The check is
forward-looking and those four are left standing: CI reads the range an event
carries, so history is not re-litigated, and rewriting pushed commits to satisfy
a gate added afterwards is the cost this repository refuses elsewhere.

#### One version, and it is the ceiling

`gate` now takes `python-version: '3.14'` rather than the floor it was pinned
to, and deliberately not a matrix. Nothing in the job is version-sensitive —
three structural readers and a subprocess to a bash hook — so a second leg buys
a duplicate rather than a data point.

The floor is not lost, and that was checked rather than argued: the unit suite
imports these same `scripts/` modules and the `test` job runs it on **3.12 and
3.14**, so *syntax newer than the floor we promise* is caught where it lives.
Pinning `gate` to the floor as well would have been a third copy of a promise
`pyproject.toml` already makes.

#### And the header comment has now been wrong in both directions in one day

It claimed `gate` needed full history for a read this fork did not run; round 10
removed the depth and rewrote the paragraph to say the job needs no history;
this round restores both. Rather than a third paragraph asserting the current
state, it now says the rule:

> **A depth is justified by the line that reads history, never by a paragraph.**
> If that step ever goes, the `fetch-depth: 0` goes with it in the same edit.

Round 10's removal was correct when it was made and is not retracted. A setting
with a caller and a setting with only a comment are different objects that look
identical in a diff.

---

### Round 14 — 2026-09-06: the manifest discrepancy closed, and `--set-arg` needs `--ported` here

Round 11 recorded `--python-ceiling 3.12` against a matrix that runs `3.12` and
`3.14`, and declined to hand-edit the manifest on the grounds that a value
invented in an adopter's tree is a second opinion about the render. The
supported verb arrived in v0.20.0 and proto.pilot ran it first. Closed:

```
--python-ceiling  3.12 → 3.14      ci.yml untouched, still ['3.12', '3.14']
```

Two lines in the diff — the argument, and `ci.yml`'s recorded base hash, which
now describes a render with two legs. `skeletor_ref` did not move.

**The inversion is the part worth keeping**, and it was proto.pilot's to find:
this looked like *a tree that edited away from its record*, which frames the fix
as reconciling two artefacts and invites fixing the file, since the file is the
thing that runs.

> **The divergence closed by making the record true, not by editing the
> workflow.** The tree was already right; the record was the wrong artefact all
> along.

#### It does not work alone in a tree with a standing conflict

`--set-arg` on its own is a **no-op here**, and silently so in the sense that
matters — it reports the amendment and then does not keep it:

```
→ 1 argument(s) changed for this render
⏸️  .skeletor.json left at v0.20.0 — 1 file(s) still pending
git status → clean
```

The amendment applies to the render and is recorded only if the run applies
everything, and this tree has a permanent conflict by ruling — round 7's
declined `ci.yml`, which is *the file the amended argument renders into*. So the
one tree in the fleet still carrying this divergence is the one that cannot use
the verb built for it. `--set-arg --ported` records it, because `--ported` is
exactly the assertion that the conflict is resolved as intended, which round 7
made and this tree has repeated on every upgrade since.

That is the second time this argument has produced the same shape. The round 11
review found that the consequence-check justifying a *valued* flag over a bare
assertion could never fire here, because the only file `PYTHON_MATRIX` reaches
is the declined one. This is the same geometry one layer out: **a mechanism
keyed to a file cannot serve the tree that has opted out of that file, and the
tree that opted out is the one most likely to need it.**

#### The check that was asked for, and it is not the manifest

proto.pilot's specific request, because this fix's failure mode is *record now
agrees, coverage silently halved* — and a halved matrix is green:

> Confirm the leg count **in the run**, not in the manifest.

Both legs reported on the push that carried this change. That is the only
instrument that sees it; the manifest agreeing proves nothing about it, and
neither does the workflow file, which is what a halved matrix would still look
correct in if the amendment had gone the other way.

#### Coda: converting a note instead of deleting it

proto.pilot's `ci.yml` carried a comment reading *"this list is a hand-edit and
the manifest disagrees with it"*, which their amendment made false. It was
reported here as **deleted** and it was not — they converted it:

```
-    # **This list is a hand-edit and the manifest disagrees with it.**
+    # **This list is not a hand-edit any more; the manifest says it.**
+    # Change the versions by changing the recorded argument, not by editing the
+    # list below.
```

Their rule, which is better than the one this round would otherwise have drawn:

> **The remedy for a note that rots is not deletion — it is converting the fact
> into a policy.** A conscientious warning rots because it *describes a state*.
> The same care spent writing a rule survives the state changing. And **a
> disobeyed instruction is not a falsified one** — which is what lets a rule
> outlive the condition that prompted it, where a description cannot.

That is round 13's move, named. The `ci.yml` header comment there had been wrong
in both directions inside one day, and the third version deliberately stopped
describing which jobs need history and started saying *a depth is justified by
the line that reads history, never by a paragraph*. This tree already complies;
what it lacked was the reason, and the reason is what tells the next person
which of the two edits to make.

**The false premise reached a message and never reached this file**, which is
the only reason there is nothing to retract above. Recorded because the near
miss is the instructive part: a relay is the only party holding both ends of a
cross-repo claim, so **a relay's error is the one error no recipient can
check** — proto.pilot could correct it because it was their tree, and this
session had neither the standing nor a reason to look.

---

### Round 15 — 2026-09-06: `skeletor_ref` names the template, and cannot name the tool

v0.20.1 shipped with the `--set-arg` reporting fix this tree's round 14 asked
for. **It changes no template file at all**, verified here rather than taken
from the release note:

```
git diff --stat v0.20.0..v0.20.1 -- template/   →  empty
                                    bin/        →  +260 lines
```

The fix works, checked against the tree that produced the report — the same bare
`--set-arg` on this declined `ci.yml` that reported an amendment and silently
dropped it now says so:

```
⚠️  the 1 --set-arg value(s) were NOT recorded
   again. Resolve the conflicts, then re-run with the same --set-arg.
```

**And it cannot be recorded as taken.** Running the upgrade — `--ported`
included — writes nothing and leaves the ref where it was:

```
→ head: skeletor @ v0.20.1
✅ already current with skeletor @ v0.20.1 — nothing to carry over
git status → clean          skeletor_ref → v0.20.0
```

Which is correct rather than a defect: with no template change there is no
render to perform, and `skeletor_ref` records the last render. This tree's
template state is byte-identical to both tags.

The consequence is the policy, and it is stated as one because the fact behind
it rots the moment there is a v0.20.2:

> **`skeletor_ref` is a fact about the last template render. It says nothing
> about the `bin/` that will perform the next upgrade, because that is chosen
> when somebody types the command — and a tool-only release cannot move it at
> all.** So an upgrade is run from a checkout pinned to the **newest** tag, not
> merely the newest one with template changes. The ledger row reading `current`
> is accurate and is not an answer to *which tool will run next*.

That is this repository's own *do not keep a copy of what a command will tell
you*, meeting a value no command in this tree can be asked: the version of a
binary in somebody else's checkout, at a time nobody has chosen yet. Round 7's
finding about branch protection was the first of these, and the family is now
three — the account's required contexts, the account's Actions permissions, and
the operator's tool version.

### Round 16 — 2026-09-07: `docs/features/` folds into the scaffold's lifecycle

Rounds 1–15 adopted the scaffold everywhere except the one place this repository
already had an opinion: **its documentation lifecycle.** `docs/features/` with a
`done/` beside it, and `docs/TODO/` with `docs/implementations/` beside it, are the
same lifecycle in two spellings. On the operator's ruling — *"features doesn't have
a purpose with implementations and TODO"* — the scaffold's half is the one that
stayed.

**The measurement that says which half, and it is not a preference.** Before
anything moved:

```
dev check docs                      → all 5 gates passed
docs/TODO/README.md                 → 0 open plans
docs/implementations/README.md      → 0 archived plans
docs/features/**                    → 25 documents, 62 KB in one of them
```

Every gate green, both generated indexes describing an empty repository, and the
whole design record outside all of it. Nothing here is *wrong* — each index is
accurate about the directory it was told to scan — which is this repository's own
**worked fine, told nobody** with the polarity that is hardest to catch: the
healthy answer and the blind answer are the same bytes, and the blind one is
green.

**Why nothing fired.** `docs/features/` counted as *routed* in
`scripts/check_doc_tables.py`, which is what should have caught it. It was routed
by **prose**: `_DOC_DIR` is a regex over whole files, `CLAUDE.md` is one of the
three tables it scans, and a paragraph in § Feature workflow spelled the path. So
a directory outside the lifecycle satisfied the routing gate by being *discussed*
in a file that also happens to be a routing table. The gate is not wrong — a row
and a sentence are the same characters to a regex — but "routed" and "mentioned"
are different claims, and only one of them is what the green means.

**Three things the pipeline's frontmatter parser cannot read, all present here,
all silent.** `scripts/docs/frontmatter.py` is stdlib-only by deliberate choice
and its docstring scopes it to "the fixed, flat schema emitted by `dumps` in this
same module". The backfill, however, runs over **hand-written** documents, so its
input is not restricted to its own output. Measured against the 24 completed docs:

| Written | Parsed as | Consequence |
|---|---|---|
| `agent_value: 3  # four rounds…` | `'3  # four rounds…'` | `int()` raises, caught, **rated 1 — "historical only"** |
| `key_files: [a.py, b.py,`<br>`  c.py]` | `'[a.py, b.py,'` | the rest of the list is silently body text |
| `key_files:`<br>`  - a.py` | `''` | the whole list vanishes |

Four of the five documents carrying the most reasoning use a trailing comment on
`agent_value`, so the archive would have sorted exactly the four best documents to
the bottom, labelled *historical only*, with no error anywhere. Sixteen of
twenty-four use a `-` block list for `key_files`. All three forms are legal YAML
and none of them fails — they degrade to a value, and in the `agent_value` case the
value is a judgment about how much the document is worth reading. **Reported to
skeletor**; the fix is not a YAML dependency but refusing what it cannot represent,
since a parser that returns a plausible wrong value is worse than one that raises.

Frontmatter was therefore **rebuilt** rather than edited, and every block verified
to round-trip through `frontmatter.read` before a single `git mv`.

**What moved.** All 25 into `docs/TODO/` first, then filed one at a time with
`dev docs file <slug> --category <category>` — never a plain `mv`, per
`docs/rules/docs.md`, and the two-step is also a positive control on a pipeline
that had never run against anything:

| Category | Plans |
|---|---|
| `commands/` | capture, delay, file-follow, follow, jsonl-reads, refresh, subprocess-env, text-reads, tools, unwatched |
| `rendering/` | chrome, header, highlight, table-views, wrap |
| `surfaces/` | canvas, mcp, workbench |
| `projects/` | agent-sessions, history, jobs, roll-call, schedule, state-root |
| `tooling/` | this plan |

Each gained a `summary:` — the only thing a reader sees in either index, and blank
on all 25 before this round. The tank rendered 25 plans, the archive rendered 25
across 5 categories, and `dev docs file` refused nothing it should have accepted.

**A `status:` field declared to be the truth, with no reader anywhere.** The old
workflow's first rule was *"`status:` in frontmatter is the truth and the directory
follows it in both directions"*. Nothing in the tree read that field —
`tests/test_docs.py` checks slugs, not frontmatter — so `workbench.md` had sat at
`status: done` for a week, in a vocabulary whose three words are
`draft | active | complete`, and no instrument existed that could have said so. In
the scaffold's half **the directory is the status** and both indexes are generated
from it, so the location cannot disagree with itself. The field was dropped rather
than translated.

**What `[[slug]]` bought, cashed in.** Twenty-five documents moved, and every one
of them gained a *category* directory that did not exist in the old layout — the
worst case for a path. Not one `[[slug]]` needed editing. The three references that
broke were the three written as paths (`skyboss/mcp.py`, `skyboss/read.py`,
`tests/test_publication.py`), and `dev check doc-refs` named all three **and the
new location of each**. One of them read *"See docs/features/done/text-reads.md —
or rather [[text-reads]]"*: the path and the slug side by side, and only the path
broke.

**A hand-maintained list, deleted rather than updated.** CLAUDE.md § Feature
workflow carried eighteen document names with a phrase about each — a hand copy of
what `docs/implementations/README.md` now generates, without the summaries, without
the `Value` column, and seven documents behind. Deleting it is the same ruling as
the workspace guide's worktree list and as `N of N` in § Branches: **do not keep a
copy of what a command will tell you.** Three copies of that lesson in one file
now, which is either three too many or exactly right.

**One template divergence removed, which is the round's quiet dividend.**
`scripts/paths.py` carried a `NARRATIVE += (DOCS_DIR / "features" / "done",)`
append with sixteen lines of comment justifying it — the mechanism skeletor
documents for adding a narrative stage, used correctly, and now with no subject.
It is gone, and this file is byte-identical to the template again. **An adopter's
divergence can end by the adopter's own layout catching up with the template**,
not only by upstream absorbing it, and that is the cheaper of the two.

**Deliberately not moved, and each for its own reason.** `docs/open.md` is not the
tank: the tank holds one document per plan, and an item in `open.md` is a paragraph
nobody has decided is a plan yet — it graduates *into* `docs/TODO/` when somebody
decides how, and that boundary is the file's whole value. `docs/ideas.md` is one
question earlier still (*should we build it*), which `docs/rules/docs.md` routes to
`docs/research/` — a folder this tree does not have, so nothing is gained by
creating one to hold a file that already has a routing row. `docs/design/` is the
constitution and its renders, which are not plans at all.

**`docs/rules/docs.md` was left untouched on purpose.** It is template-owned, and
the reopening discipline this round documents — a completed plan moves *back* to
`docs/TODO/`, which the shipped rules describe only in one direction — went into
`.claude/skills/feature/SKILL.md`, which is ours. Round 7's ruling on the same
seam: a divergence in a template file is a standing three-way-merge conflict, and
a rule that lives in a file we own costs nothing.

This round was itself filed by the path it documents: moved back out of the
archive, extended, and re-filed — so the reopen half of the lifecycle has now been
run once rather than merely written down.

### Round 17 — 2026-09-07: what a new scaffold argument's default says about this tree

A question asked before an untagged release, and the answer mattered less than
the reason for asking. skeletor is shipping `--shell-package`, which decides the
directory the shell renders into — `cli/` here, since round 1 moved the product to
`skyboss/` precisely so the shell could own that name.

**Our manifest predates the flag**, so it records no value for it and the parser
fills in the default on the next upgrade. Measured on their side: it is `cli`, so
nothing happens to this tree and no backfill is needed. That value is deliberately
**not written down here** — it is a fact about a parser in somebody else's
checkout, which is round 15's whole subject.

**What is written down is the class, because it recurs every time an argument is
added rather than changed:**

> `--set-arg` refuses to change a path-set argument. A new flag's default changes
> one **for free**. The refusal is about the loud path; a default is the quiet one,
> and the trees it reaches are exactly the ones that predate the thinking.

The distinction that makes this actionable is *within a file* versus *the set of
paths*. An argument whose effect is within files is safe to amend and safe to
default; one that decides a directory name is neither, and the second half of that
sentence has no refusal guarding it because nobody asked for anything.

**The standing check this leaves, for whoever runs the next upgrade:** when a
release adds a scaffold argument, ask whether it decides a **path** before running
`skeletor-upgrade`. If it does, and this manifest has no recorded value for it, the
default is the value — and a wrong one renders the whole shell into a new directory
while reporting the old one as no longer shipped. `--dry-run --json` names both
sets, which is the instrument; it costs one command and it is the only one that
answers before the merge rather than after.

**skeletor's gate for it was green and looking at the wrong tree**, which is the
part worth keeping. `shell_package_gate` asserted the default *from a fresh
scaffold* — the one place it cannot matter, because a fresh scaffold **records** the
flag, so the default is consumed at scaffold time and never at upgrade time. The
path where a default is load-bearing is a manifest with **no recorded value**, and
that is every tree scaffolded before the flag existed. Their fix strips the argument
from a real manifest — byte-identical to a pre-flag one — and requires the upgrade to
come back *already current*, an assertion that needs no knowledge of the default's
value and can only hold if the render put the shell back where it was.

Same shape as round 15 and as the workspace's `--tagline` incident: **a default no
gate ever produces is not a tested default.** Worse here, because the gate naming
the default was reading it off the recorded args rather than off the absence — so it
printed green about the one case it could not see. The family of *no instrument at
any distance the tree can reach* now has a sibling that is merely *the instrument
pointed at the wrong tree*, and the two want different remedies: the first is
written down as a limit, the second is fixed.

**The tell separating them, which is the half worth carrying, is whether the case
can be manufactured.** Family membership is not a question anybody can answer at the
moment of the decision — it asks whether an instrument could exist at *any* distance,
which is unfalsifiable from inside a tree. *Can I build the case?* is answerable in
one attempt. Here it took stripping one argument from a real manifest, so the hole was
closeable all along and writing it down as a limit would have been a false comfort:
a documented hole reads as a boundary, and this one was a bug.

That is the positive-control practice arriving from the other end. This file already
holds it as *when the live data cannot produce the case, a render that did not show it
is not evidence, and the fix is to manufacture the case rather than to look harder* —
[[schedule]] round 9, where the operator's live payload contained none of the three
absences the screen had to distinguish. Same move, pointed at a gate instead of a
screen: **do not ask whether the green is trustworthy, ask whether you can make it go
red on purpose.** A gate that cannot be made to fail has not been shown to pass.
