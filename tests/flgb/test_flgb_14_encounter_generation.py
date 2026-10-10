import unittest
from skeleton.game.generation.encounter_generation import EncounterCandidate, select_encounters
D="a"*64

class TestEncounterGeneration(unittest.TestCase):
    def test_budget_and_target_difficulty_drive_selection(self):
        candidates=(EncounterCandidate("easy",3,100000,D),EncounterCandidate("target",6,500000,D),EncounterCandidate("hard",5,900000,D))
        self.assertEqual(select_encounters(candidates,8,500000),("target",))

if __name__=="__main__": unittest.main()
