import unittest
from skeleton.ai.product.closure_evidence_fan_in import PlaneClosureEvidence, ProductContractError, fan_in_closure
from skeleton.ai.product.whole_system_acceptance import AcceptanceGate, WholeSystemAcceptance
D="a"*64
E="b"*64

class TestClosureFanIn(unittest.TestCase):
    def evidence(self,signed=True):
        return tuple(
            PlaneClosureEvidence(f"FLGB-{i:02d}",D,E,signed,signed,"verifier" if signed else None)
            for i in range(1,19)
        )

    def test_gapless_exact_head_signed_fan_in_required(self):
        acceptance=WholeSystemAcceptance(E,D,(AcceptanceGate("all",True,True,E),),"independent")
        receipt=fan_in_closure(self.evidence(True),acceptance)
        self.assertEqual(len(receipt.plane_ids),18)
        with self.assertRaises(ProductContractError):
            fan_in_closure(self.evidence(True)[:-1],acceptance)
        with self.assertRaises(ProductContractError):
            fan_in_closure(self.evidence(False),acceptance)
        other=WholeSystemAcceptance(E,E,(AcceptanceGate("all",True,True,E),),"independent")
        with self.assertRaises(ProductContractError):
            fan_in_closure(self.evidence(True),other)

if __name__=="__main__": unittest.main()
