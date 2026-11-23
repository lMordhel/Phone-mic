# phone-mic

Phone as a real PipeWire microphone for the PC: the phone needs no app, `scrcpy`
captures its microphone and the audio lands on a virtual device named `Phone-Mic`.
The interface is the terminal command `phone-mic`.

## Specs

S1. The PC must expose the phone audio as a normal input device that browsers, Discord and OBS all list.
    User words: "usar mi celualr como microfono en esta pc" and "ninguna pagina o app detrecta los micrfonos".
S2. Third-party microphone apps are not acceptable; none of the attempts worked.
    User words: "ya probamos con mic wo y no funciono".
S3. The phone needs no application installed: the phone side is `scrcpy --audio-source=mic`.
    Decision: no APK is built, published or required.
S4. The project is terminal-only: no desktop application, icon, window or tray entry.
    User words: "al programa solo debe de ejecutarse mediante la terminal".
S5. The existing Bluetooth headset (M07) must keep working as the audio output while the phone provides the microphone.
S6. Closing the panel or the terminal must not stop the audio, and a dropped phone connection must recover without user action.

## Tasks

| ID | Spec | What | Commit | Status |
| --- | --- | --- | --- | --- |
| T1 | S1, S5 | Virtual device: null sink `phonemic_sink` + remap source `phone_mic` (`Phone-Mic`) | 6b94e3e | done |
| T2 | S1, S3 | Phone bridge: `scrcpy --audio-source=mic`, routed to the sink, 50 ms audio buffer | 6f2bd5b, 091e3a5 | done |
| T3 | S6 | Bridge as a systemd user service with automatic adb reconnection | 87b755d | done |
| T4 | S4 | Terminal panel `phone-mic` with state, level meter and control keys | 92a27ba, ca58003 | done |
| T5 | S4 | Terminal-only cleanup: desktop entries removed from repository and system | e79ffb8, f51e567 | done |
| T6 | S1, S5 | End-to-end verification in Discord, OBS and a browser microphone page | - | open, needs the user in front of the apps |

## Log

L1 (user, verbatim): "ahora dime como puedo usar mi celualr como microfono en esta pc , ya probamos con mic wo y no funciono"

L2 (user, verbatim): "oye y si programamos una ?"

L3 (user, verbatim): "ahora si phone-mic ya detecta el audio pero esta con dyley no debe de ser asi"

L4 (user, verbatim): "si se detecta el phone-mic pero no se escucha y la lasina lo tengo en mis audifonos"

L5 (user, verbatim): "cuando cierro el progrma que instalaste hace rato microfono del telefon , deja de funcionara y el tui no tieen reconeccion automatica"

L6 (user, verbatim): "del programa solo no vamos a quedar con la parte de tui la aplicacion que hicimos la borramos del proyecto , y desintalalo de mi sistema"

L7 (user, verbatim): "el readme aun hace referencia qde que hay una app para android"

L8 (user, verbatim): "Eliminarlo tambien del repositorio" (about the unused receiver)

L9 (evidence, virtual device): `phone_mic` is listed by `pactl` and by `gst-device-monitor-1.0 Audio/Source` as
`Audio/Source` with `node.description = Phone-Mic` and `device.class = filter`; browsers, Discord and OBS enumerate it.
The name uses a hyphen because `pactl`'s proplist parser splits on whitespace and truncated "Phone Mic" to "Phone".

L10 (evidence, bridge): wireless debugging paired with `adb pair 192.168.100.57:43053`, pairing port discovered with
`avahi-browse -prt _adb-tls-pairing._tcp`. `scrcpy` ignores `PULSE_SINK` (it plays through SDL), so its stream is created
on the default sink and moved to `phonemic_sink`; because scrcpy recreates the stream on reconnect, a one-second watchdog
moves it back. Verified by moving it away by hand: it returned in under 2 s.

L11 (evidence, latency): the perceived delay was scrcpy's default 200 ms buffering. `--audio-buffer=50
--audio-output-buffer=8`, both overridable via `AUDIO_BUFFER` / `AUDIO_OUTPUT_BUFFER`.

L12 (evidence, "I hear myself"): the playback stream on the headphones came from Brave playing the microphone test page
back, not from the phone-mic chain, which has no microphone-to-headphones path.

L13 (evidence, service): the bridge moved to `phone-mic-bridge.service` because the launcher window owned the process and
closing it cut the audio. Verified: killing scrcpy restarted it in under 10 s; after `adb disconnect` plus a killed
scrcpy the service reconnected adb and resumed forwarding within 25 s of its own accord. First attempt failed because the
unit ran the forwarder alone, which exits when adb is absent; the unit now chains `connect-phone.sh` first.
`connect-phone.sh` also saves the endpoint of an existing connection, since earlier connections were made by hand and left
no port to retry.

L14 (evidence, terminal panel): `tui/phone_mic_tui.py` renders the real state (virtual device, adb peer, bridge pid and
routing, level meter) and exposes start/stop/reconnect/re-route/meter keys. Verified with `--once` against the live session
and under a pseudo-terminal.

L15 (decision, scope): the desktop application and the custom UDP receiver were removed from the repository and
uninstalled from the system. There is no APK, no desktop entry and no UDP protocol; the live path is `scrcpy` into
`phonemic_sink`. The PipeWire fragment stays because it provides the device applications use.

L16 (evidence, receiver removal): with the old receiver stopped, a capture from `phone_mic` measured -33.6 dB (ambient),
i.e. audio kept flowing without it, which is why it was removed.
