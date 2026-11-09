import unittest
from skeleton.game.build.automated_playtest import PlaytestResult
D="a"*64
class T(unittest.TestCase):
 def test_result(self): self.assertTrue(PlaytestResult("s",D,D,True,D).passed)
if __name__=="__main__": unittest.main()
