from dataclasses import replace
from datetime import datetime, time, timezone
from decimal import Decimal
import json
from pathlib import Path
import unittest

from froeling_bridge.errors import MalformedPayload, ValidationError
from froeling_bridge.messages import (
    MenuItem, Parameter, ParameterType, TimeRange, TimeRanges, ValueSpec,
    address_bytes, measurement, parse_datetime, parse_error, parse_firmware,
    parse_io, parse_menu_item, parse_parameter, parse_parameter_ack,
    parse_range, parse_status, parse_time, parse_time_ranges, parse_value_spec,
)


class MessageTests(unittest.TestCase):
    def parameter(self, **overrides):
        parameter = Parameter(0x1234, 650, 20, 90, 60, 10, 1, b"\xb0", 2, 3, -123, 4)
        return replace(parameter, **overrides)

    def test_parse_fixed_parameter_vector_with_unscaled_limits(self):
        vectors = json.loads((Path(__file__).resolve().parents[1] / "docs/protocol-vectors.json").read_text())
        p = parse_parameter(bytes.fromhex(next(v["payload"] for v in vectors if v["name"] == "response-parameter-synthetic")))
        self.assertEqual(p.value, Decimal("65"))
        self.assertEqual((p.minimum, p.maximum, p.default), (20, 90, 60))
        self.assertEqual(p.unit, "°C")
        self.assertEqual(p.to_payload().hex(" ").upper(), next(v["payload"] for v in vectors if v["name"] == "response-parameter-synthetic"))

    def test_unknown_fields_and_negative_parameter_values_preserved(self):
        p = self.parameter(raw_value=-125, minimum=-30, factor=10)
        self.assertEqual(parse_parameter(p.to_payload()), p)
        self.assertEqual(p.value, Decimal("-12.5"))
        self.assertEqual(p.target_raw("-12.6"), -126)

    def test_zero_parameter_factor_is_normalized_only_for_interpretation(self):
        p = self.parameter(raw_value=65, factor=0)
        self.assertEqual(p.value, Decimal(65))
        self.assertEqual(p.target_raw(66), 66)
        self.assertEqual(parse_parameter(p.to_payload()).factor, 0)

    def test_every_word_signed_and_unsigned_interpretation(self):
        for raw in range(65536):
            signed = raw if raw < 32768 else raw - 65536
            self.assertEqual(measurement(raw, 1, 1), raw)
            self.assertEqual(measurement(raw, 1, 2), signed)
        self.assertEqual(measurement(0xFFF4, 10, 2), Decimal("-1.2"))
        self.assertEqual(measurement(9, 2, 1), Decimal("4.5"))

    def test_zero_measurement_factor_and_invalid_metadata_rejected(self):
        for raw, factor, kind in [(1, 0, 1), (-1, 1, 1), (1, -1, 1), (1, 1, True)]:
            with self.assertRaises(ValidationError):
                measurement(raw, factor, kind)

    def test_numeric_inputs_limits_precision_and_representability(self):
        p = self.parameter()
        for value in [20, Decimal("67.5"), "90", 67.5]:
            self.assertEqual(p.target_raw(value), int(Decimal(str(value)) * 10))
        for value in [True, None, "", "-", "67,5", "NaN", "Infinity", 19.9, 90.1, "67.55"]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                p.target_raw(value)
        with self.assertRaises(ValidationError):
            self.parameter(factor=2).target_raw("65.1")
        with self.assertRaises(ValidationError):
            self.parameter(factor=255, minimum=0, maximum=32767).target_raw(32767)
        with self.assertRaises(ValidationError):
            self.parameter(minimum=90, maximum=20).target_raw(65)

    def test_boolean_and_single_time_parameters_are_distinct(self):
        p = self.parameter(raw_value=0, minimum=0, maximum=1, factor=1, digits=0)
        self.assertEqual(p.target_raw(True, ParameterType.BOOLEAN), 1)
        for value in [1, "ja", "true"]:
            with self.assertRaises(ValidationError):
                p.target_raw(value, ParameterType.BOOLEAN)
        p = self.parameter(minimum=0, maximum=1439, factor=1)
        self.assertEqual(p.target_raw("06:19", ParameterType.TIME), 379)
        with self.assertRaises(ValidationError):
            p.target_raw(123, 0x0B)

    def test_time_programs_have_ten_minute_resolution_without_rounding(self):
        interval = TimeRange(time(6, 10), time(8, 50))
        self.assertEqual(interval.to_bytes(), bytes([61, 85]))
        self.assertEqual(parse_range(interval.to_bytes()), interval)
        self.assertEqual(parse_range(b"\xff\xff"), TimeRange())
        for values in [(time(6, 19), time(8)), (None, time(8))]:
            with self.assertRaises(ValidationError):
                TimeRange(*values)
        for raw in [b"\xff\x00", b"\x09\x00", b"\xec\xeb"]:
            with self.assertRaises(MalformedPayload):
                parse_range(raw)
        # Overnight interpretation is not invented here: valid endpoints are preserved.
        self.assertEqual(parse_range(TimeRange(time(22), time(6)).to_bytes()).end, time(6))

    def test_strict_time_inputs(self):
        self.assertEqual(parse_time("23:59"), time(23, 59))
        for value in ["24:00", "6:00", "06:60", "nn:nn", time(6, 0, 1), time(6, tzinfo=timezone.utc)]:
            with self.assertRaises(ValidationError):
                parse_time(value)

    def test_time_list_and_write_reply_differ_in_address_layout(self):
        times = TimeRanges(0x38, (TimeRange(time(6), time(8)),) + (TimeRange(),) * 3)
        self.assertEqual(parse_time_ranges(times.list_payload()), times)
        ack = parse_time_ranges(b"\x00" + times.write_payload(), True)
        self.assertEqual(ack.address, times.address)
        self.assertEqual(ack.ranges, times.ranges)
        self.assertEqual(times.write_payload(), bytes.fromhex("00 38 3C 50 FF FF FF FF FF FF"))
        with self.assertRaises(MalformedPayload):
            parse_time_ranges(bytes.fromhex("00 FF FF") + b"\xff" * 8, True)

    def test_menu_unknown_metadata_type_and_raw_text_preserved(self):
        item = MenuItem(0xFE, 1, 2, 0x1234, b"\x01Gr\xf6sse\x00", 9, bytes(range(18)), 0xFE11, 7)
        self.assertEqual(parse_menu_item(item.to_payload()), item)
        self.assertEqual(item.description, "Grösse")
        self.assertIsNone(parse_menu_item(b"\x00"))

    def test_value_specs_preserve_factor_datatype_and_fallback_unit(self):
        spec = ValueSpec(0x1234, 2, 1, b"  ", b"Temperatur [C]")
        self.assertEqual(parse_value_spec(spec.to_payload()), spec)
        self.assertEqual(spec.unit, "C")
        self.assertIsNone(parse_value_spec(b"\x00"))

    def test_status_io_and_ack_lengths(self):
        self.assertEqual(parse_status(b"\x01\x02Auto;Bereit").state_text, "Bereit")
        self.assertEqual(parse_io(b"\xff\x01").state, 1)
        self.assertEqual(parse_parameter_ack(bytes.fromhex("12 34 FF F4")).raw_value, -12)
        with self.assertRaises(MalformedPayload):
            parse_status(b"\x01\x02no separator")

    def test_payloads_reject_short_extra_and_malformed_list_termination(self):
        for parser, payload in [(parse_parameter, b"x" * 17), (parse_parameter, b"x" * 19),
                                (parse_parameter_ack, b"x" * 3), (parse_io, b"x"),
                                (parse_value_spec, b"\x00x"), (parse_menu_item, b"\x01x"),
                                (parse_error, b"\x00x")]:
            with self.subTest(parser=parser.__name__), self.assertRaises(MalformedPayload):
                parser(payload)

    def test_datetime_validation_and_unknown_version_tail(self):
        raw = bytes([59, 30, 12, 29, 2, 24])
        self.assertEqual(parse_datetime(raw), datetime(2024, 2, 29, 12, 30, 59))
        info = parse_firmware(bytes.fromhex("50 04 05 20") + raw[:5] + b"\x04" + raw[5:] + b"\xaa\xbb")
        self.assertEqual(info.version_text, "50.04.05.20")
        self.assertEqual(info.extra, b"\xaa\xbb")
        for value in [bytes([0, 0, 0, 30, 2, 24]), bytes([60, 0, 0, 1, 1, 24])]:
            with self.assertRaises(MalformedPayload):
                parse_datetime(value)

    def test_invalid_addresses(self):
        for address in [-1, 65535, 65536, True]:
            with self.assertRaises(ValidationError):
                address_bytes(address)
