/**
 * Route helpers.
 *
 * The site is built with `base: '/'`, but a preview deploy can serve it from a
 * sub-path, so every link that leaves the current document goes through
 * `withBase` instead of being hardcoded. The join is slash-safe: `/` + `/es/`
 * is `/es/`, never `//es/`.
 */
export function withBase(path: string): string {
  const base = import.meta.env.BASE_URL || '/';
  const prefix = base.endsWith('/') ? base.slice(0, -1) : base;
  const suffix = path.startsWith('/') ? path : `/${path}`;
  return `${prefix}${suffix}`;
}
