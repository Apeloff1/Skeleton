"""Real CPU-native initialized model checkpoint and exact train-only vocabulary."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.policy import SupervisedPolicy
from skeleton.ai.runtime.operational_ai.native_supervised.bootstrap import initialize_aligned_model
from skeleton.ai.runtime.operational_ai.native_supervised.model_smoke import native_smoke
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime


class TestNativeSFTBootstrap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance=initialize_aligned_model(SupervisedPolicy(
            operator_approved=True,dimension=8,heads=2,context=128,
            feed_forward=0,layers=1,
        ))

    def test_real_native_runtime(self):
        self.assertIsInstance(self.instance.runtime,NativeLLMRuntime)
        self.assertEqual(self.instance.runtime.model.dim,8)
        self.assertEqual(self.instance.runtime.model.ctx,128)

    def test_no_weights_generated_from_evaluation(self):
        self.assertEqual(self.instance.vocabulary.observed_documents,432)
        self.assertEqual(self.instance.source.holdout_count,72)
        self.assertFalse(self.instance.vocabulary.record()["fit_challenges"])

    def test_seed_weights_start_untrained(self):
        self.assertEqual(self.instance.runtime.model.steps,0)
        self.assertEqual(self.instance.report()["trained_sgd_steps"],0)
        self.assertFalse(self.instance.report()["production_authorized"])

    def test_checkpoint_restores_same_identity(self):
        native=NativeLLMRuntime.restore_json(
            self.instance.initial_checkpoint.decode("utf-8")
        )
        self.assertEqual(native.model_digest,self.instance.runtime.model_digest)
        self.assertEqual(native.tokenizer.digest,self.instance.runtime.tokenizer.digest)

    def test_actual_native_chat_smoke(self):
        value=native_smoke(
            self.instance.runtime,
            expected_model_sha256=self.instance.runtime.model_digest,
        )
        self.assertEqual(value["generated_tokens"],2)
        self.assertTrue(value["actual_native_graph_executed"])
        self.assertFalse(value["answer_correctness_proven"])

    def test_model_identity_unchanged_by_smoke(self):
        self.instance.runtime.assert_model_unchanged()


if __name__=="__main__":
    unittest.main()
