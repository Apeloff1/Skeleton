import unittest
from skeleton.game.platform.network_protocol import NetworkProtocol
D="a"*64
class T(unittest.TestCase):
 def test_compatibility_window(self):
  p=NetworkProtocol("net",3,D,1024,2)
  self.assertTrue(p.compatible(2)); self.assertTrue(p.compatible(3)); self.assertFalse(p.compatible(1))
if __name__=="__main__": unittest.main()
