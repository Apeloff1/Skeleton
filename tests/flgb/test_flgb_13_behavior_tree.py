import unittest
from skeleton.game.gameplay.behavior_tree import BehaviorNode, GameplayContractError, validate_behavior_tree
class T(unittest.TestCase):
 def test_cycle_fails(self):
  validate_behavior_tree((BehaviorNode("r","sequence",("a",)),BehaviorNode("a","action",())),"r")
  with self.assertRaises(GameplayContractError):
   validate_behavior_tree((BehaviorNode("a","sequence",("b",)),BehaviorNode("b","selector",("a",))),"a")
if __name__=="__main__": unittest.main()
