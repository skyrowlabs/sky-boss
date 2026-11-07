// One product script in the `node` job, by the rule `check pre-push` applies: present
// runs, declared in `skeletor.requiredScripts` and missing is refused, otherwise there
// is no subject. Its own file because that job sets up no python, so `check.py` cannot
// be asked. No subject exits 0, the code CI reads as anything but red.
'use strict';

const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');

const gate = process.argv[2];
const manifest = JSON.parse(readFileSync('package.json', 'utf8'));

if (manifest.scripts?.[gate]) {
  const ran = spawnSync('npm', ['run', gate], { stdio: 'inherit' });
  process.exit(ran.status ?? 1);
}
if (manifest.skeletor?.requiredScripts?.includes(gate)) {
  console.error(`refused: package.json requires the \`${gate}\` script and has none`);
  process.exit(2);
}
console.error(`no subject: no \`${gate}\` script in package.json`);
