import unittest
from skeleton.ai.product.idle_mirror_room import IdleMirrorPlan, ProductContractError
D="a"*64

class TestIdleMirrorRoom(unittest.TestCase):
    def test_idle_work_never_self_promotes_or_competes_with_foreground(self):
        plan=IdleMirrorPlan("mirror",D,1000,4,1024)
        self.assertEqual(plan.output_kind,"candidate-only")
        self.assertTrue(plan.may_run(False,True))
        self.assertFalse(plan.may_run(True,True))
        self.assertFalse(plan.may_run(False,False))
        with self.assertRaises(ProductContractError):
            IdleMirrorPlan("mirror",D,1000,4,1024,"production")

if __name__=="__main__": unittest.main()
