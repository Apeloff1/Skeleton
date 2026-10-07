import unittest
from skeleton.game.generation.quest_generation import GeneratedQuest
D="a"*64
class T(unittest.TestCase):
 def test_generated_quest_binds_canon(self):
  q=GeneratedQuest("q",D,("o",),(),D); self.assertEqual(q.canon_digest,D)
if __name__=="__main__": unittest.main()
