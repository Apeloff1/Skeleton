import unittest
from skeleton.game.simulation.character_controller import CharacterController

class TestCharacterController(unittest.TestCase):
    def test_velocity_is_clamped_per_axis(self):
        controller=CharacterController("player",100,20,True)
        self.assertEqual(controller.clamp_velocity(200,-150,50),(100,-100,50))

if __name__=="__main__": unittest.main()
