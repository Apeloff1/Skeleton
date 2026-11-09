"""Test-only local subprocess driving *real* SQLite inference custody.

This fixture exercises process/SQLite/receipt boundaries; it is not evidence
that an approved GGUF checkpoint has executed or qualified.
"""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.model.isolation import IsolatedGGUFBackend, IsolationFailure
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine import (
    SpineDatabase, ExecutionSpine, Identity, SpineLimits)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Conflict
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.testing.test_ai_isolated_sidecar import FixtureProcess, manifest, MODEL


class IsolatedSpineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'state'
        self.root.mkdir(mode=0o700)
        self.lock=self.root/'locks';self.lock.mkdir(mode=0o700)
        self.db=SpineDatabase(self.root);self.addCleanup(self.db.close)
        self.gate=SessionGate(self.lock);self.addCleanup(self.gate.close)
        self.identity=Identity('tenant','operator',MODEL,MODEL)
        self.limits=SpineLimits(context_tokens=512,max_output_tokens=16,deadline_ms=3000)

    def open(self, mode='normal'):
        p=patch('skeleton.ai.runtime.operational_ai.model.isolation.client.OwnedWorker',
                new=lambda:FixtureProcess(mode))
        p.start();self.addCleanup(p.stop)
        backend=IsolatedGGUFBackend(Path('/tmp/nonexistent-unit-test-model'),manifest(),
                    n_ctx=512, startup_ms=2000, inference_ms=500)
        self.addCleanup(backend.close)
        spine=ExecutionSpine(db=self.db,session_gate=self.gate,backend=backend,
                    identity=self.identity,limits=self.limits)
        return backend,spine

    def count(self,table):
        with self.db.snapshot() as conn:
            return conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]

    def test_roundtrip_commits_atomic_sqlite_event_and_outbox(self):
        backend,spine=self.open()
        spine.create('s1')
        receipt=spine.turn('s1','r1','Hello')
        self.assertEqual(receipt['model_sha256'],MODEL)
        self.assertIn('context_sha256',receipt)
        self.assertEqual(self.count('turns'),1)
        self.assertGreaterEqual(self.count('chain'),2)
        self.assertEqual(self.count('outbox'),1)
        self.assertEqual(backend.health()['requests_completed'],1)

    def test_idempotent_replay_does_not_run_child_twice(self):
        backend,spine=self.open();spine.create('s1')
        a=spine.turn('s1','r1','Hello')
        b=spine.turn('s1','r1','Hello')
        self.assertFalse(a['replayed']);self.assertTrue(b['replayed'])
        self.assertEqual(self.count('turns'),1)
        self.assertEqual(backend.health()['requests_completed'],1)

    def test_restart_replay_from_durable_sqlite_without_new_model(self):
        _,spine=self.open();spine.create('s1')
        committed=spine.turn('s1','r1','Hello')
        # A new service uses the same authoritative DB and can replay without
        # calling its own process. It cannot claim real native-model readiness.
        backend2,spine2=self.open()
        recovered=spine2.turn('s1','r1','Hello')
        self.assertEqual(committed['output_sha256'],recovered['output_sha256'])
        self.assertTrue(recovered['replayed'])
        self.assertEqual(backend2.health()['requests_completed'],0)

    def test_child_exit_leaves_held_pending_request(self):
        _,spine=self.open('exit_after_request');spine.create('s1')
        with self.assertRaises(IsolationFailure):spine.turn('s1','r1','Hello')
        self.assertEqual(self.count('requests'),1)
        self.assertEqual(self.count('turns'),0)
        with self.db.snapshot() as conn:
            self.assertEqual(conn.execute('SELECT state FROM requests').fetchone(),('pending',))
        # The original pending request stays held. The poisoned backend now
        # refuses even admission; it must not issue another native request.
        with self.assertRaises(IsolationFailure):spine.turn('s1','r1','Hello')
        self.assertEqual(self.count('requests'),1)

    def test_child_stall_keeps_uncommitted_custody(self):
        _,spine=self.open('stall');spine.create('s1')
        with self.assertRaises(IsolationFailure):spine.turn('s1','r1','Hello')
        self.assertEqual(self.count('turns'),0)
        self.assertEqual(self.count('requests'),1)

    def test_invalid_native_result_does_not_commit(self):
        _,spine=self.open('bad_hash');spine.create('s1')
        with self.assertRaises(IsolationFailure):spine.turn('s1','r1','Hello')
        self.assertEqual(self.count('turns'),0)
        self.assertEqual(self.count('outbox'),0)

    def test_input_preflight_before_reservation(self):
        backend,spine=self.open();spine.create('s1')
        with self.assertRaises(Exception):spine.turn('s1','r1','x'*100000)
        self.assertEqual(self.count('requests'),0)
        self.assertEqual(backend.health()['requests_completed'],0)

    def test_request_id_mutation_blocked_without_extra_call(self):
        backend,spine=self.open();spine.create('s1')
        spine.turn('s1','r1','Hello')
        with self.assertRaises(Conflict):spine.turn('s1','r1','Different')
        self.assertEqual(backend.health()['requests_completed'],1)


if __name__ == '__main__':unittest.main()
