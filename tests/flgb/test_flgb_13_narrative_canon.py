import unittest
from skeleton.game.gameplay.narrative_canon import CanonFact, GameplayContractError, NarrativeCanon
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_contradiction_fails(self):
  NarrativeCanon((CanonFact("f1","hero","alive",D,D),))
  with self.assertRaises(GameplayContractError):
   NarrativeCanon((CanonFact("f1","hero","alive",D,D),CanonFact("f2","hero","alive",E,D)))
if __name__=="__main__": unittest.main()
