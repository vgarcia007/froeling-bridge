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
                assert set(layout['states'])=={'Aktiv bestätigt','gegangen','quittiert'}
                assert all(row['width']>=min(220,width-100) and row['height']<380 for row in layout['rows']), (width,layout)
                assert len(transport.requests)==before
            # A fictional stored history is longer than one page. No MariaDB connection.
            original_view = runtime.errors_view
            def historical_view(source="auto", limit=100, offset=0):
                from froeling_bridge.controller_errors import page
                data = original_view("controller", 1000, 0)
                original_items = data["items"]
                all_items = [dict(original_items[index % len(original_items)], id=index+1) for index in range(105)]
                old_open = next(item for item in original_items if item["state"] == "gekommen")
                all_items[0] = dict(old_open,id=999,active=None,activity_basis="not_in_controller",activity_checked_at=None,time1=datetime(2020,1,1))
                data.update(page(all_items[offset:offset+limit],len(all_items),limit,offset),
                            source="p4d-database",history_configured=True,history_available=True)
                return data
            runtime.errors_view = historical_view
            browser.js("document.querySelector('#refresh').click()")
            browser.wait("document.querySelectorAll('.error-entry').length===100")
            assert browser.js("document.querySelector('#errors-status').textContent.includes('Datenbankhistorie')")
            assert browser.js("document.querySelector('.error-entry .error-state').textContent==='Nicht bestätigt'")
            assert not browser.js("document.querySelector('.error-entry .error-state').classList.contains('error-state-active')")
            assert browser.js("document.querySelector('.error-entry .error-context').textContent.includes('Historischer Eintrag')")
            browser.js("document.querySelector('#errors-next').click()")
            browser.wait("document.querySelectorAll('.error-entry').length===5")
            assert browser.js("document.querySelector('#errors-page-status').textContent==='101–105 von 105'")
            browser.js("document.querySelector('#errors-previous').click()")
            browser.wait("document.querySelectorAll('.error-entry').length===100")
            assert len(transport.requests)==before
            for width in (320, 390):
                browser.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=900,deviceScaleFactor=1,mobile=True))
                browser.call('Emulation.setPageScaleFactor',dict(pageScaleFactor=1))
                assert browser.js('document.documentElement.scrollWidth') <= width
            assert not browser.errors
            print('PASS Chromium: error entries at 320/390/768/1440px, full-width titles, compact dates, all states, no page overflow or HTML injection, 105 stored entries with next/previous pagination, unconfirmed history not labeled active; fictional data only.')
        finally:
            browser.close()
            runtime.close()
            server.close()


if __name__ == '__main__':
    main()
