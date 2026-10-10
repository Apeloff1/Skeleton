import unittest
from skeleton.ai.agents.tool_schema import AgentContractError, ToolSchema
class TestToolSchema(unittest.TestCase):
    def test_object_schema_required(self):
        schema=ToolSchema("search","v1",{"type":"object"},{"type":"object"})
        self.assertEqual(len(schema.digest),64)
        with self.assertRaises(AgentContractError):
            ToolSchema("search","v1",{"type":"array"},{"type":"object"})
if __name__=="__main__": unittest.main()
