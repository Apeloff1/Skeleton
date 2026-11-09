import unittest
from skeleton.ai.forge.rival_challenger import ForgeContractError, RivalChallenge
D="a"*64
E="b"*64
class TestRivalChallenger(unittest.TestCase):
    def test_defects_are_unique_and_canonical(self):
        c=RivalChallenge("c",D,(E,D),500000,"challenger")
        self.assertEqual(c.defect_digests,(D,E))
        with self.assertRaises(ForgeContractError): RivalChallenge("c",D,(D,D),1,"challenger")
if __name__=="__main__": unittest.main()
