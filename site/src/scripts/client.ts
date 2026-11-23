/**
 * Progressive enhancement only: the page is complete and readable without any of
 * this. Stars, the level meter, the live palette picker and the copy buttons.
 */

const THEME_KEY = 'phone-mic-theme';

/* ------------------------------------------------------------------- stars */

function buildStars(): void {
  const host = document.querySelector<HTMLElement>('.stars');
  if (!host || host.childElementCount > 0) return;

  const count = window.innerWidth < 760 ? 60 : 170;
  const frag = document.createDocumentFragment();
  for (let i = 0; i < count; i += 1) {
    const pixel = document.createElement('i');
    const size = 2 + Math.floor(Math.random() * 4);
    pixel.style.width = `${size}px`;
    pixel.style.height = `${size}px`;
    pixel.style.left = `${(Math.random() * 100).toFixed(2)}%`;
    pixel.style.top = `${(Math.random() * 100).toFixed(2)}%`;
    pixel.style.animationDelay = `${(Math.random() * 7).toFixed(2)}s`;
    frag.appendChild(pixel);
  }
  host.appendChild(frag);
}

/* ------------------------------------------------------------------- meter */

function buildMeter(): void {
  const meter = document.querySelector<HTMLElement>('.meter');
  if (!meter || meter.childElementCount > 0) return;

  for (let i = 0; i < 46; i += 1) {
    const bar = document.createElement('i');
    const height = 8 + Math.abs(Math.sin(i / 3.1)) * 46;
    bar.style.setProperty('--h', `${height.toFixed(1)}px`);
    bar.style.animationDelay = `${(i * 0.045).toFixed(2)}s`;
    meter.appendChild(bar);
  }
}

/* ----------------------------------------------------------- theme picker */

function initThemePicker(): void {
  const root = document.documentElement;
  const buttons = Array.from(document.querySelectorAll<HTMLButtonElement>('.theme-btn'));
  if (buttons.length === 0) return;

  const live = document.getElementById('theme-live');
  const now = document.getElementById('theme-now');

  const sync = (name: string): void => {
    buttons.forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.themeName === name));
    });
    if (now) now.textContent = name;
  };

  const apply = (name: string): void => {
    root.dataset.theme = name;
    try {
      localStorage.setItem(THEME_KEY, name);
    } catch {
      /* private mode: the palette still applies for this visit */
    }
    sync(name);
    if (live) {
      // The announcement text lives in the copy module and reaches the script as
      // a template, so the page can be read in a language this file never knew.
      const template = live.dataset.template ?? 'Theme %s applied.';
      live.textContent = template.replace('%s', name);
    }
  };

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      const name = button.dataset.themeName;
      if (name) apply(name);
    });
  });

  // The boot script may have restored a saved palette before first paint.
  sync(root.dataset.theme ?? '');
}

/* ------------------------------------------------------------ copy buttons */

function initCopyButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('.copy').forEach((button) => {
    // Labels come from the button itself: the copy module owns the language.
    const idle = button.dataset.labelCopy ?? 'COPY';

    button.addEventListener('click', async () => {
      const text = button.dataset.copy ?? '';
      let copied = false;
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch {
        copied = false;
      }
      button.textContent = copied
        ? (button.dataset.labelCopied ?? 'COPIED')
        : (button.dataset.labelFailed ?? 'COPY FAILED');
      button.dataset.copied = String(copied);
      window.setTimeout(() => {
        button.textContent = idle;
        delete button.dataset.copied;
      }, 1800);
    });
  });
}

buildStars();
buildMeter();
initThemePicker();
initCopyButtons();
