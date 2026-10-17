from copy import deepcopy
from datetime import datetime, timedelta
import unittest
from froeling_bridge.controller_errors import activity, view
from froeling_bridge.storage import ZONE


def occurrence(state='gekommen', **changes):
    return dict(number=7,time1=datetime(2025,1,1),state=state,text='Fictional',**changes)


class ErrorActivityTests(unittest.TestCase):
    def test_old_open_history_absent_from_controller_is_unknown_and_preserved(self):
        rows=[occurrence(id=42,time2=None,time4=None)]
        before=deepcopy(rows)
        result=activity(rows,[],fresh=True,observed_at='2026-10-17T10:00:00+02:00')
        self.assertIsNone(result[0]['active']);self.assertEqual(result[0]['activity_basis'],'not_in_controller')
        self.assertEqual(result[0]['state'],'gekommen');self.assertIsNone(result[0]['time4'])
        self.assertEqual(rows,before)

    def test_only_exact_fresh_occurrence_is_confirmed_active(self):
        row=occurrence()
        result=activity([row],[row],fresh=True,observed_at='now')[0]
        self.assertIs(result['active'],True);self.assertEqual(result['activity_checked_at'],'now')
        other=dict(row,time1=row['time1']+timedelta(seconds=1))
        self.assertIsNone(activity([row],[other],fresh=True,observed_at='now')[0]['active'])
        self.assertIsNone(activity([row],[row],fresh=False,observed_at='old')[0]['active'])

    def test_documented_ended_or_acknowledged_is_not_active_even_without_controller(self):
        for row in [occurrence('gegangen'),occurrence('quittiert'),occurrence(time4=datetime(2025,1,2)),occurrence(time2=datetime(2025,1,2))]:
            with self.subTest(row=row):
                result=activity([row],[],fresh=False,observed_at=None)[0]
                self.assertIs(result['active'],False);self.assertEqual(result['activity_basis'],'documented_end')

    def test_controller_end_during_database_sync_lag_and_no_regression_of_acknowledgement(self):
        row=occurrence()
        self.assertIs(activity([row],[dict(row,state='gegangen')],fresh=True,observed_at='now')[0]['active'],False)
        self.assertIs(activity([dict(row,state='quittiert')],[row],fresh=True,observed_at='now')[0]['active'],False)

    def test_old_snapshot_or_failed_latest_poll_cannot_confirm_current_activity(self):
        event=dict(number=7,state=1,info=0,local_time='2025-01-01T00:00:00',text='Fictional')
        snapshot=dict(events=[event],observed_at=datetime.now(ZONE).isoformat(),error=None)
        self.assertIs(view(snapshot)['items'][0]['active'],True)
        snapshot['error']='last poll failed'
        self.assertIsNone(view(snapshot)['items'][0]['active'])
        snapshot.update(error=None,observed_at=(datetime.now(ZONE)-timedelta(hours=1)).isoformat())
        self.assertIsNone(view(snapshot)['items'][0]['active'])
