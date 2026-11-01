"""Real MCP HTTP transport against a fake GET-only Bridge, no heating hardware."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from froeling_bridge.mcp_server import configuration


class MCPHTTPTests(unittest.TestCase):
    def test_auth_transport_tools_and_no_writes(self):
        seen = []; role = ["read"]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                seen.append(("GET", self.path))
                if self.headers.get("Authorization") != "Bearer " + "read-api-key-1234567890123":
                    self.send_error(401); return
                path = self.path.split("?")[0]
                data = {"items": []}
                if path.endswith("/auth/me"): data = {"authenticated": True, "role": role[0]}
                elif path.endswith("/sensors"): data = {"source": "fixture", "items": [dict(type="VA", address=93, title="Boiler 1", latest=dict(value="50", stale=False))]}
                elif path.endswith("/plant"): data = {"components": [], "cached": True}
                elif path.endswith("/history"): data = {"source": "fixture-history", "items": [{"time": "2026-01-01T12:00:00", "value": "48"}]}
                elif path.endswith("/errors"): data = {"items": [], "total": 0, "source": "controller-error-memory"}
                body = json.dumps(data).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self): seen.append(("POST", self.path)); self.send_error(403)
            def do_PATCH(self): seen.append(("PATCH", self.path)); self.send_error(403)
        bridge = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=bridge.serve_forever, daemon=True).start()
        self.addCleanup(bridge.server_close); self.addCleanup(bridge.shutdown)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
        token = "test-mcp-access-token-12345678901234567890"
        env = dict(os.environ, BRIDGE_MCP_HOST="127.0.0.1", BRIDGE_MCP_PORT=str(port), BRIDGE_MCP_TOKEN=token,
                   BRIDGE_MCP_API_URL="http://127.0.0.1:%s" % bridge.server_port, BRIDGE_MCP_API_KEY="read-api-key-1234567890123", BRIDGE_MCP_ALLOWED_HOSTS="")
        proc = subprocess.Popen([sys.executable, "-m", "froeling_bridge.mcp_server"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(lambda: proc.stderr.close())
        def stop():
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
        self.addCleanup(stop)
        for _ in range(80):
            if proc.poll() is not None: self.fail(proc.stderr.read().decode()[-1500:])
            try:
                with socket.create_connection(("127.0.0.1", port), .1): break
            except OSError: time.sleep(.1)
        else: self.fail("MCP server failed to listen")
        url = "http://127.0.0.1:%s/mcp" % port
        async def check():
            async with httpx2.AsyncClient() as anon:
                self.assertEqual((await anon.get(url)).status_code, 401)
                self.assertEqual((await anon.get(url, headers={"Authorization": "Bearer wrong"})).status_code, 401)
                response = await anon.post(url, headers={"Authorization": "Bearer " + token, "Host": "untrusted.example.org"}, json={})
                self.assertEqual(response.status_code, 421)
            async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + token}) as http:
                async with Client(streamable_http_client(url, http_client=http)) as client:
                    tools = (await client.list_tools()).tools
                    self.assertEqual(len(tools), 9)
                    self.assertTrue(all(t.annotations.read_only_hint for t in tools))
                    for name, args in [
                        ("list_sensors", {}), ("search_sensors", {"query": "Boiler"}),
                        ("get_current_values", {"sensor_ids": ["VA:93"]}), ("get_system_overview", {}),
                        ("get_history", {"sensor_id": "VA:93", "start": "2026-01-01T00:00:00", "end": "2026-01-02T00:00:00"}),
                        ("get_errors", {}), ("get_menu", {}), ("search_menu", {"query": "Boiler"}), ("get_time_programs", {})]:
                        result = await client.call_tool(name, args)
                        self.assertFalse(result.is_error, name)
                        self.assertNotEqual(result.structured_content.get("status"), "unavailable", name)
                    result = await client.call_tool("write_parameter", {"address": 1, "value": 0})
                    self.assertTrue(result.is_error)
                    before = len([p for _, p in seen if p.endswith("/sensors")]); role[0] = "write"
                    result = await client.call_tool("list_sensors", {})
                    self.assertEqual(result.structured_content["status"], "unavailable")
                    self.assertEqual(before, len([p for _, p in seen if p.endswith("/sensors")]))
        asyncio.run(check())
        self.assertTrue(all(method == "GET" for method, _ in seen))
        self.assertFalse(any("/jobs" in path for _, path in seen))

    def test_configuration_requires_independent_authentication(self):
        base = dict(BRIDGE_MCP_API_URL="https://heizung.example.org", BRIDGE_MCP_API_KEY="test-read-key-1234567890", BRIDGE_MCP_TOKEN="m" * 40)
        for overrides in ({"BRIDGE_MCP_TOKEN": ""}, {"BRIDGE_MCP_TOKEN": base["BRIDGE_MCP_API_KEY"]}, {"BRIDGE_MCP_HOST": "0.0.0.0"}, {"BRIDGE_MCP_ALLOWED_HOSTS": "*"}):
            with patch.dict(os.environ, dict(base, **overrides), clear=True):
                with self.assertRaises(ValueError): configuration()


if __name__ == "__main__": unittest.main()
