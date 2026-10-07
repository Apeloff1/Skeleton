import unittest
from skeleton.game.generation.layout_grammar import GenerationContractError, LayoutGrammar, LayoutRule
from skeleton.game.generation.seed_contract import SeedContract
D="a"*64
class TestLayoutGrammar(unittest.TestCase):
    def test_expansion_is_seed_deterministic_and_bounded(self):
        grammar=LayoutGrammar((LayoutRule("a","room",("hall","room"),1),LayoutRule("b","room",("arena",),1)))
        seed=SeedContract("p","layout","v1",9,D)
        self.assertEqual(grammar.expand("room",seed,3),grammar.expand("room",seed,3))
        with self.assertRaises(GenerationContractError):
            grammar.expand("room",seed,65)
if __name__=="__main__": unittest.main()
