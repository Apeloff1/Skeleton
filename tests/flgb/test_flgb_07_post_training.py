import unittest
from skeleton.ai.training.post_training import PreferenceDataset, PostTrainingCandidate, PostTrainingRun

D="a"*64
E="b"*64

class TestPostTraining(unittest.TestCase):
    def test_existing_post_training_owner_never_self_authorizes(self):
        dataset=PreferenceDataset("DATA",D,E)
        run=PostTrainingRun("RUN",D,dataset,E,"DPO",D)
        candidate=PostTrainingCandidate("CAND",run.lineage_digest,E,D)
        self.assertTrue(candidate.experimentally_qualified)
        self.assertFalse(candidate.production_authorized())

if __name__=="__main__": unittest.main()
