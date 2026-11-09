import unittest
from skeleton.ai.training.checkpoint_lineage import TrainingCheckpoint
D="a"*64
E="b"*64

class TestCheckpointLineage(unittest.TestCase):
    def test_checkpoint_chain_binds_rng_optimizer_and_weights(self):
        base=TrainingCheckpoint(D,0,D,D,D)
        nxt=base.next(E,D,E)
        self.assertEqual(nxt.sequence,1)
        self.assertEqual(nxt.prior_checkpoint_digest,base.digest)

if __name__=="__main__": unittest.main()
