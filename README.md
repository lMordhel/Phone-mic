# phone-mic

Use an Android phone as a real microphone on Linux, exposed to every application
as an ordinary input device named **`Phone-Mic`**.

The phone needs no app: `scrcpy` captures its microphone over adb and the audio is
routed into a PipeWire virtual device. The whole interface is a terminal command.

```
 phone microphone                          Linux PC
┌──────────────────┐                    ┌────────────────────────────────────────┐
│ Android device   │  adb / Wi-Fi       │ scrcpy --audio-source=mic              │
│ (no app needed)  │───────────────────▶│        │                               │
└──────────────────┘                    │        ▼                               │
                                        │ phonemic_sink (Audio/Sink, null)       │
                                        │        │ monitor + remap               │
                                        │        ▼                               │
                                        │ phone_mic (Audio/Source) "Phone-Mic"   │
                                        │        │                               │
                                        │        ▼                               │
                                        │ Discord · OBS · browsers · recorders   │
                                        └────────────────────────────────────────┘
```

## Status

| Part | State |
| --- | --- |
| Virtual device (`Phone-Mic`) in PipeWire | **working**, tested |
| Phone bridge over `scrcpy` (`--audio-source=mic`) | **working**, tested, nothing to install on the phone |
| Terminal panel (`phone-mic`) | **working**, tested |
| `phone-mic-bridge` systemd user service | **working**, tested, reconnects by itself |

## Requirements

- Linux with PipeWire (tested on CachyOS / PipeWire 1.6, Hyprland).
- On Arch and derivatives:
  ```
  sudo pacman -S --needed pipewire-audio android-tools scrcpy
  ```
  `scrcpy` must be 3.2 or newer: `--audio-source=mic` appeared in that release.
- Android phone, Android 11 or newer, on the same network as the PC.

## Install

```bash
git clone git@github.com:lMordhel/Phone-mic.git
cd Phone-mic
./packaging/install.sh
```

The installer writes the PipeWire fragment, the `phone-mic` command in
`~/.local/bin`, the `phone-mic-bridge` user unit and the documentation. It needs no
root and **never restarts PipeWire** (a restart drops Bluetooth links and
screencasts).

Check it:

```bash
phone-mic status
```

## Phone setup

Done once. Nothing is installed on the phone.

1. **Settings → About phone**, tap *Build number* seven times.
2. **Settings → Developer options → Wireless debugging** → enable.
3. Keep the phone on the same Wi-Fi as the PC, screen unlocked.
4. Pair from the PC:
   ```bash
   adb pair 192.168.100.57:PORT     # port and 6-digit code: "Pair device with pairing code"
   ```
   The pairing port is also discoverable:
   ```bash
   avahi-browse -prt _adb-tls-pairing._tcp
   ```

## Daily use

```bash
phone-mic            # panel: i start · d stop · r reconnect · a fix routing · m meter · q quit
phone-mic status     # one snapshot
phone-mic start      # start forwarding
phone-mic stop       # stop forwarding
```

Then select **`Phone-Mic`** as the input device:

- **Discord** → Settings → Voice & Video → Input device.
- **OBS** → the microphone source properties → device.
- **Browsers** → the site's microphone picker; grant permission once.

Discord and OBS ignore the system default and cache the device list at startup: if
`Phone-Mic` is missing from a dropdown, restart that application.

### The bridge service

Forwarding belongs to the `phone-mic-bridge` systemd user service, not to the
terminal you start it from:

```bash
systemctl --user start phone-mic-bridge
systemctl --user stop  phone-mic-bridge
systemctl --user status phone-mic-bridge
journalctl --user -u phone-mic-bridge -f
```

Two consequences that matter:

- **Closing the panel or the terminal does not stop the audio.** Only an explicit
  stop does.
- **Reconnection is automatic.** A dropped adb link, a sleeping phone or a scrcpy
  crash ends the process, and `Restart=always` runs the launcher again, which
  reconnects adb (last known port, then mDNS) before resuming audio.

The service is **not** enabled at login on purpose: while it runs it captures the
phone microphone continuously. Enable it if that is what you want:

```bash
systemctl --user enable phone-mic-bridge
```

## Terminal panel

```
phone-mic  panel del microfono del telefono
  virtual device     phonemic_sink / phone_mic
  phone (adb)        192.168.100.57:40735
  bridge service     active (pid 76187), routing ok
  audio              peak -6.2 dB   rms -24.3 dB
  nivel  [###################---------]   -6.2 dB
  i iniciar   d detener   r reconectar   a arreglar ruta   m medidor   q salir
```

| Key | Action |
| --- | --- |
| `i` | start the bridge service |
| `d` | stop the bridge service |
| `r` | reconnect adb (retries the last port, then mDNS) |
| `a` | move the bridge stream back to the virtual sink |
| `m` | toggle the level meter (opens its own capture client, 8 kHz) |
| `q` | quit the panel; the bridge keeps running |

The panel owns no audio, so quitting it never cuts the microphone.

## After a reboot

| Piece | Survives a reboot |
| --- | --- |
| `Phone-Mic` virtual device | yes, PipeWire configuration |
| adb connection | no, the bridge service reconnects when started |
| `scrcpy` forwarding | no, start it with `phone-mic start` |

With a USB cable instead of Wi-Fi there is nothing to reconnect: `adb` finds the
device by itself.

## Configuration

| Setting | Where | Default |
| --- | --- | --- |
| Virtual sink / source names | `conf/60-phone-mic.conf` | `phonemic_sink` / `phone_mic` |
| scrcpy audio buffering | `AUDIO_BUFFER` env var | 50 ms (scrcpy default is 200 ms) |
| scrcpy SDL output buffer | `AUDIO_OUTPUT_BUFFER` env var | 8 ms |
| adb endpoint memory | `~/.local/state/phone-mic/` | learned on the first connection |

Lower `AUDIO_BUFFER` for less delay, raise it when Wi-Fi is busy:

```bash
AUDIO_BUFFER=30 ./scripts/scrcpy-mic.sh
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Phone-Mic` listed but silent | scrcpy recreated its stream on the default sink | press `a` in the panel; the watchdog also fixes it within a second |
| You hear your own voice | the microphone test page plays your recording back | close the test page; the chain has no microphone-to-headphones path |
| Audible delay | scrcpy buffers 200 ms by default | the wrapper already uses 50 ms; lower it or use USB |
| `Phone-Mic` missing from a dropdown | the application cached its device list | restart the application |
| `adb` cannot connect | the phone rebooted and the wireless debugging port changed | `./scripts/connect-phone.sh PORT` with the port from the phone |
| Bluetooth headset drops when audio restarts | a PipeWire restart tears down Bluetooth links | never restart PipeWire to apply configuration; use `scripts/load-virtual-mic.sh` |
| Clicky or choppy audio | buffer too low for the network | raise `AUDIO_BUFFER` |
| Bridge stuck retrying | the phone is unreachable or wireless debugging is off | `phone-mic status`, then check the phone |

## Uninstall

```bash
systemctl --user disable --now phone-mic-bridge
rm ~/.local/bin/phone-mic \
   ~/.config/systemd/user/phone-mic-bridge.service \
   ~/.config/pipewire/pipewire.conf.d/60-phone-mic.conf
rm -rf ~/.local/share/phone-mic ~/.local/state/phone-mic
```

## What this is not

- **Not an Android app.** No APK is built, published or required.
- **Not a desktop application.** No icon, window or tray entry: the terminal command
  is the whole interface.
- **No custom audio transport.** There is no UDP protocol and no receiver: the live
  audio path is `scrcpy` into `phonemic_sink`, and `Phone-Mic` is a PipeWire remap
  source over that sink.

Work tracking and evidence live in [`odd/tasks/phone-mic.md`](odd/tasks/phone-mic.md).
