# phone-mic

Use an Android phone as a real microphone on Linux. A small receiver
(`phone-micd`) takes audio packets from the phone over the local network and
plays them into a PipeWire null sink; that sink is remapped into an
`Audio/Source` node, which is the node kind applications actually enumerate as
an input device.

```
 phone app (T2)                phone-micd                     applications
┌───────────────┐   UDP/47718  ┌──────────────┐   PCM        ┌──────────────┐
│ AudioRecord   │─────────────▶│ ring buffer  │─────────────▶│ phonemic_sink│
│ + Opus encode │              │ + Opus decode│              │ Audio/Sink   │
└───────────────┘              └──────────────┘              └──────┬───────┘
                                                                    │ monitor
                                                          ┌─────────▼─────────┐
                                                          │ phone_mic         │
                                                          │ Audio/Source      │
                                                          │ "Phone-Mic"       │
                                                          └───────────────────┘
```

Requirements: a C compiler, `libpipewire-0.3` and `opus` development packages,
PipeWire running. On Arch: `pacman -S --needed base-devel pipewire-audio opus`.

## Build

```
make
```

Produces `phone-micd` (the receiver) and `pm-send` (a test tone sender).

## Install the virtual microphone

Persistent, read by PipeWire on its next start:

```
mkdir -p ~/.config/pipewire/pipewire.conf.d
cp conf/60-phone-mic.conf ~/.config/pipewire/pipewire.conf.d/
```

For the current session, without restarting PipeWire (a restart drops Bluetooth
links and in-flight screencasts):

```
./scripts/load-virtual-mic.sh
```

## Run

```
./phone-micd --stats          # listens on udp/47718, plays into phonemic_sink
```

Open the firewall for the phone on the same network:

```
sudo ufw allow 47718/udp
```

## Install as a user service

```
./packaging/install.sh          # build, install binary, unit, PipeWire conf
systemctl --user start phone-micd
journalctl --user -u phone-micd -f
```

The unit is `Restart=on-failure`, runs after PipeWire, and never restarts the
audio server. Uninstall commands are printed at the end of the script.

## Test without a phone

In two terminals:

```
./phone-micd --stats
```

```
./pm-send --freq 440 --duration 5 --codec raw    # or --codec opus
```

Then verify the virtual microphone carries the tone:

```
parec --device=phone_mic --format=s16le --rate=48000 --channels=2 --raw > /tmp/t.raw &
./pm-send --freq 440 --duration 3
kill %1
ffmpeg -f s16le -ar 48000 -ac 2 -i /tmp/t.raw -af volumedetect -f null -
```

A 0.3 amplitude sine (the `pm-send` default) reads about -10 dB max, which is
what the tests in the feature document assert.

## Status

- T1 Linux receiver: done. `Phone-Mic` is listed by PipeWire, GStreamer device
  monitoring, and captured correctly for both raw PCM and Opus.
- T2 Android app: pending, needs the Android toolchain.
- T3 discovery, T4 robustness, T5 packaging, T6 end-to-end verification: pending.

See `odd/tasks/phone-mic.md` for specs, tasks and the decision log, and
`PROTOCOL.md` for the wire format.

## Notes

- The virtual microphone always exists once the configuration is installed and
  produces silence while no phone is connected. Applications keep their own
  device selection, so a dead phone does not silently replace another mic.
- `device.class` of the remapped node is `filter`; browsers, Discord and OBS
  still list it as an input. T6 checks that explicitly.
- Audio latency through the ring buffer is capped at two seconds; latency in
  normal operation is one packet (20 ms) plus the process quantum.
