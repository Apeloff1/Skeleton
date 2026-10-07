import unittest
from skeleton.game.simulation.deterministic_simulation import DeterministicSimulationLog, SimulationContractError, SimulationFrame
D="a"*64
E="b"*64
F="c"*64

class TestDeterministicSimulation(unittest.TestCase):
    def test_state_chain_and_tick_identity_are_strict(self):
        log=DeterministicSimulationLog().append(D,E,F).append(E,F,D)
        self.assertEqual([frame.tick for frame in log.frames],[0,1])
        self.assertEqual(log.frames[1].state_digest_before,E)
        with self.assertRaises(SimulationContractError):
            DeterministicSimulationLog((SimulationFrame(1,D,D,E,F),))

if __name__=="__main__": unittest.main()
