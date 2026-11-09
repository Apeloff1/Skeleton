import unittest
from skeleton.ai.training.adapter_training import AdapterTrainingRun, TrainingContractError
D="a"*64

class TestAdapterTraining(unittest.TestCase):
    def test_adapter_target_modules_are_explicit_and_unique(self):
        run=AdapterTrainingRun("r",D,D,("q_proj","v_proj"),D)
        self.assertEqual(run.target_modules,("q_proj","v_proj"))
        with self.assertRaises(TrainingContractError):
            AdapterTrainingRun("r",D,D,("q_proj","q_proj"),D)

if __name__=="__main__": unittest.main()
