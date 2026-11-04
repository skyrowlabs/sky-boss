// Whether a Dependabot pull request may merge itself, decided from its diff.
//
// `dependabot-auto-merge.yml` calls this after CI has passed on the pull
// request, and merges only when it returns `merge: true`. Pure: it reads the
// pull request and its files and nothing else, so `bin/skeletor-verify` runs it
// over a table of cases with node.
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

//: One leading version per line, for the three ecosystems dependabot.yml names.
const VERSION_LINES = [
  // pip: `name==1.2.3`, `name>=1.2`, `name[extra]~=1.2`
  /^([-+])\s*([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*[><=~!]+\s*v?(\d+)(?:\.(\d+))?/,
  // npm package.json: `"name": "^1.2.3"`
  /^([-+])\s*"([^"]+)"\s*:\s*"[~^>=<\s]*v?(\d+)(?:\.(\d+))?/,
  // GitHub Actions: `uses: owner/repo@v4`
  /^([-+]).*\buses:\s*([^@\s]+)@v?(\d+)(?:\.(\d+))?/,
];

const SECURITY_FOOTER = /disable automated security fix PRs/i;
const SECURITY_LABELS = ['security', 'dependabot-security'];

function majorBump(patch) {
  const before = new Map();
  const after = new Map();
  for (const line of (patch || '').split('\n')) {
    for (const pattern of VERSION_LINES) {
      const m = pattern.exec(line);
      if (!m) continue;
      const version = { major: parseInt(m[3], 10), minor: parseInt(m[4] || '0', 10) };
      (m[1] === '-' ? before : after).set(m[2].toLowerCase(), version);
      break;
    }
  }
  for (const [name, next] of after) {
    const prev = before.get(name);
    if (!prev) continue;
    if (next.major > prev.major) return `${name} ${prev.major}.x -> ${next.major}.x`;
    if (HOLD_PRE_1_0_MINOR && prev.major === 0 && next.major === 0 && next.minor > prev.minor) {
      return `${name} 0.${prev.minor} -> 0.${next.minor} (pre-1.0 minor)`;
    }
  }
  return null;
}

module.exports = function decide({ pr, files }) {
  const author = (pr && pr.user && pr.user.login) || '';
  if (author !== 'dependabot[bot]') {
    return { merge: false, reason: `authored by ${author || 'nobody'}, not dependabot[bot]` };
  }
  for (const file of files || []) {
    const finding = majorBump(file.patch);
    if (finding)
      return {
        merge: false,
        reason: `major bump in ${file.filename}: ${finding} — left for review`,
      };
  }
  if (
    String(pr.title || '')
      .toLowerCase()
      .includes('major')
  ) {
    return { merge: false, reason: 'the title names a major update — left for review' };
  }
  const labels = (pr.labels || []).map((l) => String((l && l.name) || l).toLowerCase());
  const label = labels.find((name) => SECURITY_LABELS.includes(name));
  if (label || SECURITY_FOOTER.test(pr.body || '')) {
    return {
      merge: false,
      reason: `a security update (${label ? `\`${label}\` label` : 'alerts footer'}) — left for review`,
    };
  }
  return { merge: true, reason: 'patch or minor version update with CI green' };
};
