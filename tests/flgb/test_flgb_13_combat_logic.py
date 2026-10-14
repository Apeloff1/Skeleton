import unittest
from skeleton.game.gameplay.combat_logic import CombatRule, order_combat_rules
D="a"*64
class T(unittest.TestCase):
 def test_priority(self):
  rules=(CombatRule("low",1,D,D),CombatRule("high",10,D,D))
  self.assertEqual([r.rule_id for r in order_combat_rules(rules)],["high","low"])
if __name__=="__main__": unittest.main()
