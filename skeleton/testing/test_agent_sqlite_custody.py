"""SQLite atomicity, replay, principal custody and tamper refusal."""
import unittest
from skeleton.testing.agent_fabric_fixture import prepare,MODEL
from skeleton.ai.runtime.operational_ai.agent_fabric.core.identity import Identity
from skeleton.ai.runtime.operational_ai.agent_fabric.custody.store import AgentStore
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Conflict,Integrity
from skeleton.ai.runtime.operational_ai.agent_fabric.operations.doctor import inspect
class SQLiteCustodyTests(unittest.TestCase):
    def setUp(self):self.db,self.store,self.fabric,self.plan,self.model,self.tool=prepare()
    def tearDown(self):self.db.close()
    def test_plan_accepted(self):self.assertEqual(self.store.load('plan_1')[2],'active')
    def test_replay(self):self.assertTrue(self.store.create(self.plan)['replayed'])
    def test_exact_model_work(self):
        result=self.fabric.run_one('plan_1');self.assertEqual(result['status'],'complete')
        self.assertEqual(self.model.calls,1);self.assertEqual(self.store.load('plan_1')[2],'complete')
        self.assertIsNone(self.fabric.run_one('plan_1'))
        self.assertEqual(self.model.calls,1)
    def test_durable_restart_no_rerun(self):
        self.fabric.run_one('plan_1')
        again=AgentStore(self.db,self.store.identity)
        self.assertEqual(again.load('plan_1')[2],'complete')
    def test_identity_rebinding_denied(self):
        other=AgentStore(self.db,Identity('other','operator',MODEL,MODEL))
        with self.assertRaises(Conflict):other.load('plan_1')
    def test_plan_blob_tampering(self):
        self.db.db.execute('UPDATE agent_plans SET plan_sha=? WHERE plan_id=?',('0'*64,'plan_1'))
        with self.assertRaises(Integrity):self.store.load('plan_1')
    def test_event_tampering(self):
        self.db.db.execute("UPDATE agent_events SET event_sha=? WHERE plan_id='plan_1'",('f'*64,))
        with self.assertRaises(Integrity):self.store.load('plan_1')
    def test_step_receipt_integrity(self):
        self.fabric.run_one('plan_1');inspect(self.store,'plan_1')
        self.db.db.execute("UPDATE agent_steps SET result_sha=? WHERE step_id='first'",('0'*64,))
        with self.assertRaises(Integrity):inspect(self.store,'plan_1')
    def test_held_request_requires_operator(self):
        self.model.fail=True
        with self.assertRaises(RuntimeError):self.fabric.run_one('plan_1')
        self.assertEqual(self.store.load('plan_1')[2],'held')
        self.assertEqual(self.model.calls,1)
        self.assertIsNone(self.fabric.run_one('plan_1'))
    def test_explicit_repair_only(self):
        self.model.fail=True
        with self.assertRaises(RuntimeError):self.fabric.run_one('plan_1')
        with self.assertRaises(Exception):self.store.repair('plan_1','first')
        self.store.repair('plan_1','first',approved=True)
        self.model.fail=False;self.fabric.run_one('plan_1')
        self.assertEqual(self.model.calls,2)
if __name__=='__main__':unittest.main()
