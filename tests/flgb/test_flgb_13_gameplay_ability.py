import unittest
from skeleton.game.gameplay.gameplay_ability import GameplayAbility
D="a"*64
class T(unittest.TestCase):
 def test_digest_and_tags(self):
  a=GameplayAbility("dash",3,2,("move","combat"),D)
  self.assertEqual(a.tags,("combat","move")); self.assertEqual(len(a.digest),64)
if __name__=="__main__": unittest.main()
