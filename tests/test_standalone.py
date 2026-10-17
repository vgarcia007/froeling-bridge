from dataclasses import replace
from datetime import datetime
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

from froeling_bridge.api import create_app
from froeling_bridge.client import HeatingClient
from froeling_bridge.errors import RequestTimeout, ValidationError
from froeling_bridge.local_store import LocalRepository
from froeling_bridge.messages import MenuItem, Command
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport, demo_heater
from froeling_bridge.standalone import StandaloneRuntime, ReconnectingClient


def controller():
    heater = demo_heater()
    heater.menu += (MenuItem(3, 1, 0, 43, b"Demo temperature"),)
    return MemoryTransport(heater)


class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.transport = controller()
        self.runtime = StandaloneRuntime(
            self.directory.name,
            lambda: (HeatingClient(ProtocolSession(self.transport)), lambda: None),
            simulator=True,
            allow_writes=True,
            autostart=False,
        )
        self.addCleanup(self.runtime.close)
        self.http = create_app(self.runtime.service).test_client()

    def test_empty_start_discovers_names_menu_times_and_live_values_without_mysql(self):
        self.runtime.discover_once()
        self.runtime.refresh_status()
        self.runtime.service.collect_once()
        self.assertEqual(self.runtime.phase, "ready")
        sensors = self.http.get("/api/v1/sensors").get_json()["items"]
        sensor = next(s for s in sensors if s["address"] == 43)
        self.assertEqual(sensor["latest"]["value"], "-1.2")
        self.assertTrue(sensor["active"])
        self.assertFalse(sensor["recording"])
        self.assertEqual(len(self.runtime.repository.menu_catalog()), 5)
        self.assertTrue(self.runtime.service.time_program_cache()["available"])
        before = len(self.transport.requests)
        self.http.get("/api/v1/sensors")
        self.http.get("/api/v1/values")
        self.assertEqual(len(self.transport.requests), before)
        self.assertFalse(
            self.http.get("/api/v1/runtime").get_json()["history"]["configured"]
        )

    def test_repeated_sensor_definitions_update_metadata_and_keep_preferences(self):
        self.runtime.discover_once()
        self.runtime.repository.patch_sensor("VA", 43, dict(record=True, active=False))
        self.transport.heater.value_specs += (
            replace(self.transport.heater.value_specs[0], factor=20,
                    description_raw=b"Repeated updated temperature"),
        )
        with self.assertLogs("froeling_bridge.discovery", level="WARNING") as logs:
            self.runtime.discover_once()
        sensors = [s for s in self.runtime.repository.sensors()
                   if s["type"] == "VA" and s["address"] == 43]
        self.assertEqual(len(sensors), 1)
        self.assertEqual(sensors[0]["factor"], 20)
        self.assertEqual(sensors[0]["title"], "Repeated updated temperature")
        self.assertEqual((sensors[0]["record"], sensors[0]["state"]), ("A", "D"))
        self.assertIn("merged 1 repeated definitions", logs.output[0])
        self.assertEqual(self.runtime.phase, "ready")

    def test_persisted_values_after_restart_are_explicitly_stale_and_not_refreshed(
        self,
    ):
        self.runtime.discover_once()
        self.runtime.service.collect_once()
        values = self.runtime.service.cached_values()
        store = LocalRepository(Path(self.directory.name) / "catalogue.sqlite3")
        restored = store.latest_values()
        old = {(v["type"], v["address"]): v["observed_at"] for v in values}
        self.assertEqual(
            old, {(v["type"], v["address"]): v["observed_at"] for v in restored}
        )
        self.assertTrue(all(v["origin"] == "local-persisted" for v in restored))
        self.runtime.service.values = {(v["address"], v["type"]): v for v in restored}
        response = self.http.get("/api/v1/values").get_json()["items"]
        self.assertTrue(all(v["stale"] for v in response))

    def test_failed_rediscovery_preserves_complete_previous_catalogue(self):
        self.runtime.discover_once()
        old = self.runtime.repository.menu_catalog()
        self.runtime.client.inner.get_time_ranges = Mock(side_effect=RequestTimeout())
        with self.assertRaises(RequestTimeout):
            self.runtime.discover_once()
        self.assertEqual(old, self.runtime.repository.menu_catalog())

    def test_record_toggle_preserves_history_and_forces_read_with_active_off(self):
        self.runtime.discover_once()
        response = self.http.patch(
            "/api/v1/sensors/VA/43", json=dict(record=True, active=False)
        )
        self.assertEqual(response.status_code, 200)
        row = response.get_json()["item"]
        self.assertEqual((row["state"], row["record"]), ("D", "A"))
        self.runtime.service.collect_once()
        self.assertTrue(
            any(
                v["type"] == "VA" and v["address"] == 43
                for v in self.runtime.service.cached_values()
            )
        )
        self.assertEqual(
            self.http.patch(
                "/api/v1/sensors/VA/65500", json=dict(record=True)
            ).status_code,
            400,
        )
        self.assertEqual(
            self.http.patch(
                "/api/v1/sensors/VA/43", json=dict(record="yes")
            ).status_code,
            400,
        )
        self.runtime.discover_once()
        row = next(
            s
            for s in self.runtime.repository.sensors()
            if s["type"] == "VA" and s["address"] == 43
        )
        self.assertEqual((row["state"], row["record"]), ("D", "A"))

    def test_pending_configuration_version_does_not_lose_concurrent_edit(self):
        self.runtime.discover_once()
        self.runtime.repository.patch_sensor("VA", 43, dict(record=True))
        old = self.runtime.repository.pending_changes()[0]
        self.runtime.repository.patch_sensor("VA", 43, dict(record=False))
        self.runtime.repository.acknowledge_change(old)
        self.assertEqual(
            self.runtime.repository.pending_changes()[0]["changes"], dict(record=False)
        )

    def test_catalogue_corruption_preserves_damaged_file_and_can_start_again(self):
        file = Path(self.directory.name) / "damaged.sqlite3"
        file.write_bytes(b"not a database")
        repo = LocalRepository(file)
        self.assertTrue(repo.recovered)
        self.assertEqual(repo.sensors(), [])
        self.assertEqual(
            next(file.parent.glob("damaged.sqlite3.damaged-*")).read_bytes(),
            b"not a database",
        )

    def test_unknown_local_schema_is_not_quarantined_or_reinitialized(self):
        import sqlite3

        file = Path(self.directory.name) / "future.sqlite3"
        with sqlite3.connect(file) as db:
            db.execute("PRAGMA user_version=999")
        with self.assertRaises(ValidationError):
            LocalRepository(file)
        with sqlite3.connect(file) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 999)

    def test_verified_simulator_write_is_journalled_without_replaying(self):
        self.runtime.discover_once()
        item = next(m for m in self.runtime.repository.menu_catalog() if m["type"] == 7)
        r = self.http.post(
            "/api/v1/jobs",
            json=dict(operation="write_parameter", menu_id=item["id"], value="67.5"),
        )
        identifier = r.get_json()["id"]
        for _ in range(100):
            job = self.runtime.service.get_job(identifier)
            if job["state"] in ("completed", "failed"):
                break
            time.sleep(0.01)
        self.assertEqual(job["state"], "completed", job)
        with self.runtime.repository.transaction() as db:
            self.assertIn(
                "completed",
                db.execute(
                    "SELECT data FROM audit WHERE id=?", (identifier,)
                ).fetchone()[0],
            )
        self.assertEqual(self.transport.heater.parameter_write_count, 1)

    def test_reconnect_opens_new_session_but_does_not_retry_failed_call(self):
        bad = Mock()
        bad.get_status.side_effect = RequestTimeout()
        good = Mock()
        good.get_status.return_value = "ready"
        close = Mock()
        factory = Mock(side_effect=[(bad, close), (good, Mock())])
        client = ReconnectingClient(factory)
        with self.assertRaises(RequestTimeout):
            client.get_status()
        self.assertEqual(factory.call_count, 1)
        close.assert_called_once()
        self.assertEqual(client.get_status(), "ready")
        self.assertEqual(factory.call_count, 2)

    def test_imported_preferences_and_later_user_changes_are_preserved(self):
        self.runtime.discover_once()
        row = next(
            s
            for s in self.runtime.repository.sensors()
            if s["type"] == "VA" and s["address"] == 43
        )
        row.update(record="A", usrtitle="Chosen name")
        self.runtime.repository.import_preferences([row])
        self.assertEqual(
            next(s for s in self.runtime.repository.sensors() if s["address"] == 43)[
                "record"
            ],
            "A",
        )
        self.runtime.repository.patch_sensor("VA", 43, dict(record=False))
        self.runtime.repository.import_preferences([row])
        self.assertEqual(
            next(s for s in self.runtime.repository.sensors() if s["address"] == 43)[
                "record"
            ],
            "D",
        )


class DiscoveryReplyTests(unittest.TestCase):
    def test_first_response_command_on_next_matches_p4d_list_semantics(self):
        from froeling_bridge.codec import Frame, StreamDecoder, encode_frame

        def rewrite(request, wire):
            mapping = {
                Command.VALUES_NEXT: Command.VALUES_FIRST,
                Command.MENU_NEXT: Command.MENU_FIRST,
            }
            return b"".join(
                encode_frame(Frame(mapping.get(request.command, f.command), f.payload))
                for f in StreamDecoder().feed(wire)
            )

        t = MemoryTransport(wire_filter=rewrite)
        client = HeatingClient(ProtocolSession(t))
        self.assertEqual(len(client.get_value_specs()), 2)
        self.assertEqual(len(client.get_menu()), 4)

    def test_unrelated_reply_still_rejected(self):
        from froeling_bridge.codec import Frame, StreamDecoder, encode_frame
        from froeling_bridge.errors import UnexpectedReply

        def rewrite(request, wire):
            if request.command != Command.VALUES_NEXT:
                return wire
            return b"".join(
                encode_frame(Frame(Command.PARAMETER, f.payload))
                for f in StreamDecoder().feed(wire)
            )

        client = HeatingClient(ProtocolSession(MemoryTransport(wire_filter=rewrite)))
        with self.assertRaises(UnexpectedReply):
            client.get_value_specs()


class ValidationToolTests(unittest.TestCase):
    def test_chosen_parameter_changed_restored_and_simulation_is_not_hardware_proof(
        self,
    ):
        from froeling_bridge.validate_write import main
        import json

        with tempfile.TemporaryDirectory() as directory:
            proof = Path(directory) / "proof.json"
            code = main(
                [
                    "--simulate",
                    "--state-dir",
                    directory,
                    "--proof-file",
                    str(proof),
                    "parameter",
                    "--address",
                    "0x1234",
                    "--value",
                    "67.5",
                ]
            )
            self.assertEqual(code, 0)
            self.assertFalse(json.loads(proof.read_text())["validated"])

    def test_unknown_forward_outcome_never_triggers_automatic_restore(self):
        from froeling_bridge.validate_write import validate_parameter
        from froeling_bridge.errors import WriteOutcomeUnknown
        from froeling_bridge.messages import ParameterType

        transport = MemoryTransport()
        client = HeatingClient(ProtocolSession(transport))
        client.set_parameter = Mock(
            side_effect=WriteOutcomeUnknown("parameter", 0x1234, "send")
        )
        with self.assertRaises(WriteOutcomeUnknown):
            validate_parameter(client, 0x1234, "67.5", ParameterType.NUMBER)
        self.assertEqual(client.set_parameter.call_count, 1)


class OutageTests(unittest.TestCase):
    def test_real_unreachable_mariadb_does_not_prevent_discovery_or_live_http(self):
        from froeling_bridge.storage import DatabaseConfig

        with tempfile.TemporaryDirectory() as directory:
            transport = controller()
            runtime = StandaloneRuntime(
                directory,
                lambda: (HeatingClient(ProtocolSession(transport)), lambda: None),
                simulator=True,
                interval=0.05,
                status_interval=0.05,
                database_config=DatabaseConfig(
                    "froeling_bridge_test_unreachable", "user", port=1
                ),
                initialize_history=True,
            )
            try:
                http = create_app(runtime.service).test_client()
                for _ in range(200):
                    rows = http.get("/api/v1/sensors").get_json()["items"]
                    if any(
                        s["type"] == "VA" and s["address"] == 43 and s["latest"]
                        for s in rows
                    ):
                        break
                    time.sleep(0.01)
                else:
                    self.fail("MariaDB outage blocked live readings")
                state = http.get("/api/v1/runtime").get_json()
                self.assertTrue(state["connection"]["connected"])
                self.assertIsNotNone(state["history"]["error"])
                self.assertIsNone(runtime.service.fatal_reason)
                self.assertEqual(http.get("/api/v1/menu?parent=1").status_code, 200)
                self.assertEqual(
                    http.patch(
                        "/api/v1/sensors/VA/43", json=dict(record=True)
                    ).status_code,
                    200,
                )
            finally:
                runtime.close()


class SensorFailureIsolationTests(unittest.TestCase):
    def test_single_bad_sensor_does_not_starve_later_healthy_sensor(self):
        from froeling_bridge.messages import ValueSpec

        def factory():
            t = controller()
            t.heater.value_specs += (replace(t.heater.value_specs[0], address=42),)
            t.heater.menu += (MenuItem(3, 1, 0, 42, b"Unavailable sensor"),)
            return HeatingClient(ProtocolSession(t)), lambda: None

        with tempfile.TemporaryDirectory() as directory:
            runtime = StandaloneRuntime(
                directory, factory, simulator=True, autostart=False
            )
            try:
                runtime.discover_once()
                runtime.service.collect_once()
                self.assertTrue(
                    any(
                        r["type"] == "VA" and r["address"] == 43
                        for r in runtime.service.cached_values()
                    )
                )
                self.assertTrue(
                    any(
                        e.get("address") == 42
                        for e in runtime.service.collector_status()["errors"]
                    )
                )
                self.assertIsNone(runtime.service.fatal_reason)
            finally:
                runtime.close()
