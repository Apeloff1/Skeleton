import unittest
from skeleton.game.simulation.character_controller import CharacterController, SimulationContractError

class TestCharacterController(unittest.TestCase):
    def test_speed_budget_is_enforced(self):
        c=CharacterController("e",(0,0,0),100,True)
        self.assertEqual(c.move((50,0,0),500000000).position,(50,0,0))
        with self.assertRaises(SimulationContractError): c.move((51,0,0),500000000)

if __name__=="__main__": unittest.main()
