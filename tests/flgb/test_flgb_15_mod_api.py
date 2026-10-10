import unittest
from skeleton.game.platform.mod_api import ModManifest
D="a"*64
class T(unittest.TestCase):
 def test_capabilities_are_canonical(self):
  m=ModManifest("m","1",1,("write","read"),D,D)
  self.assertEqual(m.capability_requests,("read","write"))
if __name__=="__main__": unittest.main()
