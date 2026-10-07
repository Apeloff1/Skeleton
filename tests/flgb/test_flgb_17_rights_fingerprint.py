import unittest
from skeleton.ai.forge.rights_fingerprint import ForgeContractError, RightsFingerprint
D="a"*64

class TestRightsFingerprint(unittest.TestCase):
    def test_threshold_is_bounded(self):
        f=RightsFingerprint(D,D,D,250000)
        self.assertEqual(f.threshold_ppm,250000)
        with self.assertRaises(ForgeContractError):
            RightsFingerprint(D,D,D,1000001)

if __name__=="__main__": unittest.main()
