// WCAG 2.x contrast check for Dawat's colour tokens. Reads the hex values straight from src/app/globals.css, so the
// numbers are always for the colours actually shipped. Exit 1 if any required pair fails.
//   node scripts/check_contrast.mjs
// The rendered pages are checked separately by the ui-checker sub-agent; this guards the palette itself.

import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/app/globals.css", import.meta.url), "utf8");
// Brand colours live in @theme as --color-plum etc.; shadcn slots in :root as --primary etc. Both by short name.
const tokens = Object.fromEntries([...css.matchAll(/--(?:color-)?([\w-]+):\s*(#[0-9a-fA-F]{6})\b/g)]
  .map((m) => [m[1], m[2]]));

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground token, background token, minimum, what it is]
const TEXT = 4.5, UI = 3;
const PAIRS = [
  ["foreground", "background", TEXT, "body text on the page"],
  ["card-foreground", "card", TEXT, "text on cards"],
  ["muted-foreground", "background", TEXT, "secondary text on the page"],
  ["muted-foreground", "card", TEXT, "secondary text on cards"],
  ["muted-foreground", "muted", TEXT, "secondary text on muted panels"],
  ["primary-foreground", "primary", TEXT, "text on plum buttons and the banner"],
  ["secondary-foreground", "secondary", TEXT, "plum text on plum-tint chips"],
  ["accent-foreground", "accent", TEXT, "plum text on hover / selected rows"],
  ["primary", "background", TEXT, "plum links and headings on ivory"],
  ["primary", "card", TEXT, "plum links on cards"],
  ["destructive", "background", TEXT, "error text on the page"],
  ["destructive", "card", TEXT, "error text on cards"],
  ["veg", "background", TEXT, "veg label on the page"],
  ["veg", "card", TEXT, "veg label on cards"],
  ["nonveg", "background", TEXT, "non-veg label on the page"],
  ["nonveg", "card", TEXT, "non-veg label on cards"],
  ["ivory", "plum", TEXT, "ivory text on plum (header, banner)"],
  ["ivory", "night", TEXT, "ivory text on night"],
  ["gold", "plum", UI, "gold lines and icons on plum (decorative, UI minimum)"],
  ["gold", "night", UI, "gold lines and icons on night"],
  ["input", "background", UI, "form field borders on the page"],
  ["input", "card", UI, "form field borders on cards"],
  ["ring", "background", UI, "focus ring on the page"],
  ["ring", "card", UI, "focus ring on cards"],
];
// Gold must never be used as text on a light background: recorded here so the reason is visible.
const FORBIDDEN = [["gold", "ivory", "gold text on ivory (brand rule)"]];

let failed = 0;
for (const [fg, bg, min, what] of PAIRS) {
  if (!tokens[fg] || !tokens[bg]) {
    console.log(`MISSING  ${fg} on ${bg}: token not found in globals.css`);
    failed++;
    continue;
  }
  const r = ratio(tokens[fg], tokens[bg]);
  const ok = r >= min;
  if (!ok) failed++;
  console.log(`${ok ? "ok  " : "FAIL"}  ${r.toFixed(2).padStart(5)}:1 (needs ${min})  ${fg} ${tokens[fg]} on ${bg} ${tokens[bg]}  ${what}`);
}
for (const [fg, bg, what] of FORBIDDEN) {
  if (!tokens[fg] || !tokens[bg]) continue;
  console.log(`info  ${ratio(tokens[fg], tokens[bg]).toFixed(2).padStart(5)}:1  never use: ${what}`);
}
console.log(failed ? `\n${failed} pair(s) FAIL` : `\nall ${PAIRS.length} pairs pass`);
process.exit(failed ? 1 : 0);
