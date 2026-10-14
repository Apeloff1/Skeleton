import unittest
from skeleton.ai.model_runtime.device_placement import DeviceDescriptor, plan_device_placement
from skeleton.ai.model_runtime.weight_loading import WeightShard
D="a"*64
class TestPlacement(unittest.TestCase):
    def test_deterministic_capacity_bound(self):
        shards=(WeightShard(0,D,60,"s0"),WeightShard(1,D,40,"s1"))
        devices=(DeviceDescriptor("a","cpu",100),DeviceDescriptor("b","cpu",100))
        plan=plan_device_placement(shards,devices,reserve_bytes_per_device=10)
        self.assertEqual([(p.shard_index,p.device_id) for p in plan],[(0,"a"),(1,"b")])
if __name__=="__main__": unittest.main()
