"""Direct LAN login and fresh-install defaults; only fictional heating data."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from froeling_bridge.api import create_app
from froeling_bridge.auth_web import local_address, validate_auth_config
from froeling_bridge.configure import main as configure, validate_settings
from froeling_bridge.errors import ValidationError
from froeling_bridge.service import BridgeService

ORIGIN = 'http://192.168.178.50:8000'
PASSWORD = 'Fictional LAN installation password 2026!'


class LANAccessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = BridgeService(autostart=False)
        self.addCleanup(self.service.close)
        self.service.auth_state_dir = self.directory.name
        self.service.auth_config = {'mode':'lan'}
        self.app = create_app(self.service, authentication=True)
        self.http = self.app.test_client()
        self.store = self.service.auth_store
        self.store.add_user('reader', PASSWORD, 'read')
        self.store.add_user('writer', PASSWORD, 'write')

    def request(self, method, path, *, origin=ORIGIN, remote='192.168.178.20', **kwargs):
        return self.http.open(path, method=method, base_url=origin,
                              environ_overrides={'REMOTE_ADDR':remote}, **kwargs)

    def login(self, user='reader', origin=ORIGIN):
        page = self.request('GET','/login',origin=origin)
        self.assertEqual(page.status_code,200)
        csrf = re.search(r'name="csrf" value="([^"]+)"',page.get_data(as_text=True))[1]
        return self.request('POST','/api/v1/auth/login',origin=origin,
                            json=dict(username=user,password=PASSWORD,csrf=csrf),headers={'Origin':origin})

    def test_direct_ip_login_both_roles_without_proxy_or_https(self):
        for user in ('reader','writer'):
            self.assertEqual(self.request('GET','/').status_code,303)
            self.assertEqual(self.request('GET','/api/v1/sensors').status_code,401)
            response = self.login(user)
            self.assertEqual(response.status_code,200)
            cookies = response.headers.getlist('Set-Cookie')
            self.assertTrue(any('froeling_lan_session=' in c and 'HttpOnly' in c and 'SameSite=Strict' in c and 'Secure' not in c for c in cookies))
            me=self.request('GET','/api/v1/auth/me').get_json()
            self.assertEqual(me['role'],'read' if user=='reader' else 'write')
            self.assertEqual(self.request('GET','/api/v1/sensors').status_code,200)
            self.assertEqual(self.request('POST','/api/v1/auth/logout',json={}).status_code,403)
            headers={'Origin':ORIGIN,'X-CSRF-Token':me['csrf']}
            self.assertEqual(self.request('POST','/api/v1/auth/logout',json={},headers=headers).status_code,200)
            self.assertEqual(self.request('GET','/api/v1/sensors').status_code,401)

    def test_private_networks_and_local_name_supported(self):
        for origin in ('http://raspberrypi.local:8000','http://raspberrypi:8000','http://10.1.2.3:8000','http://127.0.0.1:8000','http://[fd00::50]:8000'):
            self.assertEqual(self.login(origin=origin).status_code,200,origin)
        for address in ('::1','fd00::20','fe80::20','::ffff:192.168.1.3'):
            self.assertTrue(local_address(address),address)

    def test_public_clients_and_public_hostnames_blocked_even_with_spoofed_headers(self):
        for remote in ('8.8.8.8','2001:4860:4860::8888','0.0.0.0'):
            self.assertEqual(self.request('GET','/login',remote=remote,headers={'X-Forwarded-For':'192.168.178.20','X-Forwarded-Proto':'https'}).status_code,403)
        for origin in ('http://attacker.example:8000','http://8.8.8.8:8000'):
            self.assertEqual(self.request('GET','/login',origin=origin).status_code,403)

    def test_cross_origin_login_and_write_still_denied(self):
        page=self.request('GET','/login')
        csrf=re.search(r'name="csrf" value="([^"]+)"',page.get_data(as_text=True))[1]
        payload=dict(username='writer',password=PASSWORD,csrf=csrf)
        self.assertEqual(self.request('POST','/api/v1/auth/login',json=payload,headers={'Origin':'http://attacker.example'}).status_code,403)
        self.assertEqual(self.login().status_code,200)
        me=self.request('GET','/api/v1/auth/me').get_json()
        self.assertEqual(self.request('PATCH','/api/v1/sensors/VA/43',json={'record':True},headers={'Origin':ORIGIN,'X-CSRF-Token':me['csrf']}).status_code,403)

    def test_lan_login_remains_rate_limited(self):
        with patch('argon2.PasswordHasher.verify',return_value=False):
            for _ in range(5):self.assertEqual(self.login().status_code,401)
            self.assertEqual(self.login().status_code,429)

    def test_native_dialog_uses_lan_without_domain_question(self):
        output=Path(self.directory.name)/'settings.json'
        with patch('froeling_bridge.configure.choose_device',return_value='/dev/ttyUSB0'), patch('builtins.input',side_effect=['n']) as ask, redirect_stdout(StringIO()):
            self.assertEqual(configure(['--output',str(output)]),0)
        self.assertEqual(ask.call_count,1)
        settings=json.loads(output.read_text())
        self.assertEqual(settings['auth'],{'mode':'lan'})
        self.assertEqual(settings['host'],'0.0.0.0')
        self.assertEqual(settings['port'],8000)
        validate_settings(settings)

    def test_existing_https_configuration_is_preserved_without_prompts(self):
        output=Path(self.directory.name)/'existing-settings.json'
        original={'device':'/dev/ttyUSB0','auth':{'public_origin':'https://heizung.example.org','trusted_proxy':'192.168.1.7'}}
        output.write_text(json.dumps(original))
        with patch('builtins.input',side_effect=AssertionError('Existing config must not prompt')), redirect_stdout(StringIO()):
            self.assertEqual(configure(['--output',str(output)]),0)
        self.assertEqual(json.loads(output.read_text()),original)

    def test_auth_configuration_requires_explicit_lan_and_preserves_https_default(self):
        validate_auth_config({'mode':'lan'})
        validate_auth_config({'public_origin':'https://bridge.example'})
        for config in ({}, {'public_origin':'http://192.168.1.5:8000'}, {'mode':'lan','trusted_proxy':'192.168.1.7'}, {'mode':'lan','public_origin':'http://192.168.1.5:8000'}, {'mode':'off'}):
            with self.assertRaises(ValidationError):validate_auth_config(config)


if __name__=='__main__':unittest.main()
