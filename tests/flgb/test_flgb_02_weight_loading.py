import unittest
from skeleton.ai.model_runtime.weight_loading import ModelRuntimeError, WeightLoadPlan, WeightShard
D="a"*64
class TestWeights(unittest.TestCase):
    def test_plan_binds_order_and_bytes(self):
        shards=(WeightShard(0,D,10,"artifact:0"),WeightShard(1,D,20,"artifact:1"))
        plan=WeightLoadPlan(D,shards,30)
        self.assertEqual(len(plan.digest),64)
        with self.assertRaises(ModelRuntimeError): WeightLoadPlan(D,shards,31)
if __name__=="__main__": unittest.main()
