"""An interrupted worker must be held, never automatically retried."""
from __future__ import annotations
import unittest
from skeleton.testing.agent_fabric_fixture import prepare
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Held,Conflict
from skeleton.ai.runtime.operational_ai.agent_fabric.operations.recovery import review
class UncertainWriterTests(unittest.TestCase):
    def setUp(self):self.db,self.store,self.fabric,self.plan,self.model,self.tool=prepare()
    def tearDown(self):self.db.close()
    def test_running_job_held_only_after_operator_termination(self):
        fence=self.store.start('plan_1','first','worker1')
        self.assertEqual(self.store.load('plan_1')[1]['first']['state'],'running')
        with self.assertRaises(Held):self.store.mark_uncertain('plan_1','first',approved=True)
        with self.assertRaises(Held):self.store.mark_uncertain('plan_1','first',worker_terminated=True)
        self.assertEqual(self.model.calls,0)
        self.store.mark_uncertain('plan_1','first',approved=True,worker_terminated=True)
        self.assertEqual(self.store.load('plan_1')[2],'held')
        self.assertEqual(review(self.store,'plan_1')['held'],('first',))
    def test_only_one_approved_transition(self):
        self.store.start('plan_1','first','worker1')
        self.store.mark_uncertain('plan_1','first',approved=True,worker_terminated=True)
        with self.assertRaises(Conflict):self.store.mark_uncertain('plan_1','first',approved=True,worker_terminated=True)
    def test_no_reassignment_until_operator_consent(self):
        self.store.start('plan_1','first','worker1')
        self.store.mark_uncertain('plan_1','first',approved=True,worker_terminated=True)
        self.assertIsNone(self.fabric.run_one('plan_1'))
        self.assertEqual(self.model.calls,0)
        self.store.repair('plan_1','first',approved=True)
        self.fabric.run_one('plan_1')
        self.assertEqual(self.model.calls,1)
if __name__=='__main__':unittest.main()
