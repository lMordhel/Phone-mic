#!/usr/bin/env bash
# Per-user install of phone-mic: build, place the receiver in ~/.local/bin, and
# register the systemd user service. No root required.
#
# What it does NOT do: it never restarts PipeWire (that drops Bluetooth audio
# links and in-flight screencasts). The virtual device is loaded for the running
# session through scripts/load-virtual-mic.sh and at the next PipeWire start by
# the copied configuration file.
set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PIPEWIRE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/pipewire/pipewire.conf.d"
DOC_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/phone-mic"

command -v pactl >/dev/null || { echo "pactl not found: install pipewire-pulse" >&2; exit 1; }

echo "== build"
make -C "$HERE"

echo "== install receiver"
mkdir -p "$BIN_DIR" "$UNIT_DIR" "$PIPEWIRE_DIR" "$DOC_DIR"
install -m 0755 "$HERE/phone-micd" "$BIN_DIR/phone-micd"

echo "== install virtual microphone configuration"
install -m 0644 "$HERE/conf/60-phone-mic.conf" "$PIPEWIRE_DIR/60-phone-mic.conf"

echo "== install documentation"
install -m 0644 "$HERE/README.md" "$HERE/PROTOCOL.md" "$DOC_DIR/"

echo "== register service"
sed "s|%h|$HOME|g" "$HERE/packaging/phone-micd.service" > "$UNIT_DIR/phone-micd.service"
systemctl --user daemon-reload
systemctl --user enable phone-micd.service

echo "== load the virtual device for this session"
"$HERE/scripts/load-virtual-mic.sh"

cat <<EOF

Installed.

  start now      systemctl --user start phone-micd
  follow         journalctl --user -u phone-micd -f
  status         systemctl --user status phone-micd
  uninstall      rm ~/.local/bin/phone-micd ~/.config/systemd/user/phone-micd.service \\
                    ~/.config/pipewire/pipewire.conf.d/60-phone-mic.conf
                 systemctl --user disable --now phone-micd

Open the firewall for the phone: sudo ufw allow 47718/udp
EOF
