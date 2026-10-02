import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
const OUT = process.argv[2], HEADER = process.argv[3];
const sha = (b) => createHash('sha256').update(b).digest('hex');

const css = readFileSync(join(OUT, 'sb.css'), 'utf8') + readFileSync(join(OUT, 'tokens.css'), 'utf8');
const classes = [...new Set([...css.matchAll(/(^|[\s,{}>+~():])\.([a-zA-Z][-a-zA-Z0-9_]*)/gm)].map((m) => m[2]))].sort();
const tokens = [...new Set([...css.matchAll(/(--[a-zA-Z][-a-zA-Z0-9_]*)\s*:/g)].map((m) => m[1]))].sort();

const body = `\n---\n\n# Reference\n\nGenerated from the built stylesheet. sky.boss is the source of truth:\n\`cli/theme.py\` for the roles, \`cli/canvas/static/sb.css\` for everything else.\n\n## Roles and derived values\n\n${tokens.map((t) => `\`${t}\``).join(' · ')}\n\n## Classes\n\n${classes.length} classes, one stylesheet.\n\n${classes.map((c) => `\`.${c}\``).join(' · ')}\n`;
writeFileSync(join(OUT, 'README.md'), readFileSync(HEADER, 'utf8') + body);

const header = { namespace: 'SkyBoss', components: [], sourceHashes: {}, inlinedExternals: [] };
writeFileSync(join(OUT, '_ds_bundle.js'), `/* @ds-bundle: ${JSON.stringify(header)} */
/* sky.boss is a CSS design system: the surface is one stylesheet and there are
   no runtime components to expose. */
window.SkyBoss = window.SkyBoss || {};
`);
writeFileSync(join(OUT, '.ds-build-meta.json'), JSON.stringify({
  shape: 'package', componentCount: 0, dtsStubbed: false,
  source: 'sky-boss cli/theme.py + cli/canvas/static/sb.css',
  generator: 'design-sync off-script (CSS-only DS)' }, null, 2));

let styleBytes = css + readFileSync(join(OUT, 'styles.css'), 'utf8');
for (const f of readdirSync(join(OUT, 'preview'))) styleBytes += readFileSync(join(OUT, 'preview', f), 'utf8');
writeFileSync(join(OUT, '_ds_sync.json'), JSON.stringify({
  shape: 'package', styleSha: sha(styleBytes), renderHashes: {}, sourceKeys: {},
  keyRecipe: 'css-only-v1', scriptsSha: null, sourceHashes: {},
  auxSha: sha(readFileSync(join(OUT, 'README.md'))),
  bundleSha12: sha(readFileSync(join(OUT, '_ds_bundle.js'))).slice(0, 12) }, null, 2));
mkdirSync(join(OUT, 'components'), { recursive: true });
console.log(JSON.stringify({ classes: classes.length, tokens: tokens.length }));
