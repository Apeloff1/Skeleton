import unittest
from skeleton.game.simulation.fixed_timestep import FixedTimestep

class TestFixedTimestep(unittest.TestCase):
    def test_catchup_is_bounded_and_remainder_preserved(self):
        clock=FixedTimestep(10,3)
        self.assertEqual(clock.consume(0,25),(2,5))
        self.assertEqual(clock.consume(0,100),(3,70))

if __name__=="__main__": unittest.main()
