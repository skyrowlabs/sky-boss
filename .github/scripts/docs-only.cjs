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

  // A PR into the release branch is a release candidate — where the base
  // branch and the release branch are different. **This tree was scaffolded
  // `--base-branch develop --release-branch main`**, and
  // if those read the same, every pull request here takes this branch and
  // everything below it is unreachable: `DOC_PATTERNS`, the `listFiles` call,
  // the whole classification half. A README edit runs the full suite.
  //
  // **Whether that outcome is right depends on a second flag, and two earlier
  // versions of this comment each keyed it to whichever one the writer's
  // evidence was about.** The question is whether a push to
  // `main` cuts a release:
  //
  //   * `--versioning release-please` — it does, so the merge IS the release,
  //     the pull request is the last chance to run anything, and a cheap path
  //     would put integration first on already-released code. **This tree is
  //     `--versioning tag`.**
  //   * `--versioning tag` — it does not. A push to `main`
  //     releases nothing; an annotated tag does. So the full suite that runs on
  //     that push happens BEFORE the release and is itself a gate, which makes
  //     a cheap path on the pull request affordable — exactly as it is in a
  //     two-branch tree, where the base branch merging here is the later run.
  //
  // So in a one-branch tag-versioned tree the cost is real and unrecovered:
  // the full suite runs on a docs-only pull request and there is no way to opt
  // out, because the classification half this comment sits above is
  // unreachable. Recovering it means moving the docs-only test above this one,
  // which changes when a repository's gates run — an adopter's decision rather
  // than a generator's default, and the trade is *do we accept integration
  // first running post-merge and pre-tag* rather than *do we release untested
  // code*.
  //
  // The wrong version of this said the merge is always the release. Every tree
  // that could have made that true was `--versioning tag`, so the reason held
  // for none of them — a sentence about a two-flag mechanism keyed to one
  // flag, which is the third time that shape has been written down today.
  //
  // Found by mind.head, who executed this file with real payload shapes rather
  // than reading it, and by skyrow-workspace, who surveyed the manifests. Half
  // the adopters at the time. No test here could have said so: they assert this
  // workflow's structure, and the dead branch is a fact about an argument
  // recorded in `.skeletor.json`.
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
