import unittest
from skeleton.ai.context.contradiction_handling import ContextContractError, Contradiction
D="a"*64
E="b"*64
class TestContradiction(unittest.TestCase):
    def test_resolution_is_explicit(self):
        item=Contradiction("x","a","b",D)
        resolved=item.resolve(E)
        self.assertEqual(resolved.status,"resolved")
        with self.assertRaises(ContextContractError): resolved.resolve(D)
if __name__=="__main__": unittest.main()
