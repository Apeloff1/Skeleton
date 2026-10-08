"""End-to-end capacity enforcement at the verified serving bridge."""
import unittest
from hashlib import sha256
from unittest.mock import Mock

from skeleton.ai.model_runtime.serving_policy import (
    PolicyAwareServingPlanner, ServingRequest,
)
from skeleton.ai.model_serving.admission import ServingPolicy
from skeleton.ai.model_serving.capacity import (
    CapacityDenied, CapacityLedger, CapacityLimits,
)
from skeleton.ai.model_serving.runtime_bridge import plan_and_invoke
from skeleton.ai.model_serving.verified import AdmissionDenied


def digest(value):
    return "sha256:" + sha256(value).hexdigest()


class CapacityBridgeTests(unittest.TestCase):
    def setUp(self):
        self.model = b"model"
        self.evaluation = b"evaluation"
        self.policy = ServingPolicy(digest(self.model), digest(self.evaluation),
                                    "local", 100, 30)
        self.ledger = CapacityLedger(CapacityLimits(1, 50, 10**12))
        self.request = ServingRequest("id-1", 20, 10)
        self.planner = object.__new__(PolicyAwareServingPlanner)
        self.planner.plan = Mock(return_value="plan")
        self.backend = Mock(return_value="output")

    def execute(self, **changes):
        args = dict(policy=self.policy, planner=self.planner,
                    request=self.request, model_bytes=self.model,
                    evaluation_bytes=self.evaluation, backend="local",
                    invoke=self.backend, ledger=self.ledger)
        args.update(changes)
        return plan_and_invoke(**args)

    def test_success_releases_capacity(self):
        result = self.execute()
        self.assertEqual(result.backend_result, "output")
        self.assertEqual(self.ledger.snapshot(), (0, 0))

    def test_backend_failure_releases_capacity(self):
        self.backend.side_effect = RuntimeError("failed")
        with self.assertRaisesRegex(RuntimeError, "failed"):
            self.execute()
        self.assertEqual(self.ledger.snapshot(), (0, 0))

    def test_planner_failure_releases_capacity(self):
        self.planner.plan.side_effect = RuntimeError("planner failed")
        with self.assertRaisesRegex(RuntimeError, "planner failed"):
            self.execute()
        self.assertEqual(self.ledger.snapshot(), (0, 0))
        self.backend.assert_not_called()

    def test_saturation_denies_without_execution(self):
        lease = self.ledger.acquire("other", "other", 10)
        with self.assertRaises(CapacityDenied):
            self.execute()
        self.planner.plan.assert_not_called()
        self.backend.assert_not_called()
        self.assertTrue(self.ledger.release(lease))

    def test_tampering_does_not_reserve(self):
        with self.assertRaises(AdmissionDenied):
            self.execute(model_bytes=b"tampered")
        self.assertEqual(self.ledger.snapshot(), (0, 0))
        self.backend.assert_not_called()


if __name__ == "__main__":
    unittest.main()
