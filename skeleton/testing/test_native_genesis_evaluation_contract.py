"""Independent evaluation is real, model-bound, and never training-data scoring."""
from __future__ import annotations
from pathlib import Path
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.evaluation_bridge import evaluate_pair
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected
from skeleton.ai.runtime.operational_ai.native_genesis.source import verify_source


class TestNativeGenesisEvaluationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=verify_source()

    def _args(self):
        return {
            "champion_directory":Path("/nonexistent_original_champion"),
            "champion_checkpoint_sha256":"a"*64,
            "champion_model_sha256":"b"*64,
            "candidate_directory":Path("/nonexistent_original_candidate"),
            "candidate_checkpoint_sha256":"c"*64,
            "candidate_model_sha256":"d"*64,
        }

    def test_training_partition_cannot_be_included_in_evaluation(self):
        with self.assertRaises(GenesisRejected):
            evaluate_pair(self.source,partition="train",**self._args())

    def test_same_model_is_not_candidate_improvement(self):
        args=self._args()
        args["candidate_model_sha256"]=args["champion_model_sha256"]
        with self.assertRaises(GenesisRejected):
            evaluate_pair(self.source,partition="validation",**args)

    def test_invalid_model_digest_rejected_pre_io(self):
        args=self._args()
        args["candidate_model_sha256"]="fake"
        with self.assertRaises(GenesisRejected):
            evaluate_pair(self.source,partition="holdout",**args)

    def test_missing_checkpoint_is_not_scored_success(self):
        with self.assertRaises((GenesisRejected,OSError,ValueError)):
            evaluate_pair(self.source,partition="validation",**self._args())


if __name__=="__main__":
    unittest.main()
