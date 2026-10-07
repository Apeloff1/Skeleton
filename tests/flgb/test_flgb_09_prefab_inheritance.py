import unittest
from skeleton.game.prefab_inheritance import CreatorContractError, PrefabDefinition, resolve_prefab_chain
D="a"*64
class TestPrefabInheritance(unittest.TestCase):
    def test_chain_orders_root_to_leaf_and_rejects_cycles(self):
        chain=resolve_prefab_chain((PrefabDefinition("root",None,(D,)),PrefabDefinition("child","root",())), "child")
        self.assertEqual([x.prefab_id for x in chain],["root","child"])
        with self.assertRaises(CreatorContractError):
            resolve_prefab_chain((PrefabDefinition("a","b",()),PrefabDefinition("b","a",())), "a")
if __name__=="__main__": unittest.main()
