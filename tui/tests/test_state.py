#!/usr/bin/env python3
"""Unit tests for the read layer and the state parsers of the panel.

The parsers are pure: they take text (or None when the query itself failed) and
return a value, or None when the value could not be read. A failed read must
never look like a plausible number. Run with:

    python3 -m unittest discover -s tui/tests
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import phone_mic_tui as tui  # noqa: E402  (sys.path is prepared above)


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


if __name__ == "__main__":
    unittest.main()
