"""Check heating error layout in Chromium, exclusively with fictional data."""
import argparse
from datetime import datetime
import tempfile
from threading import Thread
from waitress import create_server
from verify_menu_browser import Browser
from froeling_bridge.api import create_app
from froeling_bridge.client import HeatingClient
from froeling_bridge.messages import ErrorEntry
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport, demo_heater
from froeling_bridge.standalone import StandaloneRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate-only', action='store_true', required=True)
    parser.parse_args()
    heater = demo_heater()
    entries = []
    for index, state in enumerate((1, 4, 2)):
        description = ('Fiktive längere Heizungsmeldung mit mehreren Wörtern und Sonderzeichen <img onerror=alert(1)>').encode('latin1')
        entries.append(ErrorEntry(100 + index, 0, 1, datetime(2026, 1, 1, 10, index), description))
        if state in (4, 2):
            entries.append(ErrorEntry(100 + index, 0, 4, datetime(2026, 1, 1, 11, index), description))
        if state == 2:
            entries.append(ErrorEntry(100 + index, 0, 2, datetime(2026, 1, 1, 12, index), description))
    heater.errors = tuple(entries)
    transport = MemoryTransport(heater)
    with tempfile.TemporaryDirectory() as directory:
        runtime = StandaloneRuntime(directory, lambda: (HeatingClient(ProtocolSession(transport)), lambda: None), simulator=True, autostart=False)
        runtime.discover_once()
        runtime.refresh_errors()
        server = create_server(create_app(runtime.service), host='127.0.0.1', port=0)
        Thread(target=server.run, daemon=True).start()
        browser = Browser()
        try:
            browser.call('Page.enable')
            browser.call('Runtime.enable')
            for width in (320, 390, 768, 1440):
                browser.call('Emulation.setDeviceMetricsOverride', dict(width=width, height=900, deviceScaleFactor=1, mobile=width<650))
                browser.call('Page.navigate', dict(url='http://127.0.0.1:' + str(server.effective_port) + '/'))
                browser.wait("document.querySelectorAll('.menu-row').length>0")
                before = len(transport.requests)
                browser.js("document.querySelector('#nav-errors').click()")
                browser.wait("document.querySelectorAll('.error-entry').length===3")
                browser.call('Emulation.setPageScaleFactor', dict(pageScaleFactor=1))
                layout = browser.js("({overflow:document.documentElement.scrollWidth>innerWidth, rows:Array.from(document.querySelectorAll('.error-entry')).map(e=>({width:e.querySelector('.error-title').getBoundingClientRect().width,height:e.getBoundingClientRect().height})), images:document.querySelectorAll('#errors-list img').length,states:Array.from(document.querySelectorAll('.error-state')).map(e=>e.textContent)})")
                assert not layout['overflow'], (width,layout)
                assert browser.js('document.documentElement.scrollWidth') <= width, (width,layout)
                assert layout['images']==0
                assert set(layout['states'])=={'gekommen','gegangen','quittiert'}
                assert all(row['width']>=min(220,width-100) and row['height']<380 for row in layout['rows']), (width,layout)
                assert len(transport.requests)==before
            assert not browser.errors
            print('PASS Chromium: error entries at 320/390/768/1440px, full-width titles, compact dates, all states, no page overflow or HTML injection; fictional data only.')
        finally:
            browser.close()
            runtime.close()
            server.close()


if __name__ == '__main__':
    main()
