import unittest
from skeleton.game.generation.canon_constraints import CanonConstraint, validate_canon_constraints
from skeleton.game.generation.lore_graph import LoreFact
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_mismatch_reported(self):
  facts=(LoreFact("f","hero","alive",D,D),); constraints=(CanonConstraint("c","hero","alive",E),)
  self.assertEqual(validate_canon_constraints(facts,constraints),("c",))
if __name__=="__main__": unittest.main()
