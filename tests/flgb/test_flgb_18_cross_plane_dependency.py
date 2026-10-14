import unittest
from skeleton.ai.product.cross_plane_dependency import PlaneDependency, ProductContractError, dependency_order
D="a"*64

class TestCrossPlaneDependency(unittest.TestCase):
    def test_topological_order_and_cycle_rejection(self):
        planes=(PlaneDependency("FLGB-01",(),D),PlaneDependency("FLGB-02",("FLGB-01",),D),PlaneDependency("FLGB-03",("FLGB-01",),D))
        order=dependency_order(planes)
        self.assertEqual(order[0],"FLGB-01")
        with self.assertRaises(ProductContractError):
            dependency_order((PlaneDependency("a",("b",),D),PlaneDependency("b",("a",),D)))

if __name__=="__main__": unittest.main()
