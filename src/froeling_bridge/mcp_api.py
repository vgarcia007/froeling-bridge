"""Bounded, GET-only adapter for the separately installed MCP service."""
from datetime import datetime, timedelta, timezone
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from zoneinfo import ZoneInfo


class BridgeReadError(Exception):
    """Public error without credentials, URLs or upstream exception details."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def bounded(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be {minimum}..{maximum}")
    return value


def sensor_key(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Z0-9]{1,8}:[0-9]{1,5}", identifier):
        raise ValueError("sensor_id must be TYPE:ADDRESS from sensor discovery")
    kind, address = identifier.split(":")
    return kind, bounded(int(address), 0, 65534, "address")


def local_time(value):
    if not isinstance(value, str) or len(value) > 40 or "T" not in value:
        raise ValueError("Use an ISO date and time, optionally with a timezone offset")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid ISO timestamp") from None
    if result.tzinfo is not None:
        result = result.astimezone(ZoneInfo("Europe/Berlin")).replace(tzinfo=None)
    return result


class BridgeReader:
    PATHS = frozenset(("/auth/me", "/sensors", "/plant", "/history", "/errors",
                       "/menu", "/menu/search", "/time-programs"))

    def __init__(self, base_url, api_key, timeout=12):
        parts = urlsplit(base_url)
        if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment or parts.path not in ("", "/")):
            raise ValueError("BRIDGE_MCP_API_URL must be an HTTP(S) origin without credentials or path")
        if not isinstance(api_key, str) or not 20 <= len(api_key) <= 160 or any(c.isspace() for c in api_key):
            raise ValueError("A dedicated read-only Bridge API key is required")
        self.base_url, self.api_key, self.timeout = base_url.rstrip("/"), api_key, timeout
        # Never send credentials to a redirected host or an environment-selected proxy.
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def _get(self, path, params=None):
        if path not in self.PATHS:
            raise ValueError("API path is not a read-only MCP endpoint")
        url = self.base_url + "/api/v1" + path
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={"Authorization": "Bearer " + self.api_key,
                                       "Accept": "application/json"}, method="GET")
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise BridgeReadError("Bridge response exceeds the bounded response size")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise BridgeReadError("Invalid Bridge response")
                return result
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise BridgeReadError("Bridge read access denied; check the dedicated API key") from None
            if exc.code == 429:
                raise BridgeReadError("Bridge request limit reached; retry later") from None
            raise BridgeReadError("Bridge request failed (HTTP %d)" % exc.code) from None
        except (URLError, OSError, ValueError):
            raise BridgeReadError("Bridge is unavailable or returned invalid JSON") from None

    def check_access(self):
        actor = self._get("/auth/me")
        if actor.get("authenticated") is not True or actor.get("role") != "read":
            raise BridgeReadError("MCP requires a read-only Bridge API key; write credentials are refused")

    def read(self, path, params=None):
        # Check every tool call: revocation, role changes and accidental write keys fail closed.
        self.check_access()
        return self._get(path, params)

    def sensors(self, query="", limit=50, offset=0):
        bounded(limit, 1, 200, "limit"); bounded(offset, 0, 100000, "offset")
        if not isinstance(query, str) or len(query) > 100:
            raise ValueError("query must contain at most 100 characters")
        data = self.read("/sensors")
        items = []
        for row in data["items"]:
            identifier = "%s:%s" % (row["type"], row["address"])
            if query.casefold() not in " ".join(str(row.get(k, "")) for k in ("title", "usrtitle")).casefold() and query.casefold() not in identifier.casefold():
                continue
            items.append(dict(row, sensor_id=identifier))
        return dict(source=data.get("source"), timezone="Europe/Berlin", total=len(items),
                    offset=offset, limit=limit, has_more=offset + limit < len(items),
                    items=items[offset:offset + limit],
                    note="latest is the last collected observation, not an on-demand heater read; inspect observed_at and stale")

    def current(self, sensor_ids):
        if not isinstance(sensor_ids, list) or not 1 <= len(sensor_ids) <= 32:
            raise ValueError("Provide 1..32 sensor_ids from discovery")
        keys = {sensor_key(identifier) for identifier in sensor_ids}
        data = self.read("/sensors")
        found = {(row["type"], row["address"]): row for row in data["items"]}
        items = []
        for kind, address in sorted(keys):
            identifier = "%s:%s" % (kind, address)
            row = found.get((kind, address))
            items.append(dict(row, sensor_id=identifier) if row else dict(sensor_id=identifier, latest=None, missing=True))
        return dict(source=data.get("source"), items=items,
                    note="Cached observations only. Missing or stale observations do not establish a current state. Pump commands do not measure water flow.")

    def history(self, sensor_id, start, end, limit=500, resolution="raw"):
        kind, address = sensor_key(sensor_id)
        bounded(limit, 1, 999, "limit")
        if resolution not in ("raw", "aggregated"):
            raise ValueError("resolution must be raw or aggregated")
        begin, finish = local_time(start), local_time(end)
        if begin >= finish or finish - begin > timedelta(days=366):
            raise ValueError("History requires start < end and at most 366 days per request")
        data = self.read("/history", dict(address=address, type=kind, start=begin.isoformat(),
                         end=finish.isoformat(), aggregate="S" if resolution == "raw" else "A", limit=limit + 1))
        rows = data["items"]; more = len(rows) > limit; rows = rows[:limit]
        # SQL uses second-resolution local DATETIME and an inclusive lower boundary.
        next_start = (datetime.fromisoformat(rows[-1]["time"]) + timedelta(seconds=1)).isoformat() if more else None
        return dict(source=data.get("source"), sensor_id=sensor_id, timezone="Europe/Berlin",
                    start=begin.isoformat(), end=finish.isoformat(), resolution=resolution,
                    limit=limit, items=rows, truncated=more, next_start=next_start,
                    note="Only recorded points; no interpolation. Raw points may have been compacted: query aggregated separately. Database times are local; the repeated DST hour cannot be distinguished. Aggregated samples are not instantaneous readings.")

    def errors(self, source="auto", limit=100, offset=0):
        if source not in ("auto", "controller", "history"):
            raise ValueError("source must be auto, controller or history")
        bounded(limit, 1, 500, "limit"); bounded(offset, 0, 100000, "offset")
        return self.read("/errors", dict(source=source, limit=limit, offset=offset))

    def menu(self, parent=1):
        bounded(parent, 0, 65535, "parent")
        return self.read("/menu", dict(parent=parent))

    def search_menu(self, query):
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100:
            raise ValueError("query must contain 1..100 characters")
        return self.read("/menu/search", dict(q=query.strip()))
