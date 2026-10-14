import unittest
from skeleton.ai.training.mirror_room_evaluation import MirrorEvaluation
D="a"*64

class TestMirrorRoom(unittest.TestCase):
    def test_quality_gain_cannot_override_risk_gate(self):
        safe=MirrorEvaluation("e",D,D,700000,600000,True,"independent",D)
        risky=MirrorEvaluation("e2",D,D,1000000,600000,False,"independent",D)
        self.assertTrue(safe.candidate_wins)
        self.assertFalse(risky.candidate_wins)

if __name__=="__main__": unittest.main()
