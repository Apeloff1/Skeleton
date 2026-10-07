import unittest
from skeleton.game.simulation.constraints import DistanceConstraint

class TestConstraints(unittest.TestCase):
    def test_distance_tolerance_uses_integer_squared_distance(self):
        constraint=DistanceConstraint("rope","a","b",10,1)
        self.assertTrue(constraint.satisfied((0,0,0),(10,0,0)))
        self.assertTrue(constraint.satisfied((0,0,0),(9,0,0)))
        self.assertFalse(constraint.satisfied((0,0,0),(12,0,0)))

if __name__=="__main__": unittest.main()
