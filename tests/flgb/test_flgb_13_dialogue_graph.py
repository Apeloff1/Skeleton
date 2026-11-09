import unittest
from skeleton.game.gameplay.dialogue_graph import DialogueChoice, DialogueNode, GameplayContractError, validate_dialogue
D="a"*64
class T(unittest.TestCase):
 def test_targets_exist(self):
  validate_dialogue((DialogueNode("a",D,(DialogueChoice("go","b"),)),DialogueNode("b",D,())))
  with self.assertRaises(GameplayContractError): validate_dialogue((DialogueNode("a",D,(DialogueChoice("go","x"),)),))
if __name__=="__main__": unittest.main()
