from datetime import datetime, timezone
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest

from froeling_bridge.menu import (
    time_program_catalog,
    visible_menu,
    readable_menu,
    menu_paths,
    named_search,
)
from froeling_bridge.service import BridgeService
from froeling_bridge.storage import MemoryRepository
from froeling_bridge.errors import UnexpectedReply
from froeling_bridge.time_cache import load, save
from froeling_bridge.messages import TimeRanges, TimeRange, read_range


def row(id, parent, child, title, address=0, type=42):
    return dict(
        id=id,
        parent=parent,
        child=child,
        title=title,
        address=address,
        type=type,
        value=None,
    )


def wait_job(service, identifier):
    for _ in range(100):
        result = service.get_job(identifier)
        if result["state"] in ("completed", "failed"):
            return result
        time.sleep(0.01)
    raise AssertionError("job did not complete")


class MenuMappingTests(unittest.TestCase):
    def test_original_four_address_formulas_use_actual_menu_names_and_weekdays(self):
        items = []
        cases = [
            (230, 0, "Warmwasser Nord", 0),
            (350, 2, "Wohnbereich", 0x38 + 14),
            (430, 1, "Speicher West", 0xB6 + 7),
            (573, 0, "Zirkulationspumpe", 0xD9),
        ]
        for index, (child, instance, title, base) in enumerate(cases):
            parent = 1000 + index
            items += [
                row(index * 2 + 1, 1, parent, title),
                row(index * 2 + 2, parent, child, "Zeiten:", instance),
            ]
        labels = time_program_catalog(items)
        self.assertEqual(len(labels), 28)
        for index, (_, _, title, base) in enumerate(cases):
            days = labels[index * 7 : index * 7 + 7]
            self.assertEqual([d["address"] for d in days], list(range(base, base + 7)))
            self.assertEqual(days[0]["title"], title + " · Montag")
            self.assertEqual(days[-1]["weekday"], "Sonntag")
        self.assertEqual(
            labels[-1]["address"], 0xDF
        )  # p4d also stores Zirkulation Sunday

    def test_unconfigured_orphan_folders_are_not_invented_as_devices(self):
        items = [
            row(1, 1, 100, "Heizkreis EG"),
            row(2, 100, 350, "Zeiten"),
            row(3, 999, 350, "Zeiten", 1),
        ]
        labels = time_program_catalog(items)
        self.assertEqual(len(labels), 7)
        self.assertEqual({d["device"] for d in labels}, {"Heizkreis EG"})

    def test_original_menu_filters_and_readable_zero_parameter(self):
        items = [
            row(1, 1, 0, "Solltemperatur:", type=7),
            row(2, 1, 0, "Reset", type=35),
            row(3, 1, 0, "Bus", type=49),
            row(4, 1, 0, "  "),
            row(5, 1, 0, "Sonderwert", 9998, type=7),
            row(6, 1, 0, "Firmware", type=22),
        ]
        visible = visible_menu(items)
        self.assertEqual([r["id"] for r in visible], [1, 6])
        self.assertEqual(visible[0]["title"], "Solltemperatur")
        self.assertTrue(all(r["readable"] for r in visible))

    def test_zero_address_is_valid_for_measurement_and_io_but_not_other_parameters(
        self,
    ):
        for kind in (3, 70, 17, 18, 19, 22, 7):
            self.assertTrue(readable_menu(row(1, 1, 0, "Wert", 0, kind)))
        self.assertFalse(readable_menu(row(1, 1, 0, "Wert", 0, 8)))

    def test_search_uses_menu_titles_in_breadcrumbs_and_excludes_orphans(self):
        items = [
            row(1, 1, 100, "Heizkreise"),
            row(2, 100, 200, "Wohnbereich"),
            row(3, 200, 0, "Solltemperatur", 1, 7),
            row(4, 999, 0, "Solltemperatur", 2, 7),
        ]
        result = named_search(items[2:], menu_paths(items))
        self.assertEqual([r["id"] for r in result], [3])
        self.assertEqual(
            result[0]["breadcrumbs"],
            [
                dict(parent=100, title="Heizkreise"),
                dict(parent=200, title="Wohnbereich"),
            ],
        )


class TimeCacheTests(unittest.TestCase):
    def test_shared_cache_is_read_without_extra_heater_requests_and_survives_restart(
        self,
    ):
        from froeling_bridge.api import create_app

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "times.json"
            service = BridgeService(autostart=False, time_cache_file=path)
            try:
                http = create_app(service).test_client()
                self.assertFalse(
                    http.get("/api/v1/time-programs").get_json()["cache"]["available"]
                )
                identifier = service.submit_job(dict(operation="time_ranges"))
                self.assertEqual(wait_job(service, identifier)["state"], "completed")
                count = len(service.client.session.transport.requests)
                for _ in range(2):
                    cached = http.get("/api/v1/time-programs").get_json()
                    self.assertTrue(cached["cache"]["available"])
                    self.assertEqual(cached["programs"][0]["device"], "Demo-Heizkreis")
                self.assertEqual(len(service.client.session.transport.requests), count)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                observed = cached["cache"]["observed_at"]
            finally:
                service.close()
            restarted = BridgeService(autostart=False, time_cache_file=path)
            try:
                self.assertEqual(
                    restarted.time_program_cache()["observed_at"], observed
                )
                self.assertEqual(restarted.client.session.transport.requests, [])
            finally:
                restarted.close()

    def test_concurrent_refreshes_share_one_job_and_failure_preserves_last_success(
        self,
    ):
        service = BridgeService(autostart=False)
        started, release = Event(), Event()
        original = service.client.get_time_ranges

        def read(timeout):
            started.set()
            release.wait(1)
            return original(timeout)

        service.client.get_time_ranges = read
        try:
            first = service.submit_job(dict(operation="time_ranges"))
            self.assertTrue(started.wait(1))
            second = service.submit_job(dict(operation="time_ranges"))
            self.assertEqual(first, second)
            release.set()
            self.assertEqual(wait_job(service, first)["state"], "completed")
            before = service.time_program_cache()
            service.client.get_time_ranges = lambda **kwargs: (_ for _ in ()).throw(
                UnexpectedReply("wrong code")
            )
            failed = service.submit_job(dict(operation="time_ranges"))
            self.assertEqual(wait_job(service, failed)["state"], "failed")
            after = service.time_program_cache()
            self.assertEqual(before["items"], after["items"])
            self.assertEqual(before["observed_at"], after["observed_at"])
            self.assertFalse(after["refreshing"])
        finally:
            release.set()
            service.close()

    def test_verified_demo_change_updates_the_shared_cache(self):
        service = BridgeService(autostart=False)
        try:
            wait_job(service, service.submit_job(dict(operation="time_ranges")))
            stamp = service.time_program_cache()["observed_at"]
            change = service.submit_job(
                dict(
                    operation="write_time_range",
                    address=0x38,
                    index=1,
                    start="12:00",
                    end="13:00",
                )
            )
            self.assertEqual(wait_job(service, change)["state"], "completed")
            cached = service.time_program_cache()
            group = next(item for item in cached["items"] if item["address"] == 0x38)
            self.assertEqual(group["ranges"][1], dict(start="12:00", end="13:00"))
            self.assertEqual(cached["observed_at"], stamp)
        finally:
            service.close()

    def test_raw_time_data_persists_and_corrupt_or_symlink_cache_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "times.json"
            stamp = datetime.now(timezone.utc).isoformat()
            items = (
                TimeRanges(0, (read_range(b"\x00\xf0"),) + (TimeRange(),) * 3),
                TimeRanges(0xDF, (TimeRange(),) * 4),
            )
            save(path, items, stamp)
            self.assertEqual(load(path)[0], items)
            link = Path(directory) / "link"
            link.symlink_to(path)
            self.assertIsNone(load(link))
            path.write_text("broken")
            self.assertIsNone(load(path))


class MenuValueTests(unittest.TestCase):
    def test_measurement_io_firmware_and_parameter_follow_original_read_paths(self):
        class Repo(MemoryRepository):
            def menu_item(self, identifier):
                entries = {
                    1: row(1, 1, 0, "Temperatur", 0x2B, 3),
                    2: row(2, 1, 0, "Pumpe", 1, 17),
                    3: row(3, 1, 0, "Leistung", 1, 18),
                    4: row(4, 1, 0, "Firmware", 0, 22),
                    5: row(5, 1, 0, "Betriebswert", 0x1234, 47),
                    6: row(6, 1, 100, "Gruppe"),
                }
                return entries.get(identifier)

        service = BridgeService(Repo(), autostart=False)
        try:
            results = []
            for identifier in range(1, 6):
                job = service.submit_job(
                    dict(operation="read_menu_value", menu_id=identifier)
                )
                result = wait_job(service, job)
                self.assertEqual(result["state"], "completed")
                results.append(result["result"])
            self.assertEqual(results[0]["value"], "-1.2")
            self.assertEqual(results[1]["value"], 0)
            self.assertEqual(results[2]["value"], 0)
            self.assertEqual(results[3]["value"], "00.00.00.01")
            self.assertEqual(results[4]["value"], "65")
            self.assertEqual(
                [f.command for f in service.client.session.transport.requests],
                [0x30, 0x44, 0x45, 0x41, 0x55],
            )
        finally:
            service.close()
