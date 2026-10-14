import unittest
from skeleton.ai.forge.rival_proposer import RivalProposal
D="a"*64
class TestRivalProposer(unittest.TestCase):
    def test_proposal_binds_round_artifact_and_provenance(self):
        proposal=RivalProposal("p",3,D,D,D)
        self.assertEqual(proposal.round_index,3)
        self.assertEqual(len(proposal.digest),64)
if __name__=="__main__": unittest.main()
