import unittest
from skeleton.game.generation.layout_grammar import GrammarRule, LayoutGrammar
D="a"*64
E="b"*64

class TestLayoutGrammar(unittest.TestCase):
    def test_seeded_rule_choice_is_deterministic(self):
        grammar=LayoutGrammar((GrammarRule("a","room",D,1),GrammarRule("b","room",E,3)))
        first=grammar.choose("room",D)
        self.assertEqual(first,grammar.choose("room",D))
        self.assertIn(first.rule_id,{"a","b"})

if __name__=="__main__": unittest.main()
