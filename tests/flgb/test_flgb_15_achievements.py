import unittest
from skeleton.game.platform.achievements import AchievementReceipt, AchievementRule
D="a"*64
class T(unittest.TestCase):
 def test_receipt(self):
  r=AchievementRule("first",D); x=AchievementReceipt("first",D,10,D)
  self.assertTrue(r.irreversible); self.assertEqual(x.unlocked_tick,10)
if __name__=="__main__": unittest.main()
