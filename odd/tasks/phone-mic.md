# phone-mic

Phone as a real PipeWire microphone for the PC, built in-house (Android sender + Linux receiver), replacing third-party
apps such as WO Mic (vendor-discontinued on Linux) and Micstream (ads, telemetry).

## Specs

S1. The PC must expose the phone audio as a normal input device that browsers, Discord and OBS all list.
    User words: "usar mi celualr como microfono en esta pc" and "ninguna pagina o app detrecta los micrfonos".
S2. The third-party attempt already failed once and must not be repeated as-is:
    User words: "ya probamos con mic wo y no funciono".
S3. The application is written by us, not adapted from another project:
    User words: "oye y si programamos una ?" answered with "App propia completa (Android + Linux)".
S4. The Linux receiver comes first and is validated on its own, before any Android toolchain is installed:
    Decision "Empezar solo por el cliente Linux".
S5. The project lives outside the POS-UTP repository, at /home/swat/Proyectos/phone-mic.
S6. The existing Bluetooth headset (M07) must keep working as the audio output while the phone provides the microphone.

## Tasks

| ID | Spec | Route | Commit | Status |
| --- | --- | --- | --- | --- |
| T1 | S1, S4 | inline (C + libpipewire + libopus) | 6b94e3e | done |
| T2 | S1, S3 | inline (Kotlin, needs Android toolchain) | - | pending |
| T3 | S1 | inline (mDNS discovery via avahi) | - | pending |
| T4 | S1, S6 | inline (reconnect, silence, metrics) | - | pending |
| T5 | S1 | inline (systemd user unit + APK packaging) | pending | unit done, APK blocked by T2 |
| T6 | S1, S2, S6 | inline (end-to-end against Discord, OBS, mictests) | - | pending |

T1 - Linux receiver `phone-micd`: UDP input, sequence-aware jitter buffer, optional Opus decode, and playback into a
PipeWire null sink paired with a remap source named `Phone Mic` (class `Audio/Source`), which is the node kind that
browsers, Discord and OBS enumerate.

T2 - Android sender app (Kotlin): `AudioRecord` 48 kHz mono, packetise, send over UDP, reconnect. Starts with raw PCM to
validate latency, then Opus.

T3 - Automatic discovery so the IP is never typed by hand.

T4 - Behaviour under failure: silence fill, underrun handling, reconnection, latency/loss metrics.

T5 - Packaging: systemd user service for the receiver, installable APK for the phone.

T6 - Verification: the virtual source is selectable and audible in Discord, OBS and a browser microphone test page while
the M07 headset stays the output device.

## Log

L1 (user, verbatim): "ahora dime como puedo usar mi celualr como microfono en esta pc , ya probamos con mic wo y no funciono"

L2 (user, verbatim): "oye y si programamos una ?"

L3 (decision): full in-house app (Android + Linux). Location /home/swat/Proyectos/phone-mic. First work unit is the Linux
receiver; the Android toolchain (jdk17-openjdk, cmdline-tools, platform, build-tools) is deferred until the user accepts
the ~3 GB install.

L4 (evidence): environment checked - gcc 16.2.1, clang 23.1.5, libpipewire-0.3 1.6.11 (dev headers), opus 1.6.1 (dev +
runtime), python3 3.14, avahi active, no Java/Gradle/Android SDK, 17 GB free on /home.

L5 (evidence, prior attempt): the WO Mic virtual source was technically sound (PipeWire exposed it and OBS listed it); the
observable failure was the M07 headset dropping its Bluetooth link and a stale `default.configured.audio.source.0=womic_mic`
entry, which is why S1 names the enumeration requirement explicitly and T4 covers reconnection.

L6 (evidence, T1 verified): the remap source `phone_mic` is listed by `pactl` and by `gst-device-monitor-1.0
Audio/Source` as `Audio/Source` with `node.description = Phone-Mic` and `device.class = filter`. End-to-end capture
of `pm-send` measured -10.5 dB max for raw S16LE and -9.6 dB max for Opus against a 0.3 amplitude sine, with 0 lost
and 0 malformed packets; underruns stayed at 2/100 and 7/248 packets because idle silence no longer counts as starvation.

L7 (decision): the exposed node is named `Phone-Mic` with a hyphen, not `Phone Mic`. `pactl`'s proplist parser
splits on whitespace, so a space truncates `device.description` to its first word; the hyphen keeps the runtime
`module-remap-source` path and the persistent PipeWire configuration byte-identical.

L8 (evidence): the virtual microphone is loaded in the live session with `pactl` and not by restarting PipeWire,
because a restart drops the M07 Bluetooth link and the Hyprland screencast session (S6, and the incident recorded
in L5).

L9 (evidence, T5 unit): `packaging/install.sh` built and installed the receiver to `~/.local/bin/phone-micd`, the unit
to `~/.config/systemd/user/phone-micd.service` (enabled, `systemd-analyze --user verify` clean) and the PipeWire fragment
to `~/.config/pipewire/pipewire.conf.d/`. The service listens on udp/47718 and an Opus test tone captured from `phone_mic`
through the service measured -9.6 dB max with 0 lost packets.

L10 (evidence, environment): `sudo pacman -S jdk17-openjdk android-tools` failed with 404 on every mirror because the
stale `cachyos-v3` database (2026-11-14) offers `17.0.21.0.2` while `extra` (2026-11-16) offers `17.0.21.0.3`. Corrected
command for the user to run: `sudo pacman -S --needed extra/jdk17-openjdk extra/android-tools`.

L11 (evidence, scrcpy shortcut verified): wireless debugging paired with `adb pair 192.168.100.57:43053` (pairing port
discovered with `avahi-browse -prt _adb-tls-pairing._tcp`, because the phone shows only the connection port on the main
screen), then `adb connect 192.168.100.57:40735` against Redmi Note 13 (23129RA5FL, Android 15). `scrcpy 5.0.1
--audio-source=mic` works, but `PULSE_SINK` is ignored because scrcpy plays through SDL, so its stream is created on the
default sink and must be moved with `pactl move-sink-input`. After the move, sink-input 1181 sat on phonemic_sink and a
6 s capture from phone_mic measured -1.8 dB max / -37.9 dB mean, i.e. real phone audio in the virtual microphone.

L12 (evidence, routing is not sticky): scrcpy recreated its audio stream (1181 -> 1262/1460) and the new stream was
born on the default sink again, which is why the user saw Phone-Mic but heard silence: the audio was leaving through the
M07 headphones. Fix: the wrapper now keeps a watchdog that moves any scrcpy stream back to phonemic_sink every second.
Verified by moving the stream to bluez_output.FC_9D_CF_FC_86_77.1 by hand: it returned to phonemic_sink in under 2 s,
and a capture from phone_mic measured -14.5 dB max.

L13 (evidence, "I hear myself"): the playback stream on the headphones was Brave playing the microphone test page back,
not a routing loop in the phone-mic chain.

L14 (evidence, latency): the perceived delay was scrcpy's default 200 ms audio buffering (`--audio-buffer=ms`). The
wrapper now launches with `--audio-buffer=50 --audio-output-buffer=8`, overridable through AUDIO_BUFFER /
AUDIO_OUTPUT_BUFFER. Stream 1766 stayed on phonemic_sink and the capture measured -20.3 dB.

L15 (evidence, "I hear myself" is not a routing loop): with the phone as the microphone, Brave held a source-output on
phone_mic and a playback stream on the default sink (the M07 headphones) at the same time, i.e. the microphone test page
was playing the user's own recording back. The phone-mic chain has no monitor path from microphone to headphones.

L16 (evidence, after-reboot procedure): `phone-micd` is `enabled` and the virtual device configuration is installed, so
both survive a reboot. The adb connection and the scrcpy bridge do not. `scripts/connect-phone.sh` reconnects using the
last working port (saved in ~/.local/state/phone-mic), then adb mDNS, then avahi, and only then asks the user for the
port. `scripts/phone-mic.sh` chains connect + forwarding and is wired to a desktop entry, so the daily action is one click.
Verified: with the device connected the script reports "already connected" and exits without touching the session.

L17 (evidence, terminal panel): `tui/phone_mic_tui.py` renders the real state (service, virtual device, adb peer, bridge
pid and routing, level meter) and exposes start/stop/reconnect/re-route/meter keys. Verified with `--once` (snapshot
against the live session) and by running it under a pseudo-terminal: it renders and the meter bar fills as audio arrives.
The panel owns no audio path, so quitting it does not cut the microphone.

L18 (evidence, the bridge moved to systemd): closing the launcher window used to stop the microphone because the window
owned the scrcpy process. `phone-mic-bridge.service` now owns it, the menu entry only starts the service and returns, and
`phone-mic`/the TUI call systemctl. Verified: killing scrcpy brought it back (new pid) in under 10 s, and after
`adb disconnect` plus a killed scrcpy the service reconnected adb (port 40735) and restarted forwarding within 25 s with no
user action. Root cause of the first failed attempt: the unit ran `scrcpy-mic.sh`, which exits when no adb device exists;
it now runs `phone-mic.sh` so every restart reconnects first. `connect-phone.sh` also learned to save the endpoint when a
connection already exists, because earlier connections were made by hand and left no port to retry.
