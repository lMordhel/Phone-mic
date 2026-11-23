#!/usr/bin/env bash
# Route the phone microphone into the "Phone-Mic" virtual device using scrcpy.
#
# scrcpy >= 3.2 can capture the phone microphone (--audio-source=mic, Android 11+)
# and plays it as a normal playback stream on the PC. The stream is routed into
# phonemic_sink, which the remap source exposes as "Phone-Mic".
#
# scrcpy uses SDL for audio output and ignores PULSE_SINK, so its stream is
# created on the default sink and then moved to phonemic_sink once it exists.
# The move is verified before the script reports success.
#
# Requirements: scrcpy >= 3.2, adb, wireless debugging paired or a USB device,
# and the virtual device loaded (scripts/load-virtual-mic.sh).
set -eu

SINK=phonemic_sink
SOURCE=phone_mic
WAIT_S=60

die() { echo "scrcpy-mic: $*" >&2; exit 1; }

command -v scrcpy >/dev/null || die "scrcpy is not installed (sudo pacman -S --needed extra/scrcpy)"
command -v adb >/dev/null || die "adb is not installed (sudo pacman -S --needed extra/android-tools)"

pactl list short sinks | grep -qw "$SINK" ||
    die "sink $SINK is missing: run scripts/load-virtual-mic.sh first"
pactl list short sources | grep -qw "$SOURCE" ||
    die "source $SOURCE is missing: run scripts/load-virtual-mic.sh first"

adb devices | awk 'NR>1 && $2=="device" {found=1} END {exit !found}' ||
    die "no authorized device: pair wireless debugging (adb pair) or connect USB and accept the prompt"

echo "scrcpy-mic: starting microphone forwarding into $SINK (Ctrl+C to stop)"
scrcpy --no-video --audio-source=mic --audio-codec=opus "$@" &
SCRCPY_PID=$!

cleanup() {
    kill "$SCRCPY_PID" 2>/dev/null || true
    wait "$SCRCPY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Confirm the stream really landed on the virtual sink. The verbose listing is
# used because `pactl list short sink-inputs` carries no application name.
for _ in $(seq 1 $((WAIT_S * 2))); do
    kill -0 "$SCRCPY_PID" 2>/dev/null || die "scrcpy exited before capturing audio (see its output above)"

    idx=$(pactl list sink-inputs 2>/dev/null | awk '
        /^Sink Input #[0-9]+/ { id = $3; gsub(/[^0-9]/, "", id) }
        /application\.name = "scrcpy"/ { if (id != "") { print id; exit } }')

    if [ -n "$idx" ]; then
        want=$(pactl list short sinks | awk -v s="$SINK" '$2==s {print $1; exit}')
        sink=$(pactl list sink-inputs 2>/dev/null |
               awk -v want="$idx" '/^Sink Input #[0-9]+/ { id = $3; gsub(/[^0-9]/, "", id) }
                    id == want && /^\tSink: / { print $2; exit }')
        if [ "$sink" != "$want" ]; then
            pactl move-sink-input "$idx" "$SINK" 2>/dev/null || true
            sleep 0.3
            sink=$(pactl list sink-inputs 2>/dev/null |
                   awk -v want="$idx" '/^Sink Input #[0-9]+/ { id = $3; gsub(/[^0-9]/, "", id) }
                        id == want && /^\tSink: / { print $2; exit }')
        fi
        if [ "$sink" = "$want" ]; then
            echo "scrcpy-mic: phone microphone active on $SOURCE (sink-input $idx)"
            echo "scrcpy-mic: select 'Phone-Mic' as the input in Discord, OBS or the browser"
            echo "scrcpy-mic: keep this terminal open; Ctrl+C stops forwarding"
            wait "$SCRCPY_PID"
            exit 0
        fi
        echo "scrcpy-mic: stream $idx appeared on sink $sink, expected $SINK" >&2
        exit 1
    fi
    sleep 0.5
done

die "scrcpy never created an audio stream: check --audio-source=mic support (Android 11+) and that the phone screen is unlocked"
