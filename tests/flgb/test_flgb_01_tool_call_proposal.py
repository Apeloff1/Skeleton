import unittest
from skeleton.inference.tool_call_proposal import FLGBInferenceError, ToolCallProposal
class TestToolCallProposal(unittest.TestCase):
    def test_never_self_authorizes(self):
        proposal = ToolCallProposal("p", "op", "search", {"q":"x"}, ("network.read",))
        self.assertEqual(proposal.authority_scope, "proposal-only")
        with self.assertRaises(FLGBInferenceError):
            ToolCallProposal("p", "op", "search", {}, (), "execute")
if __name__ == "__main__": unittest.main()
