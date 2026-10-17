"""Independent cached-HTTP health guard; never opens the heater or database."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import build_opener, ProxyHandler

STATE = Path('/var/lib/froeling-bridge-installer')
HELPER = '/usr/local/sbin/froeling-bridge-control'


def active(unit):
    return subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', unit],
                          capture_output=True, timeout=10).returncode == 0


def fresh(stamp, now, maximum):
    try:
        observed = datetime.fromisoformat(stamp)
        if observed.tzinfo is None:
            return False
        return -5 <= (now - observed).total_seconds() <= maximum
    except (TypeError, ValueError):
        return False


def healthy(runtime, sensors, now, maximum):
    connection = runtime.get('connection', {})
    if (runtime.get('phase') != 'ready' or not connection.get('connected')
            or not fresh(connection.get('last_success'), now, maximum)):
        return False
    selected = [s for s in sensors if s.get('supported')
                and (s.get('active') or s.get('recording')) and s['type'] != 'UD']
    # With no measurements selected, fresh controller status is sufficient.
    if not selected:
        return True
    return any(s.get('latest') and s['latest'].get('origin') == 'controller'
               and fresh(s['latest'].get('observed_at'), now, maximum)
               for s in selected)


def decide(previous_failure, now, ok, grace=60):
    if ok:
        return None, False
    # Ignore wall-clock adjustment by treating negative elapsed time as a new incident.
    since = previous_failure if previous_failure is not None and previous_failure <= now else now
    return since, now - since >= grace


def main():
    incident = STATE / 'health-failure.json'
    if not active('froeling-bridge.service') or active('froeling-bridge-startup.timer'):
        incident.unlink(missing_ok=True)
        return 0
    config = json.loads(Path('/etc/froeling-bridge/settings.json').read_text())
    state = json.loads((STATE / 'installation.json').read_text())
    maximum = max(180, 3 * float(config.get('interval', 60)))
    opener = build_opener(ProxyHandler({}))
    def get(path):
        with opener.open('http://127.0.0.1:' + str(config.get('port', 8000))
                         + '/api/v1/' + path, timeout=3) as response:
            return json.load(response)
    runtime = None
    try:
        runtime = get('runtime')
        ok = healthy(runtime, get('sensors')['items'], datetime.now(timezone.utc), maximum)
    except Exception:
        ok = False  # No exception details: connection settings and operating values stay private.
    previous = None
    if incident.exists():
        try:
            previous = float(json.loads(incident.read_text())['since'])
        except (ValueError, KeyError, TypeError):
            pass
    # A new host has no p4d fallback; a complete catalogue rebuild may take
    # several minutes. Do not repeatedly kill healthy discovery before it ends.
    rebuilding = (not state['p4d_fallback'] and runtime is not None
                  and not runtime.get('catalogue_ready') and not runtime.get('last_failure')
                  and (runtime.get('phase') == 'starting'
                       or runtime.get('phase', '').startswith('discovery:')))
    since, recover = decide(previous, time.time(), ok, grace=700 if rebuilding else 60)
    if since is None:
        incident.unlink(missing_ok=True)
        return 0
    temporary = incident.with_suffix('.new')
    temporary.unlink(missing_ok=True)
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as stream:
        json.dump(dict(since=since), stream)
    os.replace(temporary, incident)
    if recover:
        print('No current heating readings: restoring p4d.' if state['p4d_fallback']
              else 'No current heating readings: restarting Bridge.', flush=True)
        command = [HELPER, 'rollback'] if state['p4d_fallback'] else [
            '/usr/bin/systemctl', 'restart', 'froeling-bridge.service']
        subprocess.run(command, check=True, timeout=80)
        incident.unlink(missing_ok=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
