#!/usr/bin/env bash
# Load the virtual microphone for the current session without restarting
# PipeWire (a restart drops Bluetooth audio links and in-flight screencasts).
#
# The persistent equivalent is conf/60-phone-mic.conf, which PipeWire reads on
# its next start. Both paths create the same two objects:
#   phonemic_sink  Audio/Sink      where the phone bridge plays its audio
#   phone_mic      Audio/Source    what applications capture from
set -eu

SINK=phonemic_sink
SOURCE=phone_mic

if pactl list short sinks 2>/dev/null | grep -qw "$SINK" &&
   pactl list short sources 2>/dev/null | grep -qw "$SOURCE"; then
    echo "virtual microphone already loaded ($SINK + $SOURCE)"
    exit 0
fi

if ! pactl list short sinks 2>/dev/null | grep -qw "$SINK"; then
    pactl load-module module-null-sink \
        sink_name="$SINK" \
        sink_properties=device.description=Phone-Mic-Sink >/dev/null
    echo "loaded null sink: $SINK"
fi

if ! pactl list short sources 2>/dev/null | grep -qw "$SOURCE"; then
    pactl load-module module-remap-source \
        master="$SINK.monitor" \
        source_name="$SOURCE" \
        source_properties=device.description=Phone-Mic >/dev/null
    echo "loaded remap source: $SOURCE (Phone-Mic)"
fi

pactl list short sources | grep -w "$SOURCE"
