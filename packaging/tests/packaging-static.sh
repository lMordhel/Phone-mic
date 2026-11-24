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
# 0 = passed, 77 = skipped because a tool this check needs is absent, else failed.
# A skipped check must never print "ok": reporting an unexecuted check as a pass is
# how a suite quietly stops covering anything.
ck() {
    local name="$1"; shift
    local rc=0
    "$@" || rc=$?
    case "$rc" in
        0)  echo "ok   $name" ;;
        77) echo "skip $name (tool absent)" ;;
        *)  echo "FAIL $name"; fail=1 ;;
    esac
}

# A throwaway user environment: no root, no real systemd, no real audio server.
mkbin() { # $1 = directory, $2 = exit code of the fake `pactl info`
    mkdir -p "$1"
    printf '#!/bin/sh\nexit 0\n' > "$1/systemctl"
    printf '#!/bin/sh\nexit 0\n' > "$1/adb"
    printf '#!/bin/sh\necho "scrcpy 3.3.1 <https://github.com/Genymobile/scrcpy>"\n' > "$1/scrcpy"
    {
        printf '#!/bin/sh\ncase "$1 $2" in\n'
        printf '  "info "*) exit %s ;;\n' "$2"
        printf '  "list short") case "$3" in sinks) echo "0 phonemic_sink";; sources) echo "0 phone_mic";; esac ;;\n'
        printf 'esac\nexit 0\n'
    } > "$1/pactl"
    chmod +x "$1"/*
}

run_install() { # $1 = install.sh, $2 = HOME, $3 = fake bin, $4 = TMPDIR; rest = args
    _script=$1; _home=$2; _bin=$3; _tmp=$4
    shift 4
    env -i PATH="$_bin:/usr/bin:/bin" HOME="$_home" TMPDIR="$_tmp" bash "$_script" "$@"
}

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
    command -v pw-config >/dev/null || return 77
    mkdir -p "$T/h/.config/pipewire/pipewire.conf.d"
    cp "$ROOT/conf/60-phone-mic.conf" "$T/h/.config/pipewire/pipewire.conf.d/"
    env -i PATH=/usr/bin:/bin HOME="$T/h" TMPDIR="$T/h" \
        pw-config -N merge context.objects | grep -q phonemic_sink; }
ck "R2b pipewire parses the fragment" r2b

r3() { # R3: the unit is templated, loads the source first, keeps its directives
    local u="$ROOT/packaging/phone-mic-bridge.service"
    grep -qx 'ExecStartPre="@PHONE_MIC_PREFIX@/scripts/load-virtual-mic.sh"' "$u" &&
    ! grep -q '@PHONE_MIC_ROOT@' "$u" &&
    ! grep -q '%h/' "$u" &&
    # The substitution itself is verified behaviourally by R4b and R6: the
    # installed unit carries the prefix and no placeholder survives. Asserting the
    # implementation text here would break on any rewrite that keeps the outcome.
    grep -qx 'After=pipewire.service wireplumber.service pipewire-pulse.service' "$u" &&
    grep -qx 'Wants=pipewire.service pipewire-pulse.service' "$u" &&
    grep -qx 'StartLimitIntervalSec=0' "$u" &&
    grep -qx 'Restart=always' "$u" && grep -qx 'Nice=-5' "$u" &&
    grep -qx 'WantedBy=default.target' "$u" && test -x "$ROOT/scripts/load-virtual-mic.sh"; }
ck "R3 unit templated, source loaded first, directives kept" r3

r4() { # R4: never enabled at login, health check guarded and never fatal
    local i="$ROOT/packaging/install.sh"
    ! grep -qE 'systemctl --user enable|systemctl enable' "$i" &&
    grep -q 'if ! pactl info' "$i" && ! grep -qE '^[[:space:]]*pactl info' "$i"; }
ck "R4 installer does not enable and guards the health check" r4

r4b() { # R4b: a dead audio server warns but does not abort the install
    command -v pactl >/dev/null || return 77
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
    grep -q 'the audio server does not answer' "$T/err" &&
    grep -qF "ExecStartPre=\"$T/home/.local/share/phone-mic/scripts/load-virtual-mic.sh\"" \
        "$T/home/.config/systemd/user/phone-mic-bridge.service" &&
    ! grep -q '@PHONE_MIC_PREFIX@' "$T/home/.config/systemd/user/phone-mic-bridge.service"; }
ck "R4b dead audio server: install still succeeds and templates the unit" r4b

r5() { # R5: persistent vs runtime documented, stale claim gone
    local r="$ROOT/README.md"
    grep -q '| `phonemic_sink` (the sink) | yes, PipeWire reads `60-phone-mic.conf` |' "$r" &&
    grep -q '| `phone_mic` (the source) | no, the bridge service creates it on start |' "$r" &&
    ! grep -qiE 'virtual device.*PipeWire configuration' "$r"; }
ck "R5 README separates persistent from runtime" r5

r6() { # R6: the install is self-contained, executable, and re-runs cleanly
    local d="$T/r6" h="$T/r6/home" src="$T/r6/src" p="$T/r6/home/.local/share/phone-mic"
    mkdir -p "$h" "$src"
    mkbin "$d/bin" 0
    cp -R "$ROOT/tui" "$ROOT/scripts" "$ROOT/conf" "$ROOT/packaging" "$src/"
    cp "$ROOT/README.md" "$ROOT/VERSION" "$src/"
    run_install "$src/packaging/install.sh" "$h" "$d/bin" "$d" >"$d/out1" 2>"$d/err1" ||
        { echo "  install failed:"; sed 's/^/  /' "$d/err1"; return 1; }
    find "$p" -type f | sort > "$d/tree1"

    test -f "$p/tui/phone_mic_tui.py" &&
    test -x "$p/tui/phone_mic_tui.py" &&
    test -x "$p/scripts/load-virtual-mic.sh" &&
    test -x "$p/scripts/scrcpy-mic.sh" &&
    test -x "$p/scripts/connect-phone.sh" &&
    test -f "$p/conf/60-phone-mic.conf" &&
    test -f "$p/README.md" &&
    test ! -e "$p/tui/__pycache__" &&
    test -x "$h/.local/bin/phone-mic" &&
    grep -qxF "exec \"$p/tui/phone_mic_tui.py\" \"\$@\"" "$h/.local/bin/phone-mic" &&
    ! grep -qF "$src" "$h/.local/bin/phone-mic" &&
    grep -qxF "ExecStartPre=\"$p/scripts/load-virtual-mic.sh\"" \
        "$h/.config/systemd/user/phone-mic-bridge.service" &&
    ! grep -q '@PHONE_MIC_PREFIX@' "$h/.config/systemd/user/phone-mic-bridge.service" &&
    ! grep -qF "$src" "$h/.config/systemd/user/phone-mic-bridge.service" &&
    test -f "$h/.config/pipewire/pipewire.conf.d/60-phone-mic.conf" &&
    run_install "$src/packaging/install.sh" "$h" "$d/bin" "$d" >"$d/out2" 2>"$d/err2" &&
    find "$p" -type f | sort > "$d/tree2" &&
    cmp -s "$d/tree1" "$d/tree2" &&
    test "$(grep -c '^exec ' "$h/.local/bin/phone-mic")" -eq 1 &&
    test "$(find "$h" -name phone-mic-bridge.service | wc -l | tr -d ' ')" -eq 1 &&
    test "$(find "$h/.config/pipewire/pipewire.conf.d" -name 60-phone-mic.conf | wc -l | tr -d ' ')" -eq 1 &&
    mv "$src" "$d/src-moved" &&
    test -x "$p/tui/phone_mic_tui.py" &&
    test -x "$p/scripts/scrcpy-mic.sh" &&
    ! grep -rqF "$d/src" "$h"; }
ck "R6 install is self-contained and idempotent" r6

r7() { # R7: --version prints VERSION, --help documents the modes, neither installs
    local d="$T/r7" h="$T/r7/home"
    mkdir -p "$h"
    mkbin "$d/bin" 0
    test "$(run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" --version)" = \
        "$(cat "$ROOT/VERSION")" &&
    run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" --help >"$d/help" 2>&1 &&
    grep -q -- '--uninstall' "$d/help" &&
    grep -q -- '--prefix' "$d/help" &&
    ! run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" --bogus >/dev/null 2>&1 &&
    test ! -e "$h/.local"; }
ck "R7 --version and --help work and install nothing" r7

r8() { # R8: --uninstall removes exactly what the installer created
    local d="$T/r8" h="$T/r8/home"
    mkdir -p "$h"
    mkbin "$d/bin" 0
    run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" >"$d/out" 2>"$d/err" ||
        { echo "  install failed:"; sed 's/^/  /' "$d/err"; return 1; }
    printf 'not ours\n' > "$h/.local/bin/other-tool" &&
    printf 'not ours\n' > "$h/.config/pipewire/pipewire.conf.d/50-other.conf" &&
    run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" --uninstall >"$d/un" 2>&1 &&
    test ! -e "$h/.local/bin/phone-mic" &&
    test ! -e "$h/.local/share/phone-mic" &&
    test ! -e "$h/.config/systemd/user/phone-mic-bridge.service" &&
    test ! -e "$h/.config/pipewire/pipewire.conf.d/60-phone-mic.conf" &&
    test -f "$h/.local/bin/other-tool" &&
    test -f "$h/.config/pipewire/pipewire.conf.d/50-other.conf" &&
    grep -q 'next PipeWire start' "$d/un" &&
    grep -q 'phonemic_sink' "$d/un" &&
    grep -q 'pipewire-pulse' "$d/un" &&
    ! grep -qE 'systemctl --user (restart|stop) (pipewire|wireplumber)' "$d/un" &&
    run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" --uninstall >/dev/null 2>&1; }
ck "R8 uninstall removes only our files and reports leftovers" r8

r9() { # R9: missing adb and scrcpy are named with the fix, install still completes
    local d="$T/r9" h="$T/r9/home"
    mkdir -p "$h" "$d/bin"
    # Only what install.sh itself needs: adb and scrcpy are genuinely absent and
    # the fake audio server does not answer.
    for t in sed awk cat mkdir cp chmod rm install tr dirname grep bash; do
        ln -sf "$(command -v "$t")" "$d/bin/$t"
    done
    printf '#!/bin/sh\nexit 1\n' > "$d/bin/pactl"
    printf '#!/bin/sh\nexit 0\n' > "$d/bin/systemctl"
    chmod +x "$d/bin/pactl" "$d/bin/systemctl"
    env -i PATH="$d/bin" HOME="$h" TMPDIR="$d" \
        bash "$ROOT/packaging/install.sh" >"$d/out" 2>"$d/err" &&
    grep -qF 'sudo pacman -S --needed android-tools' "$d/err" &&
    grep -qF 'sudo pacman -S --needed scrcpy' "$d/err" &&
    grep -q 'the audio server does not answer' "$d/err" &&
    grep -q 'systemctl --user start pipewire-pulse' "$d/err" &&
    grep -q 'environment problem' "$d/err" &&
    test -x "$h/.local/bin/phone-mic"; }
ck "R9 preflight names adb, scrcpy and pipewire-pulse with fixes" r9

r9b() { # R9b: a missing pactl is named with the fix too, install still completes
    local d="$T/r9b" h="$T/r9b/home"
    mkdir -p "$h" "$d/bin"
    for t in sed awk cat mkdir cp chmod rm install tr dirname grep bash; do
        ln -sf "$(command -v "$t")" "$d/bin/$t"
    done
    printf '#!/bin/sh\nexit 0\n' > "$d/bin/systemctl"
    chmod +x "$d/bin/systemctl"
    env -i PATH="$d/bin" HOME="$h" TMPDIR="$d" \
        bash "$ROOT/packaging/install.sh" >"$d/out" 2>"$d/err" &&
    grep -qF 'sudo pacman -S --needed pipewire-pulse' "$d/err" &&
    test -x "$h/.local/bin/phone-mic"; }
ck "R9b a missing pactl is reported, not fatal" r9b

r9c() { # R9c: scrcpy older than 3.2 is reported with the version requirement
    local d="$T/r9c" h="$T/r9c/home"
    mkdir -p "$h"
    mkbin "$d/bin" 0
    printf '#!/bin/sh\necho "scrcpy 3.1.0 <https://github.com/Genymobile/scrcpy>"\n' \
        > "$d/bin/scrcpy"
    chmod +x "$d/bin/scrcpy"
    run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" >"$d/out" 2>"$d/err" &&
    grep -q '3.1.0' "$d/err" &&
    grep -q '3\.2' "$d/err" &&
    grep -q -- '--audio-source=mic' "$d/err" &&
    grep -qF 'sudo pacman -S --needed scrcpy' "$d/err" &&
    test -x "$h/.local/bin/phone-mic"; }
ck "R9c scrcpy older than 3.2 is reported with the fix" r9c

r10() { # R10: per-user prefix only, audio stack never restarted or stopped
    local i="$ROOT/packaging/install.sh"
    grep -qF 'PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/phone-mic"' "$i" &&
    ! grep -v '^#!' "$i" | grep -qE '/(usr|etc)/' &&
    ! grep -qE 'systemctl[^#]*(restart|stop)[[:space:]]+[^#]*(pipewire|wireplumber)' "$i"; }
ck "R10 per-user only, audio stack never restarted" r10

r11() { # R11: --uninstall must not delete a directory this installer did not create
    local d="$T/r11" h="$T/r11/home" alien="$T/r11/alien"
    mkdir -p "$h" "$alien/sub"
    mkbin "$d/bin" 0
    printf 'keep me\n' > "$alien/sub/data.txt"
    ! run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" \
        --uninstall --prefix "$alien" >/dev/null 2>"$d/err" &&
    test -f "$alien/sub/data.txt" &&
    grep -qi 'refus' "$d/err"; }
ck "R11 uninstall refuses a prefix it did not create" r11

r12() { # R12: a prefix holding sed metacharacters is substituted verbatim
    local d="$T/r12" h="$T/r12/home" p="$T/r12/home/.local/share/ph&ne|mic"
    mkdir -p "$h"
    mkbin "$d/bin" 0
    run_install "$ROOT/packaging/install.sh" "$h" "$d/bin" "$d" --prefix "$p" \
        >"$d/out" 2>"$d/err" &&
    grep -qxF "ExecStartPre=\"$p/scripts/load-virtual-mic.sh\"" \
        "$h/.config/systemd/user/phone-mic-bridge.service"; }
ck "R12 a prefix with sed metacharacters is substituted verbatim" r12

exit "$fail"
