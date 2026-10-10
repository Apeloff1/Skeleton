import unittest
from skeleton.game.gameplay.quest_graph import GameplayContractError, QuestNode, quest_order
D="a"*64
class T(unittest.TestCase):
 def test_order_and_cycle(self):
  self.assertEqual(quest_order((QuestNode("b",("a",),D),QuestNode("a",(),D))),("a","b"))
  with self.assertRaises(GameplayContractError): quest_order((QuestNode("a",("b",),D),QuestNode("b",("a",),D)))
if __name__=="__main__": unittest.main()
