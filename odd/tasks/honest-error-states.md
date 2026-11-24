# honest-error-states

The panel must stop inventing measurements. Today every failed read collapses
into a plausible constant (`0%`, `-60.0 dB`, empty bars), so a dead audio server
is indistinguishable from a silent room. This feature makes unknown state visible
and names the command that fixes it.

## Specs

S1. Axis chosen by the owner, option label verbatim: "Estados de error honestos
en el panel". The owner's selected example, verbatim:

```
Antes:  Phone-Mic   ACTIVATING   GAIN 0%   -60.0 dB
Después:
  AUDIO SERVER DOWN
  pipewire-pulse no responde.
  Arreglo: systemctl --user reset-failed pipewire ...

Y lo mismo para: adb unauthorized, teléfono no alcanzable,
scrcpy demasiado viejo.
```

S2. A value that could not be read is never rendered as a number. Unknown shows
as `—`, never as `0%`, `0`, or a floor dB value.

S3. Real silence and no data must look different. A measured floor belongs to a
running capture; no capture at all is a different state with its own words.

S4. The audio-server-down state names the cause and the fixing command, as in the
S1 example.

S5. The phone link distinguishes: adb missing, device `unauthorized`, device
`offline`, no device attached, and bridge unit state unknown. Each gets its own
words; a missing device model is reported as unknown, not `-`.

S6. The one-shot `status` path and the interactive panel cannot disagree: both
read state through the same helpers.

S7. No fabricated success. A control that failed never reports success.

S8. Behaviour is preserved: key bindings, themes, layout and the four existing
`status` fields keep working; only state words and unreadable values change.

## Tasks

- P1 — Split failure from empty in the read layer: a query helper that reports
  failure distinctly, and converters that return None instead of `0`. S2. worker.
  `refactor(tui): distinguish a failed read from an empty one` — done, `8a8d046`.
  Shared commit with P2: same file, and the tests belong with the behaviour.
- P2 — Pure parsers plus tests: volume percent, mute, adb device states, sink
  input lookup and model props become pure functions with unit tests that need no
  terminal. S2 S5. worker. `test(tui): cover the state parsers` — done,
  `8a8d046`. 37 of the new cases fail against the previous module.
- P3 — Input monitor honesty: `NO SIGNAL` when nothing is being captured,
  `NO CAPTURE TOOL` when `parec` is missing, measured floor still shown as the
  genuine level. S2 S3. worker. `feat(tui): report capture state honestly` —
  done, `ca7b635`. 11 of the new cases fail against the previous module.
- P4 — Audio server and controls honesty: probe `pactl info`, show
  `AUDIO SERVER DOWN` with the fixing command, render gain/volume as `—` and
  refuse to pretend a write succeeded. S2 S4 S7. worker. — in flight.
  `feat(tui): report audio server state honestly`
- P5 — Phone link honesty: adb unavailable, unauthorized, offline, no device,
  unknown unit state, unknown model. S5. worker.
  `feat(tui): report phone link state honestly`
- P6 — One source of truth for state: `status` reuses the panel helpers instead
  of its own copy of the logic. S6. worker.
  `refactor(tui): share state logic between panel and status`
- P7 — Footer advertises every key the loop handles, including `[R]`, `Tab` and
  the arrows. S8. inline. `fix(tui): list every handled key in the footer`

## Log

L1 — owner, verbatim: "claro pero antes de hacer un instaldaor profesional hay que
pulir el progrma"

L2 — owner selected the polish axis, label verbatim: "Estados de error honestos en
el panel", with the before/after example quoted in S1.

L3 — evidence for the root cause, from `tui/phone_mic_tui.py`: `run()` at
`:233-238` never inspects `returncode` and returns `""` for a non-zero exit, a
missing binary, a timeout or an OSError, so failure and legitimate empty output
are the same value. `percent()` `:320-331` returns `0` when no `%` line is found;
`source_volume()` `:334` caches it; `stream_volume()` `:350-359` returns `0` both
for "no scrcpy stream" and for a failed `pactl`; the meter seeds
`peak_db = FLOOR_DB` `:431-432` and renders `-60.0 dB` `:692-693` with no marker
when `parec` is missing and the thread never runs `:437-438`. `adb devices` `:264`
parses only lines ending in `device`, so `unauthorized` and `offline` are
invisible; `systemctl is-active` failure yields `"unknown"` `:285` which is then
painted as a red state word `:708`. `toggle_mute()` `:380-382` always returns
True. `status` `:893-899` re-implements the state logic instead of reusing it.

L4 — scope boundary: this feature touches `tui/` only. The installer work (T2/T3
of professional-distribution) is parked by L1 of that document.

L5 — review policy for this feature, decided by the orchestrator and reported to
the owner: the TUI slice is reviewed ONCE, when P1-P7 are committed and the tree
is quiet, instead of once per task. Each intermediate task keeps the file in
motion, so a per-task review would freeze a half-written panel and pay four times
for the same file. Commits `8a8d046` (P1+P2) and `ca7b635` (P3) were committed
with local verification and no native review.
