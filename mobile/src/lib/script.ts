// Telugu text must use a Telugu font; everything else uses the UI font.
const TELUGU = /[ఀ-౿]/;

export function hasTelugu(text: string): boolean {
  return TELUGU.test(text);
}

/** Flatten React children to the plain text they contain (strings and numbers only). */
export function plainText(children: unknown): string {
  if (typeof children === 'string' || typeof children === 'number') return String(children);
  if (Array.isArray(children)) return children.map(plainText).join('');
  return '';
}
