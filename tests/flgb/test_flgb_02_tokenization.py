import unittest
from skeleton.ai.model_runtime.tokenization import ModelRuntimeError, TokenSequence
D="a"*64
class TestTokenization(unittest.TestCase):
    def test_identity_and_bounds(self):
        seq=TokenSequence(D,(1,2,3),D)
        self.assertEqual(len(seq.digest),64)
        with self.assertRaises(ModelRuntimeError): TokenSequence(D,(-1,),D)
if __name__=="__main__": unittest.main()
