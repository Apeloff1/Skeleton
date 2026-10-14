import unittest
from skeleton.ai.product.build_to_chat_evidence import BuildEvidence, ProductContractError
D="a"*64
E="b"*64

class TestBuildEvidence(unittest.TestCase):
    def test_status_is_explicit_and_exact_head_bound(self):
        evidence=BuildEvidence(D,E,D,E,D,"passed")
        self.assertEqual(len(evidence.digest),64)
        with self.assertRaises(ProductContractError):
            BuildEvidence(D,E,D,E,D,"unknown")

if __name__=="__main__": unittest.main()
