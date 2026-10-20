// Fails if a RELEASE bundle contains any trace of the local dev login (D-059 idea, docs/MOBILE_RULES.md rule 6).
// It exports a production Android bundle with the dev switch deliberately ON (the worst case) and scans every output
// file for the markers. Run: npm run check:release
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const MARKERS = ['dawat-dev-login-marker', '/dev/auth', 'Local sign-in (dev only)', 'New fake user', 'DevLoginPanel'];
const out = fs.mkdtempSync(path.join(os.tmpdir(), 'dawat-release-'));

const r = spawnSync('npx', ['expo', 'export', '--platform', 'android', '--output-dir', out], {
  shell: true,
  stdio: ['ignore', 'ignore', 'inherit'],
  env: { ...process.env, EXPO_PUBLIC_DAWAT_DEV_LOGIN: '1', CI: '1' },
});
if (r.status !== 0) {
  console.error('Release export failed; nothing was checked.');
  process.exit(2);
}

function* walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) yield* walk(p);
    else yield p;
  }
}

let files = 0;
let bytes = 0;
const hits = [];
for (const f of walk(out)) {
  const buf = fs.readFileSync(f);
  files += 1;
  bytes += buf.length;
  const text = buf.toString('latin1');
  for (const m of MARKERS) if (text.includes(m)) hits.push(`${m}  in  ${path.relative(out, f)}`);
}
fs.rmSync(out, { recursive: true, force: true });
console.log(`Scanned ${files} files, ${(bytes / 1e6).toFixed(1)} MB, for ${MARKERS.length} markers.`);
if (hits.length) {
  console.error('DEV LOGIN FOUND IN RELEASE BUNDLE:\n' + hits.join('\n'));
  process.exit(1);
}
console.log('OK: no dev-login code in the release bundle.');
