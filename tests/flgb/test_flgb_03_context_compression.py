import unittest
from skeleton.ai.context.context_compression import CompressionReceipt, ContextContractError
D="a"*64
E="b"*64
class TestCompression(unittest.TestCase):
    def test_compression_must_reduce_and_bind_sources(self):
        receipt=CompressionReceipt("op",(D,E),100,D,20,("policy",))
        self.assertEqual(receipt.savings_tokens,80)
        with self.assertRaises(ContextContractError): CompressionReceipt("op",(D,),100,D,100,())
if __name__=="__main__": unittest.main()
