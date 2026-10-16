from datetime import datetime, timedelta
from decimal import Decimal
from threading import Event, Thread
from unittest.mock import patch
import time
import unittest

from froeling_bridge.client import HeatingClient
from froeling_bridge.errors import ValidationError
from froeling_bridge.messages import Command
from froeling_bridge.service import BridgeService, HeatingWorker, QueueBusy, public
from froeling_bridge.session import ProtocolSession
from froeling_bridge.simulator import MemoryTransport
from froeling_bridge.storage import MemoryRepository, DatabaseUnavailable, demo_sensors


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.transport = MemoryTransport()
        self.repo = MemoryRepository()
        self.service = BridgeService(self.repo, client=HeatingClient(ProtocolSession(self.transport)), autostart=False)
        self.addCleanup(self.service.close)

    def test_continuous_fresh_unchanged_values_and_scaling(self):
        for stamp in (1700000000, 1700000060):
            with patch('froeling_bridge.service.time.time', return_value=stamp):
                self.service.collect_once()
        rows = list(self.repo.rows.values())
        self.assertEqual(len(rows), 10)
        self.assertEqual({r['value'] for r in rows if r['address'] == 43}, {Decimal('-1.2')})
        self.assertTrue(all(r['aggregate'] == 'S' and r['samples'] == 1 for r in rows))
        self.assertTrue(all(r['time'].tzinfo is None and r['time'].microsecond == 0 for r in rows))
        self.assertEqual(self.service.collector_status()['stored'], 5)

    def test_partial_failure_does_not_store_stale_cache(self):
        self.service.collect_once()
        original = self.service.read_sensor
        def failing(sensor):
            if sensor['address'] == 43:
                raise ValidationError('bad metadata')
            return original(sensor)
        self.service.read_sensor = failing
        with patch('froeling_bridge.service.time.time', return_value=1700000000):
            self.service.collect_once()
        state = self.service.collector_status()
        self.assertEqual(state['stored'], 4)
        self.assertEqual(state['errors'][0]['address'], 43)
        self.assertNotIn((43, 'VA', 'S', datetime(2023, 11, 14, 23, 13, 20)), self.repo.rows)
        self.assertEqual(next(r for r in self.service.cached_values() if r['address'] == 43)['value'], '-1.2')

    def test_selection_and_unsupported_types(self):
        sensors = demo_sensors()
        sensors[0].update(state='D', record='D')
        sensors[1].update(record='D')
        sensors.append(dict(sensors[0], address=50, type='SD', state='A', record='A'))
        self.repo.sensors = lambda: sensors
        self.service.collect_once()
        self.assertEqual(self.service.collector_status()['stored'], 3)
        self.assertEqual(self.service.collector_status()['skipped'][0]['reason'], 'unsupported')
        self.assertEqual(len(self.service.cached_values()), 4)

    def test_io_and_ud_identity(self):
        for kind, command, raw, expected in [('DO', Command.DIGITAL_OUT, 5, 1), ('DI', Command.DIGITAL_IN, 0, 0), ('AO', Command.ANALOG_OUT, 75, 75)]:
            self.transport.heater.io_states[(command, 43)] = (255, raw)
            result = self.service.read_sensor(dict(address=43, type=kind))
            self.assertEqual(result['value'], expected)
            self.assertEqual(result['type'], kind)
        ud = self.service.read_sensor(dict(address=3, type='UD'))
        self.assertEqual(ud['value'], 1705316400)

    def test_database_failure_does_not_claim_store_success(self):
        self.repo.store_cycle = lambda *args: (_ for _ in ()).throw(DatabaseUnavailable())
        self.service.collect_once()
        state = self.service.collector_status()
        self.assertEqual(state['stored'], 0)
        self.assertIsNone(state['last_successful_store'])
        self.assertEqual(state['errors'][0]['error']['code'], 'database_unavailable')
        self.assertEqual(len(self.service.cached_values()), 5)

    def test_user_job_runs_between_collector_reads(self):
        entered, release = Event(), Event()
        original = self.service.read_sensor
        first = True
        order = []
        def read(sensor):
            nonlocal first
            if first:
                first = False
                entered.set()
                release.wait(2)
            order.append('sensor')
            return original(sensor)
        self.service.read_sensor = read
        collector = Thread(target=self.service.collect_once)
        collector.start()
        self.assertTrue(entered.wait(1))
        future = self.service.worker.submit(lambda: order.append('user'))
        release.set()
        collector.join(2)
        self.assertFalse(collector.is_alive())
        future.result(1)
        self.assertEqual(order[:3], ['sensor', 'user', 'sensor'])

    def test_no_parallel_cycles(self):
        self.service.cycle_lock.acquire()
        try:
            with self.assertRaises(QueueBusy):
                self.service.collect_once()
        finally:
            self.service.cycle_lock.release()

    def test_periodic_loop_does_not_catch_up_after_slow_cycle(self):
        service = BridgeService(interval=10, autostart=False)
        self.addCleanup(service.close)
        starts, waits = [], []
        class FakeStop:
            stopped = False
            def is_set(self): return self.stopped
            def wait(self, delay): waits.append(delay); self.stopped = True
            def set(self): self.stopped = True
        service.stop = FakeStop()
        service.collect_once = lambda: starts.append(1)
        with patch('froeling_bridge.service.time.monotonic', side_effect=[100, 125, 125]):
            service._collect_loop()
        self.assertEqual(starts, [1])
        self.assertEqual(waits, [5])

    def test_worker_timeout_exception_is_not_mistaken_for_pending_future(self):
        from concurrent.futures import Future, TimeoutError
        future = Future()
        future.set_exception(TimeoutError("operation timeout"))
        with self.assertRaises(TimeoutError):
            self.service._wait(future)

    def test_invalid_intervals(self):
        for interval in (0, -1, True, float('inf'), float('nan')):
            with self.assertRaises(ValidationError):
                BridgeService(interval=interval)

    def test_bounded_fifo_and_shutdown(self):
        worker = HeatingWorker(1)
        self.addCleanup(worker.close)
        entered, release = Event(), Event()
        active = worker.submit(lambda: (entered.set(), release.wait(2)))
        self.assertTrue(entered.wait(1))
        pending = worker.submit(lambda: None)
        with self.assertRaises(QueueBusy):
            worker.submit(lambda: None)
        release.set()
        active.result(1)
        pending.result(1)

    def test_nested_parameter_write_serialization_contains_values(self):
        result = self.service.client.set_parameter(0x1234, '67.5')
        self.assertEqual(public(result)['current']['value'], '67.5')
