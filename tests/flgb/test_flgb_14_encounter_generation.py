import unittest
from skeleton.game.generation.encounter_generation import EncounterSpec
D="a"*64
class T(unittest.TestCase):
 def test_actor_order_is_canonical(self):
  e=EncounterSpec("e",D,500000,("b","a"),D); self.assertEqual(e.actor_ids,("a","b"))
if __name__=="__main__": unittest.main()
