import unittest
from skeleton.ai.agents.checkpointing import append_checkpoint
D="a"*64
E="b"*64
class TestCheckpointing(unittest.TestCase):
    def test_checkpoint_chain(self):
        cps=append_checkpoint((),run_id="r",state_digest=D,plan_digest=D,authority_digest=D)
        cps=append_checkpoint(cps,run_id="r",state_digest=E,plan_digest=D,authority_digest=D)
        self.assertEqual(cps[1].prior_checkpoint_digest,cps[0].digest)
if __name__=="__main__": unittest.main()
