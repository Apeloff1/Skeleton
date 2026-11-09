import unittest
from skeleton.game.platform.prediction import PredictionFrame
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_reconciliation(self):
  self.assertTrue(PredictionFrame(1,D,E,E).reconciled)
  self.assertFalse(PredictionFrame(1,D,D,E).reconciled)
if __name__=="__main__": unittest.main()
