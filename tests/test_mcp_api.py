"""The MCP adapter must never submit jobs, follow redirects or accept write keys."""
import json
from io import BytesIO
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

from froeling_bridge.mcp_api import BridgeReader, BridgeReadError, NoRedirects, local_time


class Reply(BytesIO):
    def __init__(self, value):
        super().__init__(json.dumps(value).encode())


class MCPReaderTests(unittest.TestCase):
    def reader(self, *responses):
        reader = BridgeReader("https://heizung.example.org", "test-read-key-1234567890")
        reader.opener = Mock()
        reader.opener.open.side_effect = [Reply(x) for x in responses]
        return reader

    def test_write_or_anonymous_credentials_stop_before_data_read(self):
        for actor in ({"authenticated": True, "role": "write"}, {"authenticated": False, "role": "read"}):
            reader = self.reader(actor)
            with self.assertRaises(BridgeReadError):
                reader.current(["VA:93"])
            self.assertEqual(reader.opener.open.call_count, 1)

    def test_values_keep_freshness_and_missing_values(self):
        row = dict(type="VA", address=93, title="Boiler 1", unit="°C", latest=dict(value="49.5", observed_at="2026-01-01T12:00:00+01:00", stale=True, origin="local-persisted"))
        reader = self.reader({"authenticated": True, "role": "read"}, {"source": "controller", "items": [row]})
        result = reader.current(["VA:93", "VA:99"])
        self.assertEqual(result["items"][0]["latest"], row["latest"])
        self.assertTrue(result["items"][1]["missing"])
        for call in reader.opener.open.call_args_list:
            self.assertEqual(call.args[0].get_method(), "GET")

    def test_search_pagination_and_original_title(self):
        reader = self.reader({"authenticated": True, "role": "read"}, {"items": [dict(type="VA", address=i, title="Boiler %d" % i) for i in range(3)]})
        result = reader.sensors("boiler", limit=1, offset=1)
        self.assertEqual(result["items"][0]["sensor_id"], "VA:1")
        self.assertTrue(result["has_more"])

    def test_history_fetches_extra_point_and_pages_without_duplicates(self):
        reader = self.reader({"authenticated": True, "role": "read"}, {"source": "p4d-database", "items": [dict(time="2026-01-01T12:00:00", value="42"), dict(time="2026-01-01T12:01:00", value="43")]})
        result = reader.history("VA:93", "2026-01-01T11:00:00Z", "2026-01-01T14:00:00+01:00", limit=1, resolution="aggregated")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["next_start"], "2026-01-01T12:00:01")
        url = reader.opener.open.call_args.args[0].full_url
        self.assertIn("aggregate=A", url)
        self.assertIn("limit=2", url)
        self.assertEqual(result["start"], "2026-01-01T12:00:00")

    def test_empty_history_is_not_synthesized(self):
        reader = self.reader({"authenticated": True, "role": "read"}, {"items": []})
        result = reader.history("VA:93", "2026-01-01T00:00:00", "2026-01-02T00:00:00")
        self.assertEqual(result["items"], [])
        self.assertFalse(result["truncated"])

    def test_invalid_ids_and_limits_never_reach_network(self):
        reader = self.reader()
        for ids in (["../../jobs"], ["VA:65535"], [], ["VA:0"] * 33):
            with self.assertRaises(ValueError): reader.current(ids)
        for limit in (0, 1000, True):
            with self.assertRaises(ValueError): reader.history("VA:0", "2026-01-01T00:00:00", "2026-01-02T00:00:00", limit)
        with self.assertRaises(ValueError): reader._get("/jobs")
        reader.opener.open.assert_not_called()

    def test_time_bounds(self):
        self.assertIsNone(local_time("2026-01-01T00:00:00+01:00").tzinfo)
        reader = self.reader()
        for start, end in (("2026-01-01", "2026-01-02"), ("2026-01-02T00:00:00", "2026-01-01T00:00:00"), ("2020-01-01T00:00:00", "2026-01-01T00:00:00")):
            with self.assertRaises(ValueError): reader.history("VA:0", start, end)
        reader.opener.open.assert_not_called()

    def test_errors_preserve_activity_uncertainty_and_fallback(self):
        data = dict(items=[dict(active=None, state="gekommen")], fallback=True, history_available=False)
        reader = self.reader({"authenticated": True, "role": "read"}, data)
        self.assertEqual(reader.errors(), data)

    def test_upstream_failures_do_not_leak_credentials_or_urls(self):
        for exc in (URLError("secret-password"), HTTPError("https://secret/", 403, "secret", {}, None)):
            reader = self.reader(); reader.opener.open.side_effect = exc
            with self.assertRaises(BridgeReadError) as caught: reader.check_access()
            self.assertNotIn("secret", str(caught.exception))

    def test_redirects_and_credential_urls_are_rejected(self):
        self.assertIsNone(NoRedirects().redirect_request(None, None, 302, "", {}, "https://other/"))
        for url in ("https://user:password@example.org", "file:///etc/passwd", "https://example.org/api", "https://example.org?x=1"):
            with self.assertRaises(ValueError): BridgeReader(url, "test-read-key-1234567890")


if __name__ == "__main__":
    unittest.main()
