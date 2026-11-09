import unittest
from skeleton.game.simulation.constraints import Constraint, SimulationContractError

class TestConstraints(unittest.TestCase):
    def test_constraint_body_identity_is_validated(self):
        self.assertEqual(Constraint("c","distance","a","b",10).kind,"distance")
        with self.assertRaises(SimulationContractError):
            Constraint("c","distance","a","a",10)

if __name__=="__main__": unittest.main()
