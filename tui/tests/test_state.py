#!/usr/bin/env python3
"""Unit tests for the read layer and the state parsers of the panel.

The parsers are pure: they take text (or None when the query itself failed) and
return a value, or None when the value could not be read. A failed read must
never look like a plausible number. Run with:

    python3 -m unittest discover -s tui/tests
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import phone_mic_tui as tui  # noqa: E402  (sys.path is prepared above)


# `pactl info` while the server answers; it names itself on the Server Name line.
PACTL_INFO = (
    "Server String: /run/user/1000/pulse/native\n"
    "Library Protocol Version: 35\n"
    "Server Name: PulseAudio (on PipeWire 1.6.11)\n"
    "Server Version: 15.0.0\n"
)

# What pactl prints when pipewire-pulse is not there to answer.
PACTL_INFO_DOWN = "Connection failure: Connection refused\n"

# pactl prints one line with every channel and one balance line after it.
PACTL_VOLUME = (
    "Volume: front-left: 26214 /  40% / -23.88 dB,   "
    "front-right: 26214 /  40% / -23.88 dB\n"
    "        balance 0.00\n"
)

ADB_DEVICES = (
    "List of devices attached\n"
    "R58M12345\tdevice\n"
    "emulator-5554\tunauthorized\n"
    "0123456789\toffline\n"
    "\n"
)

SINK_INPUTS_WITH_SCRCPY = """\
Sink Input #42
\tDriver: protocol-native.c
\tOwner Module: 12
\tClient: 8
\tSink: 3
\tSample Specification: s16le 1ch 48000Hz
\tCorked: no
\tMute: no
\tVolume: front-left: 65536 / 100% / 0.00 dB
\t        balance 0.00
\tProperties:
\t\tapplication.name = "scrcpy"
\t\tmedia.name = "phone mic"
Sink Input #43
\tSink: 3
\tVolume: front-left: 16384 /  25% / -36.12 dB
\tProperties:
\t\tapplication.name = "firefox"
"""

SINK_INPUTS_NO_SCRCPY = """\
Sink Input #51
\tSink: 0
\tVolume: front-left: 32768 /  50% / -18.06 dB
\tProperties:
\t\tapplication.name = "firefox"
"""

SINK_INPUTS_NO_VOLUME = """\
Sink Input #42
\tSink: 3
\tProperties:
\t\tapplication.name = "scrcpy"
"""


class QueryTest(unittest.TestCase):
    """query() reports a failed read as None, and an empty answer as ""."""

    def test_missing_binary_is_unknown(self):
        self.assertIsNone(tui.query(["phone-mic-no-such-binary"]))

    def test_non_zero_exit_without_output_is_unknown(self):
        self.assertIsNone(
            tui.query([sys.executable, "-c", "raise SystemExit(2)"]))

    def test_non_zero_exit_with_output_is_a_real_answer(self):
        # `systemctl is-active` exits non-zero for anything but "active" but
        # still prints the state; that is an answer, not a read failure.
        text = tui.query(
            [sys.executable, "-c", "print('inactive'); raise SystemExit(3)"])
        self.assertEqual(text.strip(), "inactive")

    def test_empty_success_is_not_a_failure(self):
        self.assertEqual(tui.query([sys.executable, "-c", "pass"]), "")

    def test_timeout_is_unknown(self):
        self.assertIsNone(tui.query(
            [sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2))


class RunCompatibilityTest(unittest.TestCase):
    """run() keeps its fire-and-forget "" contract for the setters."""

    def test_failure_is_an_empty_string(self):
        self.assertEqual(tui.run(["phone-mic-no-such-binary"]), "")

    def test_success_returns_the_output(self):
        self.assertEqual(
            tui.run([sys.executable, "-c", "print('ok')"]).strip(), "ok")


class VolumePercentTest(unittest.TestCase):
    def test_reads_the_aggregate_percent(self):
        self.assertEqual(tui.parse_volume_percent(PACTL_VOLUME), 40)

    def test_zero_percent_is_a_real_value(self):
        self.assertEqual(tui.parse_volume_percent(
            "Volume: front-left: 0 /   0% / -inf dB\n"), 0)

    def test_empty_output_is_unknown_not_zero(self):
        self.assertIsNone(tui.parse_volume_percent(""))

    def test_missing_output_is_unknown(self):
        self.assertIsNone(tui.parse_volume_percent(None))

    def test_pactl_failure_message_is_unknown(self):
        self.assertIsNone(
            tui.parse_volume_percent("Failure: No such entity\n"))


class MuteTest(unittest.TestCase):
    def test_yes(self):
        self.assertIs(tui.parse_mute("Mute: yes\n"), True)

    def test_no(self):
        self.assertIs(tui.parse_mute("Mute: no\n"), False)

    def test_unknown_word_is_unknown(self):
        self.assertIsNone(tui.parse_mute("Mute: unknown\n"))

    def test_empty_output_is_unknown(self):
        self.assertIsNone(tui.parse_mute(""))

    def test_missing_output_is_unknown(self):
        self.assertIsNone(tui.parse_mute(None))


class UnitStateTest(unittest.TestCase):
    def test_active(self):
        self.assertEqual(tui.parse_unit_state("active\n"), "active")

    def test_inactive_is_still_an_answer(self):
        # is-active prints the state and exits non-zero; the state stands.
        self.assertEqual(tui.parse_unit_state("inactive\n"), "inactive")

    def test_empty_output_is_unknown(self):
        self.assertIsNone(tui.parse_unit_state(""))

    def test_missing_output_is_unknown(self):
        self.assertIsNone(tui.parse_unit_state(None))


class AdbDevicesTest(unittest.TestCase):
    def test_reads_device_unauthorized_and_offline(self):
        self.assertEqual(
            tui.parse_adb_device_states(ADB_DEVICES),
            [("R58M12345", "device"),
             ("emulator-5554", "unauthorized"),
             ("0123456789", "offline")])

    def test_empty_list_is_an_empty_list_not_unknown(self):
        self.assertEqual(
            tui.parse_adb_device_states("List of devices attached\n\n"), [])

    def test_missing_output_is_unknown(self):
        self.assertIsNone(tui.parse_adb_device_states(None))


class ModelPropsTest(unittest.TestCase):
    def test_value(self):
        self.assertEqual(tui.parse_model_props("Pixel 7\n"), "Pixel 7")

    def test_empty_output_is_unknown(self):
        self.assertIsNone(tui.parse_model_props(""))

    def test_blank_output_is_unknown(self):
        self.assertIsNone(tui.parse_model_props("\n"))

    def test_missing_output_is_unknown(self):
        self.assertIsNone(tui.parse_model_props(None))


class SinkInputTest(unittest.TestCase):
    def test_finds_the_scrcpy_stream_and_its_volume(self):
        inputs = tui.parse_sink_inputs(SINK_INPUTS_WITH_SCRCPY)
        stream = tui.find_sink_input(inputs)
        self.assertIsNotNone(stream)
        self.assertEqual(stream.index, "42")
        self.assertEqual(stream.sink, "3")
        self.assertEqual(stream.volume, 100)

    def test_without_a_scrcpy_stream(self):
        inputs = tui.parse_sink_inputs(SINK_INPUTS_NO_SCRCPY)
        self.assertEqual(len(inputs), 1)
        self.assertIsNone(tui.find_sink_input(inputs))

    def test_missing_listing_is_unknown(self):
        self.assertIsNone(tui.parse_sink_inputs(None))
        self.assertIsNone(tui.find_sink_input(None))

    def test_unparsable_volume_is_unknown(self):
        inputs = tui.parse_sink_inputs(SINK_INPUTS_NO_VOLUME)
        stream = tui.find_sink_input(inputs)
        self.assertIsNotNone(stream)
        self.assertIsNone(stream.volume)


class ReaderTest(unittest.TestCase):
    """The readers return None instead of substituting a plausible value."""

    def setUp(self):
        self._query = tui.query
        for key in ("vol", "mute", "svol", "sinputs", "devices", "model"):
            tui.CACHE.invalidate(key)

    def tearDown(self):
        tui.query = self._query
        for key in ("vol", "mute", "svol", "sinputs", "devices", "model"):
            tui.CACHE.invalidate(key)

    def test_failed_queries_leave_every_reader_unknown(self):
        tui.query = lambda *args, **kwargs: None
        self.assertIsNone(tui.source_volume())
        self.assertIsNone(tui.source_muted())
        self.assertIsNone(tui.stream_volume())
        self.assertIsNone(tui.bridge_unit_state())
        self.assertIsNone(tui.adb_devices())
        self.assertIsNone(tui.adb_model())

    def test_empty_queries_leave_every_reader_unknown(self):
        tui.query = lambda *args, **kwargs: ""
        self.assertIsNone(tui.source_volume())
        self.assertIsNone(tui.source_muted())
        self.assertIsNone(tui.stream_volume())
        self.assertIsNone(tui.bridge_unit_state())
        self.assertEqual(tui.adb_devices(), [])
        self.assertIsNone(tui.adb_model())

    def test_sink_index_distinguishes_absent_from_unreadable(self):
        tui.query = lambda *args, **kwargs: "5\tphonemic_sink\ts16le\n"
        self.assertEqual(tui.sink_index(), "5")
        tui.query = lambda *args, **kwargs: "1\tother_sink\ts16le\n"
        self.assertEqual(tui.sink_index(), "")
        tui.query = lambda *args, **kwargs: None
        self.assertIsNone(tui.sink_index())

    def test_bridge_stream_is_none_without_scrcpy(self):
        tui.query = lambda *args, **kwargs: SINK_INPUTS_NO_SCRCPY
        self.assertIsNone(tui.bridge_stream())
        tui.CACHE.invalidate("sinputs")
        tui.query = lambda *args, **kwargs: SINK_INPUTS_WITH_SCRCPY
        self.assertEqual(tui.bridge_stream().index, "42")


class MeterStateTest(unittest.TestCase):
    """S2/S3: no capture, not started yet and real silence never look alike."""

    def test_missing_capture_tool_says_so_and_has_no_level(self):
        state = tui.meter_state(False, False, 0, None)
        self.assertEqual(state.word, "NO CAPTURE TOOL")
        self.assertIsNone(state.level)
        self.assertFalse(state.measuring)

    def test_capture_not_started_is_no_signal(self):
        state = tui.meter_state(True, False, 0, None)
        self.assertEqual(state.word, "NO SIGNAL")
        self.assertIsNone(state.level)
        self.assertFalse(state.measuring)

    def test_started_but_no_window_yet_is_no_signal(self):
        state = tui.meter_state(True, True, 0, None)
        self.assertEqual(state.word, "NO SIGNAL")
        self.assertIsNone(state.level)
        self.assertFalse(state.measuring)

    def test_measured_floor_is_a_real_reading(self):
        # S3: a running capture that measures silence shows its measured value.
        state = tui.meter_state(True, True, 5, tui.FLOOR_DB)
        self.assertTrue(state.measuring)
        self.assertEqual(state.word, "")
        self.assertEqual(state.level, tui.FLOOR_DB)

    def test_measured_level_above_the_floor(self):
        state = tui.meter_state(True, True, 5, -12.5)
        self.assertTrue(state.measuring)
        self.assertEqual(state.level, -12.5)

    def test_a_stopped_capture_is_not_a_reading(self):
        # The last window of a capture that died is history, not a measurement.
        state = tui.meter_state(True, False, 5, -12.5)
        self.assertFalse(state.measuring)
        self.assertEqual(state.word, "NO SIGNAL")
        self.assertIsNone(state.level)

    def test_a_running_capture_without_a_peak_is_unknown(self):
        state = tui.meter_state(True, True, 3, None)
        self.assertFalse(state.measuring)
        self.assertIsNone(state.level)

    def test_no_capture_level_renders_as_the_dash_not_the_floor(self):
        # S2: through the existing formatter the column shows —, never -60.0 dB.
        state = tui.meter_state(False, False, 0, None)
        self.assertEqual(
            tui.fmt_value(state.level, "5.1f", " dB", 8), "—       ")

    def test_renderer_rows_are_blank_when_nothing_was_measured(self):
        # An all-floor bar is exactly what a silent room looks like: blank it.
        state = tui.meter_state(False, False, 0, None)
        self.assertEqual(tui.wave_row(state, [tui.FLOOR_DB] * 4, 10), " " * 10)
        self.assertEqual(tui.level_row(state, 20), " " * 20)

    def test_renderer_rows_keep_their_geometry_when_measuring(self):
        state = tui.meter_state(True, True, 5, tui.FLOOR_DB)
        self.assertEqual(len(tui.wave_row(state, [tui.FLOOR_DB] * 4, 10)), 10)
        self.assertEqual(tui.level_row(state, 20), "░" * 20)

    def test_a_measured_capture_renders_exactly_the_old_rows(self):
        # PRESERVE: when the capture is real, the panel draws what it always did.
        state = tui.meter_state(True, True, 5, -13.9)
        slots = [-60.0, -40.0, -20.0, -13.9]
        self.assertEqual(tui.wave_row(state, slots, 10),
                         tui.wave_line(slots, 10))
        self.assertEqual(tui.level_row(state, 20), tui.level_bar(-13.9, 20))


class UnknownFormatTest(unittest.TestCase):
    """S2: an unreadable value renders as an em dash, never as a number."""

    def test_unknown_is_an_em_dash(self):
        self.assertEqual(tui.fmt_value(None, "3d", "%", 4).strip(), "—")

    def test_unknown_keeps_the_numeric_column_width(self):
        self.assertEqual(len(tui.fmt_value(None, "3d", "%", 4)), 4)
        self.assertEqual(len(tui.fmt_value(None, "5.1f", " dB", 8)), 8)

    def test_known_value_keeps_its_number(self):
        self.assertEqual(tui.fmt_value(40, "3d", "%", 4), " 40%")
        self.assertEqual(tui.fmt_value(-60.0, "5.1f", " dB", 8), "-60.0 dB")


class AudioServerStateTest(unittest.TestCase):
    """S4: a dead audio server is its own state, with a cause and a fix."""

    def test_an_answer_means_the_server_is_up(self):
        state = tui.audio_state(PACTL_INFO)
        self.assertTrue(state.up)
        self.assertEqual((state.word, state.cause, state.fix), ("", "", ""))

    def test_no_answer_is_its_own_state(self):
        state = tui.audio_state(None)
        self.assertFalse(state.up)
        self.assertEqual(state.word, "AUDIO SERVER DOWN")

    def test_the_down_state_names_the_cause(self):
        self.assertIn("pipewire-pulse", tui.audio_state(None).cause)

    def test_the_down_state_prints_the_fixing_command(self):
        # S4: the box says what to run, in the owner's shape ("Arreglo: ...").
        fix = tui.audio_state(None).fix
        self.assertTrue(fix.startswith("Arreglo: "), fix)
        self.assertIn("systemctl --user restart pipewire-pulse", fix)

    def test_a_failure_message_is_not_an_answer(self):
        self.assertFalse(tui.audio_state(PACTL_INFO_DOWN).up)
        self.assertFalse(tui.audio_state("").up)


class AudioProbeTest(unittest.TestCase):
    """One cheap probe per refresh, and the server coming back is noticed."""

    def setUp(self):
        self._query = tui.query
        self._ttl = tui.AUDIO_TTL
        tui.CACHE.invalidate("audio")
        tui.AUDIO_TTL = 0.01

    def tearDown(self):
        tui.query = self._query
        tui.AUDIO_TTL = self._ttl
        tui.CACHE.invalidate("audio")

    def test_the_probe_is_cached_between_frames(self):
        calls: list[list[str]] = []
        tui.query = lambda cmd, **kw: calls.append(cmd) or PACTL_INFO
        for _ in range(3):
            tui.audio_probe()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:2], ["pactl", "info"])

    def test_the_server_coming_back_is_noticed_without_a_restart(self):
        answers = [None]
        tui.query = lambda cmd, **kw: answers[0]
        self.assertFalse(tui.audio_state(tui.audio_probe()).up)
        answers[0] = PACTL_INFO
        time.sleep(0.05)
        self.assertTrue(tui.audio_state(tui.audio_probe()).up)

    def test_a_dead_server_is_reported_again_after_the_answer_expires(self):
        answers = [PACTL_INFO]
        tui.query = lambda cmd, **kw: answers[0]
        self.assertTrue(tui.audio_state(tui.audio_probe()).up)
        answers[0] = None
        time.sleep(0.05)
        self.assertFalse(tui.audio_state(tui.audio_probe()).up)


class MicStateTest(unittest.TestCase):
    """S4/S8: what the VIRTUAL MICROPHONE box may claim."""

    def test_a_dead_audio_server_makes_the_box_say_so(self):
        state = tui.mic_state(tui.audio_state(None), None, True, "active")
        self.assertEqual(state.word, "AUDIO SERVER DOWN")
        self.assertNotEqual(state.word, "ACTIVE")
        self.assertEqual(state.tone, "bad")
        self.assertTrue(state.cause)
        self.assertTrue(state.fix)

    def test_a_dead_audio_server_wins_over_a_healthy_unit(self):
        # The bridge can look fine while pactl cannot ask the server anything.
        state = tui.mic_state(tui.audio_state(None), False, True, "active")
        self.assertEqual(state.word, "AUDIO SERVER DOWN")

    def test_a_live_server_keeps_the_old_state_words(self):
        # PRESERVE: ACTIVE / MUTED / the unit state read exactly as before (S8).
        up = tui.audio_state(PACTL_INFO)
        self.assertEqual(tui.mic_state(up, False, True, "active").word, "ACTIVE")
        self.assertEqual(tui.mic_state(up, True, True, "active").word, "MUTED")
        self.assertEqual(tui.mic_state(up, False, False, "inactive").word,
                         "INACTIVE")
        self.assertEqual(tui.mic_state(up, False, False, None).word, "—")

    def test_a_live_server_shows_the_service_line_not_a_cause(self):
        state = tui.mic_state(tui.audio_state(PACTL_INFO), False, True, "active")
        self.assertEqual((state.cause, state.fix), ("", ""))


class MicValueLineTest(unittest.TestCase):
    """S2: with the server down the gains are dashes, never 0%."""

    def test_unknown_values_are_dashes_not_zero_percent(self):
        line = tui.mic_value_line(None, None)
        self.assertNotIn("0%", line)
        self.assertIn("GAIN", line)
        self.assertIn("VOLUME", line)
        self.assertEqual(line.count(tui.UNKNOWN), 2)

    def test_known_values_keep_their_numbers(self):
        line = tui.mic_value_line(40, 100)
        self.assertIn(" 40%", line)
        self.assertIn("100%", line)


class ControlOutcomeTest(unittest.TestCase):
    """S7: a control that failed never reports success."""

    def test_a_working_write_keeps_the_success_wording(self):
        self.assertEqual(tui.control_outcome(True, True, "MUTED"),
                         tui.ControlResult(True, "MUTED"))
        self.assertEqual(tui.control_outcome(True, True, "unmuted").message,
                         "unmuted")

    def test_a_failed_write_reports_the_failure_not_the_success(self):
        result = tui.control_outcome(True, False, "MUTED")
        self.assertFalse(result.ok)
        self.assertNotIn("MUTED", result.message)
        self.assertIn("pactl failed", result.message)

    def test_the_failure_keeps_pactls_own_words(self):
        result = tui.control_outcome(True, False, "MUTED",
                                     "Connection failure: Connection refused")
        self.assertIn("Connection refused", result.message)

    def test_an_unreadable_value_is_refused_before_any_write(self):
        result = tui.control_outcome(False, False, "MUTED")
        self.assertFalse(result.ok)
        self.assertNotIn("MUTED", result.message)
        self.assertIn("no current value", result.message)

    def test_what_is_missing_can_be_named_by_the_caller(self):
        result = tui.control_outcome(False, False, "", "", "NO BRIDGE STREAM")
        self.assertEqual(result.message, "NO BRIDGE STREAM")


class MuteControlTest(unittest.TestCase):
    """S7: the mute toggle never writes a guess and never fakes success."""

    def setUp(self):
        self._query = tui.query
        self._write = tui.write_cmd
        tui.CACHE.invalidate("mute")

    def tearDown(self):
        tui.query = self._query
        tui.write_cmd = self._write
        tui.CACHE.invalidate("mute")

    def test_a_failed_write_is_reported(self):
        tui.query = lambda *a, **k: "Mute: no\n"
        tui.write_cmd = lambda cmd, **k: (False,
                                          "Connection failure: Connection refused")
        result = tui.toggle_mute()
        self.assertFalse(result.ok)
        self.assertIn("Connection refused", result.message)
        self.assertNotIn("MUTED", result.message)

    def test_an_unknown_mute_refuses_to_write_a_guess(self):
        tui.query = lambda *a, **k: None

        def refuse(*args, **kwargs):
            raise AssertionError("mute was written without a reading")

        tui.write_cmd = refuse
        result = tui.toggle_mute()
        self.assertFalse(result.ok)
        self.assertNotEqual(result.message, "MUTED")

    def test_a_working_write_keeps_the_old_wording(self):
        tui.query = lambda *a, **k: "Mute: no\n"
        tui.write_cmd = lambda cmd, **k: (True, "")
        self.assertEqual(tui.toggle_mute().message, "MUTED")
        tui.CACHE.invalidate("mute")
        tui.query = lambda *a, **k: "Mute: yes\n"
        self.assertEqual(tui.toggle_mute().message, "unmuted")

    def test_the_write_targets_the_phone_mic_source(self):
        calls: list[list[str]] = []
        tui.query = lambda *a, **k: "Mute: no\n"
        tui.write_cmd = lambda cmd, **k: (calls.append(cmd) or (True, ""))
        tui.toggle_mute()
        self.assertEqual(calls[0][1:], ["set-source-mute", tui.SOURCE, "yes"])


class VolumeControlTest(unittest.TestCase):
    """S7: the sliders report a failed write and never invent one."""

    def setUp(self):
        self._query = tui.query
        self._write = tui.write_cmd
        for key in ("vol", "svol", "sinputs"):
            tui.CACHE.invalidate(key)

    def tearDown(self):
        tui.query = self._query
        tui.write_cmd = self._write
        for key in ("vol", "svol", "sinputs"):
            tui.CACHE.invalidate(key)

    def test_a_failed_gain_write_is_reported(self):
        tui.write_cmd = lambda cmd, **k: (False, "Connection refused")
        result = tui.set_source_volume(55)
        self.assertFalse(result.ok)
        self.assertIn("Connection refused", result.message)

    def test_a_working_gain_write_reports_success_and_clamps(self):
        calls: list[list[str]] = []
        tui.write_cmd = lambda cmd, **k: (calls.append(cmd) or (True, ""))
        self.assertTrue(tui.set_source_volume(140).ok)
        self.assertEqual(calls[0][-1], "100%")

    def test_a_failed_volume_write_is_reported(self):
        tui.query = lambda *a, **k: SINK_INPUTS_WITH_SCRCPY
        tui.write_cmd = lambda cmd, **k: (False, "No such entity")
        result = tui.set_stream_volume(70)
        self.assertFalse(result.ok)
        self.assertIn("No such entity", result.message)

    def test_without_a_stream_nothing_is_written_and_nothing_is_claimed(self):
        tui.query = lambda *a, **k: SINK_INPUTS_NO_SCRCPY
        written: list[list[str]] = []
        tui.write_cmd = lambda cmd, **k: (written.append(cmd) or (True, ""))
        result = tui.set_stream_volume(70)
        self.assertFalse(result.ok)
        self.assertEqual(written, [])


# What `adb devices` answers in each of the situations S5 names.
ADB_ONE_READY_WIFI = [("192.168.100.99:39999", "device")]
ADB_ONE_READY_USB = [("R58M12345", "device")]
ADB_ONE_UNAUTHORIZED = [("emulator-5554", "unauthorized")]
ADB_ONE_OFFLINE = [("0123456789", "offline")]
ADB_NONE = []
ADB_UNUSABLE = None     # adb itself could not answer at all


def audio_up():
    return tui.audio_state(PACTL_INFO)


def audio_down():
    return tui.audio_state(None)


def rows_of(link):
    """The (label, value, tone) rows the PHONE LINK box shows."""
    return list(tui.link_rows(link))


def field(link, label):
    """The value in one labelled column of the box, or None when absent."""
    for row_label, value, _ in rows_of(link):
        if row_label == label:
            return value
    return None


class RoutingFactTest(unittest.TestCase):
    """The routing comparison itself, before any box decides what to say."""

    def test_the_stream_on_the_remap_sink_is_routed(self):
        self.assertTrue(tui.routing_ok("5", "5"))

    def test_the_stream_on_another_sink_is_not_routed(self):
        self.assertFalse(tui.routing_ok("5", "3"))

    def test_an_unknown_sink_never_matches(self):
        # None means the listing failed; "" means the sink is absent.
        self.assertFalse(tui.routing_ok(None, None))
        self.assertFalse(tui.routing_ok("", ""))
        self.assertFalse(tui.routing_ok("5", None))
        self.assertFalse(tui.routing_ok(None, "5"))


class LinkStateTest(unittest.TestCase):
    """S5: the phone link decides its own state from the facts."""

    def test_adb_unusable_is_its_own_state(self):
        link = tui.link_state(ADB_UNUSABLE, None, "active", audio_up(), False)
        self.assertEqual(link.word, "NO ADB")
        self.assertNotIn(link.word, ("CONNECTED", "DISCONNECTED"))
        self.assertEqual(link.tone, "bad")

    def test_adb_unusable_names_the_fixing_command(self):
        # S5, in the audio box's shape: the cause, then "Arreglo: <command>".
        link = tui.link_state(ADB_UNUSABLE, None, "active", audio_up(), False)
        self.assertTrue(link.cause, link.cause)
        self.assertTrue(link.fix.startswith("Arreglo: "), link.fix)
        self.assertIn("android-tools", link.fix)

    def test_an_unauthorized_device_is_not_a_missing_device(self):
        link = tui.link_state(ADB_ONE_UNAUTHORIZED, None, "active",
                              audio_up(), False)
        self.assertEqual(link.word, "UNAUTHORIZED")
        self.assertNotEqual(link.word, "DISCONNECTED")
        self.assertTrue(link.cause)
        self.assertTrue(link.fix.startswith("Arreglo: "), link.fix)

    def test_an_offline_device_is_not_a_missing_device(self):
        link = tui.link_state(ADB_ONE_OFFLINE, None, "active", audio_up(),
                              False)
        self.assertEqual(link.word, "OFFLINE")
        self.assertNotEqual(link.word, "DISCONNECTED")
        self.assertTrue(link.cause)
        self.assertTrue(link.fix.startswith("Arreglo: "), link.fix)

    def test_the_three_situations_never_look_alike(self):
        words = [
            tui.link_state(ADB_UNUSABLE, None, "active", audio_up(), False).word,
            tui.link_state(ADB_ONE_UNAUTHORIZED, None, "active", audio_up(),
                           False).word,
            tui.link_state(ADB_ONE_OFFLINE, None, "active", audio_up(),
                           False).word,
            tui.link_state(ADB_NONE, None, "active", audio_up(), False).word,
        ]
        self.assertEqual(len(set(words)), 4, words)

    def test_every_fix_offered_is_its_own(self):
        fixes = [
            tui.link_state(ADB_UNUSABLE, None, "active", audio_up(), False).fix,
            tui.link_state(ADB_ONE_UNAUTHORIZED, None, "active", audio_up(),
                           False).fix,
            tui.link_state(ADB_ONE_OFFLINE, None, "active", audio_up(),
                           False).fix,
        ]
        self.assertEqual(len(set(fixes)), 3, fixes)
        for fix in fixes:
            self.assertTrue(fix.startswith("Arreglo: "), fix)

    def test_no_device_attached_keeps_the_old_word(self):
        link = tui.link_state(ADB_NONE, None, "active", audio_up(), False)
        self.assertEqual(link.word, "DISCONNECTED")

    def test_a_usable_device_keeps_the_old_word(self):
        # PRESERVE: a phone that works still reads CONNECTED, in the ok tone.
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", "active",
                              audio_up(), True)
        self.assertEqual(link.word, "CONNECTED")
        self.assertEqual(link.tone, "ok")
        self.assertEqual((link.cause, link.fix), ("", ""))

    def test_a_usb_device_is_named_as_usb(self):
        link = tui.link_state(ADB_ONE_READY_USB, "Pixel 7", "active",
                              audio_up(), False)
        self.assertEqual(link.transport, "USB")
        self.assertEqual(link.address, "R58M12345")

    def test_a_wireless_device_keeps_its_host_as_the_address(self):
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", "active",
                              audio_up(), True)
        self.assertEqual(link.transport, "Wi-Fi")
        self.assertEqual(link.address, "192.168.100.99")

    def test_a_device_that_is_not_usable_still_reports_where_it_is(self):
        link = tui.link_state([("192.168.100.99:39999", "offline")], None,
                              "active", audio_up(), False)
        self.assertEqual(link.transport, "Wi-Fi")
        self.assertEqual(link.address, "192.168.100.99")

    def test_a_state_this_module_does_not_know_gets_adbs_own_word(self):
        link = tui.link_state([("R58M12345", "recovery")], None, "active",
                              audio_up(), False)
        self.assertEqual(link.word, "RECOVERY")
        self.assertNotIn(link.word, ("CONNECTED", "DISCONNECTED"))


class LinkBoxTest(unittest.TestCase):
    """S5/S8: what the PHONE LINK box prints, in the rows it already has."""

    def test_a_missing_model_is_unknown_not_a_dash(self):
        link = tui.link_state(ADB_ONE_READY_WIFI, None, "active", audio_up(),
                              True)
        self.assertEqual(field(link, "device"), tui.UNKNOWN)

    def test_a_missing_model_over_a_dead_link_is_unknown_too(self):
        link = tui.link_state(ADB_ONE_UNAUTHORIZED, None, "active", audio_up(),
                              False)
        self.assertEqual(field(link, "device"), tui.UNKNOWN)
        for _, value, _ in rows_of(link):
            self.assertNotEqual(value.strip(), "-")

    def test_a_known_model_is_shown(self):
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", "active",
                              audio_up(), True)
        self.assertEqual(field(link, "device"), "Redmi Note 13")

    def test_an_unreadable_unit_state_is_unknown_not_a_state_word(self):
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", None,
                              audio_up(), True)
        self.assertEqual(field(link, "service"), tui.UNKNOWN)
        for _, value, _ in rows_of(link):
            self.assertNotIn(value.strip().lower(), ("unknown", "none"))

    def test_a_readable_unit_state_is_shown_as_itself(self):
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", "active",
                              audio_up(), True)
        self.assertEqual(field(link, "service"), "active")

    def test_the_link_words_reach_the_box(self):
        boxes = [
            rows_of(tui.link_state(ADB_UNUSABLE, None, None, audio_up(),
                                     False)),
            rows_of(tui.link_state(ADB_ONE_UNAUTHORIZED, None, None,
                                     audio_up(), False)),
            rows_of(tui.link_state(ADB_ONE_OFFLINE, None, None, audio_up(),
                                     False)),
            rows_of(tui.link_state(ADB_NONE, None, None, audio_up(), False)),
        ]
        states = [box[0][1] for box in boxes]
        self.assertEqual(len(set(states)), 4, states)

    def test_the_box_keeps_its_seven_rows_in_every_situation(self):
        # S8: the words change, the geometry of the box does not.
        situations = [
            (ADB_ONE_READY_WIFI, "Redmi Note 13", "active", True),
            (ADB_NONE, None, None, False),
            (ADB_UNUSABLE, None, None, False),
            (ADB_ONE_UNAUTHORIZED, None, None, False),
            (ADB_ONE_OFFLINE, None, None, False),
            ([("R58M12345", "recovery")], None, "failed", False),
        ]
        for devices, model, unit, routed in situations:
            for audio in (audio_up(), audio_down()):
                link = tui.link_state(devices, model, unit, audio, routed)
                self.assertEqual(len(rows_of(link)), 7,
                                 (devices, audio, rows_of(link)))

    def test_a_connected_link_still_prints_the_old_fields(self):
        # PRESERVE: state, device, transport, address and buffer read as before.
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", "active",
                              audio_up(), True)
        values = [value for _, value, _ in rows_of(link)]
        self.assertIn("CONNECTED", values)
        self.assertIn("Redmi Note 13", values)
        self.assertIn("Wi-Fi", values)
        self.assertIn("192.168.100.99", values)
        self.assertTrue(any(v.endswith(" ms") for v in values), values)

    def test_routing_is_reported_when_the_server_answers(self):
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", "active",
                              audio_up(), True)
        self.assertTrue(link.routing)
        self.assertIn("routing ok", [v for _, v, _ in rows_of(link)])

    def test_a_stream_elsewhere_is_reported_as_wrong(self):
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", "active",
                              audio_up(), False)
        self.assertFalse(link.routing)
        self.assertIn("routing WRONG", [v for _, v, _ in rows_of(link)])

    def test_no_routing_claim_while_the_audio_server_is_silent(self):
        # S5: WRONG is a claim about routing; a silent server cannot support it.
        link = tui.link_state(ADB_ONE_READY_WIFI, "Redmi Note 13", "active",
                              audio_down(), True)
        self.assertIsNone(link.routing)
        values = [v for _, v, _ in rows_of(link)]
        self.assertIn(f"routing {tui.UNKNOWN}", values)
        self.assertNotIn("routing WRONG", values)
        self.assertNotIn("routing ok", values)


class OnceSnapshotTest(unittest.TestCase):
    """S5/S6: the one-shot snapshot says the same words as the panel."""

    class FakeMeter:
        """A meter that has already measured nothing and needs no capture."""

        def __init__(self):
            self.available = True
            self.peak_db = None
            self.rms_db = None
            self.windows = 4
            self.running = False

        def start(self):
            pass

        def stop(self):
            pass

        def snapshot(self):
            return [tui.FLOOR_DB] * tui.WAVE_SLOTS

    def setUp(self):
        self.saved = {name: getattr(tui, name) for name in (
            "LevelMeter", "adb_devices", "adb_model", "bridge_pids",
            "bridge_unit_state", "sink_index", "bridge_stream",
            "source_volume", "stream_volume", "source_muted", "audio_probe")}
        tui.LevelMeter = self.FakeMeter
        tui.adb_model = lambda: None
        tui.bridge_pids = lambda: []
        tui.bridge_unit_state = lambda: "active"
        tui.sink_index = lambda: "5"
        tui.bridge_stream = lambda: None
        tui.source_volume = lambda: None
        tui.stream_volume = lambda: None
        tui.source_muted = lambda: None
        tui.audio_probe = lambda: PACTL_INFO

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(tui, name, value)

    def snapshot(self, devices):
        tui.adb_devices = lambda: devices
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            tui.once()
        return buffer.getvalue()

    def test_an_unusable_adb_is_named_in_the_snapshot(self):
        text = self.snapshot(None)
        self.assertIn("NO ADB", text)
        self.assertIn("Arreglo: ", text)
        self.assertNotIn("DISCONNECTED", text)

    def test_an_unauthorized_device_is_named_in_the_snapshot(self):
        text = self.snapshot(ADB_ONE_UNAUTHORIZED)
        self.assertIn("UNAUTHORIZED", text)
        self.assertNotIn("CONNECTED", text)
        self.assertNotIn("DISCONNECTED", text)

    def test_an_offline_device_is_named_in_the_snapshot(self):
        text = self.snapshot(ADB_ONE_OFFLINE)
        self.assertIn("OFFLINE", text)
        self.assertNotIn("DISCONNECTED", text)

    def test_no_device_keeps_the_disconnected_snapshot(self):
        text = self.snapshot(ADB_NONE)
        self.assertIn("DISCONNECTED", text)

    def test_the_snapshot_never_prints_a_dash_for_a_missing_model(self):
        # PRESERVE: the label column keeps its words, but "-" is not a value.
        text = self.snapshot(ADB_ONE_UNAUTHORIZED)
        for line in text.splitlines():
            if "device" in line:
                self.assertNotIn("-", line.replace("device", ""), line)


if __name__ == "__main__":
    unittest.main()
