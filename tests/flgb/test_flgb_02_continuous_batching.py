import unittest
from skeleton.ai.model_runtime.continuous_batching import BatchRequest, ModelRuntimeError, plan_continuous_batches
class TestBatching(unittest.TestCase):
    def test_priority_and_token_budget(self):
        reqs=(BatchRequest("low",4,4,0),BatchRequest("high",4,4,2),BatchRequest("mid",4,4,1))
        self.assertEqual(plan_continuous_batches(reqs,max_batch_size=2,max_tokens_per_batch=16),(("high","mid"),("low",)))
        with self.assertRaises(ModelRuntimeError): BatchRequest("empty",0,0)
if __name__=="__main__": unittest.main()
