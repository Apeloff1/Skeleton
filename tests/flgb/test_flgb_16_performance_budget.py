import unittest
from skeleton.game.build.performance_budget import PerformanceBudget
class T(unittest.TestCase):
 def test_hard_ceiling(self):
  b=PerformanceBudget("frame",16667,"us"); self.assertTrue(b.allows(16000)); self.assertFalse(b.allows(17000))
if __name__=="__main__": unittest.main()
