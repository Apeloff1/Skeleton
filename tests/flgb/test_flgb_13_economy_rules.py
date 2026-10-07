import unittest
from skeleton.game.gameplay.economy_rules import EconomyRule, GameplayContractError
class TestEconomy(unittest.TestCase):
    def test_quote_is_integer_and_quantity_bounded(self):
        rule=EconomyRule("shop","potion","gold",25,5)
        self.assertEqual(rule.quote(4),100)
        with self.assertRaises(GameplayContractError): rule.quote(6)
if __name__=="__main__": unittest.main()
