import unittest
from skeleton.game.generation.character_generation import CharacterProfile, GenerationContractError
D="a"*64

class TestCharacterGeneration(unittest.TestCase):
    def test_traits_are_unique_and_canonical(self):
        profile=CharacterProfile("c","merchant",D,D,("kind","clever"))
        self.assertEqual(profile.trait_ids,("clever","kind"))
        with self.assertRaises(GenerationContractError):
            CharacterProfile("c","merchant",D,D,("kind","kind"))

if __name__=="__main__": unittest.main()
