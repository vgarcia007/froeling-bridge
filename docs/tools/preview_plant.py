"""Preview /anlage using fictional hardware or a private read-only catalogue snapshot.

A snapshot is the JSON inspection report containing menu and sensors.items under out.
With --source-url, only GET /api/v1/sensors is called on that Bridge. All mutations
on a snapshot preview are rejected, including parameter reads and sensor activation.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from threading import RLock
import time
from urllib.parse import urlparse
from urllib.request import urlopen, build_opener, ProxyHandler

from froeling_bridge.api import create_app
from froeling_bridge.client import HeatingClient
from froeling_bridge.local_store import LocalRepository
from froeling_bridge.messages import MenuItem, ValueSpec, Command
from froeling_bridge.service import BridgeService
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport, demo_heater
from froeling_bridge.standalone import StandaloneRuntime


def fictional_runtime(directory):
    heater = demo_heater()
    menu, specs = [], []
    def group(parent, child, name):
        menu.append(MenuItem(33, parent, child, 0, name.encode('latin1')))
    def reading(parent, address, title, value, unit='°C'):
        specs.append(ValueSpec(address, 10, 2, b'\xb0 ' if unit=='°C' else b'% ', title.encode('latin1')))
        menu.append(MenuItem(3, parent, 0, address, title.encode('latin1')))
        heater.measurements[address]=int(value*10)
    def setting(parent, address, title, value):
        menu.append(MenuItem(7,parent,0,address,title.encode('latin1')))
        heater.parameters[address]=replace(heater.parameters[0x1234],address=address,raw_value=int(value*10))
    group(1,100,'Kessel')
    reading(100,400,'Kesseltemperatur',76.4)
    reading(100,401,'Rücklauftemperatur',61.8)
    reading(100,402,'Kesselladepumpe',70,'%')
    setting(100,900,'Kessel-Solltemperatur',80)
    group(1,200,'Puffer 01')
    reading(200,410,'Puffertemperatur oben',72.3)
    reading(200,411,'Puffertemperatur unten',44.2)
    reading(200,412,'Pufferpumpen Ansteuerung',62,'%')
    setting(200,901,'Minimale Drehzahl der Pufferpumpe',30)
    for index in (1,2):
        parent=300+index
        group(1,parent,'Boiler 0'+str(index))
        reading(parent,420+index,'Boilertemperatur oben',48.1+index*3)
        reading(parent,430+index,'Boilerpumpe Ansteuerung',55 if index==1 else 0,'%')
        setting(parent,910+index,'Gewünschte Boilertemperatur',60 if index==1 else 55)
        setting(parent,920+index,'Nachladen, wenn Boilertemperatur unter',45)
    for index in (1,2):
        parent=500+index
        group(1,parent,'Heizkreis 0'+str(index))
        reading(parent,440+index,'Vorlauf-Isttemperatur',34.5+index*3)
        reading(parent,450+index,'Vorlauf-Solltemperatur',38+index*3)
        menu.append(MenuItem(17,parent,0,10+index,b'Heizkreispumpe'))
        heater.io_states[(Command.DIGITAL_OUT,10+index)]=(255,1 if index==1 else 0)
        setting(parent,930+index,'Maximale Heizkreis Vorlauftemperatur',55)
    heater.menu=tuple(menu);heater.value_specs=tuple(specs)
    transport=MemoryTransport(heater)
    runtime=StandaloneRuntime(directory,lambda:(HeatingClient(ProtocolSession(transport)),lambda:None),simulator=True,autostart=False)
    runtime.discover_once();runtime.refresh_status();runtime.service.collect_once()
    return runtime,transport


def snapshot_preview(snapshot, directory, source_url=None):
    data=json.loads(Path(snapshot).read_text())
    if data.get('ok') is False:
        raise ValueError('Snapshot inspection failed')
    data=data.get('out',data)
    repo=LocalRepository(Path(directory)/'catalogue.sqlite3')
    repo.replace_catalogue(data['sensors']['items'],data['menu'])
    repo.configurable=False
    repo.source='read-only-api-preview'
    service=BridgeService(repo,mode='database',autostart=False)
    app=create_app(service, authentication=False)  # Isolated read-only preview, never production.
    original_health=app.view_functions['health']
    def preview_health():
        response,status=original_health()
        data=response.get_json();data['preview']=True
        from flask import jsonify
        return jsonify(data),status
    app.view_functions['health']=preview_health
    current={'items':data['sensors']['items'],'at':0}
    lock=RLock()
    if source_url and (urlparse(source_url).scheme not in ('http','https') or not urlparse(source_url).netloc):
        raise ValueError('source-url must be an HTTP(S) Bridge base URL')
    opener=build_opener(ProxyHandler({}))
    def sensors():
        with lock:
            return [{k:v for k,v in s.items() if k!='latest'} for s in current['items']]
    repo.sensors=sensors
    @app.before_request
    def readonly_source():
        from flask import request,jsonify
        if request.method not in ('GET','HEAD'):
            return jsonify(error=dict(code='read_only',message='read-only API preview')),403
        with lock:
            if source_url and time.monotonic()-current['at']>3:
                try:
                    with opener.open(source_url.rstrip('/')+'/api/v1/sensors',timeout=3) as f:
                        current['items']=json.load(f)['items']
                    current['at']=time.monotonic()
                except Exception:
                    for s in current['items']:
                        if s.get('latest'):s['latest']['stale']=True
            values=[];errors=[]
            for s in current['items']:
                latest=s.get('latest')
                if latest:
                    value=dict(latest)
                    if not source_url:value['origin']='local-persisted'
                    values.append(value)
                    if latest.get('stale'):errors.append(dict(type=s['type'],address=s['address']))
            with service.lock:
                service.values={(v['address'],v['type']):v for v in values}
                service.collector_state['errors']=errors
    return app,service


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--simulate-only',action='store_true')
    source.add_argument('--source-snapshot')
    parser.add_argument('--source-url',help='optional live Bridge base URL, GET /sensors only')
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--port',type=int,default=8001)
    args=parser.parse_args()
    if args.source_url and not args.source_snapshot:parser.error('source-url requires a catalogue snapshot')
    from waitress import serve
    with tempfile.TemporaryDirectory(prefix='froeling-plant-preview-') as directory:
        if args.simulate_only:
            runtime,_=fictional_runtime(directory)
            app,owner=create_app(runtime.service),runtime
        else:
            app,owner=snapshot_preview(args.source_snapshot,directory,args.source_url)
        print('Separate plant preview: http://'+args.host+':'+str(args.port)+'/anlage',flush=True)
        print('Fictional data only.' if args.simulate_only else 'Read-only preview. No heater commands or source configuration changes.',flush=True)
        try:serve(app,host=args.host,port=args.port)
        finally:owner.close()

if __name__=='__main__':main()
