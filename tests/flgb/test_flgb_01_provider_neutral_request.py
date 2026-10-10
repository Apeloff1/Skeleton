import unittest
from skeleton.inference.operation_envelope import OperationEnvelope
from skeleton.inference.provider_neutral_request import ProviderNeutralRequest
D = "a" * 64
class TestProviderNeutralRequest(unittest.TestCase):
    def test_compiles_to_existing_model_contract(self):
        env = OperationEnvelope("op", D, "inference-proposal-only", 900, 128, "idem")
        req = ProviderNeutralRequest(env, "provider", "model", D, D, metadata={"mode":"test"})
        model = req.to_model_request()
        self.assertEqual(model.request_digest, req.digest)
        self.assertEqual(model.deadline_ms, 900)
if __name__ == "__main__": unittest.main()
