import unittest
from skeleton.game.simulation.simulation_snapshot import SimulationContractError, SimulationSnapshot
D="a"*64
E="b"*64

class TestSimulationSnapshot(unittest.TestCase):
    def test_snapshot_parent_is_required_after_genesis(self):
        genesis=SimulationSnapshot(0,D,D,D,D)
        nxt=SimulationSnapshot(1,E,D,E,D,genesis.digest)
        self.assertEqual(nxt.prior_snapshot_digest,genesis.digest)
        with self.assertRaises(SimulationContractError):
            SimulationSnapshot(1,E,D,E,D)

if __name__=="__main__": unittest.main()
