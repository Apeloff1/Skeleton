"""Byte-bound model serving tests, including no-execution-on-denial."""
import unittest
from hashlib import sha256

from skeleton.ai.model_serving.admission import ServingPolicy
from skeleton.ai.model_serving.verified import (
    AdmissionDenied, ServingRequest, verified_invoke,
)


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


class VerifiedInvokeTests(unittest.TestCase):
    def setUp(self):
        self.model = b"trusted-model-artifact"
        self.evaluation = b"trusted-evaluation-evidence"
        self.policy = ServingPolicy(digest(self.model), digest(self.evaluation),
                                    "local", 1024, 128)
        self.request = ServingRequest("local", 100, 20)
        self.calls = []

    def invoke(self, request):
        self.calls.append(request)
        return "ok"

    def run_serving(self, **changes):
        values = dict(policy=self.policy, request=self.request,
                      model_bytes=self.model, evaluation_bytes=self.evaluation,
                      invoke=self.invoke)
        values.update(changes)
        return verified_invoke(**values)

    def test_success_calls_once(self):
        self.assertEqual(self.run_serving(), "ok")
        self.assertEqual(self.calls, [self.request])

    def test_fail_closed_never_executes(self):
        cases = (
            {"model_bytes": self.model + b"!"},
            {"evaluation_bytes": self.evaluation + b"!"},
            {"model_bytes": b""},
            {"evaluation_bytes": b""},
            {"model_bytes": bytearray(self.model)},
            {"evaluation_bytes": bytearray(self.evaluation)},
            {"request": ServingRequest("remote", 100, 20)},
            {"request": ServingRequest("local", 1025, 20)},
            {"request": ServingRequest("local", 100, 129)},
            {"request": ServingRequest("local", True, 20)},
            {"request": None},
            {"policy": ServingPolicy(digest(self.model), digest(self.evaluation),
                                      "local", 0, 128)},
        )
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(AdmissionDenied):
                    self.run_serving(**change)
                self.assertEqual(self.calls, [])

    def test_backend_error_propagates_without_retry(self):
        def fail(request):
            self.calls.append(request)
            raise RuntimeError("backend failure")
        with self.assertRaisesRegex(RuntimeError, "backend failure"):
            self.run_serving(invoke=fail)
        self.assertEqual(self.calls, [self.request])


if __name__ == "__main__":
    unittest.main()
