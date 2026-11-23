#!/usr/bin/env python3
"""PHONEMIC - terminal dashboard for the phone microphone bridge.

Boxed dashboard: connection state, audio monitor with waveform and level, and the
virtual microphone controls (gain, volume, mute). It owns no audio pipeline: the
bridge is a systemd user unit and every control maps to pactl or systemctl.

Usage:
    phone-mic            interactive dashboard
    phone-mic status     print one snapshot and exit (scriptable)
"""

from __future__ import annotations

import argparse
import array
import collections
import curses
import math
import os
import shutil
import subprocess
import sys
import threading
import time

# realpath, not abspath: the command is installed as a wrapper in ~/.local/bin
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SINK = "phonemic_sink"
SOURCE = "phone_mic"
BRIDGE_UNIT = "phone-mic-bridge"

SAMPLE_RATE = 8000      # metering rate: enough for level, cheap in CPU
BAR_WINDOW_MS = 70      # one waveform slot
WAVE_SLOTS = 28         # ~2 s of history
FLOOR_DB = -60.0
WAVE_CHARS = " ▁▂▃▄▅▆▇"

FRAME_MIN_W = 62
FRAME_W = 78
FRAME_H = 27

TL, TR, BL, BR = "╭", "╮", "╰", "╯"
BOX_TL, BOX_TR, BOX_BL, BOX_BR = "┌", "┐", "└", "┘"
H, V = "─", "│"
TEE_L, TEE_R = "├", "┤"


# -------------------------------------------------------------------------- themes

ROLES = ("bg", "border", "accent", "label", "text", "dim",
         "ok", "bad", "warn", "level_low", "level_mid", "level_hot")

# Each theme is a full palette of RGB values per role, so a theme is a look, not a
# single accent colour. Families are only used for ordering in the picker.
THEME_FAMILIES: list[tuple[str, list[str]]] = [
    ("PASTEL", ["pastel-mint", "pastel-lavender", "pastel-peach"]),
    ("DARK", ["dark-mono", "dark-ocean", "dark-forest"]),
    ("LIGHT", ["light-paper", "light-sky", "light-sand"]),
    ("WARM", ["warm-amber", "warm-ember", "warm-clay"]),
]

THEMES: dict[str, dict[str, tuple[int, int, int]]] = {
    "pastel-mint": {
        "bg": (235, 245, 240), "border": (150, 200, 180), "accent": (60, 150, 130),
        "label": (90, 170, 150), "text": (40, 80, 70), "dim": (145, 175, 165),
        "ok": (70, 170, 120), "bad": (225, 125, 135), "warn": (215, 175, 95),
        "level_low": (110, 200, 160), "level_mid": (240, 200, 110),
        "level_hot": (235, 140, 150),
    },
    "pastel-lavender": {
        "bg": (242, 238, 250), "border": (200, 190, 225), "accent": (120, 100, 190),
        "label": (140, 120, 200), "text": (60, 50, 90), "dim": (172, 165, 198),
        "ok": (110, 175, 150), "bad": (215, 115, 140), "warn": (220, 180, 110),
        "level_low": (150, 130, 230), "level_mid": (230, 190, 120),
        "level_hot": (230, 120, 150),
    },
    "pastel-peach": {
        "bg": (253, 242, 235), "border": (240, 205, 185), "accent": (200, 110, 80),
        "label": (215, 140, 110), "text": (90, 60, 50), "dim": (200, 170, 155),
        "ok": (130, 180, 130), "bad": (215, 105, 100), "warn": (225, 170, 90),
        "level_low": (240, 160, 120), "level_mid": (235, 180, 100),
        "level_hot": (220, 110, 100),
    },
    "dark-mono": {
        "bg": (18, 18, 18), "border": (70, 70, 70), "accent": (205, 205, 205),
        "label": (155, 155, 155), "text": (225, 225, 225), "dim": (110, 110, 110),
        "ok": (150, 205, 150), "bad": (220, 120, 120), "warn": (210, 190, 120),
        "level_low": (165, 165, 165), "level_mid": (205, 205, 205),
        "level_hot": (245, 245, 245),
    },
    "dark-ocean": {
        "bg": (10, 20, 30), "border": (30, 60, 80), "accent": (80, 200, 220),
        "label": (90, 170, 200), "text": (200, 230, 240), "dim": (90, 120, 140),
        "ok": (80, 200, 170), "bad": (230, 110, 120), "warn": (230, 190, 90),
        "level_low": (70, 180, 200), "level_mid": (120, 210, 230),
        "level_hot": (240, 140, 150),
    },
    "dark-forest": {
        "bg": (12, 22, 16), "border": (40, 70, 50), "accent": (140, 220, 150),
        "label": (110, 180, 130), "text": (210, 235, 215), "dim": (90, 120, 100),
        "ok": (130, 220, 140), "bad": (225, 120, 110), "warn": (220, 190, 100),
        "level_low": (110, 200, 130), "level_mid": (170, 225, 140),
        "level_hot": (235, 150, 120),
    },
    "light-paper": {
        "bg": (250, 250, 248), "border": (205, 205, 200), "accent": (60, 60, 60),
        "label": (100, 100, 100), "text": (30, 30, 30), "dim": (150, 150, 148),
        "ok": (60, 150, 90), "bad": (200, 70, 70), "warn": (190, 140, 40),
        "level_low": (80, 160, 110), "level_mid": (200, 160, 60),
        "level_hot": (200, 80, 80),
    },
    "light-sky": {
        "bg": (240, 247, 252), "border": (190, 210, 225), "accent": (50, 110, 160),
        "label": (80, 130, 175), "text": (30, 50, 70), "dim": (150, 170, 185),
        "ok": (60, 150, 120), "bad": (200, 80, 90), "warn": (200, 150, 60),
        "level_low": (90, 170, 200), "level_mid": (200, 170, 80),
        "level_hot": (205, 90, 95),
    },
    "light-sand": {
        "bg": (250, 247, 240), "border": (215, 205, 185), "accent": (140, 110, 60),
        "label": (160, 130, 80), "text": (60, 50, 35), "dim": (170, 160, 140),
        "ok": (110, 150, 90), "bad": (190, 90, 70), "warn": (190, 150, 60),
        "level_low": (170, 150, 90), "level_mid": (200, 165, 80),
        "level_hot": (195, 105, 80),
    },
    "warm-amber": {
        "bg": (30, 20, 10), "border": (90, 60, 25), "accent": (245, 180, 70),
        "label": (210, 160, 80), "text": (250, 235, 210), "dim": (140, 110, 80),
        "ok": (200, 190, 110), "bad": (230, 110, 80), "warn": (245, 190, 80),
        "level_low": (220, 170, 70), "level_mid": (245, 195, 90),
        "level_hot": (240, 110, 70),
    },
    "warm-ember": {
        "bg": (26, 14, 12), "border": (80, 40, 35), "accent": (240, 120, 80),
        "label": (215, 140, 110), "text": (245, 225, 215), "dim": (140, 95, 85),
        "ok": (200, 180, 120), "bad": (235, 95, 70), "warn": (240, 160, 70),
        "level_low": (235, 140, 90), "level_mid": (245, 170, 90),
        "level_hot": (240, 90, 60),
    },
    "warm-clay": {
        "bg": (245, 235, 225), "border": (210, 185, 165), "accent": (170, 100, 70),
        "label": (150, 105, 85), "text": (70, 50, 40), "dim": (175, 155, 140),
        "ok": (130, 150, 105), "bad": (195, 85, 70), "warn": (200, 150, 80),
        "level_low": (185, 130, 95), "level_mid": (210, 160, 90),
        "level_hot": (195, 95, 75),
    },
}

ALL_THEMES: list[str] = [name for _, names in THEME_FAMILIES for name in names]
DEFAULT_THEME = "dark-ocean"
CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "phone-mic", "tui.conf")


def load_theme() -> str:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as handle:
            for line in handle:
                if line.strip().startswith("theme="):
                    name = line.split("=", 1)[1].strip()
                    if name in THEMES:
                        return name
    except OSError:
        pass
    return DEFAULT_THEME


def save_theme(name: str) -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            handle.write(f"theme={name}\n")
    except OSError:
        pass


def approx_256(r: int, g: int, b: int) -> int:
    """Nearest xterm-256 cube colour, for terminals without colour redefinition."""
    def level(value: int) -> int:
        return 0 if value < 48 else 1 if value < 115 else 2 if value < 155 \
            else 3 if value < 195 else 4 if value < 235 else 5
    return 16 + 36 * level(r) + 6 * level(g) + level(b)


class Palette:
    """Maps roles to curses attributes for the active theme."""

    def __init__(self) -> None:
        self.name = DEFAULT_THEME
        self.attrs: dict[str, int] = {}
        self.exact = False
        self.enabled = False

    def apply(self, name: str) -> None:
        theme = THEMES.get(name, THEMES[DEFAULT_THEME])
        self.name = name if name in THEMES else DEFAULT_THEME
        self.attrs = {}
        if not curses.has_colors():
            return
        self.enabled = True
        curses.start_color()
        curses.use_default_colors()
        self.exact = bool(curses.can_change_color() and curses.COLORS >= 256)

        indices: dict[str, int] = {}
        for i, role in enumerate(ROLES):
            r, g, b = theme[role]
            if self.exact:
                index = 16 + i
                curses.init_color(index, r * 1000 // 255, g * 1000 // 255,
                                  b * 1000 // 255)
            else:
                index = approx_256(r, g, b)
            indices[role] = index

        bg = indices["bg"]
        for i, role in enumerate(ROLES):
            pair = 40 + i
            curses.init_pair(pair, indices[role], bg)
            self.attrs[role] = curses.color_pair(pair)

    def a(self, role: str) -> int:
        return self.attrs.get(role, 0)


PALETTE = Palette()


# --------------------------------------------------------------------------- state

def run(cmd: list[str], timeout: float = 3.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


class Cache:
    """Tiny TTL cache: pactl and adb are too slow to call on every frame."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, object]] = {}

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)

    def get(self, key: str, ttl: float, producer):
        now = time.monotonic()
        hit = self._data.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        value = producer()
        self._data[key] = (now, value)
        return value


CACHE = Cache()


def adb_devices() -> list[str]:
    lines = run(["adb", "devices"]).splitlines()[1:]
    return [line.split()[0] for line in lines if line.strip().endswith("device")]


def adb_model() -> str:
    def read() -> str:
        for prop in ("ro.product.marketname", "ro.product.odm.marketname",
                     "ro.product.model"):
            value = run(["adb", "shell", "getprop", prop]).strip()
            if value:
                return value
        return "-"
    return CACHE.get("model", 30.0, read)


def bridge_pids() -> list[int]:
    out = run(["pgrep", "-x", "scrcpy"])
    return [int(p) for p in out.split() if p.isdigit()]


def bridge_unit_state() -> str:
    return run(["systemctl", "--user", "is-active", BRIDGE_UNIT]).strip() or "unknown"


def sink_index() -> str:
    for line in run(["pactl", "list", "short", "sinks"]).splitlines():
        fields = line.split()
        if len(fields) > 1 and fields[1] == SINK:
            return fields[0]
    return ""


def source_present() -> bool:
    for line in run(["pactl", "list", "short", "sources"]).splitlines():
        fields = line.split()
        if len(fields) > 1 and fields[1] == SOURCE:
            return True
    return False


def bridge_stream() -> tuple[str, str]:
    """(sink-input index, sink index) of the scrcpy playback stream."""
    out = run(["pactl", "list", "sink-inputs"])
    idx = ""
    current = ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("Sink Input #"):
            idx = stripped.split("#", 1)[1]
        elif stripped.startswith("Sink:") and idx:
            current = stripped.split(":", 1)[1].strip()
        elif 'application.name = "scrcpy"' in stripped:
            return idx, current
    return "", ""


def percent(text: str) -> int:
    """Extract the aggregate percentage from `pactl get-*-volume` output."""
    for line in text.splitlines():
        if "%" in line:
            chunk = line.split("/")
            for part in chunk:
                part = part.strip()
                if part.endswith("%"):
                    digits = "".join(c for c in part if c.isdigit())
                    if digits:
                        return int(digits)
    return 0


def source_volume() -> int:
    return CACHE.get("vol", 1.0, lambda: percent(
        run(["pactl", "get-source-volume", SOURCE])))


def source_muted() -> bool:
    return CACHE.get("mute", 1.0, lambda: "yes" in run(
        ["pactl", "get-source-mute", SOURCE]).lower())


def stream_volume() -> int:
    # `pactl get-sink-input-volume` does not exist in every pactl release
    # ("No valid command specified"), so the volume is read from the listing.
    def read() -> int:
        idx, _ = bridge_stream()
        if not idx:
            return 0
        block = run(["pactl", "list", "sink-inputs"])
        current = ""
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("Sink Input #"):
                current = stripped.split("#", 1)[1]
            elif current == idx and stripped.startswith("Volume:"):
                return percent(stripped)
        return 0
    return CACHE.get("svol", 1.0, read)


def set_source_volume(value: int) -> None:
    run(["pactl", "set-source-volume", SOURCE, f"{max(0, min(100, value))}%"])
    CACHE.invalidate("vol")


def set_stream_volume(value: int) -> None:
    idx, _ = bridge_stream()
    if idx:
        run(["pactl", "set-sink-input-volume", idx,
             f"{max(0, min(100, value))}%"])
    CACHE.invalidate("svol")


def toggle_mute() -> tuple[bool, str]:
    muted = source_muted()
    run(["pactl", "set-source-mute", SOURCE, "no" if muted else "yes"])
    CACHE.invalidate("mute")
    return True, "unmuted" if muted else "MUTED"


# ------------------------------------------------------------------------- actions

def start_bridge() -> tuple[bool, str]:
    out = subprocess.run(["systemctl", "--user", "start", BRIDGE_UNIT],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return False, (out.stderr or "systemctl start failed").strip().splitlines()[-1]
    return True, "connecting"


def stop_bridge() -> tuple[bool, str]:
    out = subprocess.run(["systemctl", "--user", "stop", BRIDGE_UNIT],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return False, (out.stderr or "systemctl stop failed").strip().splitlines()[-1]
    return True, "stopped"


def reconnect_phone() -> tuple[bool, str]:
    script = os.path.join(REPO, "scripts", "connect-phone.sh")
    out = subprocess.run([script], capture_output=True, text=True)
    return out.returncode == 0, (out.stdout or out.stderr).strip().splitlines()[-1]


def fix_routing() -> tuple[bool, str]:
    want = sink_index()
    have = bridge_stream()[1]
    if not want:
        return False, f"{SINK} missing"
    if not have:
        return False, "no bridge stream"
    if have == want:
        return True, "already routed"
    subprocess.run(["pactl", "move-sink-input", have, SINK], check=False)
    return True, "re-routed"


# --------------------------------------------------------------------------- meter

class LevelMeter(threading.Thread):
    """Rolling windows of the virtual microphone, for the waveform and the level."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._proc: subprocess.Popen[bytes] | None = None
        self.slots: collections.deque[float] = collections.deque(
            [FLOOR_DB] * WAVE_SLOTS, maxlen=WAVE_SLOTS)
        self.peak_db = FLOOR_DB
        self.rms_db = FLOOR_DB
        self.windows = 0
        self.running = False

    def run(self) -> None:
        if not shutil.which("parec"):
            return
        window_bytes = SAMPLE_RATE * BAR_WINDOW_MS // 1000 * 2
        try:
            self._proc = subprocess.Popen(
                ["parec", "--device=" + SOURCE, "--format=s16le",
                 f"--rate={SAMPLE_RATE}", "--channels=1", "--raw"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        self.running = True
        fd = self._proc.stdout.fileno() if self._proc.stdout else -1
        pending = bytearray()
        while not self._stop.is_set() and fd >= 0:
            # os.read returns what is available; a buffered read(n) blocks until
            # n bytes accumulated, which on this pipe was ~2 s.
            try:
                data = os.read(fd, 65536)
            except OSError:
                break
            if not data:
                break
            pending.extend(data)
            while len(pending) >= window_bytes:
                window = bytes(pending[:window_bytes])
                del pending[:window_bytes]
                samples = array.array("h")
                samples.frombytes(window)
                peak = max(abs(s) for s in samples) / 32768.0
                rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0
                self.peak_db = 20 * math.log10(peak) if peak > 0 else FLOOR_DB
                self.rms_db = 20 * math.log10(rms) if rms > 0 else FLOOR_DB
                self.slots.append(self.peak_db)
                self.windows += 1
        self.running = False

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def snapshot(self) -> list[float]:
        return list(self.slots)


# ------------------------------------------------------------------------- drawing

def db_fraction(db: float) -> float:
    if db <= FLOOR_DB:
        return 0.0
    return max(0.0, min(1.0, (db - FLOOR_DB) / -FLOOR_DB))


def wave_line(slots: list[float], width: int) -> str:
    tail = slots[-width:] if width < len(slots) else slots
    tail = [FLOOR_DB] * (width - len(tail)) + tail
    out = []
    for db in tail:
        index = int(round(db_fraction(db) * (len(WAVE_CHARS) - 1)))
        out.append(WAVE_CHARS[max(0, min(len(WAVE_CHARS) - 1, index))])
    return "".join(out)


def level_bar(db: float, width: int) -> str:
    filled = int(round(db_fraction(db) * width))
    return "█" * filled + "░" * (width - filled)


def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def connection_lines(devices: list[str]) -> list[tuple[str, str, str]]:
    """(label, value, tone) rows for the CONNECTION panel."""
    rows: list[tuple[str, str, str]] = []
    if devices:
        peer = devices[0]
        kind = "Wi-Fi" if ":" in peer else "USB"
        host = peer.split(":")[0]
        rows.append(("state", "CONNECTED", "ok"))
        rows.append(("device", truncate(adb_model(), 20), "plain"))
        rows.append(("transport", kind, "plain"))
        rows.append(("address", host, "plain"))
    else:
        rows.append(("state", "DISCONNECTED", "bad"))
        rows.append(("device", "-", "plain"))
        rows.append(("transport", "-", "plain"))
        rows.append(("address", "-", "plain"))
    buffer_ms = os.environ.get("AUDIO_BUFFER", "50")
    rows.append(("buffer", f"{buffer_ms} ms", "plain"))
    return rows


def draw_box(win, y: int, x: int, h: int, w: int, title: str = "",
             color: int = 0) -> None:
    if h < 2 or w < 2:
        return
    try:
        win.addstr(y, x, BOX_TL + H * (w - 2) + BOX_TR, color)
        for row in range(1, h - 1):
            win.addstr(y + row, x, V, color)
            win.addstr(y + row, x + w - 1, V, color)
        win.addstr(y + h - 1, x, BOX_BL + H * (w - 2) + BOX_BR, color)
        if title:
            win.addstr(y, x + 2, f" {title} ", color | curses.A_BOLD)
    except curses.error:
        pass


def interactive() -> int:
    def draw(stdscr) -> None:
        curses.curs_set(0)
        stdscr.timeout(120)
        PALETTE.apply(PALETTE.name)

        def tone(kind: str) -> int:
            if not PALETTE.enabled:
                return curses.A_BOLD if kind == "accent" else 0
            role = {"ok": "ok", "bad": "bad", "warn": "warn", "accent": "accent",
                    "dim": "dim", "plain": "text", "label": "label",
                    "border": "border"}.get(kind, "text")
            attr = PALETTE.a(role)
            if kind == "accent":
                attr |= curses.A_BOLD
            return attr

        def level_tone(db: float) -> int:
            if not PALETTE.enabled:
                return 0
            if db >= -6:
                return PALETTE.a("level_hot")
            if db >= -18:
                return PALETTE.a("level_mid")
            return PALETTE.a("level_low")

        meter = LevelMeter()
        meter.start()
        started = time.monotonic()
        focus = "gain"
        message = ""
        message_at = 0.0
        show_devices = False
        picker = False
        picker_sel = ALL_THEMES.index(PALETTE.name)

        def say(text: str) -> None:
            nonlocal message, message_at
            message, message_at = text, time.monotonic()

        while True:
            height, width = stdscr.getmaxyx()
            stdscr.erase()

            frame_w = min(FRAME_W, width - 1)
            frame_h = FRAME_H
            if frame_w < FRAME_MIN_W or height - 1 < frame_h:
                frame_h = min(frame_h, height - 1)
            if frame_w < FRAME_MIN_W or frame_h < 20:
                stdscr.addstr(0, 0, "PHONEMIC: terminal too small", curses.A_BOLD)
                stdscr.addstr(1, 0, f"need {FRAME_MIN_W}x20, have {width}x{height}",
                              curses.A_DIM)
                stdscr.refresh()
                if stdscr.getch() in (ord("q"), ord("Q")):
                    meter.stop()
                    return
                continue

            left = max(0, (width - frame_w) // 2)
            top = 0
            inner = frame_w - 2
            margin = 2
            gap = 1
            col_w = (inner - 2 * margin - gap) // 2
            left_x = left + 1 + margin
            right_x = left_x + col_w + gap

            def put(row: int, col: int, text: str, attr: int = 0) -> None:
                """Write text clipped to the frame's inner width."""
                limit = left + frame_w - 1 - col
                if limit <= 0:
                    return
                try:
                    stdscr.addstr(top + row, col, text[:limit], attr)
                except curses.error:
                    pass

            def frame_row(row: int, lc: str, rc: str, fill: str = H) -> None:
                put(row, left, lc + fill * inner + rc, tone("border"))

            # --- frame and header (rows 0..3) ------------------------------
            if PALETTE.enabled:
                bg_attr = PALETTE.a("bg")
                blank = " " * frame_w
                for row in range(frame_h):
                    try:
                        stdscr.addstr(top + row, left, blank, bg_attr)
                    except curses.error:
                        pass
            frame_row(0, TL, TR)
            put(1, left + 3, "◉ PHONE-MIC", tone("accent"))
            put(1, left + frame_w - 19, "PIPEWIRE · ADB", tone("dim"))
            put(2, left + 3, "phone as a microphone", tone("dim"))
            frame_row(3, TEE_L, TEE_R)

            def edge(row: int, col: int) -> None:
                """One border cell: put() would clip it at the frame edge."""
                try:
                    stdscr.addstr(top + row, col, V, tone("border"))
                except curses.error:
                    pass

            for row in range(1, frame_h - 1):
                if row in (3, frame_h - 4):
                    continue
                edge(row, left)
                edge(row, left + frame_w - 1)

            # --- data -----------------------------------------------------
            devices = CACHE.get("devices", 2.0, adb_devices)
            pids = bridge_pids()
            state = bridge_unit_state()
            want = sink_index()
            have = bridge_stream()[1]
            volume = source_volume()
            muted = source_muted()
            stream_gain = stream_volume()
            buffer_ms = os.environ.get("AUDIO_BUFFER", "50")

            # --- two panels (rows 5..14) ----------------------------------
            panel_y = 5
            panel_h = 9
            put(panel_y - 1 + 0, left_x, "PHONE LINK", tone("label"))
            put(panel_y - 1 + 0, right_x, "INPUT MONITOR", tone("label"))
            draw_box(stdscr, top + panel_y, left_x, panel_h, col_w, color=tone("border"))
            draw_box(stdscr, top + panel_y, right_x, panel_h, col_w, color=tone("border"))

            conn = connection_lines(devices)
            for i, (label, value, kind) in enumerate(conn):
                row = panel_y + 1 + i
                if label == "state":
                    put(row, left_x + 2, "● " + value, tone(kind) | curses.A_BOLD)
                else:
                    put(row, left_x + 2, f"{label:<10}", tone("dim"))
                    put(row, left_x + 13, value, tone("plain"))
            routing_dot = "ok" if have == want else "WRONG"
            put(panel_y + panel_h - 2, left_x + 2, f"routing {routing_dot}",
                tone("ok") if routing_dot == "ok" else tone("bad"))

            wave_w = max(8, col_w - 6)
            slots = meter.snapshot()
            peak = meter.peak_db
            put(panel_y + 2, right_x + 2, wave_line(slots, wave_w), level_tone(peak))
            put(panel_y + 4, right_x + 2, "INPUT LEVEL", tone("dim"))
            bar_w = max(6, wave_w - 11)
            put(panel_y + 5, right_x + 2, level_bar(peak, bar_w), level_tone(peak))
            put(panel_y + 5, right_x + 2 + bar_w + 1, f"{peak:5.1f} dB", tone("plain"))
            put(panel_y + 6, right_x + 2, f"RMS {meter.rms_db:5.1f} dB   "
                f"buffer {buffer_ms} ms", tone("dim"))

            # --- virtual microphone (rows 16..21) -------------------------
            mic_y = panel_y + panel_h + 2
            mic_w = inner - 2 * margin
            put(mic_y - 1, left_x, "VIRTUAL MICROPHONE", tone("label"))
            draw_box(stdscr, top + mic_y, left_x, 6, mic_w, color=tone("border"))

            alive = bool(pids) and state == "active"
            if muted:
                status, dot = "MUTED", "warn"
            elif alive:
                status, dot = "ACTIVE", "ok"
            else:
                status, dot = state.upper(), "bad"
            put(mic_y + 1, left_x + 2, "●", tone(dot))
            put(mic_y + 1, left_x + 4, "Phone-Mic", curses.A_BOLD)
            put(mic_y + 1, left_x + 15, "PipeWire remap source", tone("dim"))
            put(mic_y + 1, left_x + mic_w - 3 - len(status), status,
                tone(dot) | curses.A_BOLD)
            put(mic_y + 2, left_x + 2, f"service {state}"
                + (f" · pid {pids[0]}" if pids else "") + f" · routing {routing_dot}",
                tone("ok") if routing_dot == "ok" else tone("bad"))

            def slider(row: int, label: str, value: int, selected: bool) -> None:
                track_w = 16
                filled = int(round(track_w * value / 100))
                track = "━" * filled + "●" + "━" * (track_w - filled)
                put(row, left_x + 2, f"{label:<8}",
                    tone("accent") if selected else tone("dim"))
                put(row, left_x + 11, track, tone("ok") if selected else tone("dim"))
                put(row, left_x + 29, f"{value:3d}%", tone("plain"))

            slider(mic_y + 3, "GAIN", volume, focus == "gain")
            slider(mic_y + 4, "VOLUME", stream_gain, focus == "volume")

            # --- footer (rows 23..26) -------------------------------------
            frame_row(frame_h - 4, TEE_L, TEE_R)
            put(frame_h - 3, left + 3,
                "[C] Connect [X] Stop [M] Mute [A] Reroute [T] Theme [D] Devices [Q] Quit",
                tone("dim"))
            put(frame_h - 2, left + 3,
                f"[Tab] gain/volume  [←→] ±5%   ·   focus {focus}", tone("dim"))
            if message and time.monotonic() - message_at < 6:
                put(frame_h - 2, left + 3 + 42, message, tone("warn"))
            frame_row(frame_h - 1, BL, BR)

            if picker:
                rows_total = len(ALL_THEMES) + len(THEME_FAMILIES) + 4
                pw = min(inner - 6, 40)
                ph = min(rows_total, frame_h - 4)
                py = max(1, top + (frame_h - ph) // 2)
                px = left + (frame_w - pw) // 2
                draw_box(stdscr, py, px, ph, pw, color=tone("accent"))
                put(py, px + 2, " THEME ", tone("accent"))
                row = py + 1
                index = 0
                for family, names in THEME_FAMILIES:
                    if row >= py + ph - 2:
                        break
                    put(row, px + 2, family, tone("label"))
                    row += 1
                    for name in names:
                        if row >= py + ph - 2:
                            break
                        marker = "●" if index == picker_sel else " "
                        attr = (PALETTE.a("accent") | curses.A_BOLD
                                if index == picker_sel else tone("plain"))
                        put(row, px + 4, f"{marker} {name}", attr)
                        row += 1
                        index += 1
                put(py + ph - 2, px + 2, "↵ apply · esc close", tone("dim"))

            if show_devices:
                rows = [line.split()[1] for line in
                        run(["pactl", "list", "short", "sources"]).splitlines()[1:]
                        if len(line.split()) > 1][:8]
                overlay_h = len(rows) + 4
                overlay_w = min(inner - 4, 48)
                oy = max(2, top + (frame_h - overlay_h) // 2)
                ox = left + (frame_w - overlay_w) // 2
                draw_box(stdscr, oy, ox, overlay_h, overlay_w, color=tone("accent"))
                put(oy, ox + 2, " INPUT DEVICES ", tone("accent"))
                for i, name in enumerate(rows):
                    mark = "●" if name == SOURCE else " "
                    put(oy + 1 + i, ox + 2, f"{mark} {truncate(name, overlay_w - 6)}")
                put(oy + overlay_h - 2, ox + 2, "any key closes", tone("dim"))

            stdscr.refresh()

            dump = os.environ.get("PHONE_MIC_SCREENDUMP")
            if dump and meter.windows < 8 and time.monotonic() - started < 6.0:
                dump = ""   # wait for the meter before capturing the screen
            if dump:
                # Test hook: write the exact screen buffer once and exit.
                lines = []
                for row in range(height):
                    try:
                        # instr() counts bytes, so the length is omitted: box characters are
                        # three bytes each in UTF-8 and would truncate the dump.
                        lines.append(stdscr.instr(row, 0).decode("utf-8", "replace"))
                    except curses.error:
                        lines.append("")
                try:
                    with open(dump, "w", encoding="utf-8") as handle:
                        handle.write(f"# curses {curses.COLS}x{curses.LINES} "
                                     f"frame {frame_w}x{frame_h} left {left} "
                                     f"theme {PALETTE.name} exact {PALETTE.exact}\n")
                        handle.write("\n".join(line.rstrip() for line in lines) + "\n")
                except OSError:
                    pass
                meter.stop()
                return

            ch = stdscr.getch()
            if picker:
                if ch in (curses.KEY_UP, ord("k")):
                    picker_sel = (picker_sel - 1) % len(ALL_THEMES)
                elif ch in (curses.KEY_DOWN, ord("j")):
                    picker_sel = (picker_sel + 1) % len(ALL_THEMES)
                elif ch in (10, 13, curses.KEY_ENTER):
                    PALETTE.apply(ALL_THEMES[picker_sel])
                    save_theme(ALL_THEMES[picker_sel])
                    picker = False
                    say(f"tema: {ALL_THEMES[picker_sel]}")
                elif ch in (27, ord("t"), ord("T"), ord("q"), ord("Q")):
                    picker = False
                continue
            if show_devices and ch != -1:
                show_devices = False
                continue
            if ch == -1:
                continue
            if ch in (ord("q"), ord("Q")):
                meter.stop()
                return
            if ch in (ord("c"), ord("C")):
                say(start_bridge()[1])
            elif ch in (ord("x"), ord("X")):
                say(stop_bridge()[1])
            elif ch in (ord("m"), ord("M")):
                say(toggle_mute()[1])
            elif ch in (ord("a"), ord("A")):
                say(fix_routing()[1])
            elif ch in (ord("t"), ord("T")):
                picker_sel = ALL_THEMES.index(PALETTE.name)
                picker = True
            elif ch in (ord("d"), ord("D")):
                show_devices = True
            elif ch in (ord("r"), ord("R")):
                say(reconnect_phone()[1])
            elif ch == 9:
                focus = "volume" if focus == "gain" else "gain"
            elif ch in (curses.KEY_LEFT, ord("-"), ord("_")):
                set_source_volume(volume - 5) if focus == "gain" else set_stream_volume(stream_gain - 5)
            elif ch in (curses.KEY_RIGHT, ord("+"), ord("=")):
                set_source_volume(volume + 5) if focus == "gain" else set_stream_volume(stream_gain + 5)

    try:
        curses.wrapper(draw)
    except KeyboardInterrupt:
        return 0
    return 0


def once() -> int:
    meter = LevelMeter()
    meter.start()
    deadline = time.monotonic() + 4.5
    while meter.windows < 4 and time.monotonic() < deadline:
        time.sleep(0.1)

    devices = adb_devices()
    pids = bridge_pids()
    state = bridge_unit_state()
    want = sink_index()
    have = bridge_stream()[1]
    slots = meter.snapshot()
    peak = meter.peak_db
    meter.stop()

    width = 62
    def row(text: str) -> None:
        print(V + truncate(text, width - 2).ljust(width - 2) + V)

    print(TL + H * (width - 2) + TR)
    row("  ◉ PHONE-MIC" + " " * (width - 2 - 13 - 18) + "PIPEWIRE · ADB  ")
    row("  phone as a microphone")
    print(TEE_L + H * (width - 2) + TEE_R)
    row("")
    row("  PHONE LINK")
    for label, value, kind in connection_lines(devices):
        row(f"   ● {value}" if label == "state" else f"     {label:<10} {value}")
    row("")
    row("  INPUT MONITOR")
    row("   " + wave_line(slots, width - 6))
    row("   " + level_bar(peak, 20) + f" {peak:5.1f} dB")
    row("")
    row("  VIRTUAL MICROPHONE")
    alive = bool(pids) and state == "active"
    routing = "ok" if have == want else "WRONG"
    row(f"   ● Phone-Mic   {'ACTIVE' if alive else state.upper()}   routing {routing}")
    row(f"     service {state}" + (f" · pid {pids[0]}" if pids else ""))
    row(f"   GAIN    {source_volume():3d}%    VOLUME  {stream_volume():3d}%"
        f"    {'MUTED' if source_muted() else ''}")
    row("")
    row("  [C] Connect  [X] Stop  [M] Mute  [D] Devices  [Q] Quit")
    print(BL + H * (width - 2) + BR)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="phone-mic",
        description="PHONEMIC terminal dashboard for the phone microphone bridge")
    parser.add_argument("command", nargs="?", default="tui",
                        choices=["tui", "status", "start", "stop", "reconnect"],
                        help="default: tui")
    parser.add_argument("--once", action="store_true",
                        help="print one snapshot and exit (same as 'status')")
    parser.add_argument("--theme", choices=ALL_THEMES,
                        help="theme for this run (default: the saved one)")
    args = parser.parse_args()

    PALETTE.name = args.theme or load_theme()

    if args.once or args.command == "status":
        return once()
    if args.command == "start":
        ok, message = start_bridge()
        print(f"phone-mic: {message}")
        return 0 if ok else 1
    if args.command == "stop":
        ok, message = stop_bridge()
        print(f"phone-mic: {message}")
        return 0 if ok else 1
    if args.command == "reconnect":
        ok, message = reconnect_phone()
        print(f"phone-mic: {message}")
        return 0 if ok else 1
    return interactive()


if __name__ == "__main__":
    sys.exit(main())
