"""Failure holds preserve uncertain side effects and prohibit autonomous repair."""
import unittest
from skeleton.testing.agent_fabric_fixture import prepare
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.spec import Step
from skeleton.ai.runtime.operational_ai.agent_fabric.operations.recovery import review,reconcile_model_only
from skeleton.ai.runtime.operational_ai.agent_fabric.operations.export import inventory
from skeleton.ai.runtime.operational_ai.agent_fabric.core.canonical import parse
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Held
class RecoveryTests(unittest.TestCase):
    def setUp(self):self.db,self.store,self.fabric,self.plan,self.model,self.tool=prepare()
    def tearDown(self):self.db.close()
    def test_before_work(self):self.assertFalse(review(self.store,'plan_1')['requires_operator'])
    def test_crash_holds(self):
        self.model.fail=True
        with self.assertRaises(RuntimeError):self.fabric.run_one('plan_1')
        proof=review(self.store,'plan_1')
        self.assertEqual(proof['held'],('first',))
        self.assertFalse(proof['automatic_retry_accepted'])
        with self.assertRaises(Held):reconcile_model_only(self.store,'plan_1','first')
        reconcile_model_only(self.store,'plan_1','first',operator_approved=True)
        self.assertEqual(self.store.load('plan_1')[2],'active')
    def test_export_excludes_private_contents(self):
        raw=inventory(self.store,'plan_1')
        record=parse(raw)
        self.assertFalse(record['contains_model_text'])
        self.assertNotIn('Explain offline inference',raw.decode())
if __name__=='__main__':unittest.main()
