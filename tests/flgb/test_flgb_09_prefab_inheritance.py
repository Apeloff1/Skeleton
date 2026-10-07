import unittest
from skeleton.game.prefab_inheritance import GameProjectError, PrefabSpec, validate_prefabs
D="a"*64
E="b"*64

class TestPrefabInheritance(unittest.TestCase):
    def test_prefab_inheritance_is_acyclic(self):
        prefabs=(PrefabSpec("base",None,(D,)),PrefabSpec("child","base",(E,)))
        self.assertEqual([p.prefab_id for p in validate_prefabs(prefabs)],["base","child"])
        with self.assertRaises(GameProjectError):
            validate_prefabs((PrefabSpec("a","b",()),PrefabSpec("b","a",())))

if __name__=="__main__": unittest.main()
