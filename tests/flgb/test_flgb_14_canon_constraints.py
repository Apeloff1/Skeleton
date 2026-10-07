import unittest
from skeleton.game.generation.canon_constraints import CanonConstraint, verify_canon
D="a"*64
E="b"*64
class TestCanonConstraints(unittest.TestCase):
    def test_equal_and_not_equal_constraints(self):
        constraints=(CanonConstraint("must","hero","alive",D,"must-equal"),CanonConstraint("not","hero","faction",E,"must-not-equal"))
        self.assertEqual(verify_canon(constraints,{("hero","alive"):D,("hero","faction"):D}),())
        self.assertEqual(verify_canon(constraints,{("hero","alive"):E,("hero","faction"):E}),("must","not"))
if __name__=="__main__": unittest.main()
