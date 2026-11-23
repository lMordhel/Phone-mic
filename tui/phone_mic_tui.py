#!/usr/bin/env python3
"""Terminal panel for phone-mic.

Shows whether the phone is connected, whether the bridge is forwarding and how
much audio is arriving, and lets the user start or stop it without remembering
the scripts. It owns no audio pipeline: starting the bridge spawns the same
scripts a terminal would run, and stopping it kills the scrcpy child, which
makes the wrapper exit on its own.

Usage:
    phone-mic-tui            interactive panel
    phone-mic-tui --once     print one snapshot and exit (scriptable, no curses)
"""

from __future__ import annotations

import argparse
import array
import math
import os
import shutil
import subprocess
import sys
import threading
import time

# realpath, not abspath: the command is installed as a symlink in ~/.local/bin
REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SINK = "phonemic_sink"
SOURCE = "phone_mic"
BRIDGE_UNIT = "phone-mic-bridge"


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


def bridge_unit_active() -> bool:
    return run(["systemctl", "--user", "is-active", BRIDGE_UNIT]).strip() == "active"


def bridge_unit_state() -> str:
    """active (running) | activating (retrying) | inactive | failed"""
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
    current_pid_sink = ""
    idx = ""
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("Sink Input #"):
            idx = stripped.split("#", 1)[1]
        elif stripped.startswith("Sink:") and idx:
            current_pid_sink = stripped.split(":", 1)[1].strip()
        elif 'application.name = "scrcpy"' in stripped:
            return current_pid_sink
    return ""


class LevelMeter(threading.Thread):
    """Reads a low-rate copy of the virtual microphone and keeps peak/RMS in dBFS.

    A second capture client is harmless for PipeWire and costs a few kB/s; it is
    started on demand so the panel does not record while nobody is looking.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop = threading.Event()
        self._proc: subprocess.Popen[bytes] | None = None
        self.peak_db = -120.0
        self.rms_db = -120.0
        self.running = False

    def run(self) -> None:
        if not shutil.which("parec"):
            return
        try:
            self._proc = subprocess.Popen(
                ["parec", "--device=" + SOURCE, "--format=s16le",
                 "--rate=8000", "--channels=1", "--raw"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        self.running = True
        while not self._stop.is_set():
            chunk = self._proc.stdout.read(1600) if self._proc.stdout else b""
            if not chunk:
                break
            samples = array.array("h")
            samples.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
            if not samples:
                continue
            peak = max(abs(s) for s in samples) / 32768.0
            rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0
            self.peak_db = 20 * math.log10(peak) if peak > 0 else -120.0
            self.rms_db = 20 * math.log10(rms) if rms > 0 else -120.0
        self.running = False

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def decay(self, amount: float = 2.0) -> None:
        self.peak_db = max(-120.0, self.peak_db - amount)


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


# ----------------------------------------------------------------------- rendering

def snapshot(level: LevelMeter | None) -> list[tuple[str, str]]:
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
        rows.append(("audio", f"peak {level.peak_db:.1f} dB   rms {level.rms_db:.1f} dB"
                     if level.running else "meter unavailable"))
    return rows


def bar(peak_db: float, width: int = 28) -> str:
    fraction = 0.0 if peak_db <= -60 else (peak_db + 60) / 60
    filled = int(max(0.0, min(1.0, fraction)) * width)
    return "#" * filled + "-" * (width - filled)


def once() -> int:
    meter = LevelMeter()
    meter.start()
    time.sleep(1.2)
    rows = snapshot(meter)
    meter.stop()
    width = max(len(k) for k, _ in rows) + 2
    print("phone-mic status")
    for key, value in rows:
        print(f"  {key:<{width}} {value}")
    print(f"  {'level':<{width}} [{bar(meter.peak_db)}] peak {meter.peak_db:.1f} dB")
    return 0


def interactive() -> int:
    import curses

    def draw(stdscr) -> None:
        curses.curs_set(0)
        stdscr.timeout(250)
        has_colors = curses.has_colors()
        if has_colors:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)

        def color_for(value: str) -> int:
            if not has_colors:
                return 0
            low = value.lower()
            if low.startswith(("running", "ok", "forwarding", "already")) or "forwarding" in low:
                return curses.color_pair(1)
            if low.startswith(("stopped", "not connected", "missing", "no bridge", "meter unavailable")) \
                    or "wrong" in low:
                return curses.color_pair(2)
            return curses.color_pair(3)

        meter = LevelMeter()
        meter.start()
        message = ""
        message_at = 0.0
        meter_on = True

        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            stdscr.addstr(0, 0, "phone-mic", curses.A_BOLD)
            stdscr.addstr(0, 10, "panel del microfono del telefono", curses.A_DIM)

            rows = snapshot(meter)
            label_width = max(len(k) for k, _ in rows) + 2
            for i, (key, value) in enumerate(rows, start=2):
                if i >= height - 8:
                    break
                stdscr.addstr(i, 2, f"{key:<{label_width}}")
                stdscr.addstr(i, 2 + label_width, value[: max(0, width - label_width - 3)],
                              color_for(value))

            level_row = len(rows) + 3
            stdscr.addstr(level_row, 2, "nivel  ")
            stdscr.addstr(level_row, 9, f"[{bar(meter.peak_db, max(10, min(40, width - 22)))}]")
            stdscr.addstr(level_row, 11 + max(10, min(40, width - 22)),
                          f"{meter.peak_db:6.1f} dB")
            if not meter_on:
                stdscr.addstr(level_row + 1, 2, "medidor apagado", curses.A_DIM)

            help_row = height - 3
            keys = "i iniciar   d detener   r reconectar   a arreglar ruta   m medidor   q salir"
            stdscr.addstr(help_row, 2, keys[: max(0, width - 3)], curses.A_DIM)
            if message:
                if time.monotonic() - message_at > 6:
                    message = ""
                else:
                    stdscr.addstr(help_row + 1, 2, message[: max(0, width - 3)],
                                  curses.color_pair(3) if has_colors else 0)

            stdscr.refresh()
            meter.decay(3.0)

            ch = stdscr.getch()
            if ch in (ord("q"), ord("Q")):
                meter.stop()
                return 0
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
