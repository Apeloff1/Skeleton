import unittest
from skeleton.game.generation.character_generation import GeneratedCharacter
D="a"*64
class T(unittest.TestCase):
 def test_traits_canonicalized(self):
  c=GeneratedCharacter("c",D,"hero",("brave","agile"),D); self.assertEqual(c.trait_ids,("agile","brave"))
if __name__=="__main__": unittest.main()
