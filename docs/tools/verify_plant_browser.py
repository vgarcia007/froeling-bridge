"""Check functional plant UI with fictional equipment only, never physical hardware."""
import argparse
import json
import tempfile
from threading import Thread
from pathlib import Path
from waitress import create_server
from verify_menu_browser import Browser
from preview_plant import fictional_runtime, snapshot_preview
from froeling_bridge.api import create_app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate-only',action='store_true',required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        runtime,transport=fictional_runtime(directory)
        service=runtime.service
        server=create_server(create_app(service),host='127.0.0.1',port=0)
        Thread(target=server.run,daemon=True).start()
        browser=Browser()
        try:
            browser.call('Page.enable');browser.call('Runtime.enable')
            url='http://127.0.0.1:'+str(server.effective_port)+'/anlage'
            for width in (320,390,768,1440):
                browser.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=1000,deviceScaleFactor=1,mobile=width<650))
                browser.call('Page.navigate',dict(url=url))
                browser.wait("document.querySelectorAll('.plant-card').length===6 && !document.querySelector('#plant-view').hidden")
                assert browser.js("document.querySelector('#nav-plant').classList.contains('active')")
                assert browser.js("document.documentElement.scrollWidth <= window.innerWidth"), ('overflow',width)
                assert browser.js("(()=>{const a=document.querySelector('#view-title').getBoundingClientRect(), b=document.querySelector('#refresh').getBoundingClientRect();return a.right<=b.left || a.bottom<=b.top || b.bottom<=a.top;})()"), ('heading overlaps button',width)
                assert browser.js("document.querySelectorAll('.plant-running').length")>=3
                browser.js("document.querySelector('[data-component-id=\"boiler-301\"] details').open=true")
                browser.wait("document.querySelector('[data-component-id=\"boiler-301\"] .plant-setting strong').textContent.includes('60')")
                assert browser.js("document.querySelectorAll('[data-component-id=\"boiler-301\"] .plant-setting').length") == 2
                assert not browser.js("document.querySelector('#plant-view').textContent.includes('0x')")
                browser.js("document.querySelector('#nav-menu').click()")
                assert browser.js("location.pathname==='/'")
                browser.js("document.querySelector('#nav-plant').click()")
                browser.wait("location.pathname==='/anlage' && !document.querySelector('#plant-view').hidden")
            browser.js("window.realPlantFetch=window.fetch; window.fetch=(...a)=>String(a[0]).endsWith('/plant')?Promise.reject(new Error('test offline')):window.realPlantFetch(...a); loadPlant()")
            browser.wait("document.querySelector('#plant-status').textContent.includes('nicht erreichbar') && document.querySelectorAll('.plant-running').length===0")
            browser.js("window.fetch=window.realPlantFetch;loadPlant()")
            browser.wait("document.querySelectorAll('.plant-running').length>=3")
            # Snapshot preview can consume GET /sensors, but must reject every mutation.
            snapshot=Path(directory)/'source.json'
            source_client=create_app(service).test_client()
            snapshot.write_text(json.dumps(dict(menu=runtime.repository.menu_catalog(),sensors=source_client.get('/api/v1/sensors').get_json())))
            with tempfile.TemporaryDirectory() as readonly_directory:
                preview,owner=snapshot_preview(snapshot,readonly_directory,'http://127.0.0.1:'+str(server.effective_port))
                try:
                    before=len(transport.requests)
                    client=preview.test_client()
                    assert client.get('/api/v1/plant').status_code==200
                    assert client.post('/api/v1/jobs',json=dict(operation='status')).status_code==403
                    assert client.post('/api/v1/plant/activate',json={}).status_code==403
                    assert client.patch('/api/v1/sensors/VA/400',json=dict(active=True)).status_code==403
                    assert len(transport.requests)==before
                finally:owner.close()
            # Stale pump commands must not be animated as if confirmed active.
            with service.lock:
                for row in service.values.values():row['origin']='local-persisted'
            browser.js('loadPlant()')
            browser.wait("document.querySelectorAll('.plant-running').length===0")
            assert browser.js("document.querySelector('#plant-grid').textContent.includes('Zustand unbekannt')")
            # Controller text must be rendered as text, never executable markup.
            with runtime.repository.transaction() as db:
                row=db.execute('SELECT id,data FROM menu WHERE id=4').fetchone()
                item=json.loads(row[1]);item['title']='Kesselladepumpe <img src=x onerror="window.plantInjected=true">'
                db.execute('UPDATE menu SET data=? WHERE id=?',(json.dumps(item),row[0]))
            browser.js('window.plantInjected=false; loadPlant()')
            browser.wait("document.querySelector('#plant-grid').textContent.includes('<img')")
            assert browser.js("document.querySelectorAll('#plant-grid img').length===0 && window.plantInjected===false")
            assert transport.heater.parameter_write_count==0
            assert transport.heater.time_write_count==0
            assert not browser.errors,browser.errors
            print('Plant browser: four viewport widths, direct route/navigation, fresh/stale pumps, automatic threshold reads; no heater writes.')
        finally:
            browser.close();server.close();runtime.close()


if __name__=='__main__':main()
