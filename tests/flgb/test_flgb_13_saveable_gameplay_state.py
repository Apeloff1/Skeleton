import unittest
from skeleton.game.gameplay.saveable_gameplay_state import SaveableGameplayState
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_state_binds_canon(self):
  a=SaveableGameplayState("w",1,10,D,D)
  b=SaveableGameplayState("w",1,10,D,E)
  self.assertNotEqual(a.digest,b.digest)
if __name__=="__main__": unittest.main()
