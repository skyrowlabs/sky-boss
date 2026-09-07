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

  // A push to the release branch is a release. Everything runs.
  if (!pr) {
    return { docsOnly: false, fullSuite: true, reason: 'not a pull request — full suite' };
  }

  // A draft runs the gate alone. Nothing is un-gated by this: GitHub blocks
  // merging a draft regardless, and `ready_for_review` re-runs the full set
  // before it can merge.
  if (pr.draft) {
    return { docsOnly: false, fullSuite: false, reason: 'draft PR — gate only' };
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

  // A PR into the release branch is a release candidate — **where the base
  // branch and the release branch are different.** This tree was scaffolded
  // `--base-branch develop --release-branch main`, and
  // the second half of that condition is why this test compares two rendered
  // values rather than one.
  //
  // It used to test `base === 'main'` alone. The sentence above
  // it already named the real condition and the code did not check it, so in a
  // one-branch tree the test was true for EVERY pull request: `DOC_PATTERNS`,
  // the `listFiles` call and the whole classification half below were
  // unreachable, and a README-only change ran integration and UI with no way to
  // opt out. Three trees were in that state and none could have found it from
  // inside — an unreachable branch is not an error, it is a branch that never
  // wins.
  //
  // **The two branch names are substituted, so this is decided at scaffold time
  // and costs nothing at run time.** A two-branch tree renders
  // `'main' !== 'develop'` and behaves exactly as it did before this line
  // changed. A one-branch tree renders `'main' !== 'main'` and falls through to
  // the classification.
  //
  // ## Why falling through is safe, in both versioning modes
  //
  // The obvious worry is that a docs-only pull request now merges without
  // integration having run on it. It does — and integration still runs before
  // anything is released, because the merge produces a push, a push takes the
  // `!pr` branch at the top of this file and earns the full suite, and:
  //
  //     release-please:
  //       needs: [lint, node, unit-tests, integration]
  //
  // So the release job is downstream of integration on that push. That holds
  // for `--versioning release-please`, where the push is what opens the release
  // pull request, and for `--versioning tag`, where the push releases nothing at
  // all and the annotated tag comes later. **This tree is
  // `--versioning tag`.** An earlier version of this comment argued
  // the trade was `tag`-specific — *integration first running post-merge but
  // pre-tag* — which understated it: the guarantee is pre-RELEASE, and the
  // `needs:` edge is what supplies it either way.
  //
  // What is genuinely given up is that integration runs after the merge rather
  // than before it, so the release branch can go briefly red on a pre-existing
  // break. For a change the classifier says contains no code, integration's
  // verdict cannot differ from its verdict on the parent commit except by flake
  // or by external drift — and this is already the status quo for docs pull
  // requests into the base branch of every two-branch tree.
  //
  // The classification half is the safety argument, which is why it fails open
  // on an API error, an empty file list, or any path it does not recognise.
  //
  // ## History, because two earlier versions of this comment were wrong
  //
  // The first said the merge is always the release. Every tree that could have
  // made that true was `--versioning tag`, so the reason held for none of them
  // — a sentence about a two-flag mechanism keyed to one flag. The second fixed
  // the reason and left the code testing one flag, which is the same error one
  // layer down: the comment knew about `develop` and the condition did
  // not.
  //
  // Found by mind.head, who executed this file with real payload shapes rather
  // than reading it, and by skyrow-workspace, who surveyed the manifests. No
  // test here could have said so: they assert this workflow's structure, and a
  // dead branch is a fact about an argument recorded in `.skeletor.json`.
  if (base === 'main' && 'main' !== 'develop') {
    return { docsOnly: false, fullSuite: true, reason: 'targets the release branch — full suite' };
  }

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

  const nonDoc = files
    .map((f) => f.filename)
    .filter((name) => !DOC_PATTERNS.some((re) => re.test(name)));

  if (nonDoc.length === 0) {
    return { docsOnly: true, fullSuite: false, reason: `docs-only (${files.length} files)` };
  }

  return {
    docsOnly: false,
    fullSuite: false,
    reason: `code change into ${base} — unit tests only (e.g. ${nonDoc[0]})`,
  };
};
