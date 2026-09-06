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

  // A PR into the release branch is a release candidate.
  if (base === 'main') {
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
