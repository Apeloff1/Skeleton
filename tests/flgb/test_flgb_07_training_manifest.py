import unittest
from skeleton.ai.training.training_manifest import TrainingContractError, TrainingManifest
D="a"*64
E="b"*64

class TestTrainingManifest(unittest.TestCase):
    def test_training_output_is_candidate_only(self):
        manifest=TrainingManifest("r",D,(D,E),D,D,D,100)
        self.assertEqual(manifest.output_kind,"candidate-only")
        with self.assertRaises(TrainingContractError):
            TrainingManifest("r",D,(D,),D,D,D,100,"production")

if __name__=="__main__": unittest.main()
