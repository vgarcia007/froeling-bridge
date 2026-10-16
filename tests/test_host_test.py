from pathlib import Path
import tempfile
import unittest

from froeling_bridge.host_test import (
    read_report,
    Coordinator,
    TestControlError,
    P4D,
    TEST,
    TIMER,
)


class FakeSystem:
    def __init__(self):
        self.units = {P4D: True, TEST: False, TIMER: False}
        self.events = []
        self.free = True
        self.fail_arm = False
        self.fail_start = False
        self.confirm = True

    def active(self, unit):
        return self.units[unit]

    def enabled(self, unit):
        return True

    def preflight(self):
        self.events.append("preflight")

    def prepare_window(self, run_id):
        self.events.append("prepare")

    def arm(self):
        self.events.append("arm")
        if self.fail_arm:
            raise TestControlError("timer failed")
        self.units[TIMER] = True

    def start(self, unit):
        self.events.append("start:" + unit)
        if unit == TEST and self.fail_start:
            raise TestControlError("startup failed")
        self.units[unit] = True

    def stop(self, unit):
        self.events.append("stop:" + unit)
        self.units[unit] = False

    def device_free(self):
        return self.free

    def test_ready(self):
        self.events.append("ready")

    def capture(self):
        return {"successful_cycles": 5}

    def resumed_recording(self, after):
        self.events.append("confirm")
        return self.confirm


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.system = FakeSystem()
        self.controller = Coordinator(self.system, Path(self.tmp.name))

    def test_timer_before_p4d_stop_and_rollback_order(self):
        running = self.controller.start()
        self.assertEqual(running["phase"], "running")
        self.assertLess(
            self.system.events.index("arm"), self.system.events.index("stop:" + P4D)
        )
        self.assertFalse(self.system.active(P4D))
        self.assertTrue(self.system.active(TEST))
        result = self.controller.rollback()
        self.assertEqual(result["phase"], "returned")
        self.assertTrue(result["recording_resumed"])
        self.assertFalse(result["timer_active"])
        self.assertEqual(result["collector"]["successful_cycles"], 5)
        self.assertLess(
            self.system.events.index("stop:" + TEST),
            self.system.events.index("start:" + P4D),
        )

    def test_arm_failure_does_not_stop_original(self):
        self.system.fail_arm = True
        with self.assertRaises(TestControlError):
            self.controller.start()
        self.assertNotIn("stop:" + P4D, self.system.events)
        self.assertTrue(self.system.active(P4D))

    def test_start_failure_restores_original(self):
        self.system.fail_start = True
        with self.assertRaises(TestControlError):
            self.controller.start()
        self.assertTrue(self.system.active(P4D))
        self.assertEqual(self.controller.read()["phase"], "returned")

    def test_device_still_held_refuses_overlapping_start(self):
        self.controller.start()
        self.system.free = False
        with self.assertRaises(TestControlError):
            self.controller.rollback()
        self.assertFalse(self.system.active(P4D))
        self.assertNotIn("start:" + P4D, self.system.events)
        self.assertEqual(self.controller.read()["phase"], "restore_failed")
        self.system.free = True
        self.assertEqual(self.controller.rollback()["phase"], "returned")

    def test_new_process_can_restore_after_lost_ssh(self):
        self.controller.start()
        replacement = Coordinator(self.system, Path(self.tmp.name))
        self.assertEqual(replacement.rollback()["phase"], "returned")
        self.assertEqual(replacement.rollback()["phase"], "returned")
        self.assertEqual(self.system.events.count("start:" + P4D), 1)

    def test_no_reentry_and_recording_failure_reported(self):
        self.controller.start()
        with self.assertRaises(TestControlError):
            self.controller.start()
        self.system.confirm = False
        result = self.controller.rollback()
        self.assertTrue(result["p4d_active"])
        self.assertFalse(result["recording_resumed"])
        self.assertEqual(result["phase"], "returned_without_recording_confirmation")


class ReportTests(unittest.TestCase):
    def test_unprivileged_report_symlink_and_oversize_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report"
            other = Path(tmp) / "other"
            other.write_text('{"collector":{"secret":"do not follow"}}')
            path.symlink_to(other)
            self.assertEqual(read_report(path), {})
            path.unlink()
            path.write_text("x" * 262144)
            self.assertEqual(read_report(path), {})
            path.write_text('{"fatal_reason":"RequestTimeout"}')
            self.assertEqual(read_report(path), {"fatal_reason": "RequestTimeout"})
