import unittest
from skeleton.ai.model_runtime.distributed_serving import ModelRuntimeError, Replica, route_request
D="a"*64
E="b"*64
class TestServing(unittest.TestCase):
    def test_only_healthy_matching_least_loaded_replica_routes(self):
        reps=(Replica("a",D,E,True,2),Replica("b",D,E,True,1),Replica("c",D,E,False,0))
        self.assertEqual(route_request("req",D,reps).replica_id,"b")
        with self.assertRaises(ModelRuntimeError): route_request("req","b"*64,reps)
if __name__=="__main__": unittest.main()
