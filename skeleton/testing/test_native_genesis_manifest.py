"""Manifest references real initialized bytes and never implies training."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.factory import initialize_native
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy
from skeleton.ai.runtime.operational_ai.native_genesis.manifest import from_instance
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestGenesisManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.genesis=initialize_native(GenesisPolicy(
            operator_approved=True,dim=8,n_heads=2,ctx=64,d_ff=0
        ))
        cls.manifest=from_instance(cls.genesis)

    def test_checkpoint_provenance(self):
        self.assertEqual(self.manifest.model_sha256,self.genesis.runtime.model_digest)
        self.assertEqual(self.manifest.source_sha256,self.genesis.source.source_sha256)
        self.assertEqual(self.manifest.tokenizer_sha256,self.genesis.runtime.tokenizer.digest)
        self.assertEqual(self.manifest.checkpoint_sha256,self.genesis.checkpoint_sha256)

    def test_no_trained_weights_claim(self):
        report=self.manifest.record()
        self.assertEqual(report["initial_optimizer_steps"],0)
        self.assertFalse(report["weights_trained"])
        self.assertFalse(report["serving_admitted"])
        self.assertFalse(report["release_certified"])

    def test_manifest_digest_is_stable(self):
        self.assertEqual(self.manifest.digest,from_instance(self.genesis).digest)

    def test_forged_optimizer_steps_denied(self):
        with self.assertRaises(GenesisRejected):
            replace(self.manifest,initial_optimizer_steps=123)

    def test_model_digest_must_be_sha256(self):
        with self.assertRaises(GenesisRejected):
            replace(self.manifest,model_sha256="bad-digest")


if __name__=="__main__":
    unittest.main()
