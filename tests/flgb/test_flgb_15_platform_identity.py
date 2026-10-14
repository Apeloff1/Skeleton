import unittest
from skeleton.game.platform.platform_identity import PlatformIdentity
D="a"*64
class T(unittest.TestCase):
 def test_identity_digest(self):
  self.assertEqual(len(PlatformIdentity("steam","u",D,D).digest),64)
if __name__=="__main__": unittest.main()
