"""Model work executes only through an authoritative externally provided port."""
import unittest
from hashlib import sha256
from skeleton.testing.agent_fabric_fixture import prepare
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.spec import Step
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Invalid
from skeleton.ai.runtime.operational_ai.agent_fabric.integration.spine import SpinePort
class ModelPortTests(unittest.TestCase):
    def setUp(self):self.db,self.store,self.fabric,self.plan,self.model,self.tool=prepare()
    def tearDown(self):self.db.close()
    def test_model_passes_stable_request(self):
        result=self.fabric.run_one('plan_1')
        self.assertEqual(self.model.calls,1)
        self.assertEqual(result['status'],'complete')
    def test_model_failure_holds_only_one_attempt(self):
        self.model.fail=True
        with self.assertRaises(RuntimeError):self.fabric.run_one('plan_1')
        self.assertIsNone(self.fabric.run_one('plan_1'))
        self.assertEqual(self.model.calls,1)
    def test_spine_port_requires_identity(self):
        with self.assertRaises(Exception):SpinePort(object())
    def test_spine_port_refuses_forged_receipt(self):
        class Identity:
            model_sha256='a'*64;tokenizer_sha256='a'*64
        class Fake:
            identity=Identity()
            def turn(self,*args,**kwargs):return {'model_sha256':'b'*64,'tokenizer_sha256':'a'*64,'output_sha256':'a'*64}
        with self.assertRaises(Exception):SpinePort(Fake()).complete(session='s',request_id='r',prompt='p')
if __name__=='__main__':unittest.main()
