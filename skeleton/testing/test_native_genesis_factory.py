"""Real TinyTransformer initialization, byte checkpoint roundtrip and no SGD."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.factory import initialize_native
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime


class TestActualNativeFactory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=GenesisPolicy(
            operator_approved=True,dim=8,n_heads=2,ctx=64,d_ff=0,n_layers=1
        )
        cls.instance=initialize_native(cls.policy)

    def test_actual_runtime_not_echo(self):
        self.assertIsInstance(self.instance.runtime,NativeLLMRuntime)
        self.assertEqual(self.instance.runtime.model.dim,8)
        self.assertEqual(self.instance.runtime.model.n_layers,1)
        self.assertEqual(self.instance.runtime.device.actual,"cpu")

    def test_tokenizer_source_is_fixed(self):
        self.assertEqual(len(self.instance.vocabulary.entries)+1,
                         len(self.instance.runtime.model.itos))

    def test_checkpoint_is_real_json_bytes(self):
        self.assertTrue(self.instance.checkpoint.startswith(b"{"))
        self.assertEqual(len(self.instance.checkpoint_sha256),64)
        self.assertGreater(len(self.instance.checkpoint),100)

    def test_checkpoint_roundtrip_matches_model(self):
        restored=NativeLLMRuntime.restore_json(self.instance.checkpoint.decode("utf-8"))
        self.assertEqual(restored.model_digest,self.instance.runtime.model_digest)
        self.assertEqual(restored.tokenizer.digest,self.instance.runtime.tokenizer.digest)

    def test_untrained_weights_are_not_released(self):
        record=self.instance.report()
        self.assertEqual(record["actual_sgd_steps"],0)
        self.assertFalse(record["weights_trained"])
        self.assertFalse(record["automatically_served"])
        self.assertFalse(record["model_quality_verified"])
        self.assertFalse(record["release_certified"])

    def test_source_custody_still_held(self):
        self.assertEqual(len(self.instance.source.partitions.train),432)
        self.assertEqual(len(self.instance.source.partitions.holdout),72)


if __name__=="__main__":
    unittest.main()
