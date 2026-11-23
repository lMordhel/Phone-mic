/**
 * Contrast audit for every palette the page can wear.
 *
 * The page has twelve themes and one set of derived tokens, so a single bad
 * ratio would silently ship eleven times. This checks the exact values
 * `themeStylesheet` emits, at WCAG AA: 4.5:1 for body text, 3:1 for the large
 * wordmark.
 *
 *   node scripts/check-contrast.ts      (Node 22.18+ strips the types)
 */

import { contrast, deriveTokens, toCss, THEMES, type RGB } from '../src/data/themes.ts';

interface Pair {
  label: string;
  fg: (tokens: ReturnType<typeof deriveTokens>) => RGB;
  bg: (tokens: ReturnType<typeof deriveTokens>) => RGB;
  min: number;
}

const PAIRS: Pair[] = [
  { label: 'text / bg', fg: (t) => t.text, bg: (t) => t.bg, min: 4.5 },
  { label: 'text / bg-2', fg: (t) => t.text, bg: (t) => t.bg2, min: 4.5 },
  { label: 'text / bg-3', fg: (t) => t.text, bg: (t) => t.bg3, min: 4.5 },
  { label: 'muted / bg', fg: (t) => t.muted, bg: (t) => t.bg, min: 4.5 },
  { label: 'muted / bg-2', fg: (t) => t.muted, bg: (t) => t.bg2, min: 4.5 },
  { label: 'muted / bg-3', fg: (t) => t.muted, bg: (t) => t.bg3, min: 4.5 },
  { label: 'link / bg', fg: (t) => t.link, bg: (t) => t.bg, min: 4.5 },
  { label: 'link / bg-2', fg: (t) => t.link, bg: (t) => t.bg2, min: 4.5 },
  { label: 'accent / bg (wordmark)', fg: (t) => t.accent, bg: (t) => t.bg, min: 3 },
  { label: 'on-accent / accent-fill', fg: (t) => t.onAccent, bg: (t) => t.accentFill, min: 4.5 },
  { label: 'ok / bg-2', fg: (t) => t.ok, bg: (t) => t.bg2, min: 4.5 },
  { label: 'warn / bg-2', fg: (t) => t.warn, bg: (t) => t.bg2, min: 4.5 },
  { label: 'bad / bg-2', fg: (t) => t.bad, bg: (t) => t.bg2, min: 4.5 },
];

let failures = 0;
const rows: string[] = [];

for (const theme of THEMES) {
  const tokens = deriveTokens(theme);
  let worst = Number.POSITIVE_INFINITY;
  let worstLabel = '';

  for (const pair of PAIRS) {
    const ratio = contrast(pair.fg(tokens), pair.bg(tokens));
    const normalised = ratio / pair.min;
    if (normalised < worst) {
      worst = normalised;
      worstLabel = pair.label;
    }
    if (ratio < pair.min) {
      failures += 1;
      rows.push(
        `  FAIL ${theme.name.padEnd(16)} ${pair.label.padEnd(22)} ${ratio.toFixed(2)}:1 < ${pair.min}:1  (${toCss(pair.fg(tokens))} on ${toCss(pair.bg(tokens))})`,
      );
    }
  }

  process.stdout.write(
    `  ${theme.name.padEnd(16)} tightest ${worstLabel.padEnd(22)} ${(worst * 1).toFixed(2)}× the requirement\n`,
  );
}

process.stdout.write(`\n${THEMES.length} themes · ${THEMES.length * PAIRS.length} checks\n`);

if (failures > 0) {
  process.stdout.write(`${failures} failing pairs:\n${rows.join('\n')}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write('all pairs meet WCAG AA\n');
}
