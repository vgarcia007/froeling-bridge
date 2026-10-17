from pathlib import Path
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch

from froeling_bridge.client import ReadOnlyHeatingClient
from froeling_bridge.errors import ReadOnlyViolation, UnexpectedReply, ValidationError
from froeling_bridge.serial_transport import ReadOnlyTransport
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport
from froeling_bridge.service import BridgeService
from froeling_bridge.storage import (
    MemoryRepository,
    DatabaseConfig,
    ReadOnlyDatabase,
    TestDatabase,
    HardwareTestRepository,
)


class HardwareReadTests(unittest.TestCase):
    def setUp(self):
        self.transport = MemoryTransport()
        client = ReadOnlyHeatingClient(
            ProtocolSession(ReadOnlyTransport(self.transport))
        )
        self.service = BridgeService(
            MemoryRepository(), mode="hardware-read", client=client, autostart=False
        )
        self.addCleanup(self.service.close)

    def test_both_job_write_operations_rejected_before_queue_or_wire(self):
        for payload in (
            dict(operation="write_parameter", menu_id=2, value="67.5"),
            dict(
                operation="write_time_range",
                address=56,
                index=0,
                start="12:00",
                end="13:00",
            ),
        ):
            with self.assertRaises(ReadOnlyViolation):
                self.service.submit_job(payload)
        self.assertEqual(self.transport.requests, [])
        self.assertEqual(self.service.jobs, {})

    def test_protocol_fault_aborts_cycle_without_stale_sample_write(self):
        self.service.read_sensor = lambda _: (_ for _ in ()).throw(UnexpectedReply())
        self.service.collect_once()
        self.assertTrue(self.service.fatal.is_set())
        self.assertTrue(self.service.stop.is_set())
        self.assertEqual(self.service.collector_status()["stored"], 0)
        self.assertEqual(self.service.repository.rows, {})

    def test_hardware_source_labels_and_success_counter(self):
        self.service.collect_once()
        self.assertEqual(self.service.collector_status()["successful_cycles"], 1)
        self.assertTrue(
            all(v["source"] == "heating" for v in self.service.cached_values())
        )
        self.assertFalse(self.service.can_write)
        self.assertFalse(self.service.fatal.is_set())

    def test_deadline_fires_independently_of_collector(self):
        self.service.max_cycle_seconds = 0.01
        with self.service.lock:
            self.service.cycle_started = time.monotonic() - 1
        self.assertTrue(self.service.fatal.wait(1))
        self.assertEqual(self.service.fatal_reason, "collector_deadline")

    def test_explicit_client_required(self):
        with self.assertRaises(ValidationError):
            BridgeService(mode="hardware-read")

    def test_metadata_repository_cannot_be_writer_or_same_target(self):
        config = DatabaseConfig("froeling_bridge_test_hardware", "root")
        with self.assertRaises(ValidationError):
            HardwareTestRepository(TestDatabase(config), TestDatabase(config))
        with self.assertRaises(ValidationError):
            HardwareTestRepository(ReadOnlyDatabase(config), TestDatabase(config))
        source = ReadOnlyDatabase(DatabaseConfig("p4", "reader"))
        target = TestDatabase(config)
        repo = HardwareTestRepository(source, target)
        with (
            patch.object(source, "sensors", return_value=["original"]),
            patch.object(target, "store_cycle", return_value=5) as store,
        ):
            self.assertEqual(repo.sensors(), ["original"])
            self.assertEqual(repo.store_cycle([], None, None), 5)
            store.assert_called_once()
        self.assertFalse(hasattr(source, "store_cycle"))

    def test_http_capabilities_write_denial_and_ui_assets(self):
        try:
            import flask
        except ImportError:
            self.skipTest("install service dependencies")
        from froeling_bridge.api import create_app

        if not hasattr(flask.Flask(__name__), "json"):
            self.skipTest("Flask 3.1 required")
        http = create_app(self.service).test_client()
        health = http.get("/api/v1/health").get_json()
        self.assertEqual(
            health["capabilities"], {"controller_read": True, "heating_write": False, "sensor_configuration": False}
        )
        self.assertEqual(
            http.post(
                "/api/v1/jobs",
                json={"operation": "write_parameter", "menu_id": 2, "value": "67.5"},
            ).status_code,
            403,
        )
        self.assertEqual(self.transport.requests, [])
        self.assertFalse(
            http.get("/api/v1/menu?parent=10").get_json()["items"][0]["editable"]
        )
        root = http.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn("Servicemenü", root.get_data(as_text=True))
        self.assertIn("script-src 'self'", root.headers["Content-Security-Policy"])
        for path in ("/static/app.css", "/static/app.js"):
            response = http.get(path)
            self.assertEqual(response.status_code, 200)
            response.close()
        search = http.get("/api/v1/menu/search?q=Freigabe")
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.get_json()["items"][0]["id"], 3)
        self.assertEqual(http.get("/api/v1/menu/search?q=").status_code, 400)
