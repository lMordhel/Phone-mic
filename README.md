# phone-mic

Use an Android phone as a real microphone on Linux, exposed to every application
as an ordinary input device named **`Phone-Mic`**.

Built because the existing options either stopped working or get in the way: WO Mic
no longer ships a supported Linux client, and hosted apps add accounts, ads and
telemetry to something that should be a local audio device.

```
 phone microphone                    Linux PC
┌──────────────────┐   Wi-Fi/LAN   ┌───────────────────────────────────────────┐
│ Android device   │──────────────▶│ phonemic_sink (Audio/Sink, null)          │
│ capture + send   │               │        │ monitor                          │
└──────────────────┘               │        ▼                                  │
                                   │ phone_mic (Audio/Source) "Phone-Mic"      │
                                   │        │                                  │
                                   │        ▼                                  │
                                   │ Discord · OBS · browsers · recorders      │
                                   └───────────────────────────────────────────┘
```

## Status

| Part | State |
| --- | --- |
| Virtual device (`Phone-Mic`) in PipeWire | **working** |
| Linux receiver `phone-micd` (UDP + Opus decoder + jitter buffer) | **working**, tested |
| systemd user service + installer | **working**, tested |
| Phone bridge over `scrcpy` (`--audio-source=mic`) | **working**, tested |
| Terminal panel (`tui/phone_mic_tui.py`) | **working**, tested |
| Native Android app (Kotlin + UDP, no adb) | planned, see [Roadmap](#roadmap) |

Two phone paths exist today:

- **`scrcpy` bridge** — no app to build or install, uses the phone microphone
  through adb. This is the path documented below and the one that works now.
- **Native app** — removes the adb dependency (pure Wi-Fi). Receiver side is
  already done and tested with `pm-send`, the Android half is still to come.

## Requirements

- Linux with PipeWire (tested on CachyOS / PipeWire 1.6, Hyprland).
- On Arch and derivatives:
  ```
  sudo pacman -S --needed base-devel pipewire-audio opus \
                            android-tools scrcpy
  ```
  `scrcpy` must be 3.2 or newer (`--audio-source=mic`).
- For the development build: `libpipewire-0.3` and `opus` headers.
- Android phone, Android 11 or newer, on the same network as the PC.

## Install

```bash
git clone git@github.com:lMordhel/Phone-mic.git
cd Phone-mic
./packaging/install.sh
```

The installer builds the receiver, installs `~/.local/bin/phone-micd`, the systemd
user unit, the PipeWire fragment and the documentation, enables the service, and
loads the virtual device into the running session. It needs no root and **never
restarts PipeWire**.

Open the firewall if the native app will be used later:

```bash
sudo ufw allow 47718/udp
```

Check the virtual device exists:

```bash
pactl list short sources | grep -w phone_mic
systemctl --user status phone-micd
```

## Phone setup (scrcpy bridge)

1. On the phone: **Settings → About phone**, tap *Build number* seven times.
2. **Settings → Developer options → Wireless debugging** → enable it.
3. Keep the phone on the same Wi-Fi as the PC, screen unlocked.
4. Pair it once from the PC:
   ```bash
   # the pairing port and the 6-digit code are shown by "Pair device with pairing code"
   adb pair 192.168.100.57:PORT
   ```
   The pairing port is also discoverable over mDNS:
   ```bash
   avahi-browse -prt _adb-tls-pairing._tcp
   ```

## Daily use

One click: **Micrófono del teléfono** in the application menu.

That launcher reconnects adb (last working port, then mDNS discovery, then it asks
for the port the phone shows) and starts forwarding with a watchdog that keeps the
audio on the virtual sink across reconnections.

From a terminal:

```bash
cd Phone-mic
./scripts/phone-mic.sh          # connect + forward
./scripts/connect-phone.sh PORT # only reconnect, using the port the phone shows
```

Then pick **`Phone-Mic`** as the input device:

- **Discord** → Settings → Voice & Video → Input device.
- **OBS** → the microphone source properties → device.
- **Browsers** → the site's microphone picker; grant permission once.

Both Discord and OBS ignore the system default, so they need the device selected
explicitly. They also cache the device list at startup: if `Phone-Mic` is missing
from the dropdown, restart the application.

## Terminal panel

```bash
./tui/phone_mic_tui.py          # interactive panel
./tui/phone_mic_tui.py --once   # one snapshot, scriptable
```

```
phone-mic  panel del microfono del telefono
  receiver service   running
  virtual device     phonemic_sink / phone_mic
  phone (adb)        192.168.100.57:40735
  bridge             forwarding (pid 63115), routing ok
  audio              peak -6.2 dB   rms -24.3 dB
  nivel  [###################---------]   -6.2 dB
  i iniciar   d detener   r reconectar   a arreglar ruta   m medidor   q salir
```

| Key | Action |
| --- | --- |
| `i` | start the bridge (connect + forward) |
| `d` | stop forwarding |
| `r` | reconnect adb (asks nothing; reports what it found) |
| `a` | move the bridge stream back to the virtual sink |
| `m` | toggle the level meter (it opens its own capture client) |
| `q` | quit (the bridge keeps running) |

The panel owns no audio: closing it never cuts the microphone. Quitting is safe by
design, which is why it does not ask for confirmation.

It is also in the application menu as **Micrófono del teléfono (panel)**.

## After a reboot

| Piece | Survives a reboot |
| --- | --- |
| `phone-micd` service | yes, `enabled` |
| `Phone-Mic` virtual device | yes, PipeWire configuration |
| adb connection | no, the launcher reconnects |
| `scrcpy` forwarding | no, the launcher starts it |

With a USB cable instead of Wi-Fi there is nothing to reconnect: `adb` finds the
device by itself.

## Configuration

| Setting | Where | Default |
| --- | --- | --- |
| UDP port (native app) | `phone-micd --port` / unit `ExecStart` | 47718 |
| Virtual sink / source names | `conf/60-phone-mic.conf` | `phonemic_sink` / `phone_mic` |
| scrcpy audio buffering | `AUDIO_BUFFER` env var | 50 ms (scrcpy default is 200 ms) |
| scrcpy SDL output buffer | `AUDIO_OUTPUT_BUFFER` env var | 8 ms |

Lower `AUDIO_BUFFER` for less delay, raise it when Wi-Fi is busy:

```bash
AUDIO_BUFFER=30 ./scripts/scrcpy-mic.sh
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Phone-Mic` listed but silent | scrcpy recreated its stream on the default sink | use `scripts/phone-mic.sh`; its watchdog moves the stream back within a second |
| You hear your own voice | the microphone test page plays your recording back | close the test page; the chain has no microphone-to-headphones path |
| Audible delay | scrcpy buffers 200 ms by default | the wrapper already uses 50 ms; lower it or use USB |
| `Phone-Mic` missing from a dropdown | the application cached its device list | restart the application |
| `adb` cannot connect | phone rebooted and the wireless debugging port changed | `./scripts/connect-phone.sh PORT` with the port from the phone |
| Bluetooth headset drops when audio restarts | PipeWire restart tears down Bluetooth links | never restart PipeWire to apply configuration; use `scripts/load-virtual-mic.sh` |
| Clicky or choppy audio | buffer too low for the network | raise `AUDIO_BUFFER` |

## Build and test without a phone

```bash
make
./phone-micd --stats        # terminal 1
./pm-send --freq 440 --duration 5 --codec raw    # terminal 2 (or --codec opus)
```

Verify what the virtual microphone carries:

```bash
parec --device=phone_mic --format=s16le --rate=48000 --channels=2 --raw > /tmp/t.raw &
./pm-send --freq 440 --duration 3
kill %1
ffmpeg -f s16le -ar 48000 -ac 2 -i /tmp/t.raw -af volumedetect -f null -
```

A `pm-send` tone at the default amplitude reads about -10 dB maximum. The wire
format is documented in [PROTOCOL.md](PROTOCOL.md).

## Uninstall

```bash
systemctl --user disable --now phone-micd
rm ~/.local/bin/phone-micd ~/.config/systemd/user/phone-micd.service \
   ~/.config/pipewire/pipewire.conf.d/60-phone-mic.conf \
   ~/.local/share/applications/phone-mic.desktop
rm -rf ~/.local/share/phone-mic ~/.local/state/phone-mic
```

## Roadmap

- **T2** Native Android app: `AudioRecord` at 48 kHz mono, UDP packets per
  `PROTOCOL.md`, raw PCM first then Opus; no adb, no cable.
- **T3** mDNS discovery so the IP is never typed.
- **T4** Reconnection and loss metrics on the native path.
- **T5** APK packaging.
- **T6** End-to-end verification against Discord, OBS and a browser microphone page.

Work tracking, specs and evidence live in
[`odd/tasks/phone-mic.md`](odd/tasks/phone-mic.md).
