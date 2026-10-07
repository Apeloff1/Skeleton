import unittest
from skeleton.game.generation.layout_grammar import LayoutProduction, expand_layout
class T(unittest.TestCase):
 def test_seeded_expansion(self):
  rules=(LayoutProduction("S",("A","B"),1),)
  self.assertEqual(expand_layout("S",rules,7,2),("A","B"))
if __name__=="__main__": unittest.main()
