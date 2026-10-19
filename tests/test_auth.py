"""Security checks use fictional controller data and a private temporary auth DB."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
import sqlite3
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch

from froeling_bridge.api import create_app
from froeling_bridge.auth import AuthStore, AuthUnavailable, COOKIE, Throttled, main
from froeling_bridge.service import BridgeService
from froeling_bridge.errors import ValidationError

ORIGIN = 'https://bridge.example.test'
PASSWORD = 'Fictional password for isolated tests 19!'


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = BridgeService(autostart=False)
        self.addCleanup(self.service.close)
        self.service.auth_config = dict(public_origin=ORIGIN)
        self.service.auth_state_dir = self.directory.name
        self.service.allowed_write_operations = {'write_parameter'}
        self.app = create_app(self.service, authentication=True)
        self.http = self.app.test_client()
        self.store = self.service.auth_store
        self.store.add_user('reader', PASSWORD, 'read')
        self.store.add_user('writer', PASSWORD, 'write')
        self.read_key = self.store.create_key('reader', 'test-reader')
        self.write_key = self.store.create_key('writer', 'test-writer', 'write')

    def request(self, method, path, key=None, **kwargs):
        headers = kwargs.pop('headers', {})
        if key is not None:
            headers['Authorization'] = 'Bearer ' + key
        return self.http.open(path, method=method, base_url=ORIGIN, headers=headers, **kwargs)

    def login(self, name='writer', password=PASSWORD):
        response = self.request('GET', '/login')
        csrf = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))[1]
        return self.request('POST', '/api/v1/auth/login', json=dict(username=name,password=password,csrf=csrf),
                            headers={'Origin': ORIGIN})

    def wait_job(self, identifier):
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            result = self.service.get_job(identifier)
            if result['state'] in ('completed', 'failed'):
                return result
            time.sleep(.005)
        self.fail('job timeout')

    def test_all_operational_routes_require_authentication(self):
        for rule in self.app.url_map.iter_rules():
            if not rule.rule.startswith('/api/v1') or rule.rule == '/api/v1/auth/login':
                continue
            path = rule.rule.replace('<identifier>', 'unknown').replace('<sensor_type>', 'VA').replace('<int:address>', '43')
            method = next(m for m in ('GET','POST','PATCH') if m in rule.methods)
            response = self.request(method, path, json={} if method != 'GET' else None)
            self.assertEqual(response.status_code, 401, (path, response.get_json()))
        self.assertEqual(self.request('GET', '/anlage').status_code, 303)
        self.assertEqual(self.request('GET', '/healthz').get_json(), {'status':'ok'})

    def test_read_user_can_read_but_cannot_write_anywhere(self):
        health = self.request('GET','/api/v1/health',self.read_key).get_json()
        self.assertFalse(health['capabilities']['heating_write'])
        self.assertFalse(health['capabilities']['sensor_configuration'])
        self.assertEqual(health['write_operations'], [])
        menu = self.request('GET','/api/v1/menu?parent=10',self.read_key).get_json()
        self.assertFalse(any(m['editable'] for m in menu['items']))
        for path, method, data in [
            ('/api/v1/jobs','POST',dict(operation='write_parameter',menu_id=2,value='67.5')),
            ('/api/v1/jobs','POST',dict(operation='write_time_range',address=56,index=1,start='12:00',end='13:00')),
            ('/api/v1/sensors/VA/43','PATCH',dict(record=True)),
            ('/api/v1/plant/activate','POST',{}),
        ]:
            self.assertEqual(self.request(method,path,self.read_key,json=data).status_code,403,path)
        result = self.request('POST','/api/v1/jobs',self.read_key,json=dict(operation='read_parameter',menu_id=2))
        self.assertEqual(result.status_code,202)
        self.assertEqual(self.wait_job(result.get_json()['id'])['state'],'completed')

    def test_writer_can_write_supported_parameter_but_not_time_program(self):
        response=self.request('POST','/api/v1/jobs',self.write_key,json=dict(operation='write_parameter',menu_id=2,value='67.5'))
        self.assertEqual(response.status_code,202)
        self.assertEqual(self.wait_job(response.get_json()['id'])['result']['status'],'confirmed')
        response=self.request('POST','/api/v1/jobs',self.write_key,json=dict(operation='write_time_range',address=56,index=1,start='12:00',end='13:00'))
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.service.client.session.transport.heater.time_write_count,0)

    def test_key_scope_role_change_and_disable_are_immediate(self):
        capped=self.store.create_key('writer','read-cap','read')
        payload=dict(operation='write_parameter',menu_id=2,value='67.5')
        self.assertEqual(self.request('POST','/api/v1/jobs',capped,json=payload).status_code,403)
        self.store.change_user('writer',role='read')
        self.assertEqual(self.request('POST','/api/v1/jobs',self.write_key,json=payload).status_code,403)
        self.store.change_user('writer',enabled=False)
        self.assertEqual(self.request('GET','/api/v1/health',self.write_key).status_code,401)
        self.store.change_user('writer',enabled=True)
        self.assertEqual(self.request('GET','/api/v1/health',self.write_key).status_code,401)

    def test_queued_write_rechecks_key_revocation_before_transmission(self):
        entered,release=Event(),Event()
        blocking=self.service.worker.submit(lambda:(entered.set(),release.wait(3)))
        self.assertTrue(entered.wait(1))
        try:
            response=self.request('POST','/api/v1/jobs',self.write_key,json=dict(operation='write_parameter',menu_id=2,value='67.5'))
            self.assertEqual(response.status_code,202)
            self.store.revoke_key(self.store.authenticate(self.write_key,'key')['id'])
        finally:release.set()
        blocking.result(1)
        self.assertEqual(self.wait_job(response.get_json()['id'])['state'],'failed')
        self.assertEqual(self.service.client.session.transport.heater.parameter_write_count,0)

    def test_cookie_login_csrf_logout_and_no_bearer_fallback(self):
        response=self.login()
        self.assertEqual(response.status_code,200)
        cookies=response.headers.getlist('Set-Cookie')
        self.assertTrue(any(COOKIE in c and 'Secure' in c and 'HttpOnly' in c and 'SameSite=Strict' in c for c in cookies))
        me=self.request('GET','/api/v1/auth/me').get_json()
        self.assertEqual(me['username'],'writer')
        self.assertEqual(self.request('POST','/api/v1/jobs',json=dict(operation='status')).status_code,403)
        self.assertEqual(self.request('GET','/api/v1/health','invalid-key').status_code,401)
        headers={'Origin':ORIGIN,'X-CSRF-Token':me['csrf']}
        self.assertEqual(self.request('POST','/api/v1/jobs',headers=headers,json=dict(operation='status')).status_code,202)
        self.assertEqual(self.request('POST','/api/v1/auth/logout',headers=headers,json={}).status_code,200)
        self.assertEqual(self.request('GET','/api/v1/auth/me').status_code,401)

    def test_password_reset_ends_sessions_but_not_independent_api_keys(self):
        self.assertEqual(self.login().status_code,200)
        self.store.change_user('writer',password='Another fictional password only for tests!')
        self.assertEqual(self.request('GET','/api/v1/auth/me').status_code,401)
        self.assertEqual(self.request('GET','/api/v1/health',self.write_key).status_code,200)
        for path in ['/api/v1/auth/password','/api/v1/auth/register','/api/v1/auth/users']:
            self.assertEqual(self.request('POST',path,self.write_key,json={}).status_code,403)

    def test_session_expiry_and_replayed_login_csrf(self):
        response=self.login();self.assertEqual(response.status_code,200)
        with self.store.db() as db:db.execute('UPDATE sessions SET seen=?',(time.time()-1801,))
        self.assertEqual(self.request('GET','/api/v1/auth/me').status_code,401)
        page=self.request('GET','/login').get_data(as_text=True)
        csrf=re.search(r'name="csrf" value="([^"]+)"',page)[1]
        with patch('itsdangerous.timed.time.time',return_value=time.time()+601):
            result=self.request('POST','/api/v1/auth/login',json=dict(username='writer',password=PASSWORD,csrf=csrf),headers={'Origin':ORIGIN})
        self.assertEqual(result.status_code,403)

    def test_login_same_origin_required_and_failures_throttled(self):
        self.assertEqual(self.request('POST','/api/v1/auth/login',json=dict(username='writer',password=PASSWORD,csrf='bad'),headers={'Origin':'https://attacker.example'}).status_code,403)
        for _ in range(5):self.assertEqual(self.login('writer','incorrect password').status_code,401)
        self.assertEqual(self.login('writer',PASSWORD).status_code,429)
        self.assertNotIn('writer',self.login('unknown',PASSWORD).get_data(as_text=True))

    def test_expired_and_revoked_keys_rejected(self):
        key=self.store.create_key('reader','expires','read',time.time()+1)
        with patch('froeling_bridge.auth.time.time',return_value=time.time()+2):
            self.assertEqual(self.request('GET','/api/v1/health',key).status_code,401)
        self.store.revoke_key(self.store.authenticate(self.read_key,'key')['id'])
        self.assertEqual(self.request('GET','/api/v1/health',self.read_key).status_code,401)

    def test_login_case_variants_share_the_same_limit(self):
        for name in ['writer','WRITER','Writer','wRiTeR','wRITER']:
            self.assertIsNone(self.store.login(name,'incorrect password','case-test'))
        with self.assertRaises(Throttled):self.store.login('writer',PASSWORD,'case-test')

    def test_storage_contains_hashes_only_and_rate_limits_survive_restart(self):
        self.assertEqual(self.store.path.stat().st_mode & 0o777,0o600)
        with self.store.db() as db:
            password_hash=db.execute('SELECT password_hash FROM users LIMIT 1').fetchone()[0]
            key_hash=db.execute('SELECT hash FROM api_keys LIMIT 1').fetchone()[0]
        self.assertTrue(password_hash.startswith('$argon2id$'))
        self.assertNotIn(PASSWORD,password_hash)
        self.assertNotIn(self.read_key,key_hash)
        self.store.limit('persistent-test',1,900)
        restarted=AuthStore(self.store.path)
        with self.assertRaises(Throttled):restarted.limit('persistent-test',1,900)

    def test_auth_failure_does_not_stop_controller_worker(self):
        with patch.object(self.store,'authenticate',side_effect=AuthUnavailable()):
            self.assertEqual(self.request('GET','/api/v1/health',self.read_key).status_code,503)
        self.assertFalse(self.service.fatal.is_set())
        self.assertTrue(self.service.worker.thread.is_alive())
        service=BridgeService(autostart=False)
        self.addCleanup(service.close)
        closed=create_app(service,authentication=True)
        self.assertEqual(closed.test_client().get('/api/v1/sensors').status_code,503)

    def test_console_commands_create_and_change_user_without_password_arguments(self):
        out=StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(['--state-dir',self.directory.name,'add','console-user','--role','read','--generate-password']),0)
        generated=out.getvalue().strip()
        self.assertGreaterEqual(len(generated),15)
        self.assertIsNotNone(self.store.login('console-user',generated,'console'))
        with patch('froeling_bridge.auth.getpass.getpass',return_value=PASSWORD):
            self.assertEqual(main(['--state-dir',self.directory.name,'password','console-user']),0)
        self.assertIsNotNone(self.store.login('console-user',PASSWORD,'console'))
        with self.assertRaises(ValidationError):self.store.add_user('unsafe name',PASSWORD,'read')
        with self.assertRaises(ValidationError):self.store.add_user('short','short','read')

    def test_spoofed_forwarded_headers_do_not_authorize_http_or_other_host(self):
        response=self.http.get('/api/v1/health',base_url='http://bridge.example.test',headers={
            'X-Forwarded-Proto':'https','Authorization':'Bearer '+self.read_key},environ_overrides={'REMOTE_ADDR':'192.0.2.50'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.http.get('/api/v1/health',base_url='https://attacker.example',headers={'Authorization':'Bearer '+self.read_key}).status_code,400)

    def test_malformed_and_unknown_jobs_never_enter_controller_queue(self):
        before=len(self.service.client.session.transport.requests)
        for operation in ([],{},None,17,'not-an-operation'):
            self.assertEqual(self.request('POST','/api/v1/jobs',self.write_key,json={'operation':operation}).status_code,400)
        self.assertEqual(len(self.service.client.session.transport.requests),before)


if __name__=='__main__':unittest.main()
