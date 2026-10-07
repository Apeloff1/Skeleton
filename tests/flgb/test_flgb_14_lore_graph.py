import unittest
from skeleton.game.generation.lore_graph import GenerationContractError, LoreFact, LoreGraph
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_contradiction_fails(self):
  with self.assertRaises(GenerationContractError): LoreGraph((LoreFact("a","hero","alive",D,D),LoreFact("b","hero","alive",E,D)))
if __name__=="__main__": unittest.main()
