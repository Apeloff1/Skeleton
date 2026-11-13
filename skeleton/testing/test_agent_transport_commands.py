"""Typed agent commands do not allow unknown opcodes or hidden privileged actions."""
import unittest
from skeleton.testing.agent_fabric_fixture import prepare
from skeleton.ai.runtime.operational_ai.agent_fabric.transport.command import dispatch
from skeleton.ai.runtime.operational_ai.agent_fabric.core.canonical import canonical
from skeleton.ai.runtime.operational_ai.agent_fabric.core.errors import Invalid
class CommandTests(unittest.TestCase):
    def setUp(self):self.db,self.store,self.fabric,self.plan,self.model,self.tool=prepare()
    def tearDown(self):self.db.close()
    def cmd(self,op,args):return dispatch(self.fabric,canonical({'schema':'agent.command.v1','operation':op,'arguments':args}))
    def test_inspect(self):self.assertEqual(self.cmd('inspect',{'plan_id':'plan_1'})['status'],'active')
    def test_ready(self):self.assertEqual(self.cmd('ready',{'plan_id':'plan_1'})['ready'],['first'])
    def test_run_model(self):self.assertEqual(self.cmd('run_one',{'plan_id':'plan_1'})['status'],'complete')
    def test_unsupported_action(self):
        with self.assertRaises(Invalid):self.cmd('promote_to_production',{'plan_id':'plan_1'})
    def test_unknown_args(self):
        with self.assertRaises(Invalid):self.cmd('ready',{'plan_id':'plan_1','owner':'other'})
    def test_no_auto_tools(self):
        with self.assertRaises(Invalid):self.cmd('execute_tool',{'plan_id':'plan_1'})
if __name__=='__main__':unittest.main()
