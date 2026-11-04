// Whether a Dependabot pull request may merge itself, decided from its diff.
//
// `dependabot-auto-merge.yml` calls this after CI has passed on the pull
// request, and merges only when it returns `merge: true`. Pure: it reads the
// pull request and its files and nothing else, so `bin/skeletor-verify` runs it
// over a table of cases with node.
//
// Three tiers. A patch or minor merges, security updates included. A major in
// a dev manifest merges too: the suite running under the new version is the
// migration test. A major anywhere else is runtime and waits for a person.
//
// The design is jam.sense's (`dependabot-auto-approve.yml`), ported as a shape.
// Its three lessons are each a rule below:
//
// * A major bump is read from the DIFF, never from the title alone. A grouped
//   pull request is titled "bump the pip group with 4 updates", and that is the
//   one most likely to hide a major.
// * A security update is recognised by a marker Dependabot emits only for
//   security updates (its alerts footer, or a `security` label), never by the
//   word "security" in the body. Every Dependabot body links to a page with that
//   word in its URL, and the substring test held back every pull request.
// * Anything not authored by Dependabot is never merged here, whatever its branch.

'use strict';

//: Treat a 0.x minor bump as breaking, which semver allows. Off, as in jam.sense:
//: on, almost every batch carries a 0.x package and nothing merges itself.
const HOLD_PRE_1_0_MINOR = false;

//: Manifests whose packages only build and test this tree, so a major there
//: merges on green CI. Classified by file, not package name: Dependabot's
//: dependency-type metadata is unreliable for requirements files. Add your own
//: dev manifests here; anything unmatched is runtime and held. `scripts/requirements.txt`
//: pins `click` too, which runs this tree's own CLI, and the suite exercises it.
const DEV_MANIFESTS = [/(^|\/)scripts\/requirements\.txt$/, /(^|\/)requirements-dev[^/]*\.txt$/];

//: The package.json sections that are dev. Read from the hunk, so a bump whose
//: hunk does not show its section is unknown, and unknown is held.
const DEV_SECTIONS = ['devDependencies'];

//: A lockfile restates its manifest plus every transitive package, so beside a
//: changed package.json the manifest decides; alone, its majors are runtime.
const LOCKFILE = /(^|\/)(package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml)$/;

//: One leading version per line, for the three ecosystems dependabot.yml names.
const VERSION_LINES = [
  // pip: `name==1.2.3`, `name>=1.2`, `name[extra]~=1.2`, and pyproject's `"name>=1.2",`
  /^([-+])\s*"?([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*[><=~!]+\s*v?(\d+)(?:\.(\d+))?/,
  // npm package.json: `"name": "^1.2.3"`
  /^([-+])\s*"([^"]+)"\s*:\s*"[~^>=<\s]*v?(\d+)(?:\.(\d+))?/,
  // GitHub Actions: `uses: owner/repo@v4`
  /^([-+]).*\buses:\s*([^@\s]+)@v?(\d+)(?:\.(\d+))?/,
];

const SECURITY_FOOTER = /disable automated security fix PRs/i;
const SECURITY_LABELS = ['security', 'dependabot-security'];

const SECTION_OPEN = /^[-+ ]\s*"(\w*[dD]ependencies)"\s*:\s*\{/;
const SECTION_CLOSE = /^[-+ ]\s*\},?\s*$/;

//: Every major bump in one file, each marked dev or runtime.
function majorBumps(file, files) {
  const name = file.filename || '';
  if (LOCKFILE.test(name)) {
    const dir = name.slice(0, name.lastIndexOf('/') + 1);
    if ((files || []).some((other) => other.filename === `${dir}package.json`)) return [];
  }
  const packageJson = /(^|\/)package\.json$/.test(name);
  const devManifest = DEV_MANIFESTS.some((pattern) => pattern.test(name));
  const before = new Map();
  const after = new Map();
  let section = null;
  for (const line of (file.patch || '').split('\n')) {
    const opened = SECTION_OPEN.exec(line);
    if (opened) {
      section = opened[1];
      continue;
    }
    if (SECTION_CLOSE.test(line)) section = null;
    for (const pattern of VERSION_LINES) {
      const m = pattern.exec(line);
      if (!m) continue;
      const version = { major: parseInt(m[3], 10), minor: parseInt(m[4] || '0', 10), section };
      (m[1] === '-' ? before : after).set(m[2].toLowerCase(), version);
      break;
    }
  }
  const bumps = [];
  for (const [pkg, next] of after) {
    const prev = before.get(pkg);
    if (!prev) continue;
    let finding = null;
    if (next.major > prev.major) finding = `${pkg} ${prev.major}.x -> ${next.major}.x`;
    else if (
      HOLD_PRE_1_0_MINOR &&
      prev.major === 0 &&
      next.major === 0 &&
      next.minor > prev.minor
    ) {
      finding = `${pkg} 0.${prev.minor} -> 0.${next.minor} (pre-1.0 minor)`;
    }
    if (!finding) continue;
    const dev = packageJson ? DEV_SECTIONS.includes(next.section) : devManifest;
    bumps.push({ finding: `${finding} in ${name}`, dev });
  }
  return bumps;
}

module.exports = function decide({ pr, files }) {
  const author = (pr && pr.user && pr.user.login) || '';
  if (author !== 'dependabot[bot]') {
    return { merge: false, reason: `authored by ${author || 'nobody'}, not dependabot[bot]` };
  }
  const labels = (pr.labels || []).map((l) => String((l && l.name) || l).toLowerCase());
  const label = labels.find((name) => SECURITY_LABELS.includes(name));
  const security = label || SECURITY_FOOTER.test(pr.body || '');
  const kind = security
    ? `a security update (${label ? `\`${label}\` label` : 'alerts footer'})`
    : 'an update';
  const bumps = (files || []).flatMap((file) => majorBumps(file, files));
  const runtime = bumps.filter((bump) => !bump.dev);
  if (runtime.length) {
    // `runtime-major` is what the workflow labels for the agentic `dep-migrate` job.
    return {
      merge: false,
      tier: 'runtime-major',
      reason: `${kind} with a runtime major: ${runtime[0].finding} — left for review`,
    };
  }
  if (bumps.length) {
    const named = bumps.map((bump) => bump.finding).join(', ');
    return {
      merge: true,
      reason: `${kind} with dev-tool majors only (${named}); CI green is the migration test`,
    };
  }
  // The title is a backstop only for a diff that showed no version at all.
  const read = (files || []).some((file) =>
    (file.patch || '')
      .split('\n')
      .some((line) => VERSION_LINES.some((pattern) => pattern.test(line)))
  );
  if (
    !read &&
    String(pr.title || '')
      .toLowerCase()
      .includes('major')
  ) {
    return {
      merge: false,
      reason: 'the title names a major update and the diff shows none — left for review',
    };
  }
  return { merge: true, reason: `${kind}, patch or minor, with CI green` };
};
