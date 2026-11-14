"""Cross entropy uses actual native logits for completion targets, not mock scores."""
from __future__ import annotations
import math
import unittest
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.runtime.operational_ai.native_supervised.loss import (
    _target_nll,measure_windows,
)
from skeleton.ai.runtime.operational_ai.native_supervised.token_windows import TargetWindow
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestActualCompletionLoss(unittest.TestCase):
    def test_simple_softmax_cross_entropy(self):
        value=_target_nll([0.0,0.0],1)
        self.assertAlmostEqual(value,math.log(2),places=10)

    def test_numerically_stable_large_logits(self):
        value=_target_nll([10000.0,10000.0],0)
        self.assertAlmostEqual(value,math.log(2),places=10)

    def test_nan_and_infinity_refused(self):
        for values in ([0.0,float("nan")],
                       [float("inf"),1.0],[]):
            with self.assertRaises(SupervisedRejected):
                _target_nll(values,0)

    def test_invalid_target_index_refused(self):
        with self.assertRaises(SupervisedRejected):
            _target_nll([0.0,0.0],2)

    def test_loss_is_calculated_from_real_model(self):
        model=TinyTransformer(
            vocab=("hello","world","again"),dim=8,ctx=16,seed=4,d_ff=0,
        )
        prompt=tuple(model._ids("hello world"))
        windows=(TargetWindow(prompt,model._id("again"),"test_01",0),)
        report=measure_windows(model,windows)
        self.assertEqual(report.targets,1)
        self.assertGreater(report.mean_nats,0)
        self.assertGreater(report.perplexity,1)
        self.assertTrue(report.report()["uses_actual_logits"])

    def test_empty_windows_are_not_zero_loss_pass(self):
        model=TinyTransformer(vocab=("a","b"),dim=8,ctx=16,seed=0,d_ff=0)
        with self.assertRaises(SupervisedRejected):
            measure_windows(model,())


if __name__=="__main__":
    unittest.main()
