import unittest
from skeleton.ai.agents.authority_subset import AuthorityGrant
from skeleton.ai.agents.checkpointing import append_checkpoint
from skeleton.ai.agents.handoff import authorize_handoff
D="a"*64
class TestHandoff(unittest.TestCase):
    def test_handoff_binds_delegated_authority_and_checkpoint(self):
        parent=AuthorityGrant("supervisor",("read","write"))
        child=parent.delegate("worker",("read",))
        cp=append_checkpoint((),run_id="r",state_digest=D,plan_digest=D,authority_digest=parent.digest)[0]
        receipt=authorize_handoff(handoff_id="h",from_worker="s",to_worker="w",scope_digest=D,parent_authority=parent,child_authority=child,checkpoint=cp)
        self.assertEqual(receipt.to_authority_digest,child.digest)
if __name__=="__main__": unittest.main()
