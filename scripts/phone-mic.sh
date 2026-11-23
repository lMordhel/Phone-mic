#!/usr/bin/env bash
# One-click entry point: connect the phone, then start microphone forwarding.
# Intended for the desktop entry; it keeps running until the terminal is closed.
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

"$HERE/connect-phone.sh" "$@" || {
    echo
    read -r -p "Enter para cerrar..." _ || true
    exit 1
}

exec "$HERE/scrcpy-mic.sh"
