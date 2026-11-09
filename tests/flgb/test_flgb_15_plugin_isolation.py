import unittest
from skeleton.game.platform.plugin_isolation import PlatformContractError, PluginPolicy
class T(unittest.TestCase):
 def test_boundary(self):
  p=PluginPolicy("p",("read",),("/mods/p",),"deny")
  self.assertTrue(p.authorizes("read")); self.assertFalse(p.authorizes("write"))
  with self.assertRaises(PlatformContractError): PluginPolicy("p",(),("/mods/../etc",),"deny")
if __name__=="__main__": unittest.main()
