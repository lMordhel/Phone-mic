/**
 * Snapshot the built page into the design folder as one self-contained artboard,
 * so what the canvas shows is byte-for-byte what the site serves.
 *
 *   npm run build && node scripts/snapshot-design.ts
 *
 * The artboard rules from the design skill (no external URLs, everything inline)
 * are met by inlining the hashed CSS and module script the build emits.
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const distDir = fileURLToPath(new URL('../dist/', import.meta.url));
const outDir = fileURLToPath(new URL('../../design/phone-mic-promo/', import.meta.url));
const outFile = `${outDir}01-warm-terminal.html`;

let html = readFileSync(`${distDir}index.html`, 'utf8');

const readAsset = (href: string): string =>
  readFileSync(`${distDir}${href.replace(/^\//, '')}`, 'utf8');

const inlinedStyles: string[] = [];
html = html.replace(
  /<link rel="stylesheet" href="([^"]+)"\s*\/?>/g,
  (_match, href: string) => {
    inlinedStyles.push(href);
    return `    <style>\n${readAsset(href)}\n    </style>`;
  },
);

const inlinedScripts: string[] = [];
html = html.replace(
  /<script type="module" src="([^"]+)"><\/script>/g,
  (_match, src: string) => {
    inlinedScripts.push(src);
    return `<script type="module">\n${readAsset(src)}\n</script>`;
  },
);

if (inlinedStyles.length === 0) {
  throw new Error('no stylesheet found in dist/index.html: run the build first');
}

mkdirSync(outDir, { recursive: true });
writeFileSync(outFile, html, 'utf8');

process.stdout.write(
  `wrote ${outFile}\n  inlined ${inlinedStyles.length} stylesheet(s), ${inlinedScripts.length} script(s)\n`,
);
