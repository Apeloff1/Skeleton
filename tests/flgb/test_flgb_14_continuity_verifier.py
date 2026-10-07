import unittest
from skeleton.game.generation.canon_constraints import CanonConstraint
from skeleton.game.generation.continuity_verifier import verify_continuity
from skeleton.game.generation.lore_graph import LoreFact, LoreGraph
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_canon_failure_is_critical_issue(self):
  issues=verify_continuity(LoreGraph((LoreFact("f","hero","alive",D,D),)),(),(CanonConstraint("c","hero","alive",E),))
  self.assertEqual(issues[0].severity,"critical")
if __name__=="__main__": unittest.main()
