/**
 * keywords.ts — turn the keyword text box into a list and back.
 * Commas separate keywords; quotes keep a phrase together: `"sold out", restock` -> ["sold out", "restock"].
 */
export function parseKeywords(text: string): string[] {
  const out: string[] = [];
  const re = /"([^"]+)"|([^,]+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    const word = (m[1] ?? m[2] ?? '').trim();
    if (word && !out.some((w) => w.toLowerCase() === word.toLowerCase())) out.push(word);
  }
  return out;
}

export function formatKeywords(words: string[]): string {
  return words.map((w) => (w.includes(',') || w.includes(' ') ? `"${w}"` : w)).join(', ');
}
