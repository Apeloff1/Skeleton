import unittest
from skeleton.game.generation.regeneration_diff import regeneration_diff
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_only_changed_objects_emit(self):
  changes=regeneration_diff({"a":D,"b":D},{"a":D,"b":E},"seed-change")
  self.assertEqual([c.object_id for c in changes],["b"])
if __name__=="__main__": unittest.main()
