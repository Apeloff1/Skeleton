import unittest
from skeleton.game.simulation.fixed_timestep import FixedTimestep

class TestFixedTimestep(unittest.TestCase):
    def test_advance_is_bounded_and_carries_remainder(self):
        step=FixedTimestep(10000,3)
        self.assertEqual(step.advance(0,25000),(2,5000))
        self.assertEqual(step.advance(0,99000),(3,69000))

if __name__=="__main__": unittest.main()
