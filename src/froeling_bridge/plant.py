"""Functional plant view inferred from reachable menu instances, never pipework."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
import hashlib
import re
import time
from threading import RLock, Thread
import uuid

from .errors import ReadOnlyViolation, ValidationError
from .local_store import supported
from .menu import menu_paths, visible_menu
from .messages import ParameterType
from .storage import ZONE


COMPONENT = re.compile(r"^(Kessel|Puffer|Boiler|Heizkreis)(?:\s*\d+)?$", re.I)
SETTINGS = re.compile(r"temperatur|temp\.|nachlad|differenz|schwell|heizgrenz|drehzahl|pumpe|mischer|freig[ae]b|einschalt|ausschalt|hysterese", re.I)


def role(title):
    title = title.casefold()
    if 'außen' in title:
        return 'ambient'
    if 'pumpe' in title:
        return 'pump'
    if 'mischer' in title:
        return 'mixer'
    if 'temperatur' in title or 'temp.' in title:
        return 'temperature'
    if 'ladezustand' in title:
        return 'charge'
    return 'state'


def catalogue(repository):
    """Use navigation edges, including instance-specific children supplied by p4d."""
    rows = visible_menu(repository.menu_catalog())
    paths = menu_paths(rows)
    children = defaultdict(list)
    for row in rows:
        children[row['parent']].append(row)
    roots = []
    for row in rows:
        match = COMPONENT.fullmatch(row['title'])
        # p4d's main groups (0x01) and equipment instances (0x21). Display-rights
        # submenus also say "Kessel", but are not additional boilers.
        if row['type'] in (1, 33) and row['child'] and row['parent'] in paths and match:
            # A generic Puffer container is not a second physical component.
            if any(COMPONENT.fullmatch(c['title']) for c in children[row['child']]):
                continue
            roots.append((row, match[1].casefold()))
    result = []
    for root, kind in roots:
        pending, seen, leaves = [root['child']], set(), {}
        while pending:
            parent = pending.pop()
            if parent in seen:
                continue
            seen.add(parent)
            for row in children[parent]:
                if row['child']:
                    if not COMPONENT.fullmatch(row['title']):
                        pending.append(row['child'])
                else:
                    leaves[row['id']] = row
        result.append(dict(id=f"{kind}-{root['child']}", kind=kind, title=root['title'],
                           parent=root['child'], path=[c['title'] for c in paths[root['parent']]] + [root['title']],
                           leaves=list(leaves.values())))
    order = {'kessel': 0, 'puffer': 1, 'boiler': 2, 'heizkreis': 3}
    return sorted(result, key=lambda c: (order[c['kind']], c['parent']))


class PlantOverview:
    def __init__(self, service):
        self.service = service
        self.lock = RLock()
        self.running = {}
        self.threads = set()
        self.cache = self._meta('plant_parameters', {})

    def _meta(self, key, default):
        repo = self.service.repository
        return repo.get_meta(key, default) if hasattr(repo, 'get_meta') else default

    @staticmethod
    def _key(component, item):
        identity = [component['id'], item['id'], item['type'], item['address'], item['title']]
        return hashlib.sha256(repr(identity).encode()).hexdigest()

    def snapshot(self, sensors):
        service = self.service
        repo = service.repository
        components = catalogue(repo)
        by_key = {(s['type'], s['address']): s for s in sensors}
        claims = defaultdict(set)
        used = set()
        for component in components:
            component['metrics'], component['settings'] = [], []
            for item in component.pop('leaves'):
                sensor_type = {3: 'VA', 70: 'VA', 54: 'VA', 17: 'DO', 18: 'AO', 19: 'DI'}.get(item['type'])
                sensor = by_key.get((sensor_type, item['address']))
                if sensor is not None:
                    metric = dict(menu_id=item['id'], title=item['title'], role=role(item['title']),
                                  sensor=deepcopy(sensor), association='menu', ambiguous=False)
                    component['metrics'].append(metric)
                    claims[(sensor_type, item['address'])].add(component['id'])
                    used.add((sensor_type, item['address']))
                elif item['type'] in set(ParameterType) and SETTINGS.search(item['title']):
                    with self.lock:
                        cached = deepcopy(self.cache.get(self._key(component, item), {}))
                    stamp = cached.get('observed_at')
                    age = max(0, (datetime.now(ZONE) - datetime.fromisoformat(stamp)).total_seconds()) if stamp else None
                    component['settings'].append(dict(menu_id=item['id'], title=item['title'],
                        value=cached.get('value'), unit=cached.get('unit', ''), observed_at=stamp,
                        age_seconds=age, stale=age is None or age > 600 or bool(cached.get('error')),
                        error=cached.get('error')))
            if component['kind'] == 'kessel' and sum(c['kind'] == 'kessel' for c in components) == 1:
                for address in (1, 2):
                    sensor = by_key.get(('UD', address))
                    if sensor:
                        component['metrics'].insert(0, dict(menu_id=None, title=sensor['title'],
                            role='state', sensor=deepcopy(sensor), association='controller-status', ambiguous=False))
            with self.lock:
                component['refresh_job_id'] = self.running.get(component['id'])
            priority = {'temperature': 1, 'pump': 2, 'mixer': 2, 'charge': 3, 'ambient': 4, 'state': 5}
            component['metrics'].sort(key=lambda m: 0 if m['association'] == 'controller-status' else priority[m['role']])
            component['presence'] = 'menu-catalogue'
        required = set()
        for component in components:
            for metric in component['metrics']:
                sensor = metric['sensor']
                identity = (sensor['type'], sensor['address'])
                if len(claims[identity]) > 1 and metric['role'] != 'ambient':
                    metric['ambiguous'] = True
                    metric['association'] = 'ambiguous-menu'
                if not metric['ambiguous'] and supported(sensor):
                    required.add(identity)
        pending = [dict(type=t, address=a) for t, a in sorted(required)
                   if not by_key[t, a]['active'] and not by_key[t, a]['recording']]
        unassigned = [deepcopy(s) for s in sensors if (s['type'], s['address']) not in used
                      and role(s['title']) in ('pump', 'mixer')]
        return dict(source=repo.source, components=components, unassigned=unassigned,
                    enabled=self._meta('plant_enabled', False), activation_available=getattr(repo, 'configurable', False),
                    additional_sensors=pending, parameter_max_age_seconds=600,
                    topology='functional-menu-groups', cached=True)

    def activate(self, sensors):
        repo = self.service.repository
        if not getattr(repo, 'configurable', False):
            raise ReadOnlyViolation('plant activation requires a configurable local catalogue')
        view = self.snapshot(sensors)
        if not view['components']:
            raise ValidationError('component discovery is not complete')
        changed = []
        for sensor in view['additional_sensors']:
            repo.patch_sensor(sensor['type'], sensor['address'], {'active': True})
            changed.append(sensor)
        repo.set_meta('plant_enabled', True)
        return dict(enabled=True, activated=changed, history_selection_changed=False)

    def remember_parameter(self, menu_id, parameter):
        """A menu read/verified write also updates the corresponding overview cache."""
        from .service import public
        from .storage import DatabaseUnavailable
        target = self.service.repository.menu_item(menu_id)
        if not target or target['address'] != parameter.address:
            return
        for component in catalogue(self.service.repository):
            for item in component['leaves']:
                if item['address'] != parameter.address or item['type'] not in set(ParameterType) or not SETTINGS.search(item['title']):
                    continue
                with self.lock:
                    self.cache[self._key(component, item)] = public(dict(value=parameter.value,
                        unit=parameter.unit, observed_at=datetime.now(ZONE).isoformat(), error=None))
                    if hasattr(self.service.repository, 'set_meta'):
                        try:
                            self.service.repository.set_meta('plant_parameters', self.cache)
                        except DatabaseUnavailable:
                            # An auxiliary cache failure must not turn a confirmed write into a failure.
                            import logging
                            logging.getLogger(__name__).warning('Plant parameter cache could not be persisted')

    def submit(self, data):
        from .service import QueueBusy, ServiceStopped
        if set(data) != {'operation', 'component_id'} or not isinstance(data['component_id'], str):
            raise ValidationError('refresh_component requires a component_id from /plant')
        if not self.service.worker or self.service.stop.is_set():
            raise ServiceStopped()
        component = next((c for c in catalogue(self.service.repository) if c['id'] == data['component_id']), None)
        if component is None:
            raise ValidationError('unknown component')
        items = [i for i in component['leaves'] if i['type'] in set(ParameterType) and SETTINGS.search(i['title'])]
        with self.lock:
            if component['id'] in self.running:
                return self.running[component['id']]
            if len(self.running) >= 4:
                raise QueueBusy()
            identifier = uuid.uuid4().hex
            with self.service.lock:
                if len(self.service.jobs) >= self.service.job_limit:
                    old = next((k for k, v in self.service.jobs.items() if v['state'] in ('completed', 'failed')), None)
                    if old is None:
                        raise QueueBusy()
                    del self.service.jobs[old]
                self.service.jobs[identifier] = dict(id=identifier, state='queued', operation='refresh_component',
                    source=self.service.source, created_at=datetime.now(ZONE).isoformat())
            self.running[component['id']] = identifier
            thread = Thread(target=self._refresh, args=(component, items, identifier), name='plant-parameters', daemon=True)
            self.threads.add(thread)
            thread.start()
            return identifier

    def _refresh(self, component, items, identifier):
        from .service import failure, public, ServiceStopped, QueueBusy
        from .errors import ProtocolError
        from threading import current_thread
        with self.service.lock:
            self.service.jobs[identifier]['state'] = 'running'
        errors, read = [], 0
        deadline = time.monotonic() + 90
        try:
            for item in items:
                if self.service.stop.is_set():
                    raise ServiceStopped()
                if time.monotonic() >= deadline:
                    errors.append(dict(menu_id=item['id'], error=dict(code='refresh_deadline', message='component refresh deadline exceeded')))
                    break
                key = self._key(component, item)
                try:
                    current = self.service.repository.menu_item(item['id'])
                    if not current or any(current[k] != item[k] for k in ('type', 'address', 'title')):
                        raise ValidationError('menu catalogue changed; reload the plant view')
                    action = self.service._job_action(dict(operation='read_parameter', menu_id=item['id']))
                    parameter = self.service._wait(self.service.worker.submit(action))
                    value = public(dict(value=parameter.value, unit=parameter.unit,
                                        observed_at=datetime.now(ZONE).isoformat(), error=None))
                    read += 1
                except Exception as exc:
                    with self.lock:
                        value = dict(self.cache.get(key, {}), error=failure(exc))
                    errors.append(dict(menu_id=item['id'], error=failure(exc)))
                    if isinstance(exc, ProtocolError) and self.service.mode in ('hardware-read', 'hardware-live'):
                        self.service.abort(type(exc).__name__)
                    if isinstance(exc, (ProtocolError, ServiceStopped, QueueBusy)):
                        with self.lock:
                            self.cache[key] = value
                        break
                with self.lock:
                    self.cache[key] = value
            if hasattr(self.service.repository, 'set_meta'):
                with self.lock:
                    self.service.repository.set_meta('plant_parameters', self.cache)
            update = dict(state='completed', result=dict(component_id=component['id'], read=read, errors=errors))
        except Exception as exc:
            update = dict(state='failed', error=failure(exc))
        finally:
            with self.lock:
                with self.service.lock:
                    self.service.jobs[identifier].update(update, finished_at=datetime.now(ZONE).isoformat())
                self.running.pop(component['id'], None)
                self.threads.discard(current_thread())

    def close(self):
        with self.lock:
            threads = tuple(self.threads)
        for thread in threads:
            thread.join(timeout=2)
