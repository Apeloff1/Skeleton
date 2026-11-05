"""A model cannot mint tool authority; one-time grants are spent before effects."""
import unittest,time
from hashlib import sha256
from skeleton.testing.agent_fabric_fixture import prepare
from skeleton.ai.runtime.operational_ai.agent_fabric.planning.spec import Step
from skeleton.ai.runtime.operational_ai.agent_fabric.authorization.grants import grant_from_operator,verify
from skeleton.ai.runtime.operational_ai.agent_fabric.core.canonical import canonical
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Unauthorized,Held
class ToolAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.db,self.store,self.fabric,self.plan,self.model,self.tool=prepare(steps=(Step('effect','tool','create report',resource='approved_export'),))
    def tearDown(self):self.db.close()
    def grant(self,params):
        return grant_from_operator(b'k'*32,plan='plan_1',step='effect',resource='approved_export',
           operation='execute',argument_sha256=sha256(canonical(params)).hexdigest(),nonce='once',
           expiry_ns=time.time_ns()+10**11)
    def test_no_grant_no_claim(self):
        with self.assertRaises(Unauthorized):self.fabric.run_one('plan_1')
        self.assertEqual(self.store.load('plan_1')[1]['effect']['state'],'pending')
        self.assertEqual(self.tool.calls,0)
    def test_signed_grant_effect_once(self):
        args={'report_id':'approved'}
        self.fabric.run_one('plan_1',grant=self.grant(args),arguments=args)
        self.assertEqual(self.tool.calls,1)
        self.assertEqual(self.store.load('plan_1')[2],'complete')
        self.assertIsNone(self.fabric.run_one('plan_1'))
    def test_wrong_arguments_held_without_effect(self):
        with self.assertRaises(Unauthorized):self.fabric.run_one('plan_1',grant=self.grant({'v':1}),arguments={'v':2})
        self.assertEqual(self.tool.calls,0)
        self.assertEqual(self.store.load('plan_1')[2],'held')
    def test_tool_uncertainty_cannot_auto_reset(self):
        with self.assertRaises(Unauthorized):self.fabric.run_one('plan_1',grant=self.grant({'v':1}),arguments={'v':2})
        with self.assertRaises(Held):self.store.repair('plan_1','effect',approved=True)
    def test_bad_signature(self):
        g=self.grant({'a':1})
        with self.assertRaises(Unauthorized):verify(b'f'*32,g,now_ns=time.time_ns(),plan='plan_1',step='effect',resource='approved_export',operation='execute',arguments={'a':1})
    def test_expired(self):
        args={};g=self.grant(args)
        with self.assertRaises(Unauthorized):verify(b'k'*32,g,now_ns=g.expiry_ns,plan='plan_1',step='effect',resource='approved_export',operation='execute',arguments=args)
if __name__=='__main__':unittest.main()
