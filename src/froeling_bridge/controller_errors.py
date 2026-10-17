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
    Confirmed timestamps and current-state metadata are refreshed even if the
    stored label already matches, repairing previously incomplete matching rows.
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
        old = rows.get(key)
        row = dict(old or {}, number=event['number'], time1=time_one)
        transition = old is None or (state == 2 and row.get('state') != STATES[2]) or (
            state == 4 and row.get('state') == STATES[1])
        if transition:
            row['state'] = STATES[state]
        # A repeated label can still supply a missing/corrected timestamp.
        # Only the controller supplies these times; never infer them from absence.
        row['time' + str(state)] = when
        if transition or row.get('state') == STATES[state]:
            row.update(info=event['info'], text=event['text'])
        if row != old:
            rows[key] = row
            changed.add(key)
        if state == 2:
            time_one = None
    return rows, {key for key in changed if rows[key] != (existing or {}).get(key)}


def activity(items, controller_items, *, fresh, observed_at):
    """Historical 'gekommen' alone is not proof of a currently active fault.

    Absence from the bounded controller memory is inconclusive, never a synthetic
    departure/acknowledgement. Preserve the stored state and all timestamps.
    """
    def key(row):
        when = row.get('time1')
        if isinstance(when, str):
            try:
                when = datetime.fromisoformat(when)
            except ValueError:
                return None
        if not isinstance(when, datetime) or when.tzinfo is not None:
            return None
        return row.get('number'), when

    def ended(row):
        return row.get('state') in ('gegangen', 'quittiert') or bool(row.get('time4') or row.get('time2'))

    current = {key(row): row for row in controller_items if key(row) is not None}
    result = []
    for original in items:
        row = dict(original)
        match = current.get(key(row))
        checked = None
        if ended(row):
            active, basis = False, 'documented_end'
        elif fresh and match is not None:
            active = False if ended(match) else True if match.get('state') == 'gekommen' else None
            basis, checked = 'controller', observed_at
        else:
            active, basis = None, 'not_in_controller' if fresh else 'controller_unavailable'
        row.update(active=active, activity_basis=basis, activity_checked_at=checked)
        result.append(row)
    return result


def view(snapshot, interval=60):
    from .storage import ZONE
    snapshot = snapshot or {}
    rows, _ = merge_events(snapshot.get('events', []))
    observed = snapshot.get('observed_at')
    age = None if not observed else max(0, (datetime.now(ZONE) - datetime.fromisoformat(observed)).total_seconds())
    stale = age is None or age > max(180, interval * 3)
    items = sorted(rows.values(), key=lambda r:r['time1'], reverse=True)
    items = activity(items, items, fresh=not stale and not snapshot.get('error'), observed_at=observed)
    return dict(available=bool(observed), observed_at=observed, age_seconds=age,
                stale=stale,
                error=snapshot.get('error'), last_attempt=snapshot.get('last_attempt'),
                interval_seconds=interval, source='controller-error-memory',
                items=items)


def check_page(limit, offset):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValidationError('error limit must be 1..1000')
    if type(offset) is not int or not 0 <= offset <= 1000000:
        raise ValidationError('error offset must be 0..1000000')


def page(items, total, limit, offset):
    check_page(limit, offset)
    return dict(items=list(items), total=total, limit=limit, offset=offset,
                has_more=offset + len(items) < total)
