#!/usr/bin/env python3
"""Terminal panel for phone-mic.

Shows whether the phone is connected, whether the bridge is forwarding and a
vertical level meter fed by the phone microphone, and lets the user start or stop
the bridge without remembering the scripts. It owns no audio pipeline: starting
the bridge talks to the systemd user unit, and stopping it stops that unit.

Usage:
    phone-mic            interactive panel
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

METER_BARS = 14        # columns of the vertical meter
METER_ROWS = 7         # height of the vertical meter
BAR_WINDOW_MS = 90     # one bar per this much audio
SAMPLE_RATE = 8000     # metering rate; enough for level, cheap in CPU
FLOOR_DB = -60.0       # bottom of the scale


# --------------------------------------------------------------------------- state

def run(cmd: list[str], timeout: float = 3.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def adb_devices() -> list[str]:
    lines = run(["adb", "devices"]).splitlines()[1:]
    return [line.split()[0] for line in lines if line.strip().endswith("device")]


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


def bridge_sink() -> str:
    """Sink index the scrcpy playback stream is currently attached to."""
    out = run(["pactl", "list", "sink-inputs"])
    current = ""
    idx = ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("Sink Input #"):
            idx = stripped.split("#", 1)[1]
        elif stripped.startswith("Sink:") and idx:
            current = stripped.split(":", 1)[1].strip()
        elif 'application.name = "scrcpy"' in stripped:
            return current
    return ""


class LevelMeter(threading.Thread):
    """Reads a low-rate copy of the virtual microphone into a rolling set of bars.

    A second capture client is harmless for PipeWire and costs a few kB/s. One bar
    is one short window of audio, so the meter scrolls with the sound instead of
    showing a single averaged value.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._proc: subprocess.Popen[bytes] | None = None
        self.bars: collections.deque[float] = collections.deque(
            [FLOOR_DB] * METER_BARS, maxlen=METER_BARS)
        self.peak_db = FLOOR_DB
        self.rms_db = FLOOR_DB
        self.windows = 0    # windows measured; the panel waits for real data
        self.running = False

    def run(self) -> None:
        if not shutil.which("parec"):
            return
        frames = SAMPLE_RATE * BAR_WINDOW_MS // 1000
        window_bytes = frames * 2  # s16le mono
        try:
            self._proc = subprocess.Popen(
                ["parec", "--device=" + SOURCE, "--format=s16le",
                 f"--rate={SAMPLE_RATE}", "--channels=1", "--raw"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        self.running = True
        debug = bool(os.environ.get("PHONE_MIC_DEBUG"))
        fd = self._proc.stdout.fileno() if self._proc.stdout else -1
        pending = bytearray()
        while not self._stop.is_set() and fd >= 0:
            # os.read returns whatever is available; a buffered read(n) blocks
            # until n bytes have accumulated, which on this pipe took ~2 s.
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
                self.bars.append(self.peak_db)
                self.windows += 1
                if debug:
                    print(f"meter: peak={self.peak_db:.1f} rms={self.rms_db:.1f}",
                          file=sys.stderr)
        self.running = False

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def snapshot_bars(self) -> list[float]:
        return list(self.bars)


# ------------------------------------------------------------------------- actions

def start_bridge() -> tuple[bool, str]:
    """Start the systemd user unit: the bridge outlives this panel."""
    out = subprocess.run(["systemctl", "--user", "start", BRIDGE_UNIT],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return False, (out.stderr or "systemctl start failed").strip().splitlines()[-1]
    return True, "bridging (service started; closing the panel keeps it running)"


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
    have = bridge_sink()
    if not want:
        return False, f"{SINK} is missing"
    if not have:
        return False, "no bridge stream"
    if have == want:
        return True, "already routed"
    subprocess.run(["pactl", "move-sink-input", have, SINK], check=False)
    return True, "re-routed"


# ------------------------------------------------------------------------- drawing

def bar_height(db: float, rows: int) -> int:
    fraction = 0.0 if db <= FLOOR_DB else (db - FLOOR_DB) / -FLOOR_DB
    return max(0, min(rows, round(fraction * rows)))


def state_rows(level: LevelMeter | None) -> list[tuple[str, str]]:
    devices = adb_devices()
    pids = bridge_pids()
    want = sink_index()
    have = bridge_sink()
    rows: list[tuple[str, str]] = []
    rows.append(("virtual device", f"{SINK} / {SOURCE}" if want and source_present()
                 else "missing (run scripts/load-virtual-mic.sh)"))
    rows.append(("phone (adb)", ", ".join(devices) if devices else "not connected"))
    state = bridge_unit_state()
    if pids:
        routing = "ok" if have == want else f"WRONG (sink {have or '?'})"
        rows.append(("bridge service", f"{state} (pid {pids[0]}), routing {routing}"))
    elif state in ("activating", "active"):
        rows.append(("bridge service", f"{state}, waiting for the phone"))
    else:
        rows.append(("bridge service", state))
    if level is not None:
        rows.append(("audio", f"peak {level.peak_db:6.1f} dB   rms {level.rms_db:6.1f} dB"
                     if level.running else "meter unavailable"))
    return rows


def once() -> int:
    meter = LevelMeter()
    meter.start()
    # parec needs ~2 s to connect to the graph and start delivering audio, so wait
    # for measured windows instead of a fixed delay.
    deadline = time.monotonic() + 4.0
    while meter.windows < 4 and time.monotonic() < deadline:
        time.sleep(0.1)
    rows = state_rows(meter)
    bars = [bar_height(db, METER_ROWS) for db in meter.snapshot_bars()]
    meter.stop()

    width = max(len(k) for k, _ in rows) + 2
    print("phone-mic")
    for key, value in rows:
        print(f"  {key:<{width}} {value}")
    print()
    # vertical meter, one column per window, scale on the left
    for row in range(METER_ROWS, 0, -1):
        line = "  "
        for height in bars:
            line += "█  " if height >= row else "·  "
        if row == METER_ROWS:
            line += " 0 dB"
        elif row == METER_ROWS - 2:
            line += " -18 dB"
        elif row == 1:
            line += " -60 dB"
        print(line)
    print("  " + "-" * (len(bars) * 3))
    print(f"  peak {meter.peak_db:6.1f} dB   rms {meter.rms_db:6.1f} dB")
    return 0


def interactive() -> int:
    def draw(stdscr) -> None:
        curses.curs_set(0)
        stdscr.timeout(120)
        has_colors = curses.has_colors()
        if has_colors:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)   # healthy / low level
            curses.init_pair(2, curses.COLOR_RED, -1)     # problem / hot level
            curses.init_pair(3, curses.COLOR_YELLOW, -1)  # warning / mid level

        def state_color(value: str) -> int:
            if not has_colors:
                return 0
            low = value.lower()
            if "wrong" in low or low.startswith(
                    ("stopped", "failed", "inactive", "not connected", "missing",
                     "no bridge", "meter unavailable", "unknown", "waiting")):
                return curses.color_pair(2)
            if low.startswith(("active", "ok", "already")) or "forwarding" in low:
                return curses.color_pair(1)
            return curses.color_pair(3)

        def level_color(db: float) -> int:
            if not has_colors:
                return 0
            if db >= -6:
                return curses.color_pair(2)
            if db >= -18:
                return curses.color_pair(3)
            return curses.color_pair(1)

        meter = LevelMeter()
        meter.start()
        message = ""
        message_at = 0.0
        meter_on = True

        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            stdscr.addstr(0, 0, "phone-mic", curses.A_BOLD)
            stdscr.addstr(0, 10, "microfono del telefono", curses.A_DIM)

            rows = state_rows(meter)
            label_width = max(len(k) for k, _ in rows) + 2
            for i, (key, value) in enumerate(rows, start=2):
                stdscr.addstr(i, 2, f"{key:<{label_width}}")
                stdscr.addstr(i, 2 + label_width, value[: max(0, width - label_width - 3)],
                              state_color(value))

            # vertical meter: one column per audio window, drawn bottom-up
            top = len(rows) + 4
            bottom = top + METER_ROWS - 1
            if bottom < height - 4:
                bars = [bar_height(db, METER_ROWS) for db in meter.snapshot_bars()] \
                    if meter_on else [0] * METER_BARS
                dbs = meter.snapshot_bars() if meter_on else [FLOOR_DB] * METER_BARS
                for column, (height_units, db) in enumerate(zip(bars, dbs)):
                    x = 3 + column * 2
                    if x >= width - 2:
                        break
                    for r in range(METER_ROWS):
                        y = bottom - r
                        if r < height_units:
                            stdscr.addstr(y, x, "█", level_color(db))
                        else:
                            stdscr.addstr(y, x, "·", curses.A_DIM)
                # scale markers
                for value, y in ((0, bottom), (-18, bottom - 2), (-6, bottom - 6)):
                    if 0 <= y <= bottom:
                        stdscr.addstr(y, 0, f"{value:>3}", curses.A_DIM)
                stdscr.addstr(bottom + 1, 2, f"peak {meter.peak_db:6.1f} dB   "
                              f"rms {meter.rms_db:6.1f} dB", curses.A_DIM)
                if not meter_on:
                    stdscr.addstr(bottom + 2, 2, "medidor apagado", curses.A_DIM)

            help_row = height - 2
            keys = "i iniciar   d detener   r reconectar   a arreglar ruta   m medidor   q salir"
            stdscr.addstr(help_row, 2, keys[: max(0, width - 3)], curses.A_DIM)
            if message:
                if time.monotonic() - message_at > 6:
                    message = ""
                else:
                    stdscr.addstr(height - 1, 2, message[: max(0, width - 3)],
                                  curses.color_pair(3) if has_colors else 0)

            stdscr.refresh()

            ch = stdscr.getch()
            if ch in (ord("q"), ord("Q")):
                meter.stop()
                return
            if ch in (ord("i"), ord("I")):
                ok, message = start_bridge()
                message_at = time.monotonic()
            elif ch in (ord("d"), ord("D")):
                ok, message = stop_bridge()
                message_at = time.monotonic()
            elif ch in (ord("r"), ord("R")):
                ok, message = reconnect_phone()
                message_at = time.monotonic()
            elif ch in (ord("a"), ord("A")):
                ok, message = fix_routing()
                message_at = time.monotonic()
            elif ch in (ord("m"), ord("M")):
                meter_on = not meter_on
                if meter_on:
                    meter = LevelMeter()
                    meter.start()
                else:
                    meter.stop()

    try:
        curses.wrapper(draw)
    except KeyboardInterrupt:
        return 0
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="phone-mic",
        description="phone-mic terminal panel and control",
        epilog="keys: i start   d stop   r reconnect adb   a fix routing   m meter   q quit")
    parser.add_argument("command", nargs="?", default="tui",
                        choices=["tui", "status", "start", "stop", "reconnect"],
                        help="default: tui")
    parser.add_argument("--once", action="store_true",
                        help="print one status snapshot and exit (same as 'status')")
    args = parser.parse_args()

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
