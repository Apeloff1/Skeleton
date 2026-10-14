import unittest
from skeleton.ai.training.candidate_weights import CandidateWeights
D="a"*64

class TestCandidateWeights(unittest.TestCase):
    def test_candidate_object_never_grants_production_authority(self):
        candidate=CandidateWeights("c",D,D,D,"promoted")
        self.assertFalse(candidate.production_authorized())
        self.assertEqual(len(candidate.digest),64)

if __name__=="__main__": unittest.main()
