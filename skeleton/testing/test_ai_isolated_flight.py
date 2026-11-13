"""Durable queue -> isolated local subprocess -> atomic SQLite inference.

All model outputs are deterministic fixture outputs. This suite proves
coordination and failure custody, *not* native GGUF or consumer readiness.
"""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.orchestration.flight_control.production import activate_flight
from skeleton.ai.runtime.operational_ai.orchestration.flight_control import FlightSpec
from skeleton.testing.test_ai_isolated_sidecar import FixtureProcess,manifest,MODEL


class IsolatedQueueTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='isolated-flight-fixture-',dir=Path.home())
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'private';self.root.mkdir(mode=0o700)
        self.model=Path(temp.name)/'operator-model';self.model.mkdir(mode=0o700)

    def activate(self,mode='normal'):
        p1=patch('skeleton.ai.runtime.operational_ai.deployment.production.startup.load_approved_manifest',return_value=manifest())
        p2=patch('skeleton.ai.runtime.operational_ai.model.isolation.client.OwnedWorker',new=lambda:FixtureProcess(mode))
        p1.start();p2.start();self.addCleanup(p1.stop);self.addCleanup(p2.stop)
        return activate_flight(model_root=self.model,state_dir=self.root,
               tenant='tenant',subject='operator',worker_id='worker1',
               n_ctx=512,max_new_tokens=32,n_threads=2,isolate_native=True)

    def spec(self,app,num=1):
        return FlightSpec(app.spine.identity,'job'+str(num),'s1','req'+str(num),
                          'Explain the native worker path '+str(num))

    def test_isolated_real_flight_sqlite_queue_to_commit(self):
        with self.activate() as app:
            self.assertEqual(app.spine.identity.model_sha256,MODEL)
            app.spine.create('s1')
            app.ledger.submit(self.spec(app))
            result=app.worker.run_one()
            self.assertEqual(result.state,'completed')
            self.assertEqual(app.ledger.inspect('job1')['state'],'completed')
            self.assertEqual(app.spine.backend.health()['requests_completed'],1)
            self.assertEqual(app.ledger.state_count()['queued'],0)

    def test_isolated_multiple_jobs_no_unqualified_parallel_calls(self):
        with self.activate() as app:
            app.spine.create('s1')
            for n in range(1,6):app.ledger.submit(self.spec(app,n))
            records=app.worker.drain(maximum=5)
            self.assertEqual(len(records),5)
            self.assertEqual([r.revision for r in records],list(range(1,6)))
            self.assertEqual(app.spine.backend.health()['requests_completed'],5)

    def test_no_queued_job_no_native_generation(self):
        with self.activate() as app:
            app.spine.create('s1')
            self.assertIsNone(app.worker.run_one())
            self.assertEqual(app.spine.backend.health()['requests_completed'],0)

    def test_restart_completed_job_does_not_regenerate(self):
        with self.activate() as app:
            app.spine.create('s1');app.ledger.submit(self.spec(app))
            app.worker.run_one()
            self.assertEqual(app.spine.backend.health()['requests_completed'],1)
        with self.activate() as app2:
            self.assertIsNone(app2.worker.run_one())
            self.assertEqual(app2.spine.backend.health()['requests_completed'],0)
            self.assertEqual(app2.ledger.inspect('job1')['state'],'completed')

    def test_worker_crash_holds_job_without_replay(self):
        with self.activate('exit_after_request') as app:
            app.spine.create('s1');app.ledger.submit(self.spec(app))
            with self.assertRaises(Exception):app.worker.run_one()
            self.assertEqual(app.ledger.inspect('job1')['state'],'held')
            self.assertEqual(app.ledger.state_count()['held'],1)
            self.assertIsNone(app.worker.run_one())
            with app.spine.db.snapshot() as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM turns').fetchone()[0],0)

    def test_native_bad_hash_never_completed(self):
        with self.activate('bad_hash') as app:
            app.spine.create('s1');app.ledger.submit(self.spec(app))
            with self.assertRaises(Exception):app.worker.run_one()
            self.assertEqual(app.ledger.inspect('job1')['state'],'held')
            self.assertEqual(app.spine.backend.health()['requests_failed'],1)

    def test_identity_rebinding_refused_after_job(self):
        with self.activate() as app:
            app.spine.create('s1')
            app.ledger.submit(self.spec(app))
        p1=patch('skeleton.ai.runtime.operational_ai.deployment.production.startup.load_approved_manifest',return_value=manifest())
        p2=patch('skeleton.ai.runtime.operational_ai.model.isolation.client.OwnedWorker',new=lambda:FixtureProcess('normal'))
        with p1,p2:
            with self.assertRaises(Exception):
                with activate_flight(model_root=self.model,state_dir=self.root,
                   tenant='other',subject='operator',worker_id='worker1',
                   n_ctx=512,max_new_tokens=32,isolate_native=True):
                    pass


if __name__ == '__main__':unittest.main()
