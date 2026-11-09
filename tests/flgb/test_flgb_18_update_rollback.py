import unittest
from skeleton.ai.product.update_rollback import ProductContractError, UpdateRollbackPlan
D="a"*64
E="b"*64

class TestUpdateRollback(unittest.TestCase):
    def test_update_requires_distinct_release_and_rollback_artifact(self):
        plan=UpdateRollbackPlan(D,E,D,E,D,E)
        self.assertTrue(plan.ready)
        self.assertEqual(len(plan.digest),64)
        with self.assertRaises(ProductContractError):
            UpdateRollbackPlan(D,D,D,E,D,E)

if __name__=="__main__": unittest.main()
