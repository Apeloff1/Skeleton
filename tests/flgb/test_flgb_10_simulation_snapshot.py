import unittest
from skeleton.game.simulation.simulation_snapshot import SimulationSnapshot
D="a"*64
E="b"*64

class TestSimulationSnapshot(unittest.TestCase):
    def test_snapshot_binds_tick_and_state_surfaces(self):
        a=SimulationSnapshot(1,D,D,D,D)
        b=SimulationSnapshot(2,D,D,D,E)
        self.assertNotEqual(a.digest,b.digest)

if __name__=="__main__": unittest.main()
