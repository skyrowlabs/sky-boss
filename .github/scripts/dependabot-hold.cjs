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

//: The package.json sections that are dev. Read from the base-ref manifest the
//: workflow fetches; without it, from the hunk, where a 3-line context often
//: does not show the section. Either way a section not established is `unknown`,
//: which is held and not labelled runtime (dream-doll's eslint read as runtime).
const DEV_SECTIONS = ['devDependencies'];

//: A lockfile restates its manifest plus every transitive package, so beside a
//: changed package.json the manifest decides.
const LOCKFILE = /(^|\/)(package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml)$/;

//: npm's JSON lockfile, read alone entry by entry: only an entry's own `"version"`
//: is a version. Read line by line, an `engines` `"node": "18 || 20"` was a node
//: major and two entries of one package shared a key (dream-doll#28).
const NPM_LOCK = /(^|\/)(package-lock\.json|npm-shrinkwrap\.json)$/;
const LOCK_ENTRY = /^[-+ ]\s*"((?:[^"]*\/)?node_modules\/(?:@[^/"]+\/)?[^/"]+)"\s*:\s*\{/;
const LOCK_VERSION = /^([-+])\s*"version"\s*:\s*"v?(\d+)(?:\.(\d+))?/;
const LOCK_DEV = /^[-+ ]\s*"dev(?:Optional)?"\s*:\s*true/;

//: npm and Actions: one version per line, at the line's start.
const LINE_VERSIONS = [
  // npm package.json: `"name": "^1.2.3"`
  /^([-+])\s*"([^"]+)"\s*:\s*"[~^>=<\s]*v?(\d+)(?:\.(\d+))?/,
  // GitHub Actions: `uses: owner/repo@v4`
  /^([-+]).*\buses:\s*([^@\s]+)@v?(\d+)(?:\.(\d+))?/,
];

//: pip: every `name==1.2.3`, `name>=1.2` or `name[extra]~=1.2` on the line, so a
//: one-line pyproject list `dev = ["pytest>=8.0", "black>=24"]` reads as two.
//: Anchoring at the line's start read none of it, and its majors merged (mind-head).
const PIP_SPEC =
  /(?:^|[\s"',[])([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:===|==|~=|>=|<=|!=|>|<)\s*v?(\d+)(?:\.(\d+))?/g;

//: Files whose lines the patterns above claim to read. A changed line in one of
//: them that yields no version is held as unknown: a shape this cannot read must
//: not be read as "no major".
const READ_SHAPES = [
  /(^|\/)[^/]*requirements[^/]*\.txt$/,
  /(^|\/)pyproject\.toml$/,
  /(^|\/)package\.json$/,
  /(^|\/)\.github\/workflows\/[^/]+\.ya?ml$/,
];

//: A changed line with nothing to read: blank, a comment, a hash, or punctuation.
const NOTHING_TO_READ = /^\s*(?:$|#|\/\/|--hash=|[[\]{}(),]+\s*$)/;

//: Every version on one diff line, as { sign, name, major, minor }.
function versionsOn(line) {
  const sign = line[0];
  if (sign !== '-' && sign !== '+') return [];
  for (const pattern of LINE_VERSIONS) {
    const m = pattern.exec(line);
    if (m)
      return [{ sign, name: m[2], major: parseInt(m[3], 10), minor: parseInt(m[4] || '0', 10) }];
  }
  const body = line.slice(1);
  if (NOTHING_TO_READ.test(body)) return [];
  return [...body.matchAll(PIP_SPEC)].map((m) => ({
    sign,
    name: m[1],
    major: parseInt(m[2], 10),
    minor: parseInt(m[3] || '0', 10),
  }));
}

const SECURITY_FOOTER = /disable automated security fix PRs/i;
const SECURITY_LABELS = ['security', 'dependabot-security'];

const SECTION_OPEN = /^[-+ ]\s*"(\w*[dD]ependencies)"\s*:\s*\{/;
const SECTION_CLOSE = /^[-+ ]\s*\},?\s*$/;

//: A base manifest as JSON; one absent or unparseable is null, so the hunk decides.
function parsed(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

//: The section `pkg` is declared in, from the parsed base manifest, or null.
function declaredSection(manifest, pkg) {
  if (!manifest || typeof manifest !== 'object') return null;
  const sections = Object.keys(manifest).filter(
    (key) => /dependencies$/i.test(key) && manifest[key] && pkg in manifest[key]
  );
  return sections.length === 1 ? sections[0] : null;
}

//: A finding for a version change worth holding, or null.
function majorFinding(pkg, prev, next) {
  if (next.major > prev.major) return `${pkg} ${prev.major}.x -> ${next.major}.x`;
  if (HOLD_PRE_1_0_MINOR && prev.major === 0 && next.major === 0 && next.minor > prev.minor)
    return `${pkg} 0.${prev.minor} -> 0.${next.minor} (pre-1.0 minor)`;
  return null;
}

//: Majors in an npm lockfile changed alone. An entry is dev when the base
//: lockfile's `packages` says so or the hunk shows `"dev": true`; neither is unknown.
function lockBumps(name, patch, base) {
  const packages = (base && base.packages) || {};
  const entries = new Map();
  let entry = null;
  for (const line of (patch || '').split('\n')) {
    if (line.startsWith('@@')) {
      entry = null;
      continue;
    }
    const opened = LOCK_ENTRY.exec(line);
    if (opened) {
      entry = opened[1];
      if (!entries.has(entry)) entries.set(entry, { dev: false });
      continue;
    }
    if (!entry) continue;
    const seen = entries.get(entry);
    if (LOCK_DEV.test(line)) seen.dev = true;
    const m = LOCK_VERSION.exec(line);
    if (m) seen[m[1]] = { major: parseInt(m[2], 10), minor: parseInt(m[3] || '0', 10) };
  }
  const bumps = [];
  for (const [path, seen] of entries) {
    if (!seen['-'] || !seen['+']) continue;
    const pkg = path.slice(path.lastIndexOf('node_modules/') + 'node_modules/'.length);
    const finding = majorFinding(pkg, seen['-'], seen['+']);
    if (!finding) continue;
    const declared = packages[path];
    const dev = seen.dev || Boolean(declared && (declared.dev || declared.devOptional));
    const tier = dev ? 'dev' : declared ? 'runtime' : 'unknown';
    bumps.push({
      finding: `${finding} in ${name}`,
      tier,
      what: 'a lockfile major not known to be dev',
    });
  }
  return bumps;
}

//: Every major bump in one file, each marked dev, runtime or unknown.
function majorBumps(file, files, manifests) {
  const name = file.filename || '';
  if (LOCKFILE.test(name)) {
    const dir = name.slice(0, name.lastIndexOf('/') + 1);
    if ((files || []).some((other) => other.filename === `${dir}package.json`)) return [];
  }
  if (NPM_LOCK.test(name)) return lockBumps(name, file.patch, parsed(manifests && manifests[name]));
  const packageJson = /(^|\/)package\.json$/.test(name);
  const devManifest = DEV_MANIFESTS.some((pattern) => pattern.test(name));
  const before = new Map();
  const after = new Map();
  let section = null;
  const base = packageJson ? parsed(manifests && manifests[name]) : null;
  const readable = READ_SHAPES.some((pattern) => pattern.test(name));
  const unread = [];
  for (const line of (file.patch || '').split('\n')) {
    // Each hunk starts afresh: a section open in one hunk says nothing about the
    // next, and carrying it classed a runtime major as dev (dream-doll).
    if (line.startsWith('@@')) {
      section = null;
      continue;
    }
    const opened = SECTION_OPEN.exec(line);
    if (opened) {
      section = opened[1];
      continue;
    }
    if (SECTION_CLOSE.test(line)) section = null;
    const found = versionsOn(line);
    for (const { sign, name: pkg, major, minor } of found) {
      (sign === '-' ? before : after).set(pkg.toLowerCase(), { major, minor, section });
    }
    const changed = line[0] === '-' || line[0] === '+';
    if (readable && changed && !found.length && !NOTHING_TO_READ.test(line.slice(1)))
      unread.push(line);
  }
  const bumps = unread.slice(0, 1).map((line) => ({
    finding: `\`${line.slice(1).trim()}\` in ${name}`,
    tier: 'unknown',
    what: 'a changed line this cannot read',
  }));
  for (const [pkg, next] of after) {
    const prev = before.get(pkg);
    if (!prev) continue;
    const finding = majorFinding(pkg, prev, next);
    if (!finding) continue;
    let tier = devManifest ? 'dev' : 'runtime';
    if (packageJson) {
      const declared = declaredSection(base, pkg) || next.section;
      tier = declared ? (DEV_SECTIONS.includes(declared) ? 'dev' : 'runtime') : 'unknown';
    }
    bumps.push({
      finding: `${finding} in ${name}`,
      tier,
      what: 'a major whose section is not known',
    });
  }
  return bumps;
}

function decide({ pr, files, manifests }) {
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
  const bumps = (files || []).flatMap((file) => majorBumps(file, files, manifests));
  const runtime = bumps.filter((bump) => bump.tier === 'runtime');
  const unknown = bumps.filter((bump) => bump.tier === 'unknown');
  if (runtime.length) {
    // `runtime-major` is the tier the workflow labels, for whoever drafts migrations.
    return {
      merge: false,
      tier: 'runtime-major',
      reason: `${kind} with a runtime major: ${runtime[0].finding} — left for review`,
    };
  }
  if (unknown.length) {
    return {
      merge: false,
      tier: 'unknown',
      reason: `${kind} with ${unknown[0].what}: ${unknown[0].finding} — left for review`,
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
    (file.patch || '').split('\n').some((line) => versionsOn(line).length > 0)
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
}

//: The manifests whose base-ref text `decide` reads, for the workflow to fetch.
decide.manifestPaths = (files) =>
  (files || [])
    .map((file) => file.filename || '')
    .filter((name) => /(^|\/)package\.json$/.test(name) || NPM_LOCK.test(name));

module.exports = decide;
