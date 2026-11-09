import unittest
from skeleton.game.gameplay.script_sandbox import ScriptSandboxPolicy
class T(unittest.TestCase):
 def test_capability_subset(self):
  p=ScriptSandboxPolicy("s",("read","emit"),100,1024)
  self.assertTrue(p.allows("read")); self.assertFalse(p.allows("write"))
if __name__=="__main__": unittest.main()
