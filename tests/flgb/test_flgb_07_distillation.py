import unittest
from skeleton.ai.training.distillation import DistillationRun, TrainingContractError
D="a"*64

class TestDistillation(unittest.TestCase):
    def test_distillation_is_candidate_only(self):
        run=DistillationRun("r",D,D,D,D)
        self.assertEqual(run.output_kind,"candidate-only")
        with self.assertRaises(TrainingContractError):
            DistillationRun("r",D,D,D,D,"production")

if __name__=="__main__": unittest.main()
