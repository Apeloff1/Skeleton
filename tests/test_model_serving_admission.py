"""Adversarial model-serving admission regression coverage."""
import unittest
from skeleton.ai.model_serving.admission import ServingPolicy, admit

MODEL = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
EVAL = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.policy = ServingPolicy(MODEL, EVAL, "local", 4096, 512)
        self.request = dict(model_digest=MODEL, evaluation_digest=EVAL,
                            backend="local", context_tokens=100, output_tokens=10)

    def test_valid(self):
        self.assertTrue(admit(self.policy, **self.request))

    def test_reject_invalid_requests(self):
        changes = (
            {"model_digest": ""}, {"model_digest": "sha256:unverified"},
            {"model_digest": MODEL.upper()}, {"evaluation_digest": ""},
            {"evaluation_digest": "sha256:" + "c" * 64},
            {"backend": "remote"}, {"backend": "LOCAL"},
            {"context_tokens": -1}, {"context_tokens": 4097},
            {"context_tokens": True}, {"context_tokens": 1.0},
            {"output_tokens": 0}, {"output_tokens": 513},
            {"output_tokens": True}, {"output_tokens": 10.0},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(admit(self.policy, **(self.request | change)))

    def test_reject_invalid_policies(self):
        policies = (
            ServingPolicy("", EVAL, "local", 4096, 512),
            ServingPolicy(MODEL, "", "local", 4096, 512),
            ServingPolicy(MODEL, EVAL, "", 4096, 512),
            ServingPolicy(MODEL, EVAL, "local", True, 512),
            ServingPolicy(MODEL, EVAL, "local", 4096, 0),
        )
        for policy in policies:
            with self.subTest(policy=policy):
                self.assertFalse(admit(policy, **self.request))
        self.assertFalse(admit(None, **self.request))


if __name__ == "__main__":
    unittest.main()
