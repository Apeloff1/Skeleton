import unittest
from skeleton.game.generation.encounter_generation import EncounterTemplate, GenerationContractError, generate_encounters
from skeleton.game.generation.seed_contract import SeedContract
D="a"*64
class TestEncounterGeneration(unittest.TestCase):
    def test_threat_budget_never_exceeded(self):
        seed=SeedContract("p","enc","v1",1,D)
        templates=(EncounterTemplate("a",4,("grunt",),()),EncounterTemplate("b",7,("boss",),()),EncounterTemplate("c",3,("grunt",),()))
        selected=generate_encounters(templates,7,seed)
        costs={t.encounter_id:t.threat_cost for t in templates}
        self.assertLessEqual(sum(costs[x] for x in selected),7)
        with self.assertRaises(GenerationContractError):
            generate_encounters((templates[0],templates[0]),10,seed)
if __name__=="__main__": unittest.main()
