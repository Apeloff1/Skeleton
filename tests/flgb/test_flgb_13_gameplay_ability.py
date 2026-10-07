import unittest
from skeleton.game.gameplay.gameplay_ability import GameplayAbility, GameplayContractError
class TestAbility(unittest.TestCase):
    def test_resource_and_cooldown_gate(self):
        ability=GameplayAbility("dash",10,5,("mobility",))
        self.assertTrue(ability.can_activate(10,None,0))
        self.assertFalse(ability.can_activate(9,None,0))
        self.assertFalse(ability.can_activate(10,8,10))
        self.assertTrue(ability.can_activate(10,5,10))
        with self.assertRaises(GameplayContractError): ability.can_activate(10,11,10)
if __name__=="__main__": unittest.main()
