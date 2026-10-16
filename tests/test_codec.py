import json
from pathlib import Path
import random
import unittest

from froeling_bridge.codec import Frame, StreamDecoder, checksum, decode_frame, encode_frame
from froeling_bridge.errors import (
    ChecksumError, FrameError, InvalidEscape, InvalidLength, InvalidStart,
    TruncatedFrame, ValidationError,
)

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "docs/protocol-vectors.json").read_text())


class CodecTests(unittest.TestCase):
    def test_all_vectors_match_original_cpp_checked_bytes(self):
        for case in VECTORS:
            with self.subTest(case=case["name"]):
                expected = bytes.fromhex(case["wire"])
                frame = Frame(int(case["command"], 16), bytes.fromhex(case["payload"]))
                self.assertEqual(encode_frame(frame), expected)
                self.assertEqual(decode_frame(expected), frame)
                logical = b"\x02\xfd" + (len(frame.payload) + 1).to_bytes(2, "big") + bytes([frame.command]) + frame.payload
                self.assertEqual(checksum(logical), int(case["checksum"], 16))

    def test_every_split_of_every_vector_including_inside_escapes(self):
        for case in VECTORS:
            data = bytes.fromhex(case["wire"])
            expected = decode_frame(data)
            for split in range(len(data) + 1):
                with self.subTest(case=case["name"], split=split):
                    parser = StreamDecoder()
                    self.assertEqual(parser.feed(data[:split]) + parser.feed(data[split:]), [expected])
                    parser.finish()

    def test_each_byte_value_in_payload_and_one_byte_chunks(self):
        for value in range(256):
            frame = Frame(value, bytes([value, 2, 43, 254, 17, 19]))
            parser = StreamDecoder()
            decoded = []
            for byte in encode_frame(frame):
                decoded.extend(parser.feed(bytes([byte])))
            parser.finish()
            self.assertEqual(decoded, [frame])

    def test_multiple_frames_and_random_chunking(self):
        rng = random.Random(3200)
        expected = [Frame(rng.randrange(256), bytes(rng.randrange(256) for _ in range(rng.randrange(255)))) for _ in range(40)]
        wire = b"".join(encode_frame(frame) for frame in expected)
        parser = StreamDecoder()
        actual = []
        while wire:
            count = rng.randrange(1, 30)
            actual.extend(parser.feed(wire[:count]))
            wire = wire[count:]
        parser.finish()
        self.assertEqual(actual, expected)

    def test_maximum_payload_and_length_excludes_command_and_escaping(self):
        frame = Frame(0x22, b"\x02" * 254)
        self.assertEqual(decode_frame(encode_frame(frame)), frame)
        self.assertTrue(encode_frame(frame).startswith(b"\x02\xfd\x00\xff\x22"))
        with self.assertRaises(ValidationError):
            Frame(0x22, b"x" * 255)

    def test_invalid_escapes_and_error_reset(self):
        valid = bytes.fromhex("02 FD 00 01 37 5B")
        for pair in [b"\x02\x01", b"\x2b\x01", b"\xfe\x01"]:
            parser = StreamDecoder()
            with self.assertRaises(InvalidEscape):
                parser.feed(b"\x02\xfd" + pair)
            self.assertFalse(parser.has_partial)
            self.assertEqual(parser.feed(valid), [Frame(0x37)])

    def test_every_truncated_prefix_is_detected_at_end(self):
        data = bytes.fromhex(VECTORS[-1]["wire"])
        for end in range(1, len(data)):
            parser = StreamDecoder()
            parser.feed(data[:end])
            with self.assertRaises(TruncatedFrame):
                parser.finish()

    def test_corrupt_checksum(self):
        with self.assertRaises(ChecksumError):
            decode_frame(bytes.fromhex("02 FD 00 03 55 12 34 90"))

    def test_impossible_lengths_are_rejected_before_payload(self):
        for length in [b"\x00\x00", b"\x01\x00", b"\xff\xff"]:
            with self.assertRaises(InvalidLength):
                StreamDecoder().feed(b"\x02\xfd" + length)

    def test_unexpected_prefix_and_trailing_noise_are_not_silently_skipped(self):
        with self.assertRaises(InvalidStart):
            decode_frame(b"noise" + encode_frame(Frame(0x37)))
        with self.assertRaises(InvalidStart):
            decode_frame(encode_frame(Frame(0x37)) + b"x")

    def test_single_frame_decode_rejects_empty_or_multiple(self):
        for data in [b"", encode_frame(Frame(1)) + encode_frame(Frame(2))]:
            with self.assertRaises(InvalidLength):
                decode_frame(data)

    def test_invalid_commands_and_mutable_payloads(self):
        for value in [-1, 256, True, 1.2, "55"]:
            with self.assertRaises(ValidationError):
                Frame(value)
        with self.assertRaises(ValidationError):
            Frame(1, bytearray(b"x"))
