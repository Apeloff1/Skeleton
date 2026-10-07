import unittest
from skeleton.game.gameplay.quest_graph import GameplayContractError, QuestGraph, QuestNode
D="a"*64
class TestQuestGraph(unittest.TestCase):
    def test_dependencies_are_acyclic(self):
        g=QuestGraph((QuestNode("start",(),D),QuestNode("finish",("start",),D)))
        self.assertEqual(g.order,("start","finish"))
        with self.assertRaises(GameplayContractError):
            QuestGraph((QuestNode("a",("b",),D),QuestNode("b",("a",),D)))
if __name__=="__main__": unittest.main()
