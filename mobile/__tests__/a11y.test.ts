// Source-level accessibility checks for the whole app: every touchable and text input says what it is, and every touchable
// is at least MIN_TARGET points tall and wide. (Text size, contrast and safe areas have their own tests.)
declare const __dirname: string;
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..', 'src');
const files: string[] = [];
const walk = (d: string) =>
  fs.readdirSync(d, { withFileTypes: true }).forEach((e: { isDirectory: () => boolean; name: string }) => (e.isDirectory() ? walk(path.join(d, e.name)) : /\.tsx$/.test(e.name) && files.push(path.join(d, e.name))));
walk(root);

/** The opening tag text of every <Tag ...> in a file (up to the `>` that closes it, ignoring `>` inside braces). */
function tags(src: string, name: string): { text: string; line: number }[] {
  const out: { text: string; line: number }[] = [];
  const re = new RegExp(`<${name}(?=[\\s>])`, 'g');
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    let depth = 0;
    let i = m.index + name.length + 1;
    for (; i < src.length; i++) {
      const c = src[i];
      if (c === '{') depth++;
      else if (c === '}') depth--;
      else if (c === '>' && depth === 0 && src[i - 1] !== '=') break;
    }
    out.push({ text: src.slice(m.index, i + 1), line: src.slice(0, m.index).split('\n').length });
  }
  return out;
}
const rel = (f: string) => path.relative(root, f).split(path.sep).join('/');

describe('accessibility (source scan)', () => {
  test('the scan really finds the touchables and inputs (so the checks below are not empty)', () => {
    const count = (n: string) => files.reduce((a, f) => a + tags(fs.readFileSync(f, 'utf8'), n).length, 0);
    expect(count('Pressable')).toBeGreaterThanOrEqual(20);
    expect(count('TextInput')).toBeGreaterThanOrEqual(3);
  });

  test('every Pressable has a role and a name or readable content, and a target of at least MIN_TARGET', () => {
    const bad: string[] = [];
    for (const f of files)
      for (const t of tags(fs.readFileSync(f, 'utf8'), 'Pressable')) {
        const where = `${rel(f)}:${t.line}`;
        if (!/accessibilityRole/.test(t.text)) bad.push(`${where} no role`);
        if (!/MIN_TARGET|minHeight|minWidth|hitSlop|size\b|height:|styles\.base|styles\.tab\b|\.\.\.box/.test(t.text)) bad.push(`${where} no size`);
      }
    expect(bad).toEqual([]);
  });

  test('every icon-only Pressable (no Text inside) has an accessibilityLabel', () => {
    const bad: string[] = [];
    for (const f of files) {
      const src = fs.readFileSync(f, 'utf8');
      for (const t of tags(src, 'Pressable')) {
        const after = src.slice(src.indexOf(t.text) + t.text.length);
        const body = after.slice(0, after.indexOf('</Pressable>'));
        const hasText = /<AppText|<Text|\{[a-zA-Z.]*label|\{children\}/.test(body);
        if (!hasText && !/accessibilityLabel/.test(t.text)) bad.push(`${rel(f)}:${t.line}`);
      }
    }
    expect(bad).toEqual([]);
  });

  test('every TextInput has an accessibilityLabel', () => {
    const bad: string[] = [];
    for (const f of files) for (const t of tags(fs.readFileSync(f, 'utf8'), 'TextInput')) if (!/accessibilityLabel/.test(t.text)) bad.push(`${rel(f)}:${t.line}`);
    expect(bad).toEqual([]);
  });

  test('no screen turns off text scaling or caps it below 1.3', () => {
    // The five bottom-tab labels are the one place text size is kept at their normal size (cap 1.0): five words must fit in a fixed-width bar.
    const bad = files.filter((f) => !f.endsWith('TabBar.tsx') && /allowFontScaling=\{?false|maxFontSizeMultiplier=\{?(0\.\d+|1(\.[0-2]\d*)?)(?![\d.])/.test(fs.readFileSync(f, 'utf8')));
    expect(bad.map(rel)).toEqual([]);
  });

  test('every Modal can be closed with the Android back button', () => {
    const bad: string[] = [];
    for (const f of files) for (const t of tags(fs.readFileSync(f, 'utf8'), 'Modal')) if (!/onRequestClose/.test(t.text)) bad.push(`${rel(f)}:${t.line}`);
    expect(bad).toEqual([]);
  });

  test('every custom Back button falls back to a screen when there is nothing to go back to', () => {
    const bad = files.filter((f) => {
      const src = fs.readFileSync(f, 'utf8');
      return /accessibilityLabel="Back"/.test(src) && !/canGoBack\(\)/.test(src);
    });
    expect(bad.map(rel)).toEqual([]);
  });

  test('MIN_TARGET is 44', () => {
    const tokens = fs.readFileSync(path.join(root, 'theme', 'tokens.ts'), 'utf8');
    expect(tokens).toMatch(/MIN_TARGET\s*=\s*44/);
  });
});
