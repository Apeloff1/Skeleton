"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.local_router import LocalRouter
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestLocalRouter(unittest.TestCase):
    def test_pinned_local_backend_and_capacity(self):
        router=LocalRouter()
        router.register("native",model_sha="a"*64,tokenizer_sha="b"*64,concurrency=1)
        with self.assertRaises(GateViolation):router.admit(model_sha="a"*64,tokenizer_sha="b"*64)
        router.observe("native",healthy=True)
        self.assertEqual(router.admit(model_sha="a"*64,tokenizer_sha="b"*64),"native")
        with self.assertRaises(GateViolation):router.admit(model_sha="a"*64,tokenizer_sha="b"*64)
        router.release("native")
        router.retire("native")
    def test_remote_model_is_rejected(self):
        with self.assertRaises(GateViolation):
            LocalRouter().register("cloud",model_sha="a"*64,tokenizer_sha="b"*64,local=False)

if __name__=="__main__":
    unittest.main()
