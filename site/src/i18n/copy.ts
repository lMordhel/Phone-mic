/**
 * Page copy. English is the default and the reference shape: `Copy` is derived
 * from it, so a missing or extra key in another language fails to compile
 * instead of shipping half a translation.
 *
 * Terminal content is deliberately NOT translated: the panel, the commands and
 * their output are what the tool actually prints, and the tool speaks English.
 */

export const LANGS = ['en', 'es'] as const;
export type Lang = (typeof LANGS)[number];

/** A sentence fragment; `code: true` renders it inside <code>. */
export interface Seg {
  t: string;
  code?: boolean;
}

const en = {
  meta: {
    title: 'phone-mic — use your Android phone as a Linux microphone',
    description:
      'phone-mic turns an Android phone into a real microphone on Linux: scrcpy over adb into a PipeWire virtual device named Phone-Mic, controlled from a terminal panel.',
    ogLocale: 'en_US',
  },
  topbar: {
    nav: [
      { href: '#why', label: 'why' },
      { href: '#panel', label: 'panel' },
      { href: '#keys', label: 'keys' },
      { href: '#themes', label: 'themes' },
      { href: '#security', label: 'security' },
    ],
    install: 'Install',
  },
  alt: { href: '/es/', label: 'Español', lang: 'es' as Lang, title: 'Ver esta página en español' },
  a11y: { skip: 'Skip to content', navLabel: 'Page sections' },
  hero: {
    eyebrow: 'phone-mic · android phone as a linux microphone',
    taglineBefore: 'Your phone is the ',
    taglineStrong: 'microphone',
    taglineAfter: ' now.',
    lede: [
      { t: 'scrcpy', code: true },
      { t: ' captures the phone mic over adb, PipeWire republishes it as ' },
      { t: 'Phone-Mic', code: true },
      { t: ' and every application you already own converts it into an ordinary input device. Nothing to install on the phone, no driver, no proprietary cable.' },
    ] as Seg[],
    ctaPrimary: 'Install in one command',
    ctaSecondary: 'See the panel',
  },
  why: {
    heading: 'Why it feels native',
    note: '4 rules it keeps',
    sub: 'One process, one PipeWire node, one command. The phone stays a phone.',
    cards: [
      {
        title: 'Nothing on the phone',
        body: 'Wireless debugging plus scrcpy 3.2 or newer. No APK is built, published or required.',
      },
      {
        title: 'One device, every app',
        body: 'Discord, OBS, browsers and recorders pick Phone-Mic from their own device list.',
      },
      {
        title: 'Terminal only',
        body: 'No tray icon, no window, no updater in the background. The command is the interface.',
      },
      {
        title: 'Survives the window',
        body: 'A systemd user service owns the bridge, so closing the terminal never cuts the audio.',
      },
    ],
  },
  panel: {
    heading: 'The panel',
    note: 'one snapshot, real controls',
    sub: [
      { t: 'Every reading is a real PipeWire control. GAIN is what applications receive, VOLUME is what arrives from the phone, and the meter opens its own 8 kHz capture client.' },
      { t: ' A reading that could not be taken is shown as unknown — an em dash — never as a plausible zero.' },
    ] as Seg[],
    caption:
      'The phone-mic terminal panel. PHONE LINK shows a connected Redmi Note 13 over Wi-Fi at 192.168.100.57, the bridging service state, a 50 millisecond buffer and routing OK. A value that cannot be read is printed as an em dash instead of a number, and an unavailable link is named — NO ADB, UNAUTHORIZED or OFFLINE — with its cause and the command that fixes it. INPUT MONITOR draws a waveform; the input level reads -10.5 dB peak and -20.7 dB RMS, and when nothing can be measured it says NO CAPTURE TOOL or NO SIGNAL. VIRTUAL MICROPHONE lists Phone-Mic, a PipeWire remap source, as active with gain and volume at 100 percent; when the audio server does not answer it says AUDIO SERVER DOWN with its cause and the fixing command. The footer has two lines and lists every key: C connect, X stop, M mute, A reroute, D devices, T theme, R reconnect, Q quit, Tab to switch between gain and volume, and the arrow keys to adjust by 5 percent.',
    footLeft: 'below 62×20 columns it prints “terminal too small” instead of a broken frame',
    footRight: 'meter cost ≈ 16 kB/s',
  },
  keys: {
    heading: 'Keys, not menus',
    note: 'one keystroke per action',
    sub: 'The dashboard is a TUI on purpose: no pointer, no navigation stack, no dialog that hides the reading you were watching.',
    items: [
      { kbd: ['C'], action: 'Connect', note: 'start the bridge service' },
      { kbd: ['X'], action: 'Stop', note: 'stop the bridge service' },
      { kbd: ['M'], action: 'Mute', note: 'virtual microphone on or off' },
      { kbd: ['A'], action: 'Reroute', note: 'move the stream back to the sink' },
      { kbd: ['D'], action: 'Devices', note: 'list PipeWire input devices' },
      { kbd: ['R'], action: 'Reconnect', note: 'reconnect adb' },
      { kbd: ['Tab'], action: 'Gain / Volume', note: 'switch the focused control' },
      { kbd: ['←', '→'], action: '±5 %', note: 'adjust the focused control' },
      { kbd: ['T'], action: 'Theme', note: 'picker with the twelve palettes' },
      { kbd: ['Q'], action: 'Quit', note: 'the bridge keeps running' },
    ],
  },
  themes: {
    heading: 'Twelve palettes',
    note: 'a theme is a look, not an accent',
    sub: [
      { t: 'Background, border, labels, state colours and the three level colours move together, saved to ' },
      { t: '~/.config/phone-mic/tui.conf', code: true },
      { t: '. Colours use the portable 256-colour palette by default; redefining the terminal’s own palette is opt-in with ' },
      { t: 'PHONE_MIC_EXACT=1', code: true },
      { t: ', because some terminals advertise that capability and ignore it. In the picker, moving the selection previews the theme, Enter applies and saves it, and ' },
      { t: 'esc', code: true },
      { t: ' or ' },
      { t: 't', code: true },
      { t: ' restores the saved one. This page is painted with the same values the panel uses.' },
    ] as Seg[],
    ariaLabel: (family: string) => `${family.toLowerCase()} palettes`,
    appliedTemplate: 'Theme %s applied.',
  },
  security: {
    heading: 'Not security tested',
    note: 'read before you install',
    sub: 'phone-mic is a small utility, not a hardened product. What follows is stated plainly so nobody discovers it later.',
    noticeStrong: 'No security testing has been performed on phone-mic.',
    noticeRest:
      'There has been no security audit, no threat model, no penetration test, no fuzzing and no adversarial review of this codebase. The functional checks documented in the manual say nothing about whether it resists a malicious network, a malicious application on the same machine, or hostile input.',
    cards: [
      {
        title: 'The microphone stays open while it runs',
        body: 'While phone-mic-bridge is running, the phone captures audio continuously and publishes it as an input device every application can select. Stop the service when you do not need it.',
      },
      {
        title: 'Wireless debugging is real access',
        body: 'Pairing gives this PC adb access to the phone: shell commands, file access, app installation. The pairing code is a credential. Remove the pairing on the phone when you are done, and keep wireless debugging off between sessions.',
      },
      {
        title: 'No privilege boundary is added',
        body: 'The installer runs as your user and writes to ~/.config, ~/.local and a systemd user unit. It needs no root, and it also creates no sandbox: the bridge and the PipeWire node run with your permissions.',
      },
      {
        title: 'The tests that exist are functional',
        body: 'The status table in the manual records manual checks on one machine (CachyOS, PipeWire 1.6, Hyprland): device present, bridge capturing, panel working, service reconnecting. It is not coverage of other distributions, other versions or hostile input.',
      },
    ],
    closingBefore: 'If that is not acceptable for your use, do not install it. The manual has a ',
    closingLink: 'complete uninstall',
    closingAfter:
      ' that removes the command, the prefix, the unit and the PipeWire fragment, and leaves the remembered adb state alone.',
    closingHref: 'https://github.com/lMordhel/Phone-mic#uninstall',
  },
  install: {
    heading: 'Install',
    note: 'no root, no PipeWire restart',
    sub: [
      { t: 'The installer is a self-contained per-user install: it copies the panel, the scripts, the configuration and the documentation into ' },
      { t: '${XDG_DATA_HOME:-~/.local/share}/phone-mic', code: true },
      { t: ', then generates the ' },
      { t: 'phone-mic', code: true },
      { t: ' command and the ' },
      { t: 'phone-mic-bridge', code: true },
      { t: ' unit from that prefix, so moving or deleting the checkout afterwards breaks nothing. The PipeWire fragment is installed where PipeWire reads it. It never restarts PipeWire, because that drops Bluetooth links and screencasts, and it does not enable the service at login. A preflight names ' },
      { t: 'adb', code: true },
      { t: ', ' },
      { t: 'scrcpy', code: true },
      { t: ' 3.2 or newer (the release that added ' },
      { t: '--audio-source=mic', code: true },
      { t: ') and ' },
      { t: 'pactl', code: true },
      { t: ' answering from ' },
      { t: 'pipewire-pulse', code: true },
      { t: ', with the command that fixes each one; a missing tool never aborts an otherwise valid install. Options: ' },
      { t: '--prefix DIR', code: true },
      { t: ', ' },
      { t: '--version', code: true },
      { t: ', ' },
      { t: '--help', code: true },
      { t: ' and ' },
      { t: '--uninstall', code: true },
      { t: '.' },
    ] as Seg[],
    blockTitles: ['1 · dependencies (Arch and derivatives)', '2 · the installer'],
    checkTitle: '3 · check it, then talk',
    footLeft: 'then pick Phone-Mic in Discord, OBS or the browser microphone picker',
    footRight: 'the service reconnects by itself',
    copyLabel: 'COPY',
    copyCopied: 'COPIED',
    copyFailed: 'COPY FAILED',
    copyAria: (command: string) => `Copy: ${command}`,
  },
  status: {
    active: 'Phone-Mic active',
    hints: ['[C] Connect', '[X] Stop', '[M] Mute', '[T] Theme', '[Q] Quit'],
    manual: 'manual',
    github: 'github',
    license: 'MIT licence',
    themeLabel: 'theme',
    audited: 'not security tested',
  },
};

export type Copy = typeof en;

const es: Copy = {
  meta: {
    title: 'phone-mic — usa tu teléfono Android como micrófono en Linux',
    description:
      'phone-mic convierte un teléfono Android en un micrófono real en Linux: scrcpy por adb hacia un dispositivo virtual de PipeWire llamado Phone-Mic, controlado desde un panel de terminal.',
    ogLocale: 'es_ES',
  },
  topbar: {
    nav: [
      { href: '#why', label: 'por qué' },
      { href: '#panel', label: 'panel' },
      { href: '#keys', label: 'teclas' },
      { href: '#themes', label: 'temas' },
      { href: '#security', label: 'seguridad' },
    ],
    install: 'Instalar',
  },
  alt: { href: '/', label: 'English', lang: 'en' as Lang, title: 'View this page in English' },
  a11y: { skip: 'Saltar al contenido', navLabel: 'Secciones de la página' },
  hero: {
    eyebrow: 'phone-mic · un Android como micrófono en Linux',
    taglineBefore: 'Tu teléfono ya es el ',
    taglineStrong: 'micrófono',
    taglineAfter: '.',
    lede: [
      { t: 'scrcpy', code: true },
      { t: ' captura el micrófono del teléfono por adb, PipeWire lo republica como ' },
      { t: 'Phone-Mic', code: true },
      { t: ' y cada aplicación que ya usas lo ve como un dispositivo de entrada normal. Nada que instalar en el teléfono, sin controladores, sin cables propietarios.' },
    ] as Seg[],
    ctaPrimary: 'Instalar con un comando',
    ctaSecondary: 'Ver el panel',
  },
  why: {
    heading: 'Por qué se siente nativo',
    note: '4 reglas que respeta',
    sub: 'Un proceso, un nodo de PipeWire, un comando. El teléfono sigue siendo un teléfono.',
    cards: [
      {
        title: 'Nada en el teléfono',
        body: 'Depuración inalámbrica y scrcpy 3.2 o superior. No se compila, publica ni requiere ningún APK.',
      },
      {
        title: 'Un dispositivo, todas las apps',
        body: 'Discord, OBS, el navegador y cualquier grabador eligen Phone-Mic en su propia lista de dispositivos.',
      },
      {
        title: 'Solo terminal',
        body: 'Sin icono en la bandeja, sin ventana, sin actualizador en segundo plano. El comando es la interfaz.',
      },
      {
        title: 'Sobrevive a la ventana',
        body: 'El puente es un servicio de usuario de systemd, así que cerrar la terminal nunca corta el audio.',
      },
    ],
  },
  panel: {
    heading: 'El panel',
    note: 'una instantánea, controles reales',
    sub: [
      { t: 'Cada lectura es un control real de PipeWire. GAIN es lo que reciben las aplicaciones, VOLUME es lo que llega desde el teléfono, y el medidor abre su propio cliente de captura a 8 kHz.' },
      { t: ' Una lectura que no se pudo tomar se muestra como desconocida —un guion largo—, nunca como un cero que parece real.' },
    ] as Seg[],
    caption:
      'El panel de terminal de phone-mic. PHONE LINK muestra un Redmi Note 13 conectado por Wi-Fi en 192.168.100.57, el estado del servicio del puente, un búfer de 50 milisegundos y el enrutado correcto. Un valor que no se puede leer se imprime como un guion largo en lugar de un número, y un enlace no disponible se nombra —NO ADB, UNAUTHORIZED u OFFLINE— con su causa y el comando que lo corrige. INPUT MONITOR dibuja una forma de onda; el nivel de entrada marca -10,5 dB de pico y -20,7 dB RMS, y cuando no se puede medir nada dice NO CAPTURE TOOL o NO SIGNAL. VIRTUAL MICROPHONE lista Phone-Mic, una fuente remapeada de PipeWire, como activa con ganancia y volumen al 100 por ciento; cuando el servidor de audio no responde dice AUDIO SERVER DOWN con su causa y el comando de arreglo. El pie tiene dos líneas y lista todas las teclas: C conectar, X detener, M silenciar, A redirigir, D dispositivos, T tema, R reconectar, Q salir, Tab para alternar entre ganancia y volumen, y las flechas para ajustar un 5 por ciento.',
    footLeft: 'por debajo de 62×20 columnas imprime «terminal too small» en lugar de un marco roto',
    footRight: 'el medidor cuesta ≈ 16 kB/s',
  },
  keys: {
    heading: 'Teclas, no menús',
    note: 'una pulsación por acción',
    sub: 'El panel es una TUI a propósito: sin puntero, sin pila de navegación y sin diálogos que tapen la lectura que estabas mirando.',
    items: [
      { kbd: ['C'], action: 'Conectar', note: 'arranca el servicio del puente' },
      { kbd: ['X'], action: 'Detener', note: 'para el servicio del puente' },
      { kbd: ['M'], action: 'Silenciar', note: 'micrófono virtual activo o mudo' },
      { kbd: ['A'], action: 'Redirigir', note: 'devuelve el flujo al sumidero' },
      { kbd: ['D'], action: 'Dispositivos', note: 'lista las entradas de PipeWire' },
      { kbd: ['R'], action: 'Reconectar', note: 'vuelve a conectar adb' },
      { kbd: ['Tab'], action: 'Ganancia / Volumen', note: 'cambia el control enfocado' },
      { kbd: ['←', '→'], action: '±5 %', note: 'ajusta el control enfocado' },
      { kbd: ['T'], action: 'Tema', note: 'selector con las doce paletas' },
      { kbd: ['Q'], action: 'Salir', note: 'el puente sigue funcionando' },
    ],
  },
  themes: {
    heading: 'Doce paletas',
    note: 'un tema es un conjunto, no un acento',
    sub: [
      { t: 'Fondo, borde, etiquetas, colores de estado y los tres colores del medidor se mueven juntos, y se guardan en ' },
      { t: '~/.config/phone-mic/tui.conf', code: true },
      { t: '. Los colores usan la paleta portátil de 256 colores por defecto; redefinir la paleta propia del terminal es opcional con ' },
      { t: 'PHONE_MIC_EXACT=1', code: true },
      { t: ', porque algunos terminales anuncian esa capacidad y la ignoran. En el selector, mover la selección previsualiza el tema, Intro lo aplica y lo guarda, y ' },
      { t: 'esc', code: true },
      { t: ' o ' },
      { t: 't', code: true },
      { t: ' restauran el guardado. Esta página usa los mismos valores que el panel.' },
    ] as Seg[],
    ariaLabel: (family: string) => `paletas ${family.toLowerCase()}`,
    appliedTemplate: 'Tema %s aplicado.',
  },
  security: {
    heading: 'Sin pruebas de seguridad',
    note: 'leer antes de instalar',
    sub: 'phone-mic es una utilidad pequeña, no un producto endurecido. Lo que sigue se dice sin rodeos para que nadie lo descubra después.',
    noticeStrong: 'No se hicieron pruebas de seguridad sobre phone-mic.',
    noticeRest:
      'No hubo auditoría de seguridad, ni modelo de amenazas, ni prueba de penetración, ni fuzzing, ni revisión adversarial de este código. Las comprobaciones funcionales del manual no dicen nada sobre si resiste una red maliciosa, una aplicación maliciosa en la misma máquina o una entrada hostil.',
    cards: [
      {
        title: 'El micrófono queda abierto mientras funciona',
        body: 'Mientras phone-mic-bridge está corriendo, el teléfono captura audio de forma continua y lo publica como un dispositivo de entrada que cualquier aplicación puede elegir. Para el servicio cuando no lo necesites.',
      },
      {
        title: 'La depuración inalámbrica es acceso real',
        body: 'El emparejamiento da a este PC acceso adb al teléfono: comandos de shell, acceso a ficheros, instalación de aplicaciones. El código de emparejamiento es una credencial. Borra el emparejamiento en el teléfono cuando termines y deja la depuración inalámbrica apagada entre sesiones.',
      },
      {
        title: 'No se añade ninguna frontera de privilegios',
        body: 'El instalador corre con tu usuario y escribe en ~/.config, ~/.local y una unidad de usuario de systemd. No necesita root, y tampoco crea un aislamiento: el puente y el nodo de PipeWire corren con tus permisos.',
      },
      {
        title: 'Las pruebas que existen son funcionales',
        body: 'La tabla de estado del manual recoge comprobaciones a mano en una sola máquina (CachyOS, PipeWire 1.6, Hyprland): dispositivo presente, puente capturando, panel funcionando, servicio reconectando. No cubre otras distribuciones, otras versiones ni entrada hostil.',
      },
    ],
    closingBefore:
      'Si eso no es aceptable para tu caso, no lo instales. El manual tiene una ',
    closingLink: 'desinstalación completa',
    closingAfter:
      ' que quita el comando, el prefijo, la unidad y el fragmento de PipeWire, y deja intacto el estado de adb recordado.',
    closingHref: 'https://github.com/lMordhel/Phone-mic#uninstall',
  },
  install: {
    heading: 'Instalar',
    note: 'sin root, sin reiniciar PipeWire',
    sub: [
      { t: 'El instalador es una instalación por usuario autocontenida: copia el panel, los scripts, la configuración y la documentación en ' },
      { t: '${XDG_DATA_HOME:-~/.local/share}/phone-mic', code: true },
      { t: ', y genera el comando ' },
      { t: 'phone-mic', code: true },
      { t: ' y la unidad ' },
      { t: 'phone-mic-bridge', code: true },
      { t: ' desde ese prefijo, así que mover o borrar el checkout después no rompe nada. El fragmento de PipeWire se instala donde PipeWire lo lee. Nunca reinicia PipeWire, porque eso corta enlaces Bluetooth y capturas de pantalla, y no activa el servicio al iniciar sesión. Una comprobación previa nombra ' },
      { t: 'adb', code: true },
      { t: ', ' },
      { t: 'scrcpy', code: true },
      { t: ' 3.2 o superior (la versión que añadió ' },
      { t: '--audio-source=mic', code: true },
      { t: ') y ' },
      { t: 'pactl', code: true },
      { t: ' respondiendo desde ' },
      { t: 'pipewire-pulse', code: true },
      { t: ', con el comando que corrige cada uno; una herramienta ausente nunca aborta una instalación por lo demás válida. Opciones: ' },
      { t: '--prefix DIR', code: true },
      { t: ', ' },
      { t: '--version', code: true },
      { t: ', ' },
      { t: '--help', code: true },
      { t: ' y ' },
      { t: '--uninstall', code: true },
      { t: '.' },
    ] as Seg[],
    blockTitles: ['1 · dependencias (Arch y derivadas)', '2 · el instalador'],
    checkTitle: '3 · compruébalo y habla',
    footLeft: 'luego elige Phone-Mic en Discord, OBS o el selector de micrófono del navegador',
    footRight: 'el servicio se reconecta solo',
    copyLabel: 'COPIAR',
    copyCopied: 'COPIADO',
    copyFailed: 'NO SE PUDO COPIAR',
    copyAria: (command: string) => `Copiar: ${command}`,
  },
  status: {
    active: 'Phone-Mic activo',
    hints: ['[C] Conectar', '[X] Detener', '[M] Silenciar', '[T] Tema', '[Q] Salir'],
    manual: 'manual',
    github: 'github',
    license: 'licencia MIT',
    themeLabel: 'tema',
    audited: 'sin pruebas de seguridad',
  },
};

export const copy: Record<Lang, Copy> = { en, es };
