from datetime import datetime, timedelta
from threading import Event
from unittest.mock import patch
import time
import unittest

try:
    import flask
    from importlib.metadata import version
    if tuple(int(p) for p in version("Flask").split(".")[:2]) < (3, 1):
        flask = None
except ImportError:
    flask = None

from froeling_bridge.api import create_app
from froeling_bridge.client import HeatingClient
from froeling_bridge.service import BridgeService
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport
from froeling_bridge.messages import Command
from froeling_bridge.storage import MemoryRepository, DatabaseUnavailable


@unittest.skipIf(flask is None, 'install .[service] for HTTP tests')
class APITests(unittest.TestCase):
    def setUp(self):
        self.service = BridgeService(autostart=False)
        self.addCleanup(self.service.close)
        self.http = create_app(self.service).test_client()

    def wait_job(self, identifier, http=None):
        http = http or self.http
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            result = http.get('/api/v1/jobs/' + identifier).get_json()
            if result['state'] in ('completed', 'failed'):
                return result
            time.sleep(.005)
        self.fail('job did not finish')

    def post(self, payload):
        response = self.http.post('/api/v1/jobs', json=payload)
        self.assertEqual(response.status_code, 202, response.get_json())
        self.assertEqual(response.headers['Location'], response.get_json()['url'])
        return self.wait_job(response.get_json()['id'])

    def test_menu_and_confirmed_write_then_unchanged(self):
        menu = self.http.get('/api/v1/menu?parent=10').get_json()
        self.assertTrue(menu['items'][0]['editable'])
        for status in ('confirmed', 'unchanged'):
            job = self.post(dict(operation='write_parameter', menu_id=2, value='67.5'))
            self.assertEqual(job['result']['status'], status)
            self.assertEqual(job['result']['current']['value'], '67.5')
        read = self.post(dict(operation='read_parameter', menu_id=2))
        self.assertEqual(read['result']['value'], '67.5')

    def test_boolean_time_and_measurement(self):
        self.assertEqual(self.post(dict(operation='write_parameter', menu_id=3, value=False))['result']['status'], 'confirmed')
        self.assertEqual(self.post(dict(operation='write_parameter', menu_id=4, value='07:30'))['result']['current']['raw_value'], 450)
        value = self.post(dict(operation='measurement', address=43, type='VA'))
        self.assertEqual(value['result']['value'], '-1.2')
        result = self.post(dict(operation='write_time_range', address=56, index=1, start='12:00', end='13:00'))
        self.assertEqual(result['result']['current']['ranges'][1], {'start':'12:00', 'end':'13:00'})
        self.assertEqual(result['result']['current']['ranges'][0], {'start':'06:00', 'end':'08:00'})

    def test_bad_input_and_unknown_types(self):
        for payload in (None, {}, {'operation':'bad'}, {'operation':'write_parameter','menu_id':1,'value':'5'},
                        {'operation':'write_parameter','menu_id':2,'value':67.5},
                        {'operation':'write_parameter','menu_id':3,'value':'true'},
                        {'operation':'write_parameter','menu_id':2,'value':'NaN'},
                        {'operation':'write_time_range','address':56,'index':4,'start':'12:00','end':'13:00'},
                        {'operation':'write_time_range','address':56,'index':0,'start':'12:01','end':'13:00'},
                        {'operation':'write_time_range','address':56,'index':0,'start':None,'end':'13:00'}):
            r = self.http.post('/api/v1/jobs', json=payload)
            self.assertIn(r.status_code, (400, 415), payload)
        result = self.post(dict(operation='write_parameter',menu_id=2,value='99.0'))
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['error']['code'], 'validation_error')

    def test_write_uncertain_is_not_replayed(self):
        transport = MemoryTransport(wire_filter=lambda req, wire: b'' if req.command == Command.SET_PARAMETER else wire)
        self.service.client = HeatingClient(ProtocolSession(transport))
        result = self.post(dict(operation='write_parameter', menu_id=2, value='67.5'))
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['error']['code'], 'outcome_unknown')
        self.http.get('/api/v1/health')
        self.http.get('/api/v1/jobs/' + result['id'])
        self.assertEqual(transport.heater.parameter_write_count, 1)

    def test_write_verification_failure_preserves_actual(self):
        transport = MemoryTransport()
        original = transport.heater.handle
        def handle(req):
            result = original(req)
            if req.command == Command.SET_PARAMETER:
                from dataclasses import replace
                transport.heater.parameters[4660] = replace(transport.heater.parameters[4660], raw_value=660)
            return result
        transport.heater.handle = handle
        self.service.client = HeatingClient(ProtocolSession(transport))
        result = self.post(dict(operation='write_parameter', menu_id=2, value='67.5'))
        self.assertEqual(result['error']['code'], 'verification_failed')
        self.assertEqual(result['error']['actual']['value'], '66')

    def test_health_and_menu_remain_available_during_slow_work(self):
        entered, release = Event(), Event()
        future = self.service.worker.submit(lambda: (entered.set(), release.wait(2)))
        self.assertTrue(entered.wait(1))
        try:
            started = time.monotonic()
            self.assertEqual(self.http.get('/api/v1/health').status_code, 200)
            self.assertEqual(self.http.get('/api/v1/menu').status_code, 200)
            self.assertLess(time.monotonic() - started, .5)
        finally:
            release.set()
        future.result(1)

    def test_slow_database_does_not_block_worker(self):
        entered, release = Event(), Event()
        original = self.service.repository.store_cycle
        def slow(*args):
            entered.set(); release.wait(2); return original(*args)
        self.service.repository.store_cycle = slow
        from threading import Thread
        collector = Thread(target=self.service.collect_once)
        collector.start()
        self.assertTrue(entered.wait(1))
        try:
            self.assertEqual(self.post(dict(operation='status'))['state'], 'completed')
            self.assertEqual(self.http.get('/api/v1/health').status_code, 200)
        finally:
            release.set(); collector.join(2)
        self.assertFalse(collector.is_alive())

    def test_history_filters_and_freshness(self):
        self.service.collect_once()
        values = self.http.get('/api/v1/values').get_json()['items']
        self.assertEqual(len(values), 5)
        self.assertFalse(any(v['stale'] for v in values))
        response = self.http.get('/api/v1/history?address=43&type=VA&start=2000-01-01&end=2099-01-01')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['items'][0]['value'], '-1.2')
        for query in ('limit=1001', 'aggregate=X', 'type=VA%27', 'start=2099-01-01', 'start=2020-01-01T00:00:00Z', 'end=bad', 'address=-1'):
            r = self.http.get('/api/v1/history?address=43&type=VA&start=2000-01-01&end=2099-01-01&' + query)
            self.assertEqual(r.status_code, 400)

    def test_read_only_mode_has_no_controller_or_collector(self):
        service = BridgeService(mode='database', autostart=False)
        self.addCleanup(service.close)
        http = create_app(service).test_client()
        self.assertFalse(http.get('/api/v1/collector').get_json()['enabled'])
        self.assertEqual(http.post('/api/v1/jobs', json={'operation':'status'}).status_code, 409)
        self.assertEqual(http.get('/api/v1/values').status_code, 409)
        self.assertFalse(http.get('/api/v1/menu?parent=10').get_json()['items'][0]['editable'])
        self.assertIsNone(service.worker)

    def test_errors_do_not_expose_driver_messages(self):
        self.service.repository.sensors = lambda: (_ for _ in ()).throw(DatabaseUnavailable('SECRET'))
        r = self.http.get('/api/v1/sensors')
        self.assertEqual(r.status_code, 503)
        self.assertNotIn('SECRET', r.get_data(as_text=True))
        self.assertEqual(self.http.get('/api/v1/jobs/absent').status_code, 404)
        self.assertEqual(self.http.get('/api/v1/menu?parent=bad').status_code, 400)

    def test_job_registry_is_bounded_and_completed_jobs_expire(self):
        self.service.job_limit = 1
        first = self.post(dict(operation='status'))['id']
        self.post(dict(operation='firmware'))
        self.assertEqual(self.http.get('/api/v1/jobs/'+first).status_code, 404)
        self.assertEqual(len(self.service.jobs), 1)

    def test_full_queue_returns_503(self):
        self.service.job_limit = 1
        entered, release = Event(), Event()
        future = self.service.worker.submit(lambda: (entered.set(), release.wait(2)))
        self.assertTrue(entered.wait(1))
        try:
            self.assertEqual(self.http.post('/api/v1/jobs', json={'operation':'status'}).status_code, 202)
            self.assertEqual(self.http.post('/api/v1/jobs', json={'operation':'status'}).status_code, 503)
        finally:
            release.set()
        future.result(1)

    def test_openapi_matches_routes(self):
        spec = self.http.get('/api/v1/openapi.json').get_json()
        self.assertEqual(spec['openapi'], '3.0.3')
        self.assertEqual(len(spec['components']['schemas']['JobRequest']['oneOf']), 8)
        rules = {r.rule.replace('<identifier>', '{id}') for r in self.http.application.url_map.iter_rules() if r.rule.startswith('/api/v1')}
        self.assertEqual(rules, set(spec['paths']))
