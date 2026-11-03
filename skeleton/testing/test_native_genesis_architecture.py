"""Parameter estimate precedes allocation and never claims actual peak RSS."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy
from skeleton.ai.runtime.operational_ai.native_genesis.source import verify_source
from skeleton.ai.runtime.operational_ai.native_genesis.vocabulary import build_vocabulary
from skeleton.ai.runtime.operational_ai.native_genesis.architecture import estimate
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestArchitectureAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=GenesisPolicy(operator_approved=True)
        cls.vocab=build_vocabulary(verify_source(),cls.policy)

    def test_estimate_is_finite_positive_integer(self):
        result=estimate(self.policy,self.vocab)
        self.assertGreater(result.parameters,0)
        self.assertGreater(result.weight_bytes,0)
        self.assertGreater(result.expanded_memory_bytes,result.weight_bytes)
        self.assertFalse(result.report()["actual_peak_rss_measured"])

    def test_vocab_contains_native_unk_slot(self):
        result=estimate(self.policy,self.vocab)
        self.assertEqual(result.vocab_size,len(self.vocab.entries)+1)

    def test_extreme_architecture_refused_before_allocate(self):
        big=replace(self.policy,dim=256,n_heads=16,n_layers=12,d_ff=4096,
                    maximum_model_bytes=1048576)
        with self.assertRaises(GenesisRejected):
            estimate(big,self.vocab)

    def test_increase_layers_increases_parameters(self):
        low=estimate(replace(self.policy,n_layers=1),self.vocab)
        high=estimate(replace(self.policy,n_layers=2),self.vocab)
        self.assertGreater(high.parameters,low.parameters)

    def test_swiglu_weights_accounted(self):
        result=estimate(replace(self.policy,ffn_kind="swiglu"),self.vocab)
        self.assertGreater(result.parameters,0)
        self.assertFalse(result.report()["gpu_admitted"])


if __name__=="__main__":
    unittest.main()
