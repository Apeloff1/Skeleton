import unittest
from skeleton.game.gameplay.combat_logic import CombatAction, GameplayContractError
class TestCombat(unittest.TestCase):
    def test_damage_and_stamina_are_bounded(self):
        action=CombatAction("hit",30,10,2)
        self.assertEqual(action.resolve(20,15),(0,5))
        with self.assertRaises(GameplayContractError): action.resolve(100,9)
if __name__=="__main__": unittest.main()
