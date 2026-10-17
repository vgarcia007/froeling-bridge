from pathlib import Path
import re
import tempfile
import unittest
from froeling_bridge.api import create_app
from froeling_bridge.client import HeatingClient
from froeling_bridge.recording import AUTOMATIC_UD_ADDRESSES
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport
from froeling_bridge.standalone import StandaloneRuntime

ROOT = Path(__file__).resolve().parents[1]


class AutomaticRecordingTests(unittest.TestCase):
    @unittest.skipUnless((ROOT/'reference/linux-p4d/specific.c').is_file(), 'p4d submodule required')
    def test_policy_matches_original_configuration_specials_after_sensor_initialization(self):
        source=(ROOT/'reference/linux-p4d/specific.c').read_text()
        body=source.split('int P4d::applyConfigurationSpecials()',1)[1].split('return done;',1)[0]
        names=re.findall(r'sensors\["UD"\]\[(\w+)\]\.record\s*=\s*true',body)
        self.assertEqual(set(names),{'udState','udMode','udTime'})
        header=(ROOT/'reference/linux-p4d/service.h').read_text()
        block=header.split('enum UserDefined',1)[1].split('};',1)[0]
        members=re.findall(r'\bud\w+',block)
        self.assertRegex(block,r'udState\s*=\s*1')
        addresses={members.index(name)+1 for name in names}
        self.assertEqual(addresses,AUTOMATIC_UD_ADDRESSES)
        daemon=(ROOT/'reference/linux-p4d/daemon.c').read_text()
        self.assertGreater(daemon.index('applyConfigurationSpecials();'),daemon.index('selectActiveValueFacts->freeResult();'))

    def test_internal_ud_recording_ignores_raw_flags_without_changing_them(self):
        with tempfile.TemporaryDirectory() as d:
            transport=MemoryTransport()
            runtime=StandaloneRuntime(d,lambda:(HeatingClient(ProtocolSession(transport)),lambda:None),simulator=True,autostart=False)
            try:
                runtime.discover_once()
                for address in (1,2,3):runtime.repository.patch_sensor('UD',address,dict(active=False,record=False))
                # VA remains a normal optional history sensor.
                runtime.repository.patch_sensor('VA',43,dict(active=True,record=False))
                class History:
                    samples=[]
                    def status(self):return dict(last_success=None)
                    def close(self):pass
                    def enqueue(self,samples,when,stamp):
                        self.samples=list(samples);return len(samples)
                historian=History();runtime.repository.historian=historian
                runtime.service.collect_once()
                self.assertEqual({(s['type'],s['address']) for s in historian.samples},{('UD',1),('UD',2),('UD',3)})
                for s in runtime.repository.sensors():
                    if s['type']=='UD':self.assertEqual((s['state'],s['record']),('D','D'))
                api=create_app(runtime.service).test_client()
                rows=api.get('/api/v1/sensors').get_json()['items']
                for row in rows:
                    if row['type']=='UD':
                        self.assertTrue(row['recording']);self.assertTrue(row['recording_required'])
                        self.assertFalse(row['configured_recording'])
                    else:self.assertFalse(row['recording'])
                runtime.repository.historian=None
            finally:runtime.close()
