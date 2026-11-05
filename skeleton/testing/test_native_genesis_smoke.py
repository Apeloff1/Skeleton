"""Execute native graph and require real generation receipts, not canned text."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.factory import initialize_native
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy
from skeleton.ai.runtime.operational_ai.native_genesis.smoke import run_graph_smoke
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestActualNativeSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance=initialize_native(GenesisPolicy(
            operator_approved=True,dim=8,n_heads=2,ctx=64,d_ff=0,n_layers=1
        ))

    def test_real_native_graph_run(self):
        proof=run_graph_smoke(
            self.instance.runtime,
            exact_model_sha256=self.instance.runtime.model_digest,
        )
        self.assertTrue(proof.graph_executed)
        self.assertEqual(proof.generated_tokens,2)
        self.assertGreater(proof.prompt_tokens,0)
        self.assertEqual(len(proof.generated_sha256),64)

    def test_no_model_quality_claim(self):
        report=run_graph_smoke(self.instance.runtime,
                               exact_model_sha256=self.instance.runtime.model_digest).report()
        self.assertFalse(report["answer_quality_verified"])
        self.assertFalse(report["model_trained"])
        self.assertFalse(report["serving_admitted"])

    def test_wrong_checkpoint_identity_denied(self):
        with self.assertRaises(GenesisRejected):
            run_graph_smoke(self.instance.runtime,exact_model_sha256="f"*64)

    def test_random_seed_generation_does_not_mutate_weights(self):
        runtime=self.instance.runtime
        pre=runtime.model_digest
        run_graph_smoke(runtime,exact_model_sha256=pre,seed=10)
        runtime.assert_model_unchanged()
        self.assertEqual(runtime.model_digest,pre)


if __name__=="__main__":
    unittest.main()
