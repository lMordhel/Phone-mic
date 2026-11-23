import { defineConfig } from 'astro/config';

// Single static document: no adapters, no islands framework.
//
// Deployed on Vercel with the project Root Directory set to `site` (see
// README → Deploy). Vercel detects Astro, runs `npm ci && npm run build` and
// serves `dist/`; no adapter is involved and no Node runtime ships.
//
// Once the first deployment gives you a domain, set it here so canonical and
// social URLs are absolute:
//   site: 'https://<project>.vercel.app',
export default defineConfig({
  output: 'static',
  compressHTML: true,
});
