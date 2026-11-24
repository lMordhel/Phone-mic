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
from typing import NamedTuple

# realpath, not abspath: the command is installed as a wrapper in ~/.local/bin
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SINK = "phonemic_sink"
SOURCE = "phone_mic"
BRIDGE_UNIT = "phone-mic-bridge"
ADB_READY = "device"    # the one adb device state that carries a usable transport
ADB_UNAUTHORIZED = "unauthorized"   # the phone is asking for permission
ADB_OFFLINE = "offline"             # adb knows the device, the device is mute

# S5: the phone link's own words. adb unusable, a device adb sees but cannot
# use, and no device at all must never read the same.
LINK_UP = "CONNECTED"
LINK_DOWN = "DISCONNECTED"
LINK_NO_ADB = "NO ADB"
LINK_UNAUTHORIZED = "UNAUTHORIZED"
LINK_OFFLINE = "OFFLINE"

LINK_CAUSE_ADB = "adb no responde."
LINK_FIX_ADB = "Arreglo: sudo pacman -S --needed android-tools"
LINK_CAUSE_UNAUTHORIZED = "el teléfono no autorizó esta computadora."
LINK_FIX_UNAUTHORIZED = "Arreglo: aceptar la depuración en el teléfono"
LINK_CAUSE_OFFLINE = "el teléfono no responde al adb."
LINK_FIX_OFFLINE = "Arreglo: phone-mic reconnect"

SAMPLE_RATE = 8000      # metering rate: enough for level, cheap in CPU
BAR_WINDOW_MS = 70      # one waveform slot
WAVE_SLOTS = 28         # ~2 s of history
FLOOR_DB = -60.0
WAVE_CHARS = " ▁▂▃▄▅▆▇"

UNKNOWN = "—"            # S2: an unreadable value is shown as a dash, not as 0
MIC_MUTED = "MUTED"      # the one word for a muted source, decided by mic_state()

NO_CAPTURE_TOOL = "NO CAPTURE TOOL"   # parec missing: nothing can be captured
NO_SIGNAL = "NO SIGNAL"               # no window measured: nothing is captured

# S4: the audio server did not answer, so nothing about the pipeline is known.
AUDIO_SERVER_DOWN = "AUDIO SERVER DOWN"
AUDIO_CAUSE = "pipewire-pulse no responde."
AUDIO_FIX = "Arreglo: systemctl --user restart pipewire-pulse"
AUDIO_TTL = 2.0         # one `pactl info` answer is reused for about a second

# S7: a control with no reading to start from, and a stream that is not there.
UNREADABLE_CONTROL = "no current value to change"
NO_BRIDGE_STREAM = "NO BRIDGE STREAM"

FRAME_MIN_W = 62
FRAME_W = 78
FRAME_H = 27

# Footer geometry: the text starts this far inside the left border, and a
# transient message starts at FOOTER_MSG_COL so it never lands on a key name.
FOOTER_TEXT_COL = 3
FOOTER_MSG_COL = 45

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


def use_exact_redefinition(can_change: bool, colors: int,
                           override: str | None) -> bool:
    """Whether to redefine the terminal's palette, or use the portable 256 cube.

    A terminal can advertise the capability (ccc in terminfo) and silently ignore
    the redefinition. When that happens every theme renders with the terminal's own
    colours, so every theme looks the same and the choice appears lost. An
    advertised capability is a promise, not proof: the cube is the default and
    redefining is opt-in through PHONE_MIC_EXACT=1.
    """
    if override == "0":
        return False
    if override == "1":
        return bool(can_change and colors >= 256)
    return False


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
        self.exact = use_exact_redefinition(
            curses.can_change_color(), curses.COLORS,
            os.environ.get("PHONE_MIC_EXACT"))

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

def query(cmd: list[str], timeout: float = 3.0) -> str | None:
    """Run a read-only query and return its stdout, or None when unreadable.

    None means "unknown": a missing binary, a timeout, an OSError, or a non-zero
    exit that printed nothing. It is never conflated with a successful empty
    answer, which stays "": a failed read must not look like a measurement (S2).

    A non-zero exit that did print something is kept, not discarded:
    `systemctl is-active` writes the unit state to stdout and exits non-zero for
    anything but "active", so "inactive" or "failed" is a real answer.
    """
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if out.returncode != 0 and not out.stdout.strip():
        return None
    return out.stdout


def run(cmd: list[str], timeout: float = 3.0) -> str:
    """Fire-and-forget command: "" whatever happens; setters only.

    Its callers ignore the output (`pactl set-*`, `move-sink-input`) or just list
    what exists. A read that feeds a displayed value must use query().
    """
    return query(cmd, timeout) or ""


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


def fmt_value(value, spec: str = "", suffix: str = "", width: int = 0) -> str:
    """Format a value that may be unknown: unknown is `—`, never a number (S2).

    `width` keeps a column stable: the dash is padded to the width the numeric
    form would have taken.
    """
    if value is None:
        return UNKNOWN.ljust(width)
    return format(value, spec) + suffix


def parse_volume_percent(text: str | None) -> int | None:
    """Aggregate percentage from `pactl get-*-volume`; None when unreadable."""
    if text is None:
        return None
    for line in text.splitlines():
        if "%" not in line:
            continue
        for part in line.split("/"):
            part = part.strip()
            if part.endswith("%"):
                digits = "".join(c for c in part if c.isdigit())
                if digits:
                    return int(digits)
    return None


def parse_mute(text: str | None) -> bool | None:
    """`Mute: yes|no`; None when the answer is neither."""
    if text is None:
        return None
    words = text.strip().lower().replace(":", " ").split()
    if "yes" in words:
        return True
    if "no" in words:
        return False
    return None


def parse_unit_state(text: str | None) -> str | None:
    """Unit state from `systemctl is-active`: active, inactive, failed, …"""
    if text is None:
        return None
    words = text.split()
    return words[0] if words else None


def parse_adb_device_states(text: str | None) -> list[tuple[str, str]] | None:
    """(serial, state) pairs from `adb devices`: device, unauthorized, offline, …"""
    if text is None:
        return None
    devices: list[tuple[str, str]] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[0].startswith("*") or line.startswith("List of"):
            continue
        devices.append((fields[0], fields[1]))
    return devices


def parse_model_props(text: str | None) -> str | None:
    """One `getprop` answer; None when the property is unset or unreadable."""
    if text is None:
        return None
    return text.strip() or None


class SinkInput(NamedTuple):
    index: str
    sink: str
    volume: int | None
    app: str | None


def parse_sink_inputs(text: str | None) -> list[SinkInput] | None:
    """Blocks of `pactl list sink-inputs`; None when the listing is unreadable."""
    if text is None:
        return None
    entries: list[SinkInput] = []
    index: str | None = None
    sink = ""
    app: str | None = None
    volume: int | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Sink Input #"):
            if index is not None:
                entries.append(SinkInput(index, sink, volume, app))
            index = stripped.split("#", 1)[1].strip()
            sink, app, volume = "", None, None
        elif index is None:
            continue
        elif stripped.startswith("Sink:"):
            sink = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Volume:") and volume is None:
            volume = parse_volume_percent(stripped)
        elif stripped.startswith("application.name = "):
            app = stripped.split("=", 1)[1].strip().strip('"')
    if index is not None:
        entries.append(SinkInput(index, sink, volume, app))
    return entries


def find_sink_input(inputs: list[SinkInput] | None,
                    app: str = "scrcpy") -> SinkInput | None:
    """The first sink-input owned by `app`; None when the listing has none."""
    for entry in inputs or ():
        if entry.app == app:
            return entry
    return None


def routing_ok(sink: str | None, stream_sink: str | None) -> bool:
    """Whether the bridge stream sits on the remap sink.

    An unknown index (`None`: the listing failed) and an absent one (`""`: there
    is no such sink) can never match, so neither may ever read as routed.
    """
    return bool(sink) and bool(stream_sink) and sink == stream_sink


class AudioState(NamedTuple):
    """What the panel may say about the audio server (S4).

    `up` is the licence to print any reading at all: while it is false the box
    claims no state word, no gain and no volume, because none was measured.
    """
    up: bool
    word: str
    cause: str
    fix: str


def audio_state(info: str | None) -> AudioState:
    """Decide the audio server state from the probe answer only.

    An answer must name a server: `pactl info` prints "Server Name" when the
    server replies, and only a failure line when it does not. No answer, an
    empty answer, or a failure message all mean the same thing: unknown, which
    gets its own words and the command that fixes it (S4).
    """
    if info is None or "server name" not in info.lower():
        return AudioState(False, AUDIO_SERVER_DOWN, AUDIO_CAUSE, AUDIO_FIX)
    return AudioState(True, "", "", "")


class MicState(NamedTuple):
    """What the VIRTUAL MICROPHONE box may say: a word, a tone, and the fix."""
    word: str
    tone: str
    cause: str
    fix: str


def mic_state(audio: AudioState, muted: bool | None, alive: bool,
              unit_state: str | None) -> MicState:
    """What the VIRTUAL MICROPHONE box may claim, from facts only (S4, S8).

    A server that does not answer outranks everything else: the bridge unit can
    look active while nothing can be read or written, and the box must not paint
    `ACTIVE`, a gain or a volume in that state (S2, S4).
    """
    if not audio.up:
        return MicState(audio.word, "bad", audio.cause, audio.fix)
    if muted:
        return MicState(MIC_MUTED, "warn", "", "")
    if alive:
        return MicState("ACTIVE", "ok", "", "")
    return MicState(fmt_value(unit_state).upper(), "bad", "", "")


def bridge_alive(pids: list[int], unit_state: str | None) -> bool:
    """Whether the bridge counts as up: scrcpy running and its unit active.

    One decision for the panel and the snapshot (S6): the two used to repeat the
    expression, so they could drift apart.
    """
    return bool(pids) and unit_state == "active"


def audio_buffer_ms() -> str:
    """The audio buffer the bridge runs with: AUDIO_BUFFER, 50 ms by default."""
    return os.environ.get("AUDIO_BUFFER", "50")


def transport_of(serial: str | None) -> str | None:
    """USB or Wi-Fi, from the serial adb reports; None when there is no device."""
    if not serial:
        return None
    return "Wi-Fi" if ":" in serial else "USB"


def address_of(serial: str | None) -> str | None:
    """The host part of an adb serial; None when there is no device."""
    return serial.split(":")[0] if serial else None


class LinkState(NamedTuple):
    """What the PHONE LINK box may say, from facts only (S5).

    `routing` is True when the bridge stream sits on the remap sink and False
    when it sits elsewhere, but None when the audio server did not answer: a
    routing claim needs a server that answers (S4, S5). `model` and `service`
    are None when they could not be read, which the box prints as `—`, never as
    `-` and never as a word that looks like a state (S2, S5).
    """
    word: str
    tone: str
    cause: str
    fix: str
    model: str | None
    transport: str | None
    address: str | None
    service: str | None
    routing: bool | None


def link_state(devices: list[tuple[str, str]] | None, model: str | None,
               unit_state: str | None, audio: AudioState,
               routed: bool) -> LinkState:
    """Decide the phone link state from facts only: adb, the device, the unit.

    Situations that used to read the same now have their own words (S5): adb
    itself unusable (None: no adb binary, or a server that will not answer), a
    device adb sees but cannot use (`unauthorized`, `offline`), a device in any
    other state adb reports, and no device attached at all. The unusable ones
    also name the cause and the command that fixes them, in the shape the audio
    box uses (S4). Nothing unreadable is invented: it stays None.
    """
    routing = routed if audio.up else None
    if devices is None:
        return LinkState(LINK_NO_ADB, "bad", LINK_CAUSE_ADB, LINK_FIX_ADB,
                         model, None, None, unit_state, routing)
    ready = [serial for serial, state in devices if state == ADB_READY]
    if ready:
        serial = ready[0]
        return LinkState(LINK_UP, "ok", "", "", model, transport_of(serial),
                         address_of(serial), unit_state, routing)
    if not devices:
        return LinkState(LINK_DOWN, "bad", "", "", model, None, None,
                         unit_state, routing)
    serial, state = devices[0]
    states = [state for _, state in devices]
    if ADB_UNAUTHORIZED in states:
        word, tone, cause, fix = (LINK_UNAUTHORIZED, "warn",
                                  LINK_CAUSE_UNAUTHORIZED, LINK_FIX_UNAUTHORIZED)
    elif ADB_OFFLINE in states:
        word, tone, cause, fix = (LINK_OFFLINE, "bad", LINK_CAUSE_OFFLINE,
                                  LINK_FIX_OFFLINE)
    else:
        # adb's own word for a state this module does not interpret: honest, and
        # still distinguishable from CONNECTED and from DISCONNECTED.
        word, tone, cause, fix = state.upper(), "warn", "", ""
    return LinkState(word, tone, cause, fix, model, transport_of(serial),
                     address_of(serial), unit_state, routing)


def mic_value_line(volume: int | None, stream_gain: int | None) -> str:
    """GAIN/VOLUME row for a state where neither can be read: dashes, not 0% (S2)."""
    return (f"GAIN    {fmt_value(volume, '3d', '%', 4)}"
            f"    VOLUME  {fmt_value(stream_gain, '3d', '%', 4)}")


def mic_mute_note(mic: MicState) -> str:
    """The trailing MUTED note `status` prints, taken from mic_state's word.

    S6: the note used to be re-derived from the raw mute reading, so a stale
    one could say MUTED while the panel's own decision said AUDIO SERVER DOWN.
    """
    return mic.word if mic.word == MIC_MUTED else ""


class ControlResult(NamedTuple):
    """Whether a control worked, and the one line the panel shows for it."""
    ok: bool
    message: str


def control_outcome(readable: bool, write_ok: bool, success: str,
                    detail: str = "",
                    blocked: str = UNREADABLE_CONTROL) -> ControlResult:
    """Decide whether a control may report success (S7).

    Three outcomes, never merged: the current value could not be read, so no
    write was attempted and the control says it cannot; the write itself failed,
    so the panel reports that failure in pactl's own words; or the write worked
    and the control keeps the wording it always had.
    """
    if not readable:
        return ControlResult(False, blocked)
    if not write_ok:
        return ControlResult(False, f"pactl failed: {detail}" if detail
                             else "pactl failed")
    return ControlResult(True, success)


def write_cmd(cmd: list[str], timeout: float = 3.0) -> tuple[bool, str]:
    """Run a setter and report what happened: (worked, pactl's own words).

    `run()` cannot serve here: it discards the exit status, so a refused write
    would look like a success. This runner decides nothing; control_outcome()
    owns that. A write is also evidence about the server, so the probe answer is
    dropped and the next frame asks again.
    """
    CACHE.invalidate("audio")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return False, str(exc)
    if out.returncode == 0:
        return True, ""
    detail = (out.stderr or out.stdout).strip().splitlines()
    return False, detail[-1] if detail else f"exit {out.returncode}"


def audio_probe() -> str | None:
    """One `pactl info` per refresh; None when the server does not answer.

    Cached for AUDIO_TTL so the 120 ms frame loop does not fork pactl the whole
    time, and short enough that a server that comes back is noticed without
    restarting the panel (S4).
    """
    return CACHE.get("audio", AUDIO_TTL, lambda: query(["pactl", "info"]))


def adb_devices() -> list[tuple[str, str]] | None:
    """(serial, state) of every attached device; None when adb cannot answer."""
    return CACHE.get("devices", 2.0,
                     lambda: parse_adb_device_states(query(["adb", "devices"])))


def adb_model() -> str | None:
    def read() -> str | None:
        for prop in ("ro.product.marketname", "ro.product.odm.marketname",
                     "ro.product.model"):
            value = parse_model_props(query(["adb", "shell", "getprop", prop]))
            if value:
                return value
        return None
    return CACHE.get("model", 30.0, read)


def bridge_pids() -> list[int]:
    out = run(["pgrep", "-x", "scrcpy"])
    return [int(p) for p in out.split() if p.isdigit()]


def bridge_unit_state() -> str | None:
    return parse_unit_state(
        query(["systemctl", "--user", "is-active", BRIDGE_UNIT]))


def sink_index() -> str | None:
    """Index of the remap sink: "" when absent, None when pactl failed."""
    text = query(["pactl", "list", "short", "sinks"])
    if text is None:
        return None
    for line in text.splitlines():
        fields = line.split()
        if len(fields) > 1 and fields[1] == SINK:
            return fields[0]
    return ""


def source_present() -> bool | None:
    text = query(["pactl", "list", "short", "sources"])
    if text is None:
        return None
    for line in text.splitlines():
        fields = line.split()
        if len(fields) > 1 and fields[1] == SOURCE:
            return True
    return False


def sink_inputs() -> list[SinkInput] | None:
    return CACHE.get("sinputs", 1.0, lambda: parse_sink_inputs(
        query(["pactl", "list", "sink-inputs"])))


def bridge_stream() -> SinkInput | None:
    """The scrcpy playback stream; None when there is none or it is unreadable."""
    return find_sink_input(sink_inputs())


def routed_now() -> bool:
    """Whether the bridge stream sits on the remap sink, read in one place.

    Both renderers call this instead of repeating the two reads and the
    comparison, so they cannot gather the routing facts differently (S6).
    """
    stream = bridge_stream()
    return routing_ok(sink_index(), stream.sink if stream else "")


def source_volume() -> int | None:
    return CACHE.get("vol", 1.0, lambda: parse_volume_percent(
        query(["pactl", "get-source-volume", SOURCE])))


def source_muted() -> bool | None:
    return CACHE.get("mute", 1.0, lambda: parse_mute(
        query(["pactl", "get-source-mute", SOURCE])))


def stream_volume() -> int | None:
    # `pactl get-sink-input-volume` does not exist in every pactl release
    # ("No valid command specified"), so the volume is read from the listing.
    def read() -> int | None:
        stream = bridge_stream()
        return stream.volume if stream else None
    return CACHE.get("svol", 1.0, read)


def set_source_volume(value: int) -> ControlResult:
    target = max(0, min(100, value))
    work_ok, detail = write_cmd(["pactl", "set-source-volume", SOURCE,
                                 f"{target}%"])
    CACHE.invalidate("vol")
    return control_outcome(True, work_ok, f"gain {target}%", detail)


def set_stream_volume(value: int) -> ControlResult:
    stream = bridge_stream()
    CACHE.invalidate("svol")
    CACHE.invalidate("sinputs")
    if not stream:
        # There is nothing to write to: say what is missing, never a success.
        return control_outcome(False, False, "", "", NO_BRIDGE_STREAM)
    target = max(0, min(100, value))
    work_ok, detail = write_cmd(["pactl", "set-sink-input-volume", stream.index,
                                 f"{target}%"])
    return control_outcome(True, work_ok, f"volume {target}%", detail)


def toggle_mute() -> ControlResult:
    muted = source_muted()
    if muted is None:
        # No reading: any new value would be invented, so nothing is written.
        CACHE.invalidate("mute")
        return control_outcome(False, False, "")
    work_ok, detail = write_cmd(
        ["pactl", "set-source-mute", SOURCE, "no" if muted else "yes"])
    CACHE.invalidate("mute")
    return control_outcome(True, work_ok, "unmuted" if muted else "MUTED",
                           detail)


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
    stream = bridge_stream()
    have = stream.sink if stream else ""
    if not want:
        return False, f"{SINK} missing"
    if not have:
        return False, "no bridge stream"
    if have == want:
        return True, "already routed"
    subprocess.run(["pactl", "move-sink-input", have, SINK], check=False)
    return True, "re-routed"


# --------------------------------------------------------------------------- meter

class MeterState(NamedTuple):
    """What the INPUT MONITOR may truthfully say about the capture (S2, S3).

    `measuring` is the only licence to draw a level: when it is false the level
    is None and the panel must print `—`, never a floor value that a silent room
    would also produce. `word` names the situation in words when not measuring.
    """
    measuring: bool
    word: str
    level: float | None


def meter_state(available: bool, running: bool, windows: int,
                peak: float | None) -> MeterState:
    """Decide the meter state from facts only: no capture, not started, or real.

    Three situations must never look alike: `parec` missing (nothing can be
    captured), a capture with no window yet or no longer running (nothing is
    being captured), and a running capture, whose measured value is data even
    when it sits at FLOOR_DB.
    """
    if not available:
        return MeterState(False, NO_CAPTURE_TOOL, None)
    if not running or windows <= 0 or peak is None:
        return MeterState(False, NO_SIGNAL, None)
    return MeterState(True, "", peak)


class LevelMeter(threading.Thread):
    """Rolling windows of the virtual microphone, for the waveform and the level."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._proc: subprocess.Popen[bytes] | None = None
        # Whether a capture tool exists at all: the meter cannot report a
        # measurement it has no tool to take (S3). Read before the thread runs.
        self.available = shutil.which("parec") is not None
        self.slots: collections.deque[float] = collections.deque(
            [FLOOR_DB] * WAVE_SLOTS, maxlen=WAVE_SLOTS)
        # None, not the floor: nothing has been measured until a window is read.
        self.peak_db: float | None = None
        self.rms_db: float | None = None
        self.windows = 0
        self.running = False

    def run(self) -> None:
        if not self.available:
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

def db_fraction(db: float | None) -> float:
    if db is None or db <= FLOOR_DB:
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


def wave_row(state: MeterState, slots: list[float], width: int) -> str:
    """Waveform row for a state: blank when nothing was measured (S2, S3).

    A floor-filled bar is exactly what a silent room renders, so it must never
    stand in for a missing measurement; the width is the same either way.
    """
    return wave_line(slots, width) if state.measuring else " " * width


def level_row(state: MeterState, width: int) -> str:
    """Level bar row for a state: blank when nothing was measured (S2, S3)."""
    return level_bar(state.level, width) if state.measuring else " " * width


def level_bar(db: float, width: int) -> str:
    filled = int(round(db_fraction(db) * width))
    return "█" * filled + "░" * (width - filled)


def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def footer_action_line() -> str:
    """First footer line: every action key the loop handles, in its old style.

    P7: `[R]` was handled but never advertised. The line keeps the cells of the
    original seven bindings; the keys that do not fit move to the second line
    instead of being clipped by the frame edge.
    """
    return ("[C] Connect [X] Stop [M] Mute [A] Reroute "
            "[T] Theme [D] Devices [Q] Quit")


def footer_nav(focus: str) -> list[tuple[str, str]]:
    """Second footer line as (text, tone) segments, with the focus marked.

    P7: `[R]`, `[Tab]` and the nudge keys are handled but were never shown. The
    line stops one cell before FOOTER_MSG_COL so a message never lands on it,
    which is why the words "focus gain" gave way to the emphasis on the name.
    `-`/`_` and `+`/`=` are the same ±5% nudge as the arrows, just as `c`/`C`
    are the same key; naming them would take three cells the message column
    needs, so the arrows are the ones advertised.
    """
    segments: list[tuple[str, str]] = [("[R] Reconnect [Tab] ", "dim")]
    for index, name in enumerate(("gain", "volume")):
        segments.append((name, "accent" if name == focus else "dim"))
        if index == 0:
            segments.append(("/", "dim"))
    segments.append((" [←→] ±5%", "dim"))
    return segments


def footer_nav_text(focus: str) -> str:
    """The second footer line as one string, for measuring and for tests."""
    return "".join(text for text, _ in footer_nav(focus))


def routing_claim(link: LinkState) -> tuple[str, str]:
    """(text, tone) of the routing line, shared by the box and by `status`.

    S6: the words `ok`, `WRONG` and the unknown dash used to be re-derived by
    the snapshot, which could disagree with the box about them.
    """
    if link.routing is None:
        return f"routing {UNKNOWN}", "dim"
    return ("routing ok", "ok") if link.routing else ("routing WRONG", "bad")


def link_rows(link: LinkState) -> list[tuple[str, str, str]]:
    """(label, value, tone) rows of the PHONE LINK box: seven rows, always.

    The four fields keep their places and the routing line stays last. The two
    rows between them carry either the diagnosis (cause and fix) or the bridge
    unit state and the buffer setting. Seven is what the box holds, so changed
    words never move the frame (S8).
    """
    rows: list[tuple[str, str, str]] = [
        ("state", link.word, link.tone),
        ("device", truncate(fmt_value(link.model), 20), "plain"),
        ("transport", fmt_value(link.transport), "plain"),
        ("address", fmt_value(link.address), "plain"),
    ]
    if link.cause:
        rows.append(("", link.cause, "warn"))
        rows.append(("", link.fix, "dim"))
    else:
        service_tone = "plain" if link.service else "dim"
        rows.append(("service", fmt_value(link.service), service_tone))
        rows.append(("buffer", f"{audio_buffer_ms()} ms", "plain"))
    routing, routing_tone = routing_claim(link)
    rows.append(("", routing, routing_tone))
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
            # The server answer comes first: without it nothing else is known (S4).
            audio = audio_state(audio_probe())
            devices = adb_devices()
            pids = bridge_pids()
            state = bridge_unit_state()
            model = adb_model()
            routed = routed_now()
            volume = source_volume()
            muted = source_muted()
            stream_gain = stream_volume()
            # One decision from facts, shared with the `status` snapshot (S5).
            link = link_state(devices, model, state, audio, routed)

            # --- two panels (rows 5..14) ----------------------------------
            panel_y = 5
            panel_h = 9
            put(panel_y - 1 + 0, left_x, "PHONE LINK", tone("label"))
            put(panel_y - 1 + 0, right_x, "INPUT MONITOR", tone("label"))
            draw_box(stdscr, top + panel_y, left_x, panel_h, col_w, color=tone("border"))
            draw_box(stdscr, top + panel_y, right_x, panel_h, col_w, color=tone("border"))

            conn = link_rows(link)
            for i, (label, value, kind) in enumerate(conn):
                row = panel_y + 1 + i
                if label == "state":
                    put(row, left_x + 2, "● " + value, tone(kind) | curses.A_BOLD)
                elif label:
                    put(row, left_x + 2, f"{label:<10}", tone("dim"))
                    put(row, left_x + 13, value, tone(kind))
                else:
                    put(row, left_x + 2, value, tone(kind))

            wave_w = max(8, col_w - 6)
            # One decision, taken from facts: never draw a level nobody measured
            # and never hide a measured floor (S2, S3).
            capture = meter_state(meter.available, meter.running, meter.windows,
                                 meter.peak_db)
            slots = meter.snapshot()
            bar_tone = (level_tone(capture.level) if capture.measuring
                        else tone("dim"))
            put(panel_y + 2, right_x + 2, wave_row(capture, slots, wave_w), bar_tone)
            put(panel_y + 4, right_x + 2, "INPUT LEVEL", tone("dim"))
            if capture.word:
                put(panel_y + 4, right_x + 2 + len("INPUT LEVEL") + 2,
                    capture.word, tone("warn"))
            bar_w = max(6, wave_w - 11)
            put(panel_y + 5, right_x + 2, level_row(capture, bar_w), bar_tone)
            put(panel_y + 5, right_x + 2 + bar_w + 1,
                fmt_value(capture.level, "5.1f", " dB", 8), tone("plain"))
            rms = meter.rms_db if capture.measuring else None
            put(panel_y + 6, right_x + 2,
                f"RMS {fmt_value(rms, '5.1f', ' dB', 8)}   "
                f"buffer {audio_buffer_ms()} ms", tone("dim"))

            # --- virtual microphone (rows 16..21) -------------------------
            mic_y = panel_y + panel_h + 2
            mic_w = inner - 2 * margin
            put(mic_y - 1, left_x, "VIRTUAL MICROPHONE", tone("label"))
            draw_box(stdscr, top + mic_y, left_x, 6, mic_w, color=tone("border"))

            # One decision from facts: a server that does not answer outranks the
            # word, the gain and the volume the box would otherwise print (S4).
            mic = mic_state(audio, muted, bridge_alive(pids, state), state)
            put(mic_y + 1, left_x + 2, "●", tone(mic.tone))
            put(mic_y + 1, left_x + 4, "Phone-Mic", curses.A_BOLD)
            put(mic_y + 1, left_x + 15, "PipeWire remap source", tone("dim"))
            put(mic_y + 1, left_x + mic_w - 3 - len(mic.word), mic.word,
                tone(mic.tone) | curses.A_BOLD)
            if mic.cause:
                # S4: the cause and the command that fixes it, in place of the
                # controls, whose values cannot be read at all right now.
                put(mic_y + 2, left_x + 2, mic.cause, tone("warn"))
                put(mic_y + 3, left_x + 2, mic.fix, tone("dim"))
                put(mic_y + 4, left_x + 2, mic_value_line(volume, stream_gain),
                    tone("dim"))
            else:
                routing, routing_tone = routing_claim(link)
                put(mic_y + 2, left_x + 2, f"service {fmt_value(state)}"
                    + (f" · pid {pids[0]}" if pids else "")
                    + f" · {routing}", tone(routing_tone))

                def slider(row: int, label: str, value: int | None,
                           selected: bool) -> None:
                    track_w = 16
                    if value is None:
                        # No readable volume: leave the track blank rather than flag
                        # a position nobody measured, and print a dash, not 0% (S2).
                        track = " " * track_w
                    else:
                        filled = int(round(track_w * value / 100))
                        track = "━" * filled + "●" + "━" * (track_w - filled)
                    put(row, left_x + 2, f"{label:<8}",
                        tone("accent") if selected else tone("dim"))
                    put(row, left_x + 11, track,
                        tone("ok") if selected else tone("dim"))
                    put(row, left_x + 29, fmt_value(value, "3d", "%", 4),
                        tone("plain"))

                slider(mic_y + 3, "GAIN", volume, focus == "gain")
                slider(mic_y + 4, "VOLUME", stream_gain, focus == "volume")

            def nudge(delta: int) -> None:
                """Step the focused control; unknown volume refuses instead of guessing."""
                value = volume if focus == "gain" else stream_gain
                if value is None:
                    # S7: no reading, so no write and no claim of one either.
                    say(control_outcome(False, False, "").message)
                    return
                if focus == "gain":
                    result = set_source_volume(value + delta)
                else:
                    result = set_stream_volume(value + delta)
                if not result.ok:
                    say(result.message)

            # --- footer (rows 23..26) -------------------------------------
            frame_row(frame_h - 4, TEE_L, TEE_R)
            put(frame_h - 3, left + FOOTER_TEXT_COL, footer_action_line(),
                tone("dim"))
            col = left + FOOTER_TEXT_COL
            for text, kind in footer_nav(focus):
                put(frame_h - 2, col, text, tone(kind))
                col += len(text)
            if message and time.monotonic() - message_at < 6:
                put(frame_h - 2, left + FOOTER_MSG_COL, message, tone("warn"))
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
                put(py + ph - 2, px + 2, "j/k preview · ↵ apply · esc cancel",
                    tone("dim"))

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
                    PALETTE.apply(ALL_THEMES[picker_sel])   # preview only
                elif ch in (curses.KEY_DOWN, ord("j")):
                    picker_sel = (picker_sel + 1) % len(ALL_THEMES)
                    PALETTE.apply(ALL_THEMES[picker_sel])   # preview only
                elif ch in (10, 13, curses.KEY_ENTER):
                    PALETTE.apply(ALL_THEMES[picker_sel])
                    save_theme(ALL_THEMES[picker_sel])
                    picker = False
                    say(f"tema: {ALL_THEMES[picker_sel]}")
                elif ch in (27, ord("t"), ord("T"), ord("q"), ord("Q")):
                    # Closing without confirming must not keep a preview: restore
                    # what was saved, or the choice looks applied and is not.
                    PALETTE.apply(picker_origin)
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
                say(toggle_mute().message)
            elif ch in (ord("a"), ord("A")):
                say(fix_routing()[1])
            elif ch in (ord("t"), ord("T")):
                picker_sel = ALL_THEMES.index(PALETTE.name)
                picker_origin = PALETTE.name
                picker = True
            elif ch in (ord("d"), ord("D")):
                show_devices = True
            elif ch in (ord("r"), ord("R")):
                say(reconnect_phone()[1])
            elif ch == 9:
                focus = "volume" if focus == "gain" else "gain"
            elif ch in (curses.KEY_LEFT, ord("-"), ord("_")):
                nudge(-5)
            elif ch in (curses.KEY_RIGHT, ord("+"), ord("=")):
                nudge(+5)

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

    audio = audio_state(audio_probe())
    devices = adb_devices()
    pids = bridge_pids()
    state = bridge_unit_state()
    model = adb_model()
    routed = routed_now()
    volume = source_volume()
    stream_gain = stream_volume()
    muted = source_muted()
    # The same decision the panel takes, from the same helper (S5, S6).
    link = link_state(devices, model, state, audio, routed)
    # The same decision the panel takes, from the same helper (S2, S3).
    capture = meter_state(meter.available, meter.running, meter.windows,
                          meter.peak_db)
    slots = meter.snapshot()
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
    for label, value, kind in link_rows(link):
        if label == "state":
            row(f"   ● {value}")
        elif label:
            row(f"     {label:<10} {value}")
        else:
            row(f"     {value}")
    row("")
    row("  INPUT MONITOR" + (f"   {capture.word}" if capture.word else ""))
    row("   " + wave_row(capture, slots, width - 6))
    row("   " + level_row(capture, 20) + " "
        + fmt_value(capture.level, "5.1f", " dB"))
    row("")
    row("  VIRTUAL MICROPHONE")
    # The same decisions the panel takes, from the same helpers (S4, S6, S7).
    mic = mic_state(audio, muted, bridge_alive(pids, state), state)
    claim, _ = routing_claim(link)
    row(f"   ● Phone-Mic   {mic.word}   {claim}")
    if mic.cause:
        row(f"     {mic.cause}")
        row(f"     {mic.fix}")
    else:
        row(f"     service {fmt_value(state)}"
            + (f" · pid {pids[0]}" if pids else ""))
    row(f"   {mic_value_line(volume, stream_gain)}"
        f"    {mic_mute_note(mic)}")
    row("")
    row("  [C] Connect  [X] Stop  [M] Mute  [D] Devices  [Q] Quit")
    print(BL + H * (width - 2) + BR)
    print(f"  theme {PALETTE.name}")
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
