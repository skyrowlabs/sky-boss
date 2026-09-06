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

### Round 3 — suites and CI (not started)

**16 inherited tests are red and they are all one thing.** skeletor's CI model is
marker-selected suites — a `gate` job, then `unit`, `integration` and `ui` jobs
each running `pytest -m <marker>` — and `tests/test_ci_runs_every_suite.py` scans
the workflows for those selections. sky.boss has **no markers at all**: 1485
tests in one flat suite that CI runs whole.

- [ ] Backfill markers. This is the work, not overhead — it is the first time
      anyone writes down which of these tests need a stack up.
- [ ] Restructure `ci.yml`. **This is the step with a consequence outside the
      repo.** Branch protection on `develop` *and* `main` requires exactly
      `eslint`, `pytest 3.12`, `pytest 3.14` — read from the API, not assumed.
      skeletor's `ci.yml` names its jobs `CI Gate`, `Lint & Types`,
      `Unit Tests (host-side)`. Adopting it wholesale means those three contexts
      never report again, and a context no job reports blocks every pull request
      for ever, on both branches. Either the merged workflow keeps producing all
      three names, or branch protection changes in the same sitting.
- [ ] Land any new gate as a non-required check first.

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
`scripts/check_source_doc_refs.py`, which writes `~/build/` and `~/dist/` in a
comment — about false positives from matching absolute paths. It identifies
nobody, so it is a false positive; reworded here, and worth sending upstream
since every adopter with a publication gate will hit it. And skeletor's
`cli/helpers.py` broke *our* `test_imports.py`, because it re-exports eleven
names through `__all__` and this tree had no `__all__` when that gate was
written. pyflakes counts an `__all__` entry as a use; ours did not. Fixed, and
re-verified against flake8 — both now report zero across the merged tree.

That is the thing a component consumer cannot buy: neither gate could have found
the other while the two halves lived in different repositories.
