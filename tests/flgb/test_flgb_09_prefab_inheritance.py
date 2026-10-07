import unittest
from skeleton.game.prefab_inheritance import GameContractError, PrefabDefinition, resolve_prefab_chain
D="a"*64
E="b"*64
F="c"*64

class TestPrefabInheritance(unittest.TestCase):
    def test_child_overrides_parent_and_digest_chain_is_exact(self):
        root=PrefabDefinition("root",0,None,{"transform":D,"render":E})
        child=PrefabDefinition("child",0,root.digest,{"render":F})
        resolved=resolve_prefab_chain((root,child))
        self.assertEqual(resolved["transform"],D)
        self.assertEqual(resolved["render"],F)
        with self.assertRaises(GameContractError):
            resolve_prefab_chain((child,root))

if __name__=="__main__": unittest.main()
