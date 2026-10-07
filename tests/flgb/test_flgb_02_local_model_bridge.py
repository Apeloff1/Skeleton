import unittest
from skeleton.ai.model_runtime.local_model_bridge import LocalModelReceipt, LocalModelRequest, ModelRuntimeError
D="a"*64
class TestLocalBridge(unittest.TestCase):
    def test_bridge_is_inference_only_and_failed_output_is_fenced(self):
        req=LocalModelRequest("op",D,D,32,1000)
        self.assertEqual(req.authority_scope,"inference-only")
        with self.assertRaises(ModelRuntimeError): LocalModelRequest("op",D,D,32,1000,"execute")
        with self.assertRaises(ModelRuntimeError): LocalModelReceipt("op",D,"cancelled",D,D)
if __name__=="__main__": unittest.main()
