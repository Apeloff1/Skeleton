import unittest
from skeleton.game.generation.character_generation import CharacterTemplate, GenerationContractError, generate_character
from skeleton.game.generation.seed_contract import SeedContract
D="a"*64
class TestCharacterGeneration(unittest.TestCase):
    def test_required_traits_are_preserved(self):
        template=CharacterTemplate("guard",("loyal","brave","calm"),("loyal",))
        seed=SeedContract("p","char","v1",4,D)
        traits=generate_character(template,seed,1)
        self.assertIn("loyal",traits)
        self.assertEqual(traits,generate_character(template,seed,1))
        with self.assertRaises(GenerationContractError):
            CharacterTemplate("bad",("a",),("missing",))
if __name__=="__main__": unittest.main()
