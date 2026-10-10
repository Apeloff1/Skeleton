import unittest
from skeleton.ai.product.whole_system_acceptance import AcceptanceGate, ProductContractError, WholeSystemAcceptance
D="a"*64
E="b"*64

class TestWholeSystemAcceptance(unittest.TestCase):
    def test_every_gate_must_pass(self):
        passed=WholeSystemAcceptance(D,E,(AcceptanceGate("unit",True,False,D),AcceptanceGate("security",True,True,E)),"independent")
        self.assertTrue(passed.accepted)
        blocked=WholeSystemAcceptance(D,E,(AcceptanceGate("unit",True,False,D),AcceptanceGate("security",False,True,E)),"independent")
        self.assertFalse(blocked.accepted)
        with self.assertRaises(ProductContractError):
            WholeSystemAcceptance(D,E,(AcceptanceGate("x",True,True,D),AcceptanceGate("x",True,False,E)),"independent")

if __name__=="__main__": unittest.main()
