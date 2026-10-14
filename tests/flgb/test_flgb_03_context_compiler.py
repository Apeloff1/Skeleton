import unittest
from skeleton.ai.context.context_compiler import ContextContractError, ContextItem, compile_context
D="a"*64
class TestContextCompiler(unittest.TestCase):
    def test_budget_and_mandatory_items(self):
        items=(ContextItem("must","policy",D,D,4,10,True),ContextItem("nice","note",D,D,4,1,False))
        plan=compile_context("op",items,token_budget=4)
        self.assertEqual(plan.selected_ids,("must",))
        with self.assertRaises(ContextContractError): compile_context("op",items,token_budget=3)
if __name__=="__main__": unittest.main()
