import unittest
from skeleton.game.simulation.rollback_simulation import RollbackBuffer, SimulationContractError
from skeleton.game.simulation.simulation_snapshot import SimulationSnapshot
D="a"*64
E="b"*64
F="c"*64

class TestRollbackSimulation(unittest.TestCase):
    def test_restore_is_exact_tick_and_chain_checked(self):
        s0=SimulationSnapshot(0,D,D,D,D)
        s1=SimulationSnapshot(1,E,E,E,E,s0.digest)
        s2=SimulationSnapshot(2,F,F,F,F,s1.digest)
        buffer=RollbackBuffer((s0,s1),3).append(s2)
        self.assertEqual(buffer.restore(1).state_digest,E)
        with self.assertRaises(SimulationContractError):
            buffer.restore(9)

if __name__=="__main__": unittest.main()
