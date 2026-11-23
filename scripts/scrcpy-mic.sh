#!/usr/bin/env bash
# Route the phone microphone into the "Phone-Mic" virtual device using scrcpy.
#
# scrcpy >= 3.2 can capture the phone microphone (--audio-source=mic, Android 11+)
# and plays it as a normal playback stream on the PC. This wrapper moves that
# stream into the phonemic_sink that phone-mic's remap source listens to, so any
# application sees the phone as "Phone-Mic".
#
# Requirements: scrcpy >= 3.2, adb, USB debugging enabled on the phone (or adb
# over Wi-Fi already paired), and the virtual device loaded
# (scripts/load-virtual-mic.sh).
set -eu

SINK=phonemic_sink
SOURCE=phone_mic
WAIT_S=15

die() { echo "scrcpy-mic: $*" >&2; exit 1; }

command -v scrcpy >/dev/null || die "scrcpy is not installed (sudo pacman -S --needed extra/scrcpy)"
command -v adb >/dev/null || die "adb is not installed (sudo pacman -S --needed extra/android-tools)"

pactl list short sinks | grep -qw "$SINK" ||
    die "sink $SINK is missing: run scripts/load-virtual-mic.sh first"
pactl list short sources | grep -qw "$SOURCE" ||
    die "source $SOURCE is missing: run scripts/load-virtual-mic.sh first"

adb devices | awk 'NR>1 && $2=="device" {found=1} END {exit !found}' ||
    die "no authorized device: enable USB debugging, connect the phone and accept the RSA prompt"

echo "scrcpy-mic: starting microphone forwarding (Ctrl+C to stop)"
scrcpy --no-video --audio-source=mic --audio-codec=opus "$@" &
SCRCPY_PID=$!

cleanup() {
    kill "$SCRCPY_PID" 2>/dev/null || true
    wait "$SCRCPY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Wait for scrcpy's playback stream and move it into the virtual sink.
moved=""
for _ in $(seq 1 $((WAIT_S * 5))); do
    idx=$(pactl list short sink-inputs 2>/dev/null |
          awk '/scrcpy/ {print $1; exit}')
    if [ -z "$idx" ]; then
        idx=$(pactl list sink-inputs 2>/dev/null |
              awk '/application.name = "scrcpy"/{found=1} found && /Sink Input #/{gsub(/[^0-9]/,"",$3); print $3; exit}')
    fi
    if [ -n "$idx" ]; then
        pactl move-sink-input "$idx" "$SINK" && moved=$idx && break
    fi
    sleep 0.2
done

if [ -z "$moved" ]; then
    die "scrcpy started but its audio stream never appeared; check 'pactl list short sink-inputs'"
fi

echo "scrcpy-mic: phone microphone routed into $SOURCE (sink-input $moved)"
echo "scrcpy-mic: pick 'Phone-Mic' as the input in Discord, OBS or the browser"
echo "scrcpy-mic: keep this terminal open; Ctrl+C stops forwarding"

wait "$SCRCPY_PID"
