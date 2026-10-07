import unittest
from skeleton.ai.agents.multi_agent_arbitration import AgentContractError, ArbitrationProposal, arbitrate
D="a"*64
class TestArbitration(unittest.TestCase):
    def test_quality_never_overrides_risk_gate(self):
        risky=ArbitrationProposal("r","a",D,1000000,900000,D)
        safe=ArbitrationProposal("s","b",D,700000,100000,D)
        decision=arbitrate((risky,safe),verifier_digest=D,maximum_risk_ppm=500000)
        self.assertEqual(decision.winner_proposal_id,"s")
        with self.assertRaises(AgentContractError):
            arbitrate((risky,safe),verifier_digest=D,maximum_risk_ppm=50000)
if __name__=="__main__": unittest.main()
