#!/usr/bin/env bash
# Per-user install of phone-mic: the virtual microphone, the bridge service and
# the `phone-mic` terminal command. No root required, nothing outside $HOME.
#
# The install is self-contained: the TUI, the scripts, the configuration and the
# README are copied into the install prefix, and the generated command and unit
# run from that prefix. Moving or deleting the checkout does not break them.
#
# What it does NOT do: it never restarts PipeWire (that drops Bluetooth audio
# links and in-flight screencasts). The null sink comes from the copied
# configuration file at the next PipeWire start; the remap source is created for
# the running session by scripts/load-virtual-mic.sh, and again on every bridge
# start by the unit's ExecStartPre.
set -eu

HERE="$(cd "$(dirname "$0")/.." && pwd)"
VERSION_FILE="$HERE/VERSION"

BIN_DIR="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PIPEWIRE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/pipewire/pipewire.conf.d"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/phone-mic"

PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/phone-mic"
WRAPPER="$BIN_DIR/phone-mic"
UNIT="$UNIT_DIR/phone-mic-bridge.service"
FRAGMENT="$PIPEWIRE_DIR/60-phone-mic.conf"

usage() {
    cat <<EOF
usage: install.sh [--uninstall] [--prefix DIR]

Install the phone microphone for the current user: the PipeWire sink fragment,
the bridge systemd user service, and a self-contained copy of the panel, the
scripts, the configuration and the README. No root required.

  --uninstall     remove exactly what this installer created
  --prefix DIR    install into DIR instead of $PREFIX
  --version       print the version of this install
  --help          print this help

Install prefix  $PREFIX
Command         $WRAPPER
Service         $UNIT
Fragment        $FRAGMENT

The bridge service is installed but never enabled at login: while it runs it
captures the phone microphone the whole time. Start it with 'phone-mic start'
(or 'i' in the panel).
EOF
}

die() { echo "install.sh: $*" >&2; exit 2; }

print_version() {
    if [ -r "$VERSION_FILE" ]; then
        cat "$VERSION_FILE"
    else
        echo "unknown"
    fi
}

action=install
while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --version|-V) print_version; exit 0 ;;
        --uninstall) action=uninstall ;;
        --prefix) [ "$#" -ge 2 ] || die "--prefix needs a directory"; PREFIX="$2"; shift ;;
        --prefix=*) PREFIX="${1#*=}" ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
    shift
done

# --uninstall deletes the prefix recursively: never aim it at a directory that is
# not ours.
case "$PREFIX" in
    ''|/|"$HOME"|"$HOME"/) die "refusing to use '$PREFIX' as the install prefix" ;;
esac

# -- preflight ---------------------------------------------------------------
# Environment problems are reported with the command that fixes them, and never
# abort the install: the tree this installer writes is valid either way, and the
# user must be told what will not work and why. See S7.
problems=0
audio_ok=0

preflight() {
    problems=0
    audio_ok=0

    if command -v adb >/dev/null 2>&1; then
        :
    else
        problems=$((problems + 1))
        cat >&2 <<'EOF'
warning: adb is missing, so the bridge cannot reach the phone and no audio can
         be captured. Fix:
           sudo pacman -S --needed android-tools
EOF
    fi

    if ! command -v scrcpy >/dev/null 2>&1; then
        problems=$((problems + 1))
        cat >&2 <<'EOF'
warning: scrcpy is missing, so the phone microphone cannot be captured. Fix:
           sudo pacman -S --needed scrcpy
EOF
    else
        # scrcpy gained the phone microphone in 3.2 (--audio-source=mic). An older
        # release looks installed and silently captures no microphone at all.
        scrcpy_version="$(scrcpy --version 2>&1 |
            awk '{ for (i = 1; i <= NF; i++) if ($i ~ /^[0-9]+\.[0-9]/) { print $i; exit } }')"
        if ! awk -v v="$scrcpy_version" 'BEGIN {
                if (v == "") exit 1
                split(v, p, ".")
                exit !(p[1] > 3 || (p[1] == 3 && p[2] >= 2))
            }'; then
            problems=$((problems + 1))
            cat >&2 <<EOF
warning: scrcpy ${scrcpy_version:-of unknown version} cannot capture the phone
         microphone: --audio-source=mic needs scrcpy >= 3.2. Check with
         'scrcpy --version' and upgrade:
           sudo pacman -S --needed scrcpy
EOF
        fi
    fi

    if ! pactl info >/dev/null 2>&1; then
        problems=$((problems + 1))
        if command -v pactl >/dev/null 2>&1; then
            cat >&2 <<'EOF'
warning: the audio server does not answer, so no microphone can be created.
         'pactl info' fails: PipeWire's PulseAudio front end is not running. Fix:
           systemctl --user start pipewire-pulse
         If audio is dead everywhere, a fragment is asking PipeWire for a module
         this system does not ship. Recover with:
           systemctl --user reset-failed pipewire pipewire.socket pipewire-pulse wireplumber
           systemctl --user start pipewire pipewire-pulse wireplumber
EOF
        else
            cat >&2 <<'EOF'
warning: pactl is missing, so no microphone can be created. It ships with
         PipeWire's PulseAudio front end. Fix:
           sudo pacman -S --needed pipewire-pulse
EOF
        fi
    else
        audio_ok=1
    fi
}

# -- install -----------------------------------------------------------------
install_tree() { # $1 = source directory, $2 = destination inside the prefix
    # Replace instead of merging: a stale file from an older install must not
    # survive, and a second run must not duplicate anything.
    rm -rf -- "$2"
    mkdir -p -- "$2"
    cp -R -- "$1/." "$2/"
    # Never ship a byte-code cache: the copied sources are authoritative.
    rm -rf -- "$2/__pycache__"
}

summary() {
    if [ "$problems" -gt 0 ]; then
        cat >&2 <<EOF

warning: $problems environment problem(s) reported above. The install itself is
         complete, but the parts they name will not work until they are fixed.
EOF
    fi
    cat <<EOF

Installed phone-mic $(print_version).

  prefix         $PREFIX
  panel          phone-mic              (keys: i start, d stop, r reconnect, q quit)
  status         phone-mic status
  start / stop   phone-mic start | stop
  service log    journalctl --user -u phone-mic-bridge -f
  fragment       $FRAGMENT   (read by PipeWire at its next start)

Phone side: enable wireless debugging and pair once (adb pair IP:PORT).
No app is installed on the phone.

Remove everything this installer created:
  "$HERE/packaging/install.sh" --uninstall
EOF
}

do_install() {
    echo "== install the phone-mic files into $PREFIX"
    mkdir -p -- "$PREFIX"
    # Marker: --uninstall deletes the prefix recursively, so it must be able to
    # prove the directory is ours and not a path the user mistyped.
    printf 'phone-mic install marker\n' > "$PREFIX/.phone-mic-install"
    install_tree "$HERE/tui" "$PREFIX/tui"
    install_tree "$HERE/scripts" "$PREFIX/scripts"
    install_tree "$HERE/conf" "$PREFIX/conf"
    install -m 0644 -- "$HERE/README.md" "$PREFIX/README.md"
    # The unit and the panel execute these directly, so they must stay executable
    # wherever the prefix happens to live.
    for script in "$PREFIX/scripts/"*.sh; do
        chmod 0755 -- "$script"
    done
    chmod 0755 -- "$PREFIX/tui/phone_mic_tui.py"

    echo "== install the virtual microphone configuration"
    # PipeWire only reads fragments from its own conf.d directory, so this is the
    # one file that cannot live in the prefix.
    mkdir -p -- "$PIPEWIRE_DIR"
    install -m 0644 -- "$HERE/conf/60-phone-mic.conf" "$FRAGMENT"

    echo "== install the phone-mic command"
    mkdir -p -- "$BIN_DIR"
    cat > "$WRAPPER" <<WRAPPER
#!/usr/bin/env bash
# phone-mic: terminal panel and control for the phone microphone.
# Generated by phone-mic/packaging/install.sh. Everything it runs lives in the
# install prefix below, so moving or deleting the checkout leaves it working.
exec "$PREFIX/tui/phone_mic_tui.py" "\$@"
WRAPPER
    chmod 0755 -- "$WRAPPER"

    echo "== install the bridge service"
    # Substitute with bash expansion, not sed: a prefix containing '|' is literal
    # here. But '&' means "the matched text" in the replacement of both sed and
    # ${var//pattern/replacement}, so escape it (and the backslash) first, or a
    # prefix containing '&' silently writes a corrupt unit path.
    mkdir -p -- "$UNIT_DIR"
    escaped_prefix=${PREFIX//\\/\\\\}
    escaped_prefix=${escaped_prefix//&/\\&}
    unit_template="$(cat "$HERE/packaging/phone-mic-bridge.service")"
    printf '%s\n' "${unit_template//@PHONE_MIC_PREFIX@/$escaped_prefix}" > "$UNIT"
    chmod 0644 -- "$UNIT"
    systemctl --user daemon-reload
    # Deliberately not enabled: while it runs it captures the phone microphone the
    # whole time. Start it with 'phone-mic start' (or 'i' in the panel).

    if [ "$audio_ok" -eq 1 ]; then
        echo "== load the virtual device for this session"
        if ! "$PREFIX/scripts/load-virtual-mic.sh"; then
            echo "warning: the virtual device could not be loaded now; the bridge service retries it on every start" >&2
        fi
    else
        echo "== skip the virtual device: the audio server is not answering"
        echo "   the sink is created at the next PipeWire start, the bridge service"
        echo "   creates the source on every start"
    fi

    summary
}

# -- uninstall ---------------------------------------------------------------
do_uninstall() {
    echo "== remove phone-mic"
    # Prove the prefix is ours before deleting anything: this removes the prefix
    # recursively, and a mistyped --prefix must not take an unrelated directory
    # with it.
    if [ -d "$PREFIX" ] && [ ! -f "$PREFIX/.phone-mic-install" ]; then
        die "refusing to uninstall: '$PREFIX' is not a phone-mic install (no marker)"
    fi
    if command -v systemctl >/dev/null 2>&1; then
        # Stop it before its files vanish: it runs from the prefix with
        # Restart=always, so otherwise it would restart forever against files
        # that no longer exist. Stopping is not restarting PipeWire.
        if systemctl --user stop phone-mic-bridge 2>/dev/null; then
            echo "stopped phone-mic-bridge"
        fi
    fi

    removed=0
    for file in "$WRAPPER" "$UNIT" "$FRAGMENT"; do
        if [ -e "$file" ]; then
            rm -f -- "$file"
            echo "removed $file"
            removed=$((removed + 1))
        fi
    done
    if [ -d "$PREFIX" ]; then
        rm -rf -- "$PREFIX"
        echo "removed $PREFIX"
        removed=$((removed + 1))
    fi
    if [ "$removed" -eq 0 ]; then
        echo "nothing to remove: phone-mic is not installed here"
    fi
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user daemon-reload ||
            echo "warning: systemctl --user daemon-reload failed" >&2
    fi

    if [ -d "$STATE_DIR" ]; then
        state_note="  - $STATE_DIR holds the last adb port and address, written at
    runtime. Remove it by hand if you do not want it."
    else
        state_note="  - no runtime state was left in $STATE_DIR."
    fi

    cat <<EOF

Removed: the command, the prefix, the unit and the PipeWire fragment.

Runtime leftovers, deliberately not cleared here:
  - the live phonemic_sink and phone_mic nodes are still loaded in the running
    PipeWire. The sink disappears at the next PipeWire start, and so does the
    source until a bridge runs again. Nothing here restarts or stops PipeWire,
    wireplumber or pipewire-pulse: that drops Bluetooth audio links and
    in-flight screencasts.
$state_note
  - the bridge unit is not enabled at login, so nothing starts it again.
EOF
}

case "$action" in
    uninstall) do_uninstall ;;
    install)
        echo "== phone-mic $(print_version)"
        preflight
        do_install
        ;;
esac
