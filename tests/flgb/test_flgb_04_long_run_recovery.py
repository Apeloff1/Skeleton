import unittest
from skeleton.ai.agents.checkpointing import append_checkpoint
from skeleton.ai.agents.long_run_recovery import AgentContractError, recover_from_checkpoint
D="a"*64
E="b"*64
class TestRecovery(unittest.TestCase):
    def test_recovery_advances_generation_and_binds_authority(self):
        cp=append_checkpoint((),run_id="r",state_digest=D,plan_digest=D,authority_digest=D)[0]
        receipt=recover_from_checkpoint(run_id="r",failed_generation=3,checkpoint=cp,replay_cursor=7,pending_effects_digest=E,authority_digest=D)
        self.assertEqual(receipt.recovery_generation,4)
        with self.assertRaises(AgentContractError):
            recover_from_checkpoint(run_id="r",failed_generation=3,checkpoint=cp,replay_cursor=7,pending_effects_digest=E,authority_digest=E)
if __name__=="__main__": unittest.main()
