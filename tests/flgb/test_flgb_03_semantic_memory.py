import unittest
from skeleton.ai.context.semantic_memory import ContextContractError, SemanticFact, SemanticMemory
D="a"*64
E="b"*64
class TestSemanticMemory(unittest.TestCase):
    def test_fact_revision_and_rank(self):
        fact=SemanticFact("f","hero","owns",D,E,700000,0)
        mem=SemanticMemory().put(fact)
        self.assertEqual(mem.query("hero")[0].fact_id,"f")
        with self.assertRaises(ContextContractError):
            mem.put(SemanticFact("f","hero","owns",E,D,800000,2))
if __name__=="__main__": unittest.main()
