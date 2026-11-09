import unittest
from skeleton.game.platform.save_schema import SaveSchema
D="a"*64
class T(unittest.TestCase):
 def test_save_digest(self):
  self.assertEqual(len(SaveSchema("save",1,D,D,D).digest),64)
if __name__=="__main__": unittest.main()
