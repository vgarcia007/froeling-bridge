"""Heating error occurrences, following P4d::updateErrors (not service failures)."""
from datetime import datetime
from .errors import ValidationError

STATES = {1: 'gekommen', 2: 'quittiert', 4: 'gegangen'}


def events(entries):
    return [dict(number=e.number, info=e.info, state=e.state,
                 local_time=e.local_time.isoformat(), text=e.description) for e in entries]


def merge_events(entries, existing=None):
    """Keep p4d ordering, occurrence key and its guarded state transitions.

    Orphan transitions before the first arrival are skipped, as in p4d.
    Existing acknowledged occurrences and mail counters must not regress.
    """
    rows = {k: dict(v) for k, v in (existing or {}).items()}
    changed = set()
    time_one = None
    for event in entries:
        state = event['state']
        if state not in STATES:
            raise ValidationError('unsupported heating error state; previous list preserved')
        when = datetime.fromisoformat(event['local_time'])
        if when.tzinfo is not None:
            raise ValidationError('heating error times must be controller-local')
        if state == 1:
            time_one = when
        if time_one is None:
            continue
        key = (event['number'], time_one)
        row = rows.get(key)
        if row is None or (state == 2 and row['state'] != STATES[2]) or (
                state == 4 and row['state'] == STATES[1]):
            row = dict(row or {}, number=event['number'], time1=time_one,
                       state=STATES[state], info=event['info'], text=event['text'])
            row['time' + str(state)] = when
            rows[key] = row
            changed.add(key)
        if state == 2:
            time_one = None
    return rows, changed


def view(snapshot, interval=60):
    from .storage import ZONE
    snapshot = snapshot or {}
    rows, _ = merge_events(snapshot.get('events', []))
    observed = snapshot.get('observed_at')
    age = None if not observed else max(0, (datetime.now(ZONE) - datetime.fromisoformat(observed)).total_seconds())
    return dict(available=bool(observed), observed_at=observed, age_seconds=age,
                stale=age is None or age > max(180, interval * 3),
                error=snapshot.get('error'), last_attempt=snapshot.get('last_attempt'),
                interval_seconds=interval, source='controller-error-memory',
                items=sorted(rows.values(), key=lambda r:r['time1'], reverse=True))


def check_page(limit, offset):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValidationError('error limit must be 1..1000')
    if type(offset) is not int or not 0 <= offset <= 1000000:
        raise ValidationError('error offset must be 0..1000000')


def page(items, total, limit, offset):
    check_page(limit, offset)
    return dict(items=list(items), total=total, limit=limit, offset=offset,
                has_more=offset + len(items) < total)
