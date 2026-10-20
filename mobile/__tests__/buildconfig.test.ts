// Guards the build setup: the release APK profile can never carry the dev-login switch, the development profile is separate,
// and every file app.json points at exists.
declare const __dirname: string;
const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..');
const read = (f: string) => JSON.parse(fs.readFileSync(path.join(root, f), 'utf8'));
const app = read('app.json').expo;
const eas = read('eas.json');

describe('build configuration', () => {
  test('the release apk profile is an APK, is not a development client, and has no dev-login switch', () => {
    const p = eas.build.apk;
    expect(p.android.buildType).toBe('apk');
    expect(p.developmentClient).toBeUndefined();
    expect(JSON.stringify(p)).not.toMatch(/DEV_LOGIN/);
    expect(p.autoIncrement).toBe('versionCode');
  });
  test('the development profile is a separate development client and is the only one with the dev login', () => {
    expect(eas.build.development.developmentClient).toBe(true);
    expect(eas.build.development.env.EXPO_PUBLIC_DAWAT_DEV_LOGIN).toBe('1');
    const others = Object.keys(eas.build).filter((k) => k !== 'development');
    for (const k of others) expect(JSON.stringify(eas.build[k])).not.toMatch(/DEV_LOGIN/);
  });
  test('versions are read from the project and no secret-looking value is in eas.json', () => {
    expect(eas.cli.appVersionSource).toBe('local');
    expect(JSON.stringify(eas)).not.toMatch(/secret|password|token|keystore/i);
  });
  test('package name, version and version code are set', () => {
    expect(app.android.package).toBe('com.dawat.app');
    expect(app.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(Number.isInteger(app.android.versionCode)).toBe(true);
  });
  test('the icon, adaptive icon and splash files exist and are square PNGs of the same size', () => {
    const splash = app.plugins.find((p: unknown) => Array.isArray(p) && p[0] === 'expo-splash-screen')[1];
    const files = [app.icon, app.android.adaptiveIcon.foregroundImage, app.android.adaptiveIcon.monochromeImage, splash.image];
    for (const f of files) {
      const buf = fs.readFileSync(path.join(root, f));
      expect(buf.subarray(1, 4).toString()).toBe('PNG');
      expect([buf.readUInt32BE(16), buf.readUInt32BE(20)]).toEqual([1024, 1024]);
    }
    expect(app.android.adaptiveIcon.backgroundColor).toBe('#21364B');
    expect(splash.backgroundColor).toBe('#21364B');
  });
});
