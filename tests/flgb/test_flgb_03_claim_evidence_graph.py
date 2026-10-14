import unittest
from skeleton.ai.context.claim_evidence_graph import Claim, ClaimEvidenceGraph, ContextContractError, EvidenceLink
D="a"*64
class TestClaimEvidence(unittest.TestCase):
    def test_orphans_fail_closed(self):
        graph=ClaimEvidenceGraph((Claim("c",D,D),),(EvidenceLink("e","c",D,"supports",900000),))
        self.assertEqual(graph.evidence_for("c")[0].relation,"supports")
        with self.assertRaises(ContextContractError):
            ClaimEvidenceGraph((),(EvidenceLink("e","missing",D,"supports",1),))
if __name__=="__main__": unittest.main()
