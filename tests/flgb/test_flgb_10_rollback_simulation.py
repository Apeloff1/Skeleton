import unittest
from skeleton.game.simulation.rollback_simulation import RollbackBuffer, RollbackReplayReceipt, SimulationContractError
from skeleton.game.simulation.simulation_snapshot import SimulationSnapshot
D="a"*64
E="b"*64

class TestRollback(unittest.TestCase):
    def test_buffer_is_bounded_and_restore_is_exact(self):
        buf=RollbackBuffer(max_snapshots=2)
        buf=buf.append(SimulationSnapshot(1,D,D,D,D))
        buf=buf.append(SimulationSnapshot(2,E,D,D,D))
        buf=buf.append(SimulationSnapshot(3,D,D,D,E))
        self.assertEqual([s.tick for s in buf.snapshots],[2,3])
        self.assertEqual(buf.restore(2).state_digest,E)
        with self.assertRaises(SimulationContractError): buf.restore(1)
        receipt=RollbackReplayReceipt(buf.restore(2).digest,3,D,E)
        self.assertEqual(len(receipt.digest),64)

if __name__=="__main__": unittest.main()
