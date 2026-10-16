from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import unittest

from froeling_bridge.__main__ import main


class CLITests(unittest.TestCase):
    def invoke(self, args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = main(args)
        return status, out.getvalue(), err.getvalue()

    def test_demo_reports_simulation_and_verified_virtual_changes(self):
        code, out, err = self.invoke(["demo"])
        self.assertEqual((code, err), (0, ""))
        result = json.loads(out)
        self.assertEqual(result["mode"], "offline-simulator")
        self.assertFalse(result["hardware_verified"])
        self.assertEqual(result["parameter_change"]["after"], "67.5")
        self.assertEqual(result["parameter_change"]["status"], "confirmed")
        self.assertEqual(result["time_program_change"]["status"], "confirmed")

    def test_encode_and_decode_original_vector(self):
        code, out, _ = self.invoke(["encode", "55", "12 34"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "02 FD 00 03 55 12 34 91")
        code, decoded, _ = self.invoke(["decode", out.strip()])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(decoded), {"command": "55", "payload": "12 34"})

    def test_invalid_hex_or_checksum_returns_error_without_traceback(self):
        for args in [["decode", "invalid"], ["decode", "02 FD 00 03 55 12 34 90"], ["encode", "100"]]:
            code, out, err = self.invoke(args)
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("Error:", err)
            self.assertNotIn("Traceback", err)
