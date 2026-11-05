"""A small actual CPU gradient changes weights; never claims full-corpus training."""
from __future__ import annotations
import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime


class TestActualNativeGradientPrimitive(unittest.TestCase):
    def test_gradient_modifies_a_separate_model(self):
        model=TinyTransformer(
            vocab=("alpha","beta","gamma","delta"),
            dim=8,ctx=16,seed=3,n_heads=2,n_layers=1,d_ff=0,
        )
        champion=NativeLLMRuntime(model)
        digest_before=champion.model_digest
        candidate=NativeLLMRuntime.restore_json(champion.checkpoint_json())
        steps=candidate.model.fit(("alpha beta gamma delta",),lr=0.01)
        self.assertGreater(steps,0)
        result=NativeLLMRuntime(candidate.model)
        self.assertNotEqual(result.model_digest,digest_before)
        champion.assert_model_unchanged()
        self.assertEqual(champion.model_digest,digest_before)

    def test_same_seed_base_weights_are_deterministic(self):
        args={"vocab":("alpha","beta","gamma"),"dim":8,
              "ctx":16,"seed":99,"n_heads":2,"n_layers":1,"d_ff":0}
        a=NativeLLMRuntime(TinyTransformer(**args))
        b=NativeLLMRuntime(TinyTransformer(**args))
        self.assertEqual(a.model_digest,b.model_digest)
        self.assertEqual(a.tokenizer.digest,b.tokenizer.digest)

    def test_random_initialization_not_trained_per_se(self):
        model=TinyTransformer(vocab=("alpha","beta"),
                              dim=8,ctx=16,seed=17,n_heads=2,d_ff=0)
        result=NativeLLMRuntime(model)
        self.assertEqual(model.steps,0)
        self.assertEqual(model.fitted,0)
        self.assertTrue(result.model_digest)


if __name__=="__main__":
    unittest.main()
