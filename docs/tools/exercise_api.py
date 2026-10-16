#!/usr/bin/env python3
"""Exercise fictional operations against the local simulator API only."""
import json
import time
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8000/api/v1'


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {} if data is None else {'Content-Type': 'application/json'}
    with urlopen(Request(BASE + path, data=data, headers=headers), timeout=5) as response:
        return json.load(response)


def job(payload):
    identifier = request('/jobs', payload)['id']
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = request('/jobs/' + identifier)
        if result['state'] == 'completed':
            return result['result']
        if result['state'] == 'failed':
            raise RuntimeError(result['error'])
        time.sleep(.05)
    raise RuntimeError('job timed out; do not blindly resubmit a write')


def main():
    health = request('/health')
    if health['mode'] not in ('demo', 'demo-db') or health['hardware_verified']:
        raise RuntimeError('this example requires the fictional simulator')
    menu = request('/menu?parent=10')
    numeric = next(item for item in menu['items'] if item['type'] == 7)
    before = job(dict(operation='read_parameter', menu_id=numeric['id']))
    target = '67.5' if before['value'] != '67.5' else '65.0'
    changed = job(dict(operation='write_parameter', menu_id=numeric['id'], value=target))
    assert changed['status'] == 'confirmed'
    assert job(dict(operation='read_parameter', menu_id=numeric['id']))['value'] == target
    assert job(dict(operation='write_parameter', menu_id=numeric['id'], value=target))['status'] == 'unchanged'
    times = job(dict(operation='write_time_range', address=56, index=1, start='12:00', end='13:00'))
    assert times['status'] in ('confirmed', 'unchanged')
    assert job(dict(operation='measurement', address=43, type='VA'))['value'] == '-1.2'
    print(json.dumps(dict(mode=health['mode'], parameter_write=changed['status'],
                          time_write=times['status'], collector=request('/collector')), indent=2))


if __name__ == '__main__':
    main()
