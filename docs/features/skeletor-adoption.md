---
status: active
created: 2026-09-06
updated: 2026-09-06
agent_value: 3
key_files: [.skeletor.json, .skeletor-components.json, skyboss/, cli/]
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

## Phases

### Round 1 — the rename (2026-09-06)

Independent of skeletor and correct on its own terms; a scaffold that lands on a
half-renamed tree is unreviewable.

- [ ] `cli/` → `skyboss/`, 494 import sites, 39 config references, 313 prose
      references, and the `sb` wrapper's `python -m`.
- [ ] Suite green, both gates green, eslint green, and `sb` exercised for real —
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
