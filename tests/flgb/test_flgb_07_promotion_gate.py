import unittest
from skeleton.ai.training.promotion_gate import PromotionEvidence
D="a"*64

class TestPromotionGate(unittest.TestCase):
    def test_rights_contamination_eval_and_rollback_are_non_compensable(self):
        good=PromotionEvidence(D,D,D,D,D,D,"independent",True,True,True,True)
        self.assertTrue(good.qualified)
        blocked=PromotionEvidence(D,D,D,D,D,D,"independent",True,False,True,True)
        self.assertFalse(blocked.qualified)

if __name__=="__main__": unittest.main()
