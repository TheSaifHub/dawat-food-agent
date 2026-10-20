// Local development only: starts Metro on the loopback address, with the local dev login switched on for THIS process.
// The switch is never written to a .env file. `npm start` (no switch) is the normal start.
// Node is told to prefer IPv4 so Metro listens on 127.0.0.1: `adb reverse` reaches the PC's IPv4 loopback, and a
// Metro bound only to IPv6 [::1] gives "Failed to download remote update" in Expo Go (docs/MOBILE_DEVICE_SETUP.md).
const { spawn } = require('node:child_process');

const api = process.env.EXPO_PUBLIC_API_URL;
if (api && !/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/.test(api)) {
  console.error('Refusing to enable the dev login: EXPO_PUBLIC_API_URL is not localhost.');
  process.exit(1);
}
const env = {
  ...process.env,
  EXPO_PUBLIC_DAWAT_DEV_LOGIN: '1',
  NODE_OPTIONS: `${process.env.NODE_OPTIONS || ''} --dns-result-order=ipv4first`.trim(),
};
const child = spawn('npx', ['expo', 'start', '--localhost', '--port', '8081', ...process.argv.slice(2)], {
  stdio: 'inherit',
  shell: true,
  env,
});
child.on('exit', (code) => process.exit(code ?? 0));
