#!/usr/bin/env bash
# Static packaging regressions for the PipeWire remap-source fix.
#
# The bug this pins: a module declared in `context.modules` of a pipewire.conf.d
# fragment is mandatory. pipewire 1.6 stopped shipping
# libpipewire-module-remap-source, so that declaration aborted the whole daemon
# and left the machine with no audio server. These checks are static on purpose:
# no root, no systemd, no pactl mutation, no network.
#
# Run: packaging/tests/packaging-static.sh
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)" || { echo "cannot create a temporary directory" >&2; exit 1; }
trap 'rm -rf "$T"' EXIT
fail=0
ck() { if "${@:2}"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }

r1() { # R1: no module declared in context.modules anywhere
    ! grep -vE '^[[:space:]]*#' "$ROOT/conf/60-phone-mic.conf" | grep -q 'context\.modules' &&
    ! grep -rqE 'name[[:space:]]*=[[:space:]]*libpipewire-module-remap-source' \
        --exclude-dir=.git "$ROOT/conf" "$ROOT/scripts" "$ROOT/packaging"; }
ck "R1 no module declared in context.modules" r1

r2() { # R2: the sink is declared and the fragment is structurally valid
    python3 - "$ROOT/conf/60-phone-mic.conf" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
code = "\n".join(re.sub(r'#.*', '', l) for l in s.splitlines())
assert code.count('[') == code.count(']') and code.count('{') == code.count('}'), 'unbalanced'
d = 0
for l in code.splitlines():
    if d == 0 and l.strip():
        assert l.strip().startswith('context.objects'), l
    d += l.count('[') + l.count('{') - l.count(']') - l.count('}')
assert d == 0
for w in ('node.name        = "phonemic_sink"', 'media.class      = "Audio/Sink"',
          'object.linger    = true', 'support.null-audio-sink'):
    assert w in s, w
PY
}
ck "R2 sink fragment is valid SPA-JSON" r2

r2b() { # R2b: pipewire itself accepts the fragment (skipped without pipewire)
    command -v pw-config >/dev/null || return 0
    mkdir -p "$T/h/.config/pipewire/pipewire.conf.d"
    cp "$ROOT/conf/60-phone-mic.conf" "$T/h/.config/pipewire/pipewire.conf.d/"
    env -i PATH=/usr/bin:/bin HOME="$T/h" TMPDIR="$T/h" \
        pw-config -N merge context.objects | grep -q phonemic_sink; }
ck "R2b pipewire parses the fragment" r2b

r3() { # R3: the unit loads the source before starting and keeps its directives
    local u="$ROOT/packaging/phone-mic-bridge.service"
    grep -qx 'ExecStartPre=%h/Proyectos/phone-mic/scripts/load-virtual-mic.sh' "$u" &&
    grep -qx 'After=pipewire.service wireplumber.service pipewire-pulse.service' "$u" &&
    grep -qx 'Wants=pipewire.service pipewire-pulse.service' "$u" &&
    grep -qx 'StartLimitIntervalSec=0' "$u" &&
    grep -qx 'Restart=always' "$u" && grep -qx 'Nice=-5' "$u" &&
    grep -qx 'WantedBy=default.target' "$u" && test -x "$ROOT/scripts/load-virtual-mic.sh"; }
ck "R3 unit runs the source script and keeps its directives" r3

r4() { # R4: never enabled at login, health check guarded and never fatal
    local i="$ROOT/packaging/install.sh"
    ! grep -qE 'systemctl --user enable|systemctl enable' "$i" &&
    grep -q 'if ! pactl info' "$i" && ! grep -qE '^[[:space:]]*pactl info' "$i"; }
ck "R4 installer does not enable and guards the health check" r4

r4b() { # R4b: a dead audio server warns but does not abort the install
    command -v pactl >/dev/null || return 0
    mkdir -p "$T/b" "$T/home"
    printf '#!/bin/sh\nexit 0\n' > "$T/b/systemctl"
    cat > "$T/b/pactl" <<'SH'
#!/bin/sh
case "$1 $2" in
  "info "*) exit 1 ;;
  "list short") case "$3" in sinks) echo "0 phonemic_sink";; sources) echo "0 phone_mic";; esac ;;
esac
exit 0
SH
    printf '#!/bin/sh\nexit 0\n' > "$T/b/scrcpy"
    cp "$T/b/scrcpy" "$T/b/adb"
    chmod +x "$T/b/"*
    env -i PATH="$T/b:/usr/bin:/bin" HOME="$T/home" TMPDIR="$T" \
        bash "$ROOT/packaging/install.sh" >/dev/null 2>"$T/err" &&
    grep -q 'the audio server does not answer' "$T/err"; }
ck "R4b dead audio server: install still succeeds with a warning" r4b

r5() { # R5: persistent vs runtime documented, stale claim gone
    local r="$ROOT/README.md"
    grep -q '| `phonemic_sink` (the sink) | yes, PipeWire reads `60-phone-mic.conf` |' "$r" &&
    grep -q '| `phone_mic` (the source) | no, the bridge service creates it on start |' "$r" &&
    ! grep -qiE 'virtual device.*PipeWire configuration' "$r"; }
ck "R5 README separates persistent from runtime" r5

exit "$fail"
