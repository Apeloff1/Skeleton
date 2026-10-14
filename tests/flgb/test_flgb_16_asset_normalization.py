import unittest
from skeleton.game.build.asset_normalization import NormalizedAsset
D="a"*64
class T(unittest.TestCase):
 def test_identity(self): self.assertEqual(NormalizedAsset("a",D,"mesh/v1",D,"n1").normalized_digest,D)
if __name__=="__main__": unittest.main()
