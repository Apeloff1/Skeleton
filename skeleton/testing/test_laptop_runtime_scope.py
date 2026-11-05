"""Offline laptop runtime qualification: scope; test-double only, not real native E2E."""
import unittest
from skeleton.testing.laptop_runtime_test_support import FakeWorker,MODEL,TOKENIZER
from skeleton.ai.runtime.operational_ai.laptop_runtime.scope_fence import enforce
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestPrincipalScope(unittest.TestCase):
    def setUp(self):self.worker=FakeWorker()
    def test_exact_principal_and_backend_identity(self):
        receipt=enforce(self.worker,tenant="local",subject="owner",
                         model_sha256=MODEL,tokenizer_sha256=TOKENIZER)
        self.assertTrue(receipt["scope_bound"])
    def test_cross_tenant_and_model_epoch_rejected(self):
        for overrides in ({"tenant":"other"},{"subject":"other"},
                          {"model_sha256":"c"*64},{"tokenizer_sha256":"c"*64}):
            args={"tenant":"local","subject":"owner","model_sha256":MODEL,
                  "tokenizer_sha256":TOKENIZER}
            args.update(overrides)
            with self.subTest(overrides=overrides):
                with self.assertRaises(ContractViolation):enforce(self.worker,**args)

if __name__=="__main__":
    unittest.main()
