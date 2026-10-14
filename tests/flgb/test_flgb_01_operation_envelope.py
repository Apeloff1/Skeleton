import unittest
from skeleton.inference.operation_envelope import FLGBInferenceError, OperationEnvelope
D = "a" * 64
class TestOperationEnvelope(unittest.TestCase):
    def test_bounded_authority(self):
        env = OperationEnvelope("op", D, "inference-proposal-only", 1000, 256, "idem")
        self.assertEqual(len(env.digest), 64)
        with self.assertRaises(FLGBInferenceError):
            OperationEnvelope("op", D, "execute", 1000, 256, "idem")
if __name__ == "__main__": unittest.main()
