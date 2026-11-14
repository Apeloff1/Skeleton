"""Actual single response token SGD modifies cloned weights with bounded receipts."""
from __future__ import annotations
from time import monotonic_ns
import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.runtime.operational_ai.native_supervised.optimizer import execute_epoch
from skeleton.ai.runtime.operational_ai.native_supervised.token_windows import TargetWindow
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestNativeCompletionOptimizer(unittest.TestCase):
    def test_real_sgd_changes_only_candidate(self):
        champion=NativeLLMRuntime(TinyTransformer(
            vocab=("hello","world","answer","yes"),
            dim=8,ctx=32,seed=17,n_heads=2,d_ff=0,
        ))
        starting=champion.model_digest
        candidate=NativeLLMRuntime.restore_json(champion.checkpoint_json())
        prompt=tuple(candidate.model._ids("hello world"))
        answer=candidate.model._id("yes")
        rows=(TargetWindow(prompt,answer,"source_01",0),)
        receipt=execute_epoch(
            candidate.model,rows,epoch=0,total_epochs=1,
            global_step_start=0,total_steps=1,learning_rate_ppm=10000,
            max_wall_ms=120000,start_monotonic_ns=monotonic_ns(),batch_size=1,
        )
        self.assertEqual(receipt.steps,1)
        self.assertTrue(receipt.weights_changed)
        self.assertNotEqual(NativeLLMRuntime(candidate.model).model_digest,starting)
        champion.assert_model_unchanged()
        self.assertEqual(champion.model_digest,starting)

    def test_out_of_range_optimizers_are_rejected(self):
        model=TinyTransformer(vocab=("a","b"),dim=8,ctx=32,seed=1,d_ff=0)
        windows=(TargetWindow((1,),1,"source_01",0),)
        with self.assertRaises(SupervisedRejected):
            execute_epoch(model,windows,epoch=0,total_epochs=1,
                          global_step_start=1,total_steps=1,
                          learning_rate_ppm=1000,max_wall_ms=1000,
                          start_monotonic_ns=monotonic_ns(),batch_size=1)

    def test_no_empty_batch_ever_claims_steps(self):
        model=TinyTransformer(vocab=("a","b"),dim=8,ctx=32,seed=1,d_ff=0)
        with self.assertRaises(SupervisedRejected):
            execute_epoch(model,(),epoch=0,total_epochs=1,
                          global_step_start=0,total_steps=1,
                          learning_rate_ppm=1000,max_wall_ms=1000,
                          start_monotonic_ns=monotonic_ns(),batch_size=1)


if __name__=="__main__":
    unittest.main()
