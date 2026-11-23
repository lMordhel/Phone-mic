/**
 * Design tokens for the promotional page.
 *
 * The twelve palettes are copied verbatim from `tui/phone_mic_tui.py` (THEMES), so
 * the site and the terminal panel cannot drift apart: a theme is a look, not a
 * single accent colour. Every derived token is computed here — never hand-picked —
 * so the contrast audit in `scripts/check-contrast.ts` checks the exact values the
 * page ships.
 */

export type RGB = readonly [number, number, number];

export type Role =
  | 'bg'
  | 'border'
  | 'accent'
  | 'label'
  | 'text'
  | 'dim'
  | 'ok'
  | 'bad'
  | 'warn'
  | 'level_low'
  | 'level_mid'
  | 'level_hot';

export type Family = 'PASTEL' | 'DARK' | 'LIGHT' | 'WARM';

export interface Theme {
  name: string;
  family: Family;
  roles: Record<Role, RGB>;
}

export const THEMES: Theme[] = [
  {
    name: 'pastel-mint',
    family: 'PASTEL',
    roles: {
      bg: [235, 245, 240], border: [150, 200, 180], accent: [60, 150, 130],
      label: [90, 170, 150], text: [40, 80, 70], dim: [145, 175, 165],
      ok: [70, 170, 120], bad: [225, 125, 135], warn: [215, 175, 95],
      level_low: [110, 200, 160], level_mid: [240, 200, 110], level_hot: [235, 140, 150],
    },
  },
  {
    name: 'pastel-lavender',
    family: 'PASTEL',
    roles: {
      bg: [242, 238, 250], border: [200, 190, 225], accent: [120, 100, 190],
      label: [140, 120, 200], text: [60, 50, 90], dim: [172, 165, 198],
      ok: [110, 175, 150], bad: [215, 115, 140], warn: [220, 180, 110],
      level_low: [150, 130, 230], level_mid: [230, 190, 120], level_hot: [230, 120, 150],
    },
  },
  {
    name: 'pastel-peach',
    family: 'PASTEL',
    roles: {
      bg: [253, 242, 235], border: [240, 205, 185], accent: [200, 110, 80],
      label: [215, 140, 110], text: [90, 60, 50], dim: [200, 170, 155],
      ok: [130, 180, 130], bad: [215, 105, 100], warn: [225, 170, 90],
      level_low: [240, 160, 120], level_mid: [235, 180, 100], level_hot: [220, 110, 100],
    },
  },
  {
    name: 'dark-mono',
    family: 'DARK',
    roles: {
      bg: [18, 18, 18], border: [70, 70, 70], accent: [205, 205, 205],
      label: [155, 155, 155], text: [225, 225, 225], dim: [110, 110, 110],
      ok: [150, 205, 150], bad: [220, 120, 120], warn: [210, 190, 120],
      level_low: [165, 165, 165], level_mid: [205, 205, 205], level_hot: [245, 245, 245],
    },
  },
  {
    name: 'dark-ocean',
    family: 'DARK',
    roles: {
      bg: [10, 20, 30], border: [30, 60, 80], accent: [80, 200, 220],
      label: [90, 170, 200], text: [200, 230, 240], dim: [90, 120, 140],
      ok: [80, 200, 170], bad: [230, 110, 120], warn: [230, 190, 90],
      level_low: [70, 180, 200], level_mid: [120, 210, 230], level_hot: [240, 140, 150],
    },
  },
  {
    name: 'dark-forest',
    family: 'DARK',
    roles: {
      bg: [12, 22, 16], border: [40, 70, 50], accent: [140, 220, 150],
      label: [110, 180, 130], text: [210, 235, 215], dim: [90, 120, 100],
      ok: [130, 220, 140], bad: [225, 120, 110], warn: [220, 190, 100],
      level_low: [110, 200, 130], level_mid: [170, 225, 140], level_hot: [235, 150, 120],
    },
  },
  {
    name: 'light-paper',
    family: 'LIGHT',
    roles: {
      bg: [250, 250, 248], border: [205, 205, 200], accent: [60, 60, 60],
      label: [100, 100, 100], text: [30, 30, 30], dim: [150, 150, 148],
      ok: [60, 150, 90], bad: [200, 70, 70], warn: [190, 140, 40],
      level_low: [80, 160, 110], level_mid: [200, 160, 60], level_hot: [200, 80, 80],
    },
  },
  {
    name: 'light-sky',
    family: 'LIGHT',
    roles: {
      bg: [240, 247, 252], border: [190, 210, 225], accent: [50, 110, 160],
      label: [80, 130, 175], text: [30, 50, 70], dim: [150, 170, 185],
      ok: [60, 150, 120], bad: [200, 80, 90], warn: [200, 150, 60],
      level_low: [90, 170, 200], level_mid: [200, 170, 80], level_hot: [205, 90, 95],
    },
  },
  {
    name: 'light-sand',
    family: 'LIGHT',
    roles: {
      bg: [250, 247, 240], border: [215, 205, 185], accent: [140, 110, 60],
      label: [160, 130, 80], text: [60, 50, 35], dim: [170, 160, 140],
      ok: [110, 150, 90], bad: [190, 90, 70], warn: [190, 150, 60],
      level_low: [170, 150, 90], level_mid: [200, 165, 80], level_hot: [195, 105, 80],
    },
  },
  {
    name: 'warm-amber',
    family: 'WARM',
    roles: {
      bg: [30, 20, 10], border: [90, 60, 25], accent: [245, 180, 70],
      label: [210, 160, 80], text: [250, 235, 210], dim: [140, 110, 80],
      ok: [200, 190, 110], bad: [230, 110, 80], warn: [245, 190, 80],
      level_low: [220, 170, 70], level_mid: [245, 195, 90], level_hot: [240, 110, 70],
    },
  },
  {
    name: 'warm-ember',
    family: 'WARM',
    roles: {
      bg: [26, 14, 12], border: [80, 40, 35], accent: [240, 120, 80],
      label: [215, 140, 110], text: [245, 225, 215], dim: [140, 95, 85],
      ok: [200, 180, 120], bad: [235, 95, 70], warn: [240, 160, 70],
      level_low: [235, 140, 90], level_mid: [245, 170, 90], level_hot: [240, 90, 60],
    },
  },
  {
    name: 'warm-clay',
    family: 'WARM',
    roles: {
      bg: [245, 235, 225], border: [210, 185, 165], accent: [170, 100, 70],
      label: [150, 105, 85], text: [70, 50, 40], dim: [175, 155, 140],
      ok: [130, 150, 105], bad: [195, 85, 70], warn: [200, 150, 80],
      level_low: [185, 130, 95], level_mid: [210, 160, 90], level_hot: [195, 95, 75],
    },
  },
];

export const DEFAULT_THEME = 'warm-amber';

export const FAMILY_ORDER: Family[] = ['PASTEL', 'DARK', 'LIGHT', 'WARM'];

export const themeNames = THEMES.map((theme) => theme.name);

/** Ink used on top of a solid accent fill: the higher-contrast one wins. */
export const INK_LIGHT: RGB = [248, 250, 252];
export const INK_DARK: RGB = [8, 12, 16];

const channel = (value: number): number => {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};

export const luminance = ([r, g, b]: RGB): number =>
  0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);

export const contrast = (a: RGB, b: RGB): number => {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
};

/** sRGB interpolation, identical to CSS `color-mix(in srgb, a, b weight)`. */
export const mix = (a: RGB, b: RGB, weightB: number): RGB => [
  Math.round(a[0] * (1 - weightB) + b[0] * weightB),
  Math.round(a[1] * (1 - weightB) + b[1] * weightB),
  Math.round(a[2] * (1 - weightB) + b[2] * weightB),
];

/** The ink that reads best on a given fill. */
const inkFor = (fill: RGB): RGB =>
  contrast(fill, INK_LIGHT) >= contrast(fill, INK_DARK) ? INK_LIGHT : INK_DARK;

/**
 * A solid accent fill, pushed away from its own ink until WCAG AA holds. The hue
 * survives; `warm-clay` is the palette that needs it (both inks land near 4.3).
 */
const solidFill = (accent: RGB): { fill: RGB; ink: RGB } => {
  const ink = inkFor(accent);
  const away = ink === INK_LIGHT ? INK_DARK : INK_LIGHT;
  let fill = accent;
  for (let step = 1; step <= 12; step += 1) {
    fill = mix(accent, away, step * 0.05);
    if (contrast(fill, ink) >= 4.5) return { fill, ink };
  }
  return { fill, ink };
};

/**
 * The terminal palettes use `ok`, `warn` and `bad` as indicator colours — right
 * for a bar or a dot, too weak for text on a light background. Nudging them
 * toward the theme ink keeps the semantics and makes them legible as words.
 */
const readable = (
  color: RGB,
  ink: RGB,
  surface: RGB,
  min = 4.5,
  maxWeight = 0.9,
): RGB => {
  if (contrast(color, surface) >= min) return color;
  for (let weight = 0.1; weight <= maxWeight + 1e-9; weight += 0.1) {
    const candidate = mix(color, ink, weight);
    if (contrast(candidate, surface) >= min) return candidate;
  }
  return ink;
};

export interface Tokens {
  bg: RGB;
  bg2: RGB;
  bg3: RGB;
  border: RGB;
  border2: RGB;
  accent: RGB;
  accentFill: RGB;
  onAccent: RGB;
  link: RGB;
  text: RGB;
  muted: RGB;
  dim: RGB;
  ok: RGB;
  bad: RGB;
  warn: RGB;
  levelLow: RGB;
  levelMid: RGB;
  levelHot: RGB;
}

/**
 * Derived tokens. Every text colour is anchored to the surface it sits on, so
 * the audit in `scripts/check-contrast.ts` checks the values the page ships:
 * body copy against `bg-3` (the lightest/darkest surface), state text against
 * `bg-2` (inside the terminal blocks).
 */
export const deriveTokens = (theme: Theme): Tokens => {
  const { bg, border, accent, text, dim, ok, bad, warn, level_low, level_mid, level_hot } =
    theme.roles;
  const bg2 = mix(bg, text, 0.06);
  const bg3 = mix(bg, text, 0.13);
  const solid = solidFill(accent);
  return {
    bg,
    bg2,
    bg3,
    border,
    border2: mix(border, text, 0.4),
    accent,
    accentFill: solid.fill,
    onAccent: solid.ink,
    link: readable(mix(accent, text, 0.38), text, bg3),
    text,
    muted: readable(mix(dim, text, 0.58), text, bg3),
    dim,
    ok: readable(ok, text, bg2),
    bad: readable(bad, text, bg2),
    warn: readable(warn, text, bg2),
    levelLow: level_low,
    levelMid: level_mid,
    levelHot: level_hot,
  };
};

export const toCss = (rgb: RGB): string => `rgb(${rgb[0]} ${rgb[1]} ${rgb[2]})`;

const tokenCss = (tokens: Tokens): string =>
  [
    `--bg:${toCss(tokens.bg)}`,
    `--bg-2:${toCss(tokens.bg2)}`,
    `--bg-3:${toCss(tokens.bg3)}`,
    `--border:${toCss(tokens.border)}`,
    `--border-2:${toCss(tokens.border2)}`,
    `--accent:${toCss(tokens.accent)}`,
    `--accent-fill:${toCss(tokens.accentFill)}`,
    `--on-accent:${toCss(tokens.onAccent)}`,
    `--link:${toCss(tokens.link)}`,
    `--text:${toCss(tokens.text)}`,
    `--muted:${toCss(tokens.muted)}`,
    `--dim:${toCss(tokens.dim)}`,
    `--ok:${toCss(tokens.ok)}`,
    `--bad:${toCss(tokens.bad)}`,
    `--warn:${toCss(tokens.warn)}`,
    `--level-low:${toCss(tokens.levelLow)}`,
    `--level-mid:${toCss(tokens.levelMid)}`,
    `--level-hot:${toCss(tokens.levelHot)}`,
  ].join(';');

const defaultTheme = THEMES.find((theme) => theme.name === DEFAULT_THEME) ?? THEMES[0];

/** Custom-property blocks for every palette, emitted inline into `<head>`. */
export const themeStylesheet = [
  `:root{${tokenCss(deriveTokens(defaultTheme))}}`,
  ...THEMES.map(
    (theme) => `[data-theme="${theme.name}"]{${tokenCss(deriveTokens(theme))}}`,
  ),
].join('\n');
