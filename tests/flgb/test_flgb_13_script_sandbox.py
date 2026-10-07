import unittest
from skeleton.game.gameplay.script_sandbox import ScriptSandboxPolicy
class TestScriptSandbox(unittest.TestCase):
    def test_api_allowlist_and_dangerous_defaults(self):
        p=ScriptSandboxPolicy("p",("game.read","game.emit"),1000,1024)
        self.assertTrue(p.authorizes("game.read"))
        self.assertFalse(p.authorizes("os.exec"))
        self.assertFalse(p.allow_network)
        self.assertFalse(p.allow_process_spawn)
if __name__=="__main__": unittest.main()
