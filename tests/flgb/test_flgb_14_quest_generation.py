import unittest
from skeleton.game.generation.quest_generation import GeneratedQuest, GenerationContractError, QuestNode
D="a"*64
class TestQuestGeneration(unittest.TestCase):
    def test_prerequisites_form_dag(self):
        quest=GeneratedQuest("q",(QuestNode("start","start"),QuestNode("end","finish",("start",),D)),D)
        self.assertEqual(len(quest.digest),64)
        with self.assertRaises(GenerationContractError):
            GeneratedQuest("bad",(QuestNode("a","x",("b",)),QuestNode("b","x",("a",))),D)
if __name__=="__main__": unittest.main()
