import unittest
from skeleton.ai.agents.tool_registry import AgentContractError, ToolDescriptor, ToolRegistry
D="a"*64
class TestToolRegistry(unittest.TestCase):
    def test_identity_is_immutable(self):
        tool=ToolDescriptor("search","v1",D,("net.read",),"read",True,False)
        reg=ToolRegistry().register(tool)
        self.assertEqual(reg.resolve("search","v1"),tool)
        with self.assertRaises(AgentContractError):
            reg.register(ToolDescriptor("search","v1",D,("net.write",),"read",True,False))
if __name__=="__main__": unittest.main()
