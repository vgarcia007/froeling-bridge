from datetime import time
import unittest

from froeling_bridge.errors import ValidationError
from froeling_bridge.messages import (
    TimeRange,
    RawTimeRange,
    parse_time_ranges,
    read_range,
)
from froeling_bridge.service import public


class ReadTimeDataTests(unittest.TestCase):
    def test_all_controller_byte_pairs_are_preserved_without_input_validation(self):
        for word in range(65536):
            raw = word.to_bytes(2, "big")
            self.assertEqual(read_range(raw).to_bytes(), raw)

    def test_p4d_formats_midnight_and_mixed_unset_bytes_independently(self):
        for raw, start, end in [
            (b"\x00\xf0", "00:00", "24:00"),
            (b"\xff\x00", "25:50", "00:00"),
            (b"\x09\x00", "00:90", "00:00"),
        ]:
            item = read_range(raw)
            self.assertIsInstance(item, RawTimeRange)
            self.assertEqual((public(item)["start"], public(item)["end"]), (start, end))
        self.assertEqual(public(read_range(b"\xff\xff")), dict(start=None, end=None))

    def test_full_read_reply_preserves_raw_slots(self):
        payload = b"\x01\x00\x38" + b"\x00\xf0\xff\x00\xff\xff\x3c\x50"
        result = parse_time_ranges(payload)
        self.assertEqual(result.list_payload(), payload)
        self.assertEqual(result.ranges[3], TimeRange(time(6), time(8)))

    def test_write_input_validation_remains_strict(self):
        for start, end in [("24:00", "01:00"), (None, time(8)), (time(6, 1), time(8))]:
            with self.assertRaises(ValidationError):
                TimeRange(start, end)

    def test_offline_partial_update_preserves_other_raw_controller_slots(self):
        from dataclasses import replace
        from froeling_bridge.client import HeatingClient
        from froeling_bridge.simulator import MemoryTransport, demo_heater
        from froeling_bridge.session import ProtocolSession

        heater = demo_heater()
        before = heater.time_programs[0x38]
        heater.time_programs[0x38] = replace(
            before, ranges=(read_range(b"\x00\xf0"),) + before.ranges[1:]
        )
        client = HeatingClient(ProtocolSession(MemoryTransport(heater=heater)))
        result = client.set_time_range(0x38, 1, TimeRange(time(12), time(13)))
        self.assertEqual(result.current.ranges[0].to_bytes(), b"\x00\xf0")
        self.assertEqual(result.current.ranges[1], TimeRange(time(12), time(13)))
