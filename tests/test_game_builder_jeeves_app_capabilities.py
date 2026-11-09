import unittest
from skeleton.ai.game_builder.jeeves_app_capabilities import discover,CapabilityRegistry

class JeevesAppCapabilityTests(unittest.TestCase):
    def test_inventory_classifies_without_execution(self):
        result=discover(["backend/core/asset_forge.py",
                         "frontend/components/Editor/CodeEditor.tsx",
                         "backend/routes/dragon_academy.py",
                         "skeleton/ai/game_builder/story_workspace.py"])
        self.assertEqual(result["total"],4)
        self.assertTrue(all(not x["executable_by_jeeves"] for x in result["surfaces"]))
        self.assertGreater(result["domain_counts"]["forges"],0)
    def test_path_traversal_and_duplicates_fail(self):
        for p in ("../secret.py","/etc/passwd","bad\\path.py"):
            with self.assertRaises(ValueError):discover([p])
        with self.assertRaises(ValueError):discover(["a/forge.py","a/forge.py"])
    def test_tools_require_registered_adapter_and_explicit_approval(self):
        r=CapabilityRegistry()
        calls=[]
        r.register("forge_edit",lambda payload:calls.append(payload) or {"ok":True},
                   domain="forges",mutates=True)
        with self.assertRaises(PermissionError):
            r.execute("forge_edit",{"name":"x"},authorized=True,
                      approved=False,dry_run=False)
        self.assertEqual(calls,[])
        self.assertFalse(r.execute("forge_edit",{"name":"x"},authorized=True,
                                   approved=True)["executed"])
        self.assertEqual(calls,[])
        self.assertTrue(r.execute("forge_edit",{"name":"x"},authorized=True,
                                  approved=True,dry_run=False)["ok"])
        self.assertEqual(len(calls),1)
        with self.assertRaises(PermissionError):
            r.execute("not_registered",{},authorized=True,approved=True,
                      dry_run=False)

if __name__=="__main__":
    unittest.main()
