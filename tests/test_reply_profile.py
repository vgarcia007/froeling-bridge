import json
from pathlib import Path
import unittest

from froeling_bridge.client import ReadOnlyHeatingClient
from froeling_bridge.codec import Frame, StreamDecoder, encode_frame
from froeling_bridge.errors import UnexpectedReply, ListLimitExceeded
from froeling_bridge.messages import Command, TimeRange, TimeRanges
from datetime import time
from froeling_bridge.session import ProtocolSession
from froeling_bridge.serial_transport import ReadOnlyTransport
from froeling_bridge.simulator import MemoryTransport


class ObservedTimeReplyTests(unittest.TestCase):
    def profile(self):
        path = Path(__file__).resolve().parents[1] / "deploy/heating-reply-profile.json"
        return {
            int(k, 16): tuple(int(v, 16) for v in values)
            for k, values in json.loads(path.read_text()).items()
        }

    def transport(self, reply=0x42):
        def wire_filter(request, wire):
            if request.command != Command.TIMES_NEXT:
                return wire
            frames = StreamDecoder().feed(wire)
            return b"".join(encode_frame(Frame(reply, f.payload)) for f in frames)

        return MemoryTransport(wire_filter=wire_filter, read_chunk_size=1, max_write=2)

    def test_observed_next_reply_is_accepted_with_strict_profile(self):
        transport = self.transport()
        client = ReadOnlyHeatingClient(
            ProtocolSession(ReadOnlyTransport(transport)), reply_commands=self.profile()
        )
        self.assertEqual(
            [item.address for item in client.get_time_ranges()], [0x38, 0xDF]
        )
        self.assertEqual(
            [request.command for request in transport.requests], [0x22, 0x42, 0x43]
        )
        self.assertFalse(client.session.broken)

    def test_old_profile_reproduces_the_observed_failure(self):
        client = ReadOnlyHeatingClient(ProtocolSession(self.transport()))
        with self.assertRaises(UnexpectedReply):
            client.get_time_ranges()

    def test_unrelated_reply_is_still_rejected(self):
        client = ReadOnlyHeatingClient(
            ProtocolSession(self.transport(0x41)), reply_commands=self.profile()
        )
        with self.assertRaises(UnexpectedReply):
            client.get_time_ranges()
        self.assertTrue(client.session.broken)

    def test_identical_first_entry_can_repeat_before_next_address(self):
        replies = iter([0, 0, 1, 0xDF])

        def filter_wire(request, wire):
            if request.command in (Command.TIMES_FIRST, Command.TIMES_NEXT):
                item = TimeRanges(next(replies), (TimeRange(),) * 4)
                return encode_frame(Frame(0x42, item.list_payload()))
            return wire

        transport = MemoryTransport(wire_filter=filter_wire)
        client = ReadOnlyHeatingClient(
            ProtocolSession(ReadOnlyTransport(transport)), reply_commands=self.profile()
        )
        self.assertEqual(
            [item.address for item in client.get_time_ranges()], [0, 1, 0xDF]
        )
        self.assertEqual(transport.requests[0].payload, b"Tescht ;-)")

    def test_endless_identical_responses_remain_bounded(self):
        def filter_wire(request, wire):
            if request.command in (Command.TIMES_FIRST, Command.TIMES_NEXT):
                return encode_frame(
                    Frame(0x42, TimeRanges(0, (TimeRange(),) * 4).list_payload())
                )
            return wire

        transport = MemoryTransport(wire_filter=filter_wire)
        client = ReadOnlyHeatingClient(
            ProtocolSession(transport), reply_commands=self.profile()
        )
        with self.assertRaises(ListLimitExceeded):
            client.get_time_ranges()
        self.assertEqual(len(transport.requests), 256)  # one CHECK + 255 list reads
        self.assertTrue(client.session.broken)

    def test_repeated_address_updates_the_entry_as_p4d_does(self):
        entries = iter(
            [
                TimeRanges(0, (TimeRange(),) * 4),
                TimeRanges(0, (TimeRange(time(12), time(13)),) + (TimeRange(),) * 3),
                TimeRanges(0xDF, (TimeRange(),) * 4),
            ]
        )

        def filter_wire(request, wire):
            if request.command in (Command.TIMES_FIRST, Command.TIMES_NEXT):
                return encode_frame(Frame(0x42, next(entries).list_payload()))
            return wire

        transport = MemoryTransport(wire_filter=filter_wire)
        client = ReadOnlyHeatingClient(
            ProtocolSession(ReadOnlyTransport(transport)), reply_commands=self.profile()
        )
        result = client.get_time_ranges()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].ranges[0], TimeRange(time(12), time(13)))
