import unittest
from skeleton.game.generation.canon_constraints import CanonConstraint, verify_canon
from skeleton.game.generation.lore_graph import LoreClaim
D="a"*64
E="b"*64

class TestCanonConstraints(unittest.TestCase):
    def test_conflicting_observed_claim_is_a_violation(self):
        constraint=CanonConstraint("hero-origin","hero","born-in",D,True)
        good=LoreClaim("a","hero","born-in",D,E)
        bad=LoreClaim("b","hero","born-in",E,D)
        self.assertEqual(verify_canon((constraint,),(good,)),())
        self.assertEqual(verify_canon((constraint,),(bad,)),("hero-origin",))

if __name__=="__main__": unittest.main()
