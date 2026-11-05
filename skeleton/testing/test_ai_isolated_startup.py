"""Integration: real principal/SQLite startup with TEST-ONLY IPC model stub.

The production startup remains responsible for owner binding and knowledge
custody. This test does not substitute a fake model into a real CLI/release.
"""
from __future__ import annotations
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.deployment.production.startup import activate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import SpineError
from skeleton.testing.test_ai_isolated_sidecar import FixtureProcess, manifest, MODEL


class IsolatedStartupTests(unittest.TestCase):
    def setUp(self):
        # The production custody code forbids group/world-writable ancestors,
        # so /tmp and the shared artifact directory are intentionally invalid.
        temp=tempfile.TemporaryDirectory(prefix='isolated-startup-fixture-',
                                         dir=Path.home())
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'private'
        self.root.mkdir(mode=0o700)
        self.model=Path(temp.name)/'operator-model-dir'
        self.model.mkdir(mode=0o700)

    def activate_test(self,*,tenant='tenant',subject='operator'):
        model_patch=patch('skeleton.ai.runtime.operational_ai.deployment.production.startup.load_approved_manifest',return_value=manifest())
        process_patch=patch('skeleton.ai.runtime.operational_ai.model.isolation.client.OwnedWorker',new=lambda:FixtureProcess('normal'))
        model_patch.start();process_patch.start()
        self.addCleanup(model_patch.stop);self.addCleanup(process_patch.stop)
        return activate(model_root=self.model,state_dir=self.root,tenant=tenant,subject=subject,
                        n_ctx=512,max_new_tokens=32,n_threads=2,
                        isolated=True,inference_ms=2000)

    def test_isolated_startup_real_sqlite_knowledge_and_turn(self):
        stack,worker=self.activate_test()
        with stack:
            self.assertEqual(worker.spine.identity.model_sha256,MODEL)
            self.assertTrue(worker.spine.backend.healthy)
            worker.spine.create('s1')
            result=worker.spine.turn('s1','r1','Hello')
            self.assertEqual(result['model_sha256'],MODEL)
            self.assertEqual(result['generated_tokens'],6)
            replay=worker.spine.turn('s1','r1','Hello')
            self.assertTrue(replay['replayed'])
        self.assertTrue((self.root/'ai-spine.sqlite').is_file())
        self.assertTrue((self.root/'state.identity.json').is_file())

    def test_startup_refuses_principal_adoption(self):
        stack,worker=self.activate_test()
        with stack:
            worker.spine.create('s1')
        with self.assertRaises(Exception):
            stack2,_=self.activate_test(subject='different-subject')
            stack2.close()

    def test_disallow_nonbool_isolation_flag(self):
        with patch('skeleton.ai.runtime.operational_ai.deployment.production.startup.load_approved_manifest',return_value=manifest()):
            with self.assertRaises(SpineError):
                stack,_=activate(model_root=self.model,state_dir=self.root,
                    tenant='tenant',subject='operator',n_ctx=512,isolated='true')
                stack.close()


if __name__=='__main__':unittest.main()
