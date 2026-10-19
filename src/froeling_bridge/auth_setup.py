"""Root console provisioning; credentials go only to protected local files."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys

from .host_test import atomic_json
from .errors import ValidationError


def main():
    if os.geteuid() != 0:
        raise ValidationError('native authentication provisioning requires root')
    state = Path('/var/lib/froeling-bridge')
    owner = pwd.getpwuid(state.stat().st_uid).pw_name
    if owner != 'froeling-bridge':
        raise ValidationError('native state must belong to froeling-bridge')
    keyfile = Path('/etc/froeling-bridge/monitor-api-key')
    current = keyfile.read_text().strip() if keyfile.is_file() else None
    child = r'''
import json,secrets,sys
from froeling_bridge.auth import AuthStore
store=AuthStore('/var/lib/froeling-bridge/auth.sqlite3')
initial=None
if not store.users():
 password=secrets.token_urlsafe(24)
 store.add_user('operator',password,'write')
 initial=dict(username='operator',password=password)
if not any(u['username']=='bridge-monitor' for u in store.users()):
 store.add_user('bridge-monitor',secrets.token_urlsafe(32),'read')
current=json.load(sys.stdin)
actor=store.authenticate(current,'key')
if not actor or actor['username']!='bridge-monitor' or actor['role']!='read':
 current=store.create_key('bridge-monitor','native-health','read')
print(json.dumps(dict(initial=initial,monitor_key=current)))
'''
    result = subprocess.run(['runuser', '-u', owner, '--', sys.executable, '-I', '-c', child],
                            input=json.dumps(current), capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    temporary = keyfile.with_suffix('.new')
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(data['monitor_key']+'\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, keyfile)
    if data['initial']:
        target = Path('/var/lib/froeling-bridge-installer/initial-login.json')
        atomic_json(target, data['initial'])
    print('Authentication provisioned. Initial credentials, if created, are in the root-only initial-login.json.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
