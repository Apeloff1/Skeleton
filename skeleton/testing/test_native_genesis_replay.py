"""Same-process deterministic weight initialization replay, not GPU proof."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy
from skeleton.ai.runtime.operational_ai.native_genesis.factory import initialize_native
from skeleton.ai.runtime.operational_ai.native_genesis.replay import compare_initialized
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestGenesisReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.genesis=initialize_native(GenesisPolicy(
            operator_approved=True,dim=8,n_heads=2,ctx=64,d_ff=0
        ))

    def test_claim_only_is_not_weight_replay(self):
        record=compare_initialized(
            self.genesis,expected_checkpoint_sha256=self.genesis.checkpoint_sha256
        )
        self.assertTrue(record["source_verified"])
        self.assertFalse(record["checkpoint_recomputation"])
        self.assertIsNone(record["weights_reproducible"])

    def test_explicit_real_weight_recomputation(self):
        record=compare_initialized(
            self.genesis,expected_checkpoint_sha256=self.genesis.checkpoint_sha256,
            allow_recompute=True,
        )
        self.assertTrue(record["checkpoint_recomputation"])
        self.assertTrue(record["weights_reproducible"])
        self.assertFalse(record["release_certified"])

    def test_wrong_checkpoint_sha_blocks_replay(self):
        with self.assertRaises(GenesisRejected):
            compare_initialized(
                self.genesis,expected_checkpoint_sha256="f"*64
            )


if __name__=="__main__":
    unittest.main()
