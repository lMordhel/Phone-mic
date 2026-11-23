#!/usr/bin/env bash
# Menu entry for phone-mic: start the bridge service and report, without owning
# the audio. The window this runs in closes immediately; the bridge keeps running
# because it belongs to systemd, not to the window.
set -eu

UNIT=phone-mic-bridge

notify() {
    if command -v notify-send >/dev/null; then
        notify-send -a phone-mic "phone-mic" "$1" 2>/dev/null || true
    fi
    echo "phone-mic: $1"
}

if ! systemctl --user is-active --quiet "$UNIT"; then
    systemctl --user start "$UNIT" || true
fi

sleep 2
if systemctl --user is-active --quiet "$UNIT"; then
    peer=$(adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {print $1; exit}')
    if [ -n "$peer" ]; then
        notify "micrófono activo (${peer}). Elegí Phone-Mic en Discord/OBS."
    else
        notify "puente iniciado, pero el teléfono no responde: abrí Depuración inalámbrica"
    fi
else
    notify "no pudo iniciarse. Revisá: phone-mic status"
fi
