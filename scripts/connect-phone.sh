#!/usr/bin/env bash
# Connect adb to the phone, reusing everything that can be reused.
#
# After a PC reboot only the adb connection is lost: wireless debugging on the
# phone keeps its port until the phone reboots or the setting is toggled, so the
# last port that worked is tried first. If that fails, the advertised service is
# looked up over mDNS (adb's own discovery, then avahi). Only when all of that
# fails does the user have to read the port from the phone.
set -eu

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/phone-mic"
PORT_FILE="$STATE_DIR/last-port"
IP_FILE="$STATE_DIR/last-ip"
DEFAULT_IP=192.168.100.57

mkdir -p "$STATE_DIR"

device_online() {
    adb devices 2>/dev/null | awk 'NR>1 && $2=="device" {found=1} END {exit !found}'
}

if device_online; then
    adb devices | awk 'NR>1 && $2=="device" {print "phone-mic: already connected (" $1 ")"}'
    exit 0
fi

ip=$DEFAULT_IP
[ -r "$IP_FILE" ] && ip=$(cat "$IP_FILE")
port=""
[ -r "$PORT_FILE" ] && port=$(cat "$PORT_FILE")

try() {
    local target="$1"
    local host="${target%:*}" p="${target##*:}"
    [ -z "$p" ] && return 1
    if adb connect "$target" 2>&1 | grep -qE "connected to|already connected"; then
        if device_online; then
            printf '%s\n' "$host" > "$IP_FILE"
            printf '%s\n' "$p" > "$PORT_FILE"
            echo "phone-mic: connected to $target"
            return 0
        fi
    fi
    adb disconnect "$target" >/dev/null 2>&1 || true
    return 1
}

# 1. last port that worked
if [ -n "$port" ]; then
    try "$ip:$port" && exit 0
fi

# 2. the service the phone advertises (mDNS)
discovered=$(timeout 6 adb mdns services 2>/dev/null |
             awk '/_adb-tls-connect\._tcp/ {print $3; exit}')
if [ -z "$discovered" ]; then
    discovered=$(timeout 6 avahi-browse -prt _adb-tls-connect._tcp 2>/dev/null |
                 awk -F';' '/^=/{print $8":"$9; exit}')
fi
if [ -n "$discovered" ]; then
    try "$discovered" && exit 0
fi

# 3. the port the user read from the phone, passed as an argument
if [ $# -ge 1 ]; then
    try "$ip:$1" && exit 0
fi

cat >&2 <<EOF
phone-mic: cannot connect to the phone.

On the phone: Settings > Developer options > Wireless debugging
  - make sure it is enabled and the phone is on the same Wi-Fi
  - the port is shown as "IP address & Port"
Then run again with it:
  $(basename "$0") PORT
EOF
exit 1
