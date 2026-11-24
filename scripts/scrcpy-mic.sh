#!/usr/bin/env bash
# Route the phone microphone into the "Phone-Mic" virtual device using scrcpy.
#
# scrcpy >= 3.2 can capture the phone microphone (--audio-source=mic, Android 11+)
# and plays it as a normal playback stream on the PC. That stream has to end up on
# phonemic_sink, which the remap source exposes as "Phone-Mic".
#
# scrcpy plays through SDL, so it ignores PULSE_SINK and always creates its stream
# on the default sink; the stream must be moved. It also recreates the stream when
# the phone reconnects or the capture restarts, and the new stream is born on the
# default sink again. Hence the watchdog: every second, any scrcpy stream that is
# not on the virtual sink is moved back, so the microphone keeps working across
# reconnections without user action.
#
# Requirements: scrcpy >= 3.2, adb, wireless debugging paired or a USB device,
# and the virtual device loaded (scripts/load-virtual-mic.sh).
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
SINK=phonemic_sink
SOURCE=phone_mic
FIRST_WAIT_S=60
# scrcpy buffers 200 ms of audio by default, which is audible as delay in a
# conversation. 50 ms keeps the jitter cushion over Wi-Fi without that lag; the
# SDL output buffer (10 ms default) is trimmed as well. Override with
# AUDIO_BUFFER / AUDIO_OUTPUT_BUFFER when the network is worse than usual.
AUDIO_BUFFER="${AUDIO_BUFFER:-50}"
AUDIO_OUTPUT_BUFFER="${AUDIO_OUTPUT_BUFFER:-8}"

die() { echo "scrcpy-mic: $*" >&2; exit 1; }

command -v scrcpy >/dev/null || die "scrcpy is not installed (sudo pacman -S --needed extra/scrcpy)"
command -v adb >/dev/null || die "adb is not installed (sudo pacman -S --needed extra/android-tools)"

pactl list short sinks | grep -qw "$SINK" ||
    die "sink $SINK is missing: run scripts/load-virtual-mic.sh first"
pactl list short sources | grep -qw "$SOURCE" ||
    die "source $SOURCE is missing: run scripts/load-virtual-mic.sh first"

adb devices | awk 'NR>1 && $2=="device" {found=1} END {exit !found}' ||
    die "no authorized device: pair wireless debugging (adb pair) or connect USB and accept the prompt"

sink_id() { pactl list short sinks | awk -v s="$SINK" '$2==s {print $1; exit}'; }

# Everything the pipeline needs lives in memory: the sink comes from the PipeWire
# configuration, but the remap source is loaded at runtime and the stream is
# created by scrcpy. A PipeWire restart wipes both while this process keeps
# running, so the ids and the nodes must be re-checked, never trusted from
# startup. load-virtual-mic.sh is idempotent and recreates whatever is missing.
restore_device() {
    echo "scrcpy-mic: virtual device lost ($1); recreating it"
    "$HERE/load-virtual-mic.sh" >/dev/null 2>&1 || true
}

device_ok() {
    [ -n "$(sink_id)" ] && pactl list short sources 2>/dev/null | grep -qw "$SOURCE"
}

# Prints "index sink_index" for every playback stream owned by scrcpy. The verbose
# listing is used because `pactl list short sink-inputs` carries no application name.
scrcpy_streams() {
    pactl list sink-inputs 2>/dev/null | awk '
        /^Sink Input #[0-9]+/ { id = $3; gsub(/[^0-9]/, "", id); sink = "" }
        /^\tSink: [0-9]+/      { sink = $2 }
        /application\.name = "scrcpy"/ { if (id != "" && sink != "") print id, sink }'
}

echo "scrcpy-mic: starting microphone forwarding into $SINK (buffer ${AUDIO_BUFFER} ms, Ctrl+C to stop)"
# --no-window: with --no-video scrcpy still creates an empty 256x256 window that
# shows nothing and has no decorations. It is pure visual noise for an audio-only
# bridge, so no window is created at all.
scrcpy --no-video --no-window --audio-source=mic --audio-codec=opus \
       --audio-buffer="$AUDIO_BUFFER" --audio-output-buffer="$AUDIO_OUTPUT_BUFFER" "$@" &
SCRCPY_PID=$!

cleanup() {
    kill "$SCRCPY_PID" 2>/dev/null || true
    wait "$SCRCPY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

want=$(sink_id)
announced=""
waited=0
while kill -0 "$SCRCPY_PID" 2>/dev/null; do
    # The sink index changes when PipeWire restarts, and the runtime-loaded remap
    # source disappears with it, so neither value may be trusted from startup.
    if ! device_ok; then
        restore_device "sink or $SOURCE is gone"
        # The ids are new: the active stream must be announced again.
        announced=""
    fi
    want=$(sink_id)

    on_target=""
    while read -r idx sink; do
        [ -z "${idx:-}" ] && continue
        if [ "$sink" != "$want" ]; then
            pactl move-sink-input "$idx" "$SINK" 2>/dev/null || true
            sleep 0.2
            sink=$(pactl list sink-inputs 2>/dev/null |
                   awk -v want_idx="$idx" '/^Sink Input #[0-9]+/ { id = $3; gsub(/[^0-9]/, "", id) }
                        id == want_idx && /^\tSink: / { print $2; exit }')
        fi
        [ "$sink" = "$want" ] && on_target=$idx
    done <<EOF
$(scrcpy_streams)
EOF

    if [ -n "$on_target" ] && [ "$on_target" != "$announced" ]; then
        announced=$on_target
        echo "scrcpy-mic: phone microphone active on $SOURCE (stream $on_target)"
        echo "scrcpy-mic: select 'Phone-Mic' as the input in Discord, OBS or the browser"
        echo "scrcpy-mic: keep this terminal open; Ctrl+C stops forwarding"
    fi

    waited=$((waited + 1))
    if [ -z "$announced" ] && [ "$waited" -ge $((FIRST_WAIT_S * 2)) ]; then
        die "scrcpy never produced a routable audio stream: check --audio-source=mic support (Android 11+) and that the phone screen is unlocked"
    fi
    sleep 0.5
done
