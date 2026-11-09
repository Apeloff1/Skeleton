import unittest
from skeleton.ai.model_runtime.speculative_decoding import ModelRuntimeError, SpeculativeReceipt
D="a"*64
E="b"*64
class TestSpeculative(unittest.TestCase):
    def test_target_acceptance_is_bounded(self):
        receipt=SpeculativeReceipt("r",D,E,(1,2,3),2)
        self.assertEqual(receipt.accepted_tokens,(1,2))
        with self.assertRaises(ModelRuntimeError): SpeculativeReceipt("r",D,E,(1,),2)
if __name__=="__main__": unittest.main()
