import importlib.util
from pathlib import Path
import tempfile
import unittest

from froeling_bridge.codec import Frame, encode_frame

spec = importlib.util.spec_from_file_location(
    "trace_analysis",
    Path(__file__).resolve().parents[1] / "docs/tools/analyze_serial_trace.py",
)
trace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trace)


class TraceAnalysisTests(unittest.TestCase):
    def test_fragmented_frames_report_only_protocol_identity_mismatches(self):
        request = encode_frame(Frame(0x55, bytes.fromhex("1234")))
        reply = encode_frame(Frame(0x55, bytes.fromhex("001235") + b"PRIVATE"))
        frames = [
            (0, "TX", request[:3]),
            (1, "TX", request[3:]),
            (2, "RX", reply[:4]),
            (3, "RX", reply[4:]),
            (4, "TX", encode_frame(Frame(0x51))),
            (5, "RX", encode_frame(Frame(0x41))),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture"
            path.write_text(
                "".join(
                    f"{stamp} {direction} {data.hex()}\n"
                    for stamp, direction, data in frames
                )
            )
            result = trace.analyze(path)
        self.assertEqual(result["heating_write_frames"], 0)
        self.assertEqual(
            [f["problem"] for f in result["findings"]],
            ["parameter_address", "reply_command"],
        )
        self.assertEqual(result["unanswered"], 0)
        self.assertNotIn("PRIVATE", str(result))
        self.assertFalse(any(result["partial_frames"].values()))
