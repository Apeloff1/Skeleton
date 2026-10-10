import unittest
from skeleton.ai.forge.promotion_arbitration import ForgeContractError, PromotionCandidate, arbitrate_promotion
D="a"*64
E="b"*64

class TestPromotionArbitration(unittest.TestCase):
    def test_rights_and_risk_gate_before_quality(self):
        risky=PromotionCandidate("risky",D,1000000,900000,True,D,E)
        unclear=PromotionCandidate("unclear",E,950000,100000,False,D,E)
        safe=PromotionCandidate("safe",E,800000,100000,True,E,D)
        winner=arbitrate_promotion((risky,unclear,safe),700000,200000)
        self.assertEqual(winner.candidate_id,"safe")
        with self.assertRaises(ForgeContractError):
            arbitrate_promotion((risky,),700000,200000)

if __name__=="__main__": unittest.main()
