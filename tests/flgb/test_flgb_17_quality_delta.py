import unittest
from skeleton.ai.forge.quality_delta import QualityDelta
D="a"*64
E="b"*64

class TestQualityDelta(unittest.TestCase):
    def test_delta_is_signed_and_evidence_bound(self):
        up=QualityDelta(D,E,500000,650000,D)
        down=QualityDelta(D,E,700000,600000,E)
        self.assertEqual(up.delta_ppm,150000)
        self.assertEqual(down.delta_ppm,-100000)

if __name__=="__main__": unittest.main()
