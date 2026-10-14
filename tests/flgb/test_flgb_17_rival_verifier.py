import unittest
from skeleton.ai.forge.rival_verifier import ForgeContractError, RivalVerification
D="a"*64
E="b"*64

class TestRivalVerifier(unittest.TestCase):
    def test_quality_risk_rights_and_evidence_are_explicit(self):
        v=RivalVerification("v",D,E,800000,100000,True,"independent",D)
        self.assertEqual(len(v.digest),64)
        self.assertTrue(v.rights_clear)
        with self.assertRaises(ForgeContractError):
            RivalVerification("v",D,E,1000001,0,True,"independent",D)

if __name__=="__main__": unittest.main()
