# Development Guide

## First-Time Setup

```bash
python -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt
.venv/bin/pre-commit install --install-hooks
npm install
cp .env.example .env
./dev check pre-push   # green on a fresh tree
```

**There is no `dev setup`, and there cannot be.** The CLI needs `click`, which
lives in the virtualenv the setup would be creating — so a `setup` subcommand
could not run until after the work it exists to do. This section opened with one
anyway, for long enough that it shipped: the developer guide's very first command
did not exist, in a repository whose `AGENTS.md` explained on the same page that it
never had. Nothing could see the disagreement, because the two files were separate
copies of one instruction.

That was fixed where it could be: this block, the README's and `AGENTS.md`'s were
generated from one source when this repository was scaffolded. **Do not read that
as a standing guarantee** — a guarantee implemented by rendering is spent at the
moment of rendering. All three are static text here, the generator is not present,
and the three files wrap the shared steps differently.

What holds them together now is `tests/test_setup_blocks_agree.py`, which ratchets
on how many leading lines the three blocks agree on and fails when that number
drops. Change a shared step and you change it in all three, by hand — and the test
tells you if you missed one.

That last sentence is a present-tense claim about a mechanism, which is exactly
what the paragraph above says to distrust. It is honest here for the single reason
the warning turns on: the test ships beside this file and runs in the same
`dev check pre-push`, so there is no rendering step between the claim and its
enforcement, and nothing that could separate them later.

Two things it installs are easy to miss, because they live outside version control:

- **Git hooks** (`pre-commit install --install-hooks`, above) — the commit-msg
  format check and the lint gates.
- **The `regen-docs` merge driver** — its definition lives in `.git/config`, which
  is not tracked, so a fresh clone has `.gitattributes` pointing at a driver that
  does not exist. **Every clone after the first installs it by hand:**
  `python scripts/git/install_merge_drivers.py`. Verify with
  `dev check merge-drivers`, which checks and never installs.

## Configuration

Every value the application reads appears in `.env.example` with a comment. The
real `.env` is untracked, and a pre-commit hook refuses any `.env*` that is not
the example — a committed secret is a rotated secret.

Read config through the validated config object, never `os.getenv()` at the
point of use. Validation happens once at startup, so a misconfigured process
refuses to boot rather than failing on the first request that needs the value.

## The Gates

Every gate CI blocks on is runnable locally with the same invocation, **except
the integration suite**, which needs the stack up and so has no host equivalent.
That one exception is declared in `tests/test_pre_push_covers_ci.py`, which fails
when CI grows a blocking gate `pre-push` neither runs nor declares — the earlier
version of this sentence said "everything" and was wrong about three gates.

```bash
./dev check pre-push        # every host-runnable one, in fail-fastest order
./dev check pre-push --quick # no test suites; the rest still run
./dev check lint            # the blocking lint set
./dev check docs            # indexes, tables, links, refs, report anchors
```

Every gate runs even after one fails. One fix per round trip is the thing this
exists to avoid.

## Testing

Suites are selected by **marker**, and a test file joins a suite by declaring
one. There is no registry to update:

```python
pytestmark = [pytest.mark.unit]
```

```bash
./dev test unit             # host-side, no services
./dev test integration      # needs the stack up
./dev test all              # everything except `manual`
./dev test unit --ci        # reproduce CI's skip semantics locally
./dev test coverage -w 20   # the worst-covered modules — where a test buys most
```

`--ci` sets `SB_CI=1`, under which an env-gate skip becomes a **failure**.
That is the difference between "the suite passed" and "the suite ran".

Full rules: [`docs/rules/testing.md`](rules/testing.md).

## CI/CD Pipeline

| Event                          | What runs                              | ~min |
| ------------------------------ | -------------------------------------- | ---- |
| Draft PR                       | `CI Gate` alone                        | ~1   |
| Ready PR → `develop`, docs-only | `CI Gate` alone               | ~1   |
| Ready PR → `develop`, code      | `CI Gate` + `Unit Tests`      | ~5   |
| Ready PR opened by Dependabot  | **everything** — deliberately exempt   | full |
| Push to `main`   | **everything**                         | full |

Three things about this table are load-bearing:

1. **A required context that reports `skipped` satisfies branch protection.**
   So gating is done with `if:` on the job, never `paths-ignore` on the trigger
   — a required check that never reports at all blocks the PR forever.
2. **Requiring a context costs nothing; only running a job does.** Size the
   required list for what must gate. Never trim it to save minutes.
3. **The Dependabot exemption is a mechanism, not a courtesy.** Auto-merge fires
   the moment branch protection is satisfied, so without the exemption every
   eligible bump merges having never run the suite it exists to be checked by.

## Releases

Versioning is the annotated git tag and nothing else. There is no `VERSION`
file and no `CHANGELOG.md`: a repository run from a checkout already has the
answer in `git describe`, and a file would be a second home for it — kept in
step by hand, wrong the first time somebody forgets.

Cut a release with `git tag -a vX.Y.Z -m "what moved"` and **push the tag** — an
unpushed tag names a version only your machine can resolve, and `dev --version`
reads exactly this. Conventional commit subjects are still the rule; they are
what a reader of `git log` between two tags gets instead of a changelog.

A release closes the report window: in-flight reports under
`docs/reports/regular/` freeze into `docs/reports/releases/<tag>/`. See
[`docs/rules/docs.md`](rules/docs.md).

## Command Output

Every command splits its output the same way: **stdout is what a caller
consumes** (a `--json` payload, a generated block, a listing you may pipe) and
**stderr is what only a human reads** (status lines, progress, and the "what to
do next" under an error).

Both land on your terminal, so an interactive run looks the same either way. The
difference appears the moment you pipe one:

```bash
python scripts/check_doc_tables.py --json | jq        # payload only
./dev check docs 2>/dev/null                        # silent: it is all narration
```

Every `scripts/check_*.py` supports `--json` and answers on **every** path,
including the ones that pass — a ratchet you can only read when it is red says
nothing about which way it has been moving.

Nothing spells a status symbol or picks a stream by hand; it all comes from
`scripts/output.py`, and `dev check output` enforces that by pattern.
Full rules: [`docs/rules/output.md`](rules/output.md).

## Reproducing a CI Failure Locally

```bash
./dev check lint                        # 1. fastest feedback; catches most CI rejections
./dev test unit --ci                    # 2. CI's skip semantics
SB_PYTHON=.venv-ci/bin/python ./dev check pre-push   # 3. CI's exact interpreter
```

Step 3 matters more than it looks. A local venv that has drifted from CI's
pinned interpreter produces failures that exist in one environment and not the
other, and the tool names are identical, so the version never occurs to anyone.
