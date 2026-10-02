/**
 * The ONE definition of "does this pull request earn the full suite".
 *
 * Read by ci.yml's gate job and by pr-draft-discipline.yml. Never re-inline the
 * pattern in a workflow: two copies of this rule drift, and the copy that is
 * wrong is the one deciding whether tests run.
 *
 * FAIL-OPEN, deliberately. An API error, an empty file list, or one path this
 * does not recognise leaves `docsOnly = false` and runs everything. A false
 * negative costs minutes; a false POSITIVE skips lint, tests and security *and*
 * marks them satisfied, so the PR merges having proven nothing.
 */

/** Paths whose change cannot affect runtime behaviour. */
const DOC_PATTERNS = [
  /^docs\/.*\.(md|json|ya?ml)$/,
  /^\.claude\/.*\.md$/,
  /^[^/]*\.md$/,
  /^\.github\/(DOCS_INDEX\.md|ISSUE_TEMPLATE\/.*|PULL_REQUEST_TEMPLATE\.md)$/,
  /^LICENSE$/,
];

/** Branch heads that are exempt from job-level gating — see below. */
const ALWAYS_FULL_SUITE_HEADS = [/^chore\/combined-dependabot$/];

module.exports = async function decide({ github, context, core }) {
  const pr = context.payload.pull_request;

  // Any non-PR event earns the full suite — which is a push to ANY long-lived
  // branch, not only the release branch. `ci.yml`'s `push:` trigger decides
  // which branches those are, and this rule does not read it: whatever reaches
  // here without a pull request runs everything.
  //
  // The narrower sentence that used to sit here — *a push to the release branch
  // is a release* — was a true statement about one of the branches this fires
  // on, one line above the code that refutes it. It survived into
  // `docs/DEVELOPMENT.md`'s pipeline table, where it told a two-branch reader
  // that pushes to the branch they actually work on ran nothing.
  // `tests/test_ci_pipeline_table.py` now holds the table against the trigger.
  if (!pr) {
    return { docsOnly: false, fullSuite: true, reason: 'not a pull request — full suite' };
  }

  const base = pr.base.ref;
  const head = pr.head.ref;
  const author = pr.user.login;

  // Dependency bumps are the change class integration exists to catch, and
  // auto-merge fires the moment branch protection is satisfied. Exempting them
  // from gating is load-bearing, not a courtesy: without it, every eligible
  // bump merges having never run the suite.
  //
  // Two-part test on purpose. A combine-PRs action opens the batched bump under
  // whoever ran it, so an author-only check would exclude exactly the PR the
  // combine step exists to produce.
  const isDependabot =
    author === 'dependabot[bot]' || ALWAYS_FULL_SUITE_HEADS.some((re) => re.test(head));
  if (isDependabot) {
    return { docsOnly: false, fullSuite: true, reason: 'dependency bump — full suite' };
  }

  // ## The order below is the whole design, and it took three measurements
  //
  // Classify FIRST, then ask about the base — and only about a change the
  // classifier says carries code. The two questions are independent and were
  // for a long time fused into one test that ran before either was asked.
  //
  // What that cost, in the order it was found. `base === 'main'`
  // alone was true for EVERY pull request in a tree whose base branch is its
  // release branch, so `DOC_PATTERNS`, the `listFiles` call and this whole
  // classification half were unreachable there: a README-only change ran
  // integration and UI with no way to opt out. Qualifying it with
  // `'main' !== 'develop'` made the classifier reachable
  // and took the release-candidate rule away from the trees that need it most
  // — a one-branch tree merges into the branch it releases from, so a code
  // change reaching it un-integrated has no other gate in front of it.
  //
  // Both were true statements about one axis. Walking the cross product is
  // what produced this order, and no single tree could have done it: the
  // docs-only row needs both conditions at once and is exactly where the two
  // sets overlap, so it was invisible to an analysis anchored on `docsOnly`
  // and to the correction anchored on `fullSuite`. node-zero's diagnosis, and
  // the reason this comment describes an order rather than a condition.
  //
  //     event                       two-branch (dev/main)   one-branch (main/main)
  //     push                        full                    full
  //     draft PR carrying code      node + unit + gate      node + unit + gate
  //     dependency bump             full                    full
  //     docs-only PR -> base        gate only               gate only
  //     docs-only PR -> release     gate only               (same PR as above)
  //     code PR -> base             node + unit + gate      (same PR as below)
  //     code PR -> release          full                    full
  //
  // The two-branch column loses exactly one row against the previous release:
  // a genuinely docs-only pull request into the release branch now runs the
  // gate alone. That is this file's entire premise applied to the one base it
  // used to exempt itself from, and a release pull request is unaffected —
  // `VERSION` and `.release-please-manifest.json` are not in `DOC_PATTERNS`,
  // so release-please's own PR classifies as code and takes the row below.
  //
  // ## Why running the classifier first is not a cost
  //
  // It adds one `listFiles` call to release-candidate pull requests. In
  // exchange the fail-open paths now cover every pull request rather than
  // every pull request except the ones going somewhere that matters, which is
  // the direction you want a fail-open to face.
  //
  // ## What is given up, stated per-tree because it is not uniform
  //
  // A docs-only pull request merges without integration having run on it, in
  // every tree and both versioning modes. Integration still runs before
  // anything is released: the merge produces a push, a push takes the `!pr`
  // branch at the top of this file and earns the full suite, and
  //
  //     release-please:
  //       needs: [lint, node, unit-tests, integration]
  //
  // puts the release job downstream of it. **This tree is
  // `--versioning tag`.** Under `tag` the push releases nothing and
  // the annotated tag comes later, which makes that push a real gate rather
  // than a formality.
  //
  // Which jobs that actually costs is a fact about the adopting tree, not
  // about this file, and the honest answer has ranged from *everything to
  // nothing* to *nothing at all* on the same commit. dream-doll measured
  // theirs at zero — their lint gates are duplicated in `check pre-push` and
  // their integration and UI suites collect no tests, while their real user
  // interface suite is 107 vitest tests in the `node:` job, which is gated on
  // `docs_only` and therefore runs. Apply your own `FULL-SUITE-BECAUSE:`
  // markers to the three jobs below rather than reading a number from here.
  //
  // ## History, because three earlier versions of this comment were wrong
  //
  // The first said the merge is always the release; every tree that could have
  // made that true was `--versioning tag`, so the reason held for none of them.
  // The second fixed the reason and left the code testing one flag. The third
  // fixed the code and put the test in the wrong place, which is this one.
  //
  // Found by mind.head and node-zero, both by executing this file with real
  // payload shapes rather than reading it, and by dream-doll, whose first
  // execution returned the previous release's answer because their harness
  // omitted `github.rest` and the script took its failing-open branch. That is
  // worth knowing about anything downstream of this file: **when a system
  // fails open, a broken instrument reports the safe answer**, and `reason` is
  // the only field that distinguishes the two.

  let files;
  try {
    files = await github.paginate(github.rest.pulls.listFiles, {
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: pr.number,
      per_page: 100,
    });
  } catch (error) {
    core.warning(`could not list files (${error.message}) — failing open to the full suite`);
    return { docsOnly: false, fullSuite: true, reason: 'file list unavailable — failing open' };
  }

  if (!files.length) {
    return { docsOnly: false, fullSuite: true, reason: 'empty file list — failing open' };
  }

  // **Both fail-opens above are unconditional early returns and must stay
  // that way.** Now that the classification runs first, the tidy-looking
  // refactor is to route them into the code verdict below and let the
  // release-branch rule decide them — which in a two-branch tree turns them
  // into `gate + node + unit-tests` for anything not aimed at the release
  // branch. **A fail-open whose answer depends on the base branch is not
  // failing open**; it is fail-partial, on precisely the event where least is
  // known about the change. node-zero's finding, from executing both paths.
  //
  // This ordering is also what makes the classification safe to run first at
  // all. A pull request into the release branch used to return before
  // `listFiles` was ever called, so that path had no API dependency; it has
  // one now, and these two returns are its entire failure handling.

  const nonDoc = files
    .map((f) => f.filename)
    .filter((name) => !DOC_PATTERNS.some((re) => re.test(name)));

  if (nonDoc.length === 0) {
    return { docsOnly: true, fullSuite: false, reason: `docs-only (${files.length} files)` };
  }

  // A draft carrying code runs the gate, the node job and the unit suite —
  // NOT the gate alone, which is what this comment claimed for three releases
  // while returning `docsOnly: false` and therefore running both of those.
  //
  // **It sits below the classification, and that placement is the fix rather
  // than an accident of refactoring.** Above it, a docs-only DRAFT never
  // reached the classifier and landed in the code verdict, so it ran the node
  // job and the unit suite — and marking it ready for review then dropped it
  // to the gate alone. Two jobs to zero, on the one transition in GitHub's
  // model that exists to escalate. node-zero measured it; the sentence that
  // used to sit here — *`ready_for_review` re-runs the full set before it can
  // merge* — was the safety argument for the rule it was attached to, and it
  // was false in the direction that matters.
  //
  // Below it, both rules mean *less* and neither can outrank the other in the
  // wrong direction: a docs-only change is the gate alone whether draft or
  // ready, and the draft rule applies to code, where escalation on
  // `ready_for_review` is real.
  //
  // Nothing is un-gated by this. GitHub blocks merging a draft regardless.
  if (pr.draft) {
    return {
      docsOnly: false,
      fullSuite: false,
      reason: 'draft PR carrying code — gate, node and unit tests',
    };
  }

  // A code change entering the released branch is a release candidate. In a
  // two-branch tree that is the pull request release-please opens; in a
  // one-branch tree it is every code pull request, which is the point — that
  // branch is what a stranger clones.
  //
  // **Both branch names are substituted, so this is decided at scaffold time
  // and costs nothing at run time.** A one-branch tree renders
  // `base === 'main'`, which every pull request satisfies.
  if (base === 'main') {
    return {
      docsOnly: false,
      fullSuite: true,
      reason: `code change into the release branch ${base} — full suite (e.g. ${nonDoc[0]})`,
    };
  }

  return {
    docsOnly: false,
    fullSuite: false,
    reason: `code change into ${base} — unit tests only (e.g. ${nonDoc[0]})`,
  };
};
