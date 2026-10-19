"""Exercise actual HTTPS/cookies and both roles against fictional equipment only."""
import argparse
import base64
from pathlib import Path
import subprocess
import tempfile
from threading import Thread

from werkzeug.serving import make_server
from verify_menu_browser import Browser
from preview_plant import fictional_runtime
from froeling_bridge.api import create_app
from froeling_bridge.menu import demo_time_program_catalog


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate-only',action='store_true',required=True)
    parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1',
            '-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],check=True,capture_output=True)
        runtime,transport=fictional_runtime(directory)
        service=runtime.service
        runtime.repository.time_programs=demo_time_program_catalog
        service.allowed_write_operations={'write_parameter'}
        server=make_server('127.0.0.1',0,lambda e,s:[],threaded=True,
                          ssl_context=(str(root/'cert.pem'),str(root/'key.pem')))
        origin='https://127.0.0.1:'+str(server.server_port)
        service.auth_config=dict(public_origin=origin)
        service.auth_state_dir=directory
        server.app=create_app(service,authentication=True)
        for role in ['read','write']:service.auth_store.add_user(role,'Fictional browser test password! 19',role)
        Thread(target=server.serve_forever,daemon=True).start()
        browser=Browser()
        try:
            browser.call('Page.enable');browser.call('Runtime.enable')
            browser.call('Security.setIgnoreCertificateErrors',dict(ignore=True))
            for role in ['read','write']:
                browser.call('Page.navigate',dict(url=origin+'/anlage'))
                browser.wait("location.pathname==='/login' && !!document.querySelector('#username')")
                browser.js("document.querySelector('#username').value="+repr(role)+";document.querySelector('#password').value='Fictional browser test password! 19';document.querySelector('form').requestSubmit()")
                browser.wait("location.pathname==='/anlage' && document.querySelectorAll('.plant-card').length===6")
                browser.wait("document.querySelector('#account-role').textContent==="+repr('Nur Lesen' if role=='read' else 'Lesen + Schreiben'))
                for width in [390,1440]:
                    browser.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=1000,deviceScaleFactor=1,mobile=width<650))
                    assert browser.js('document.documentElement.scrollWidth<=window.innerWidth'),(role,width)
                    browser.js("document.querySelector('#nav-times').click()")
                    browser.wait("document.querySelectorAll('.interval-row').length>0")
                    assert browser.js("[...document.querySelectorAll('.interval-row input,.interval-row button')].every(x=>x.disabled)")
                    assert browser.js("document.querySelector('#time-programs').textContent.includes('können nicht geändert') || document.querySelector('#time-programs').textContent.includes('noch nicht freigegeben')")
                    browser.js("document.querySelector('#nav-values').click()")
                    browser.wait("!document.querySelector('#values-view').hidden && !!document.querySelector('#values-grid input[type=checkbox]')")
                    if role=='read':assert browser.js("[...document.querySelectorAll('#values-grid input[type=checkbox]')].every(x=>x.disabled)")
                    else:assert browser.js("[...document.querySelectorAll('#values-grid input[type=checkbox]')].some(x=>!x.disabled)")
                    browser.js("document.querySelector('#nav-plant').click()")
                    browser.wait("!document.querySelector('#plant-view').hidden")
                browser.js("document.querySelector('#logout').click()")
                browser.wait("location.pathname==='/login' && !!document.querySelector('#username')")
                assert browser.js('document.documentElement.scrollWidth<=window.innerWidth')
            # Console password changes invalidate a real browser cookie on next request.
            browser.js("document.querySelector('#username').value='read';document.querySelector('#password').value='Fictional browser test password! 19';document.querySelector('form').requestSubmit()")
            browser.wait("location.pathname==='/anlage' && document.querySelectorAll('.plant-card').length===6")
            service.auth_store.change_user('read',password='Replacement fictional browser password 20!')
            browser.js("api('/health').catch(()=>{})")
            browser.wait("location.pathname==='/login'")
            assert transport.heater.parameter_write_count==0
            assert transport.heater.time_write_count==0
            assert not browser.errors,browser.errors
            print('Auth browser: real HTTPS, both roles, mobile/desktop, disabled time fields, logout and session revocation; no heater writes.')
        finally:
            browser.close();server.shutdown();server.server_close();runtime.close()


if __name__=='__main__':main()
