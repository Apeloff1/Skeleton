import unittest
from skeleton.game.generation.quest_generation import GenerationContractError, QuestBeat, QuestBlueprint
D="a"*64

class TestQuestGeneration(unittest.TestCase):
    def test_dependencies_form_deterministic_waves(self):
        quest=QuestBlueprint((QuestBeat("start",(),D,D),QuestBeat("a",("start",),D,D),QuestBeat("b",("start",),D,D)))
        self.assertEqual(quest.waves,(("start",),("a","b")))
        with self.assertRaises(GenerationContractError):
            QuestBlueprint((QuestBeat("a",("b",),D,D),QuestBeat("b",("a",),D,D)))

if __name__=="__main__": unittest.main()
