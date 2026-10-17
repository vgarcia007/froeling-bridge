"""Exercise the p4d-style editor in Chromium against fictional in-memory hardware only.

Requires chromium and websocket-client in the test Python environment.
"""
import argparse
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from threading import Thread
import time
from urllib.request import urlopen

import websocket
from waitress import create_server

from froeling_bridge.api import create_app
from froeling_bridge.client import HeatingClient
from froeling_bridge.messages import MenuItem
from froeling_bridge.service import BridgeService
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport, demo_heater
from froeling_bridge.storage import MemoryRepository, ZONE


class Browser:
    def __init__(self):
        self.directory = tempfile.TemporaryDirectory(prefix='froeling-editor-chrome-')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.process = subprocess.Popen([
            '/usr/bin/chromium', '--headless', '--no-sandbox', '--disable-gpu',
            '--disable-dev-shm-usage', '--remote-debugging-port=' + str(port),
            '--user-data-dir=' + self.directory.name, 'about:blank',
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(300):
            try:
                with urlopen(f'http://127.0.0.1:{port}/json', timeout=1) as response:
                    pages = json.load(response)
                self.socket = websocket.create_connection(pages[0]['webSocketDebuggerUrl'], timeout=10)
                break
            except Exception:
                time.sleep(.05)
        else:
            self.process.terminate()
            self.directory.cleanup()
            raise RuntimeError('Chromium did not start')
        self.counter = 0
        self.errors = []

    def call(self, method, params=None):
        self.counter += 1
        identifier = self.counter
        self.socket.send(json.dumps(dict(id=identifier, method=method, params=params or {})))
        while True:
            reply = json.loads(self.socket.recv())
            if reply.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(reply['params'])
            if reply.get('id') == identifier:
                if 'error' in reply:
                    raise RuntimeError(reply['error'])
                return reply['result']

    def js(self, source):
        result = self.call('Runtime.evaluate', dict(expression=source, returnByValue=True, awaitPromise=True))
        if 'exceptionDetails' in result:
            raise RuntimeError(result['exceptionDetails'])
        return result['result'].get('value')

    def wait(self, source):
        for _ in range(300):
            if self.js(source):
                return
            time.sleep(.05)
        raise AssertionError(source)

    def close(self):
        self.socket.close()
        self.process.terminate()
        self.process.wait(10)
        self.directory.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate-only', action='store_true', required=True)
    parser.parse_args()
    heater = demo_heater()
    for kind in (50, 57, 64):
        address = 0x300 + kind
        heater.parameters[address] = replace(heater.parameters[0x1234], address=address)
        heater.menu += (MenuItem(kind, 10, 0, address, ('Fictional ' + str(kind)).encode()),)
    heater.menu += (MenuItem(17, 10, 0, 43, b'Fictional IO'),)
    items = [dict(id=i, parent=m.parent, child=m.child, type=m.item_type,
                  address=m.address, title=m.description, value=None)
             for i, m in enumerate(heater.menu, 1)]
    repo = MemoryRepository()
    repo.menu = lambda parent: [m for m in items if m['parent'] == parent]
    repo.menu_item = lambda identifier: next((m for m in items if m['id'] == identifier), None)
    transport = MemoryTransport(heater)
    client = HeatingClient(ProtocolSession(transport))
    service = BridgeService(repo, client=client, autostart=False)
    service._store_time_cache(client.get_time_ranges(timeout=10), datetime.now(ZONE).isoformat())
    server = create_server(create_app(service), host='127.0.0.1', port=0)
    Thread(target=server.run, daemon=True).start()
    browser = Browser()
    try:
        browser.call('Page.enable')
        browser.call('Runtime.enable')
        url = 'http://127.0.0.1:' + str(server.effective_port) + '/'
        browser.call('Page.navigate', dict(url=url))
        browser.wait("document.querySelectorAll('.menu-row').length===1")
        browser.js("document.querySelector('.row-action').click()")
        browser.wait("document.querySelectorAll('.menu-row').length===7")
        browser.js("window.confirm=()=>{throw new Error('Unexpected second confirmation');}")
        for item in [m for m in items if m['type'] in (7, 8, 10, 50, 57, 64)]:
            identifier, kind = item['id'], item['type']
            browser.js(f"document.querySelector('[data-value-id=\"{identifier}\"]').closest('.menu-row').querySelector('button').click()")
            browser.wait("document.querySelector('#parameter-input') !== null && !document.querySelector('#save-parameter').hidden")
            control = browser.js("(()=>{const i=document.querySelector('#parameter-input');return {type:i.type,min:i.min,max:i.max,step:i.step};})()")
            before = heater.parameter_write_count
            if kind == 7:
                assert control == dict(type='number', min='20', max='90', step='0.1'), control
                browser.js("document.querySelector('#parameter-input').value='91';document.querySelector('#save-parameter').click()")
                assert not browser.js("document.querySelector('#parameter-input').checkValidity()")
                assert heater.parameter_write_count == before
            else:
                assert control['type'] == ('checkbox' if kind == 8 else 'time' if kind == 10 else 'text')
            if kind == 8:
                browser.js("document.querySelector('#parameter-input').checked=false")
            else:
                browser.js("document.querySelector('#parameter-input').value=" + json.dumps('07:30' if kind == 10 else '67.5'))
            browser.js("document.querySelector('#save-parameter').click();document.querySelector('#save-parameter').click()")
            browser.wait("document.querySelector('#edit-result').textContent.includes('Änderung bestätigt')")
            assert heater.parameter_write_count == before + 1
            expected = 0 if kind == 8 else 450 if kind == 10 else 675
            assert heater.parameters[item['address']].raw_value == expected
            browser.js("document.querySelector('#close-editor').click()")
        # An unclear result blocks another save until a fresh editor read.
        from unittest.mock import patch
        from froeling_bridge.errors import WriteOutcomeUnknown
        browser.js("document.querySelector('[data-value-id=\"2\"]').closest('.menu-row').querySelector('button').click()")
        browser.wait("document.querySelector('#parameter-input') !== null")
        with patch.object(client, 'set_parameter', side_effect=WriteOutcomeUnknown('parameter write', 0x1234, 'acknowledgements')):
            browser.js("document.querySelector('#parameter-input').value='68';document.querySelector('#save-parameter').click()")
            browser.wait("document.querySelector('#edit-result').textContent.includes('unklar')")
            assert browser.js("document.querySelector('#save-parameter').disabled")
        assert heater.parameter_write_count == 6
        browser.js("document.querySelector('#close-editor').click();document.querySelector('[data-value-id=\"2\"]').closest('.menu-row').querySelector('button').click()")
        browser.wait("document.querySelector('#parameter-input') !== null && !document.querySelector('#save-parameter').disabled")
        browser.js("document.querySelector('#save-parameter').click()")
        browser.wait("document.querySelector('#edit-result').textContent.includes('Unverändert')")
        assert heater.parameter_write_count == 6
        browser.js("document.querySelector('#close-editor').click()")
        browser.js("document.querySelector('[data-value-id=\"8\"]').closest('.menu-row').querySelector('button').click()")
        browser.wait("document.querySelector('#editor-description').textContent.includes('Aktuell gelesen')")
        assert browser.js("document.querySelector('#save-parameter').hidden")
        browser.js("document.querySelector('#close-editor').click();document.querySelector('#nav-times').click()")
        browser.wait("document.querySelectorAll('.interval-row').length===4")
        browser.js("document.querySelector('.interval-row input').value='06:10';document.querySelector('.interval-row button').click()")
        browser.wait("document.querySelector('#notice').textContent.includes('Nachlesen bestätigt')")
        assert heater.time_write_count == 1
        # Time-only authorization must not label normal parameters as writable.
        service.allowed_write_operations = ('write_time_range',)
        browser.call('Page.navigate', dict(url=url))
        browser.wait("document.querySelectorAll('.menu-row').length===1")
        browser.js("document.querySelector('.row-action').click()")
        browser.wait("document.querySelectorAll('.menu-row').length===7")
        assert browser.js("document.querySelector('[data-value-id=\"2\"]').closest('.menu-row').querySelector('button').textContent") == 'Ansehen'
        browser.js("document.querySelector('[data-value-id=\"2\"]').closest('.menu-row').querySelector('button').click()")
        browser.wait("document.querySelector('#parameter-input') !== null")
        assert browser.js("document.querySelector('#parameter-input').disabled && document.querySelector('#save-parameter').hidden")
        assert heater.parameter_write_count == 6
        assert not browser.errors, browser.errors
        print('PASS Chromium: all six p4d parameter editors, native limits/steps, one save, readback, double-click protection, read-only IO, time program and time-only permissions. Fictional simulator only.')
    finally:
        browser.close()
        server.close()
        service.close()


if __name__ == '__main__':
    main()
