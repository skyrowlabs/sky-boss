import { readFileSync } from 'node:fs';
import { join } from 'node:path';
const OUT = process.argv[2], DOC = process.argv[3];

// Everything the shipped bundle actually contains. Two flat files: the roles
// generated from cli/theme.py, and the stylesheet itself.
const all = readFileSync(join(OUT, 'sb.css'), 'utf8') + readFileSync(join(OUT, 'tokens.css'), 'utf8');

const classes = new Set([...all.matchAll(/\.([a-zA-Z][-a-zA-Z0-9_]*)/g)].map((m) => m[1]));
const tokens = new Set([...all.matchAll(/(--[a-zA-Z][-a-zA-Z0-9_]*)\s*:/g)].map((m) => m[1]));
// Vars read via var() but defined elsewhere (set inline by the page) count too.
for (const m of all.matchAll(/var\((--[a-zA-Z][-a-zA-Z0-9_]*)/g)) tokens.add(m[1]);

const doc = readFileSync(DOC, 'utf8');
// Claimed names: `.foo` / `--foo` inside backticks, and class= attributes in the snippet.
const claimedClasses = new Set();
for (const m of doc.matchAll(/`([^`]+)`/g)) {
  for (const c of m[1].matchAll(/(^|[^\w.-])\.([a-zA-Z][-a-zA-Z0-9_]*)/g)) claimedClasses.add(c[2]);
}
for (const m of doc.matchAll(/class="([^"]+)"/g)) for (const c of m[1].split(/\s+/)) claimedClasses.add(c);
const claimedTokens = new Set();
for (const m of doc.matchAll(/(^|[\s`(|])(--[a-zA-Z][-a-zA-Z0-9_]*)/gm)) {
  claimedTokens.add(m[2].replace(/-$/, ''));
}

// Modifier shorthand in the doc ("--secondary" after a .btn--primary) is a
// fragment, not a token; only check things that look like real token names.
const tokenLike = [...claimedTokens].filter((t) => tokens.has(t) || /^--[a-z]+-[a-z0-9]/.test(t));
const badClasses = [...claimedClasses].filter((c) => !classes.has(c));
// `--status-live` in the chips list is a modifier fragment of `.chip--status-live`,
// not a token. Anything that completes a real class name is treated as such.
const isModifier = (t) => [...classes].some((c) => c.endsWith(t) && c.length > t.length);
const badTokens = tokenLike.filter((t) => !tokens.has(t) && !isModifier(t));

console.log(JSON.stringify({
  checkedClasses: claimedClasses.size, unverifiedClasses: badClasses,
  checkedTokens: tokenLike.length, unverifiedTokens: badTokens,
}, null, 2));
process.exit(badClasses.length || badTokens.length ? 1 : 0);
