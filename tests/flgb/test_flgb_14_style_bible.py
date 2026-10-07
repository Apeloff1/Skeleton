import unittest
from skeleton.game.generation.style_bible import StyleBible
D="a"*64
E="b"*64
class T(unittest.TestCase):
 def test_rules_bind_version(self):
  a=StyleBible("style",1,(D,),(E,)); b=StyleBible("style",2,(D,),(E,))
  self.assertNotEqual(a.digest,b.digest)
if __name__=="__main__": unittest.main()
