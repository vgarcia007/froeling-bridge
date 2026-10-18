"""Functional grouping and read-only refresh with fictional controller data."""
from datetime import datetime
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import Mock

from froeling_bridge.api import create_app
from froeling_bridge.client import HeatingClient
from froeling_bridge.errors import RequestTimeout
from froeling_bridge.local_store import LocalRepository
from froeling_bridge.plant import PlantOverview
from froeling_bridge.service import BridgeService
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport
from froeling_bridge.storage import ZONE


def fixtures():
    rows = []
    def menu(parent, child, kind, address, title):
        rows.append(dict(id=len(rows)+1, parent=parent, child=child, type=kind, address=address, title=title, value=None))
    menu(1, 100, 1, 0, 'Kessel')
    menu(100, 0, 3, 43, 'Kesseltemperatur')
    menu(1, 200, 1, 0, 'Wasser')
    for index in (1, 2):
        parent = 200 + index
        menu(200, parent, 33, 0, 'Boiler 0'+str(index))
        menu(parent, 0, 3, 50+index, 'Boilertemperatur oben')
        menu(parent, 0, 3, 60+index, 'Boilerpumpe Ansteuerung')
        menu(parent, 0, 7, 0x1234, 'Gewünschte Boilertemperatur')
        menu(parent, 0, 7, 0x1234, 'Nachladen, wenn Boilertemperatur unter')
    menu(999, 9999, 33, 0, 'Boiler 09')
    sensors = []
    for address, title, unit in [(43,'Kesseltemperatur','°C'), (51,'Boilertemperatur oben','°C'), (52,'Boilertemperatur oben','°C'), (61,'Boilerpumpe Ansteuerung','%'), (62,'Boilerpumpe Ansteuerung','%')]:
        sensors.append(dict(type='VA', address=address, title=title, usrtitle=None, unit=unit, state='D', record='D', factor=10, res1=2))
    sensors.append(dict(type='AO', address=7, title='Pumpe 0.1', usrtitle=None, unit='%', state='A', record='D', factor=1, res1=1))
    return sensors, rows


class PlantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = LocalRepository(Path(self.temp.name)/'catalogue.sqlite3')
        self.sensors, self.menu = fixtures()
        self.repo.replace_catalogue(self.sensors, self.menu)
        self.transport = MemoryTransport()
        self.service = BridgeService(self.repo, mode='standalone-demo', client=HeatingClient(ProtocolSession(self.transport)), autostart=False)
        self.addCleanup(self.service.close)
        self.http = create_app(self.service).test_client()

    def view(self):
        response = self.http.get('/api/v1/plant')
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def refresh(self, component='boiler-201'):
        response = self.http.post('/api/v1/jobs', json=dict(operation='refresh_component', component_id=component))
        self.assertEqual(response.status_code, 202)
        return response.get_json()['id']

    def wait(self, identifier):
        for _ in range(200):
            result = self.service.get_job(identifier)
            if result['state'] in ('completed','failed'):
                return result
            time.sleep(.01)
        self.fail('Refresh did not finish')

    def test_distinct_instances_use_menu_edges_and_not_equal_sensor_names(self):
        view = self.view()
        self.assertEqual([c['title'] for c in view['components']], ['Kessel','Boiler 01','Boiler 02'])
        self.assertEqual([m['sensor']['address'] for m in view['components'][1]['metrics']], [51,61])
        self.assertEqual([m['sensor']['address'] for m in view['components'][2]['metrics']], [52,62])
        self.assertEqual(view['unassigned'][0]['title'], 'Pumpe 0.1')
        self.assertTrue(all(c['presence']=='menu-catalogue' for c in view['components']))

    def test_display_rights_menu_is_not_an_extra_boiler(self):
        self.menu.append(dict(id=100,parent=1,child=900,type=46,address=0,title='Display Bedienrechte',value=None))
        self.menu.append(dict(id=101,parent=900,child=901,type=46,address=0,title='Kessel',value=None))
        self.repo.replace_catalogue(self.sensors,self.menu)
        self.assertEqual(len(self.view()['components']),3)

    def test_page_and_get_never_read_heater_or_change_flags(self):
        before = self.repo.sensors()
        self.service.client.get_parameter = Mock(side_effect=AssertionError('GET opened controller'))
        self.assertEqual(self.http.get('/anlage').status_code, 200)
        for _ in range(3):
            self.view()
        self.assertEqual(before, self.repo.sensors())
        self.assertEqual(self.transport.requests, [])

    def test_activation_adds_only_assigned_sensors_and_preserves_record_flags(self):
        self.repo.patch_sensor('VA', 51, {'record': True, 'active': False})
        before = {(s['type'],s['address']):s['record'] for s in self.repo.sensors()}
        response = self.http.post('/api/v1/plant/activate', json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()['activated']), 4)
        self.assertEqual(before, {(s['type'],s['address']):s['record'] for s in self.repo.sensors()})
        self.assertEqual(self.repo.sensors()[0]['state'], 'A') # preselected unassigned output
        self.assertTrue(self.view()['enabled'])
        self.assertEqual(self.http.post('/api/v1/plant/activate',json={}).get_json()['activated'], [])
        self.assertEqual(self.transport.requests, [])

    def test_ambiguous_sensor_is_not_activated(self):
        row = next(m for m in self.menu if m['parent']==202 and m['address']==52)
        row['address']=51
        self.repo.replace_catalogue(self.sensors,self.menu)
        view=self.view()
        self.assertTrue(view['components'][1]['metrics'][0]['ambiguous'])
        self.assertNotIn(dict(type='VA',address=51), view['additional_sensors'])

    def test_refresh_parameters_persist_and_do_not_write(self):
        before=self.repo.sensors()
        result=self.wait(self.refresh())
        self.assertEqual(result['state'],'completed')
        self.assertEqual(result['result']['read'],2)
        settings=self.view()['components'][1]['settings']
        self.assertTrue(all(s['value']=='65' and not s['stale'] for s in settings))
        self.assertTrue(PlantOverview(self.service).cache)
        self.assertTrue(self.repo.get_meta('plant_parameters'))
        self.assertEqual(self.repo.sensors(), before)
        # 0x39 and 0x50 are heater writes; recorded requests are decoded Frame objects.
        self.assertTrue(all(r.command not in (0x39,0x50) for r in self.transport.requests))

    def test_menu_read_updates_all_overview_references_to_same_parameter(self):
        menu_id=next(m['id'] for m in self.menu if m['parent']==201 and m['type']==7)
        identifier=self.service.submit_job(dict(operation='read_parameter',menu_id=menu_id))
        self.assertEqual(self.wait(identifier)['state'],'completed')
        for component in self.view()['components'][1:]:
            self.assertTrue(all(s['value']=='65' and not s['stale'] for s in component['settings']))

    def test_parallel_refresh_is_shared_and_yields_to_other_worker_jobs(self):
        started, release = Event(), Event()
        original = self.service.client.get_parameter
        order=[]
        def read(address):
            order.append('parameter')
            if len(order)==1:
                started.set();self.assertTrue(release.wait(2))
            return original(address)
        self.service.client.get_parameter=read
        identifier=self.refresh()
        self.assertTrue(started.wait(2))
        self.assertEqual(identifier,self.refresh())
        future=self.service.worker.submit(lambda:order.append('regular-read'))
        release.set();self.wait(identifier);future.result(timeout=2)
        self.assertEqual(order,['parameter','regular-read','parameter'])

    def test_concurrent_component_refreshes_are_bounded(self):
        for index in (3,4,5):
            parent=200+index
            self.menu.append(dict(id=len(self.menu)+1,parent=200,child=parent,type=33,address=0,title='Boiler 0'+str(index),value=None))
            self.menu.append(dict(id=len(self.menu)+1,parent=parent,child=0,type=7,address=0x1234,title='Gewünschte Boilertemperatur',value=None))
        self.repo.replace_catalogue(self.sensors,self.menu)
        started,release=Event(),Event()
        original=self.service.client.get_parameter
        def read(address):
            started.set()
            if not release.wait(3):raise AssertionError('Test release missing')
            return original(address)
        self.service.client.get_parameter=read
        ids=[self.refresh()]
        self.assertTrue(started.wait(2))
        try:
            ids.extend(self.refresh('boiler-'+str(parent)) for parent in (202,203,204))
            response=self.http.post('/api/v1/jobs',json=dict(operation='refresh_component',component_id='boiler-205'))
            self.assertEqual(response.status_code,503)
        finally:release.set()
        self.assertTrue(all(self.wait(i)['state']=='completed' for i in ids))

    def test_failed_refresh_preserves_value_and_reports_old_observation(self):
        self.wait(self.refresh())
        before=self.view()['components'][1]['settings'][0]
        self.service.client.get_parameter=Mock(side_effect=RequestTimeout())
        result=self.wait(self.refresh())
        self.assertTrue(result['result']['errors'])
        after=self.view()['components'][1]['settings'][0]
        self.assertEqual((before['value'],before['observed_at']),(after['value'],after['observed_at']))
        self.assertTrue(after['stale'])
        self.assertTrue(after['error'])

    def test_sensor_freshness_matches_sensors_endpoint(self):
        stamp=datetime.now(ZONE).isoformat()
        self.service.values[(61,'VA')]=dict(type='VA',address=61,value='60',unit='%',title='Boilerpumpe Ansteuerung',observed_at=stamp,origin='controller')
        metric=self.view()['components'][1]['metrics'][1]
        self.assertFalse(metric['sensor']['latest']['stale'])
        self.service.values[(61,'VA')]['origin']='local-persisted'
        self.assertTrue(self.view()['components'][1]['metrics'][1]['sensor']['latest']['stale'])

    def test_invalid_requests_and_unknown_components_do_not_enqueue_work(self):
        for payload in [dict(operation='refresh_component'),dict(operation='refresh_component',component_id='missing'),dict(operation='refresh_component',component_id='boiler-201',address=123)]:
            self.assertEqual(self.http.post('/api/v1/jobs',json=payload).status_code,400)
        self.assertEqual(self.http.post('/api/v1/plant/activate',json={'record':True}).status_code,400)
        self.assertEqual(self.http.get('/api/v1/plant?refresh=true').status_code,400)
        self.assertEqual(self.transport.requests,[])
