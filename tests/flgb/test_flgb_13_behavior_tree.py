import unittest
from skeleton.game.gameplay.behavior_tree import BehaviorNode, BehaviorTree, GameplayContractError
class TestBehaviorTree(unittest.TestCase):
    def test_tree_is_connected_and_single_parented(self):
        tree=BehaviorTree((BehaviorNode("root","sequence",("cond","act")),BehaviorNode("cond","condition"),BehaviorNode("act","action")),"root")
        self.assertEqual(tree.root_id,"root")
        with self.assertRaises(GameplayContractError):
            BehaviorTree((BehaviorNode("root","sequence",("act",)),BehaviorNode("act","action"),BehaviorNode("orphan","action")),"root")
if __name__=="__main__": unittest.main()
