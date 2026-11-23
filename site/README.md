# phone-mic site

Promotional page for `phone-mic`, built as a terminal interface: a boxed frame,
monospace everything, box-drawing chrome and twelve palettes you can switch live.

```bash
npm install
npm run dev       # http://localhost:4321
npm run build     # static output in dist/
npm run preview   # serve dist/ on http://localhost:4321
```

`dist/` is plain HTML, CSS and one small module script, so it can be copied to
any static host.

## Deploy on Vercel

One manual setting decides everything: **Root Directory must be `site`**. The
repository root is the phone-mic tool (Python TUI, bash packaging) and has no
`package.json`; Vercel therefore has to start inside `site/`.

1. Import the repository at <https://vercel.com/new>.
2. Set **Root Directory** to `site` and keep the detected framework as **Astro**.
3. Build `npm run build`, output `dist/`, Node `24.x` — all already declared in
   `vercel.json` and `package.json`, so nothing else needs filling in.
4. No environment variables, no secrets, no database.

From the CLI, with the same result:

```bash
cd site
npx vercel          # first run links the project, preview deployment
npx vercel --prod   # production deployment
```

What `vercel.json` adds on top of the defaults:

| Setting | Why |
| --- | --- |
| `installCommand: npm ci` | installs from `package-lock.json`, reproducible builds |
| `outputDirectory: dist` | explicit, so a changed Astro default cannot break deploys |
| headers on `/:path*` | `nosniff`, `DENY` framing, strict referrer, camera and geolocation denied |
| `/_astro/*` cached 1 year | those filenames are content-hashed |

`Permissions-Policy` deliberately leaves `microphone` alone: the page does not
ask for it today, and a future audio demo would need it.

After the first deployment, put the domain Vercel gave you into
`astro.config.mjs` as `site`, so canonical and social URLs are absolute:

```js
site: 'https://<project>.vercel.app',
```

Pushing to the branch configured in Vercel redeploys automatically; pull requests
get preview URLs.

## Where the colours come from

`src/data/themes.ts` is the single source of truth. The twelve palettes are copied
verbatim from `tui/phone_mic_tui.py` (`THEMES`), so the site and the terminal panel
cannot drift apart. Each run derives every other token — panel surfaces, borders,
link, muted text, state text and the solid button fill — from those twelve roles
and emits one `[data-theme="<name>"]` block into the page head.

Two consequences worth knowing before you edit a palette:

- Do not hand-pick a derived colour in CSS. Add or change the derivation in
  `themes.ts`; the page and the audit then agree by construction.
- The terminal palettes use `ok`, `warn` and `bad` as indicator colours. They are
  nudged toward the theme ink before being used as text, because a colour that
  works as a 1-cell bar is unreadable as a sentence on a light background.

## Languages

English is the default and lives at `/`; every other language gets its own
static route, so each one is linkable, cacheable and indexable without any
JavaScript:

| Route | File | `<html lang>` |
| --- | --- | --- |
| `/` | `src/pages/index.astro` | `en` |
| `/es/` | `src/pages/es/index.astro` | `es` |

`src/i18n/copy.ts` is the single contract: it defines the English copy, derives
`type Copy` from it, and every other locale is typed as `Copy`, so a missing or
extra key is a compile error rather than a half-translated page. Components take
a `lang` prop and read `copy[lang]`.

Two rules keep this honest:

- **Terminal content is never translated.** The panel, the shell commands and
their output stay exactly as the tool prints them; only the prose around them
changes.
- **No string is hardcoded in a component, including UI chrome.** The skip link,
the nav `aria-label`, the COPY button labels and the theme announcement all come
from the copy module; the copy button reads its labels from `data-*` attributes
so `client.ts` stays language-agnostic.

Adding a language means: add the locale to `LANGS`, add its `Copy` object, add
`src/pages/<code>/index.astro`, and add the route to `routeFor()` in
`Base.astro`. Nothing else changes.

`hreflang` alternates are emitted only when `site` is set in `astro.config.mjs`,
because an alternate link must be an absolute URL and a wrong host is worse than
no link at all.

## Checks

```bash
node scripts/check-contrast.ts   # 12 palettes × 13 pairs, WCAG AA
npm run build                    # must exit 0
```

The contrast audit is the gate for design changes: it fails the build of your
confidence, not the build, so run it yourself after touching a palette or a
derived token.

## Structure

| Path | Role |
| --- | --- |
| `src/pages/index.astro` | English page (route `/`) |
| `src/pages/es/index.astro` | Spanish page (route `/es/`) |
| `src/i18n/copy.ts` | every string on the page, per language |
| `src/lib/paths.ts` | `withBase()`, so links survive a `base` path |
| `src/layouts/Base.astro` | document head, inline palette blocks, starfield host |
| `src/components/` | one file per section |
| `src/styles/base.css` | layout and components; colours only via custom properties |
| `src/scripts/client.ts` | stars, level meter, live palette picker, copy buttons |
| `src/data/themes.ts` | palettes and token derivation |
| `scripts/check-contrast.ts` | WCAG audit over every palette |
| `scripts/snapshot-design.ts` | inlines the build into the design artboard |
| `vercel.json` | build, output, headers and cache policy |
| `public/robots.txt` | crawler policy |
