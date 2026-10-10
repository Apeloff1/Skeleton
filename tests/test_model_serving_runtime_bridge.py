"""Integration tests for the canonical planner/admission seam."""
import unittest
from hashlib import sha256
from unittest.mock import Mock

from skeleton.ai.model_runtime.serving_policy import ServingRequest as RuntimeRequest
from skeleton.ai.model_serving.admission import ServingPolicy
from skeleton.ai.model_serving.runtime_bridge import plan_and_invoke
from skeleton.ai.model_serving.verified import AdmissionDenied


def digest(value):
    return "sha256:" + sha256(value).hexdigest()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.model = b"model"
        self.evaluation = b"evaluation"
        self.policy = ServingPolicy(digest(self.model), digest(self.evaluation),
                                    "local", 128, 32)
        self.request = RuntimeRequest("r1", 20, 5)
        self.planner = Mock()
        self.backend = Mock(return_value="result")

    def call(self, **changes):
        from skeleton.ai.model_runtime.serving_policy import PolicyAwareServingPlanner
        # Use a real planner type without needing a configured runtime policy:
        # denied requests must not call planner.plan.
        planner = object.__new__(PolicyAwareServingPlanner)
        planner.plan = Mock(return_value="planned")
        values = dict(policy=self.policy, planner=planner,
                      request=self.request, model_bytes=self.model,
                      evaluation_bytes=self.evaluation, backend="local",
                      invoke=self.backend)
        values.update(changes)
        return plan_and_invoke(**values), planner

    def test_authorized_plan_and_execution(self):
        outcome, planner = self.call()
        self.assertEqual(outcome.plan, "planned")
        self.assertEqual(outcome.backend_result, "result")
        planner.plan.assert_called_once_with(self.request)
        self.backend.assert_called_once_with("planned")

    def test_denial_never_executes(self):
        for change in (
            {"model_bytes": b"tampered"},
            {"evaluation_bytes": b"tampered"},
            {"backend": "remote"},
            {"request": RuntimeRequest("r2", 129, 5)},
            {"request": RuntimeRequest("r3", 20, 33)},
        ):
            with self.subTest(change=change):
                with self.assertRaises(AdmissionDenied):
                    self.call(**change)
                self.backend.assert_not_called()


    def test_invalid_backend_callback_rejected_before_planning(self):
        from skeleton.ai.model_runtime.serving_policy import PolicyAwareServingPlanner
        from skeleton.ai.model_serving.capacity import CapacityLedger, CapacityLimits
        planner = object.__new__(PolicyAwareServingPlanner)
        planner.plan = Mock(return_value="planned")
        ledger = CapacityLedger(CapacityLimits(2, 100, 1_000_000_000))
        for invalid_callback in (None, object()):
            with self.subTest(callback=invalid_callback):
                with self.assertRaisesRegex(AdmissionDenied, "trusted backend"):
                    plan_and_invoke(
                        policy=self.policy, planner=planner,
                        request=self.request, model_bytes=self.model,
                        evaluation_bytes=self.evaluation, backend="local",
                        invoke=invalid_callback, ledger=ledger,
                    )
        planner.plan.assert_not_called()
        self.assertEqual(ledger.snapshot(), (0, 0))


    def test_duplicate_in_flight_request_cannot_reenter_backend(self):
        from skeleton.ai.model_runtime.serving_policy import PolicyAwareServingPlanner
        from skeleton.ai.model_serving.capacity import CapacityDenied, CapacityLedger, CapacityLimits
        planner = object.__new__(PolicyAwareServingPlanner)
        planner.plan = Mock(return_value="planned")
        ledger = CapacityLedger(CapacityLimits(1, 100, 10**12))
        calls = []

        def backend(plan):
            calls.append(plan)
            with self.assertRaisesRegex(CapacityDenied, "active reservation"):
                plan_and_invoke(
                    policy=self.policy, planner=planner, request=self.request,
                    model_bytes=self.model, evaluation_bytes=self.evaluation,
                    backend="local", invoke=backend, ledger=ledger,
                )
            self.assertEqual(ledger.snapshot(), (1, 25))
            return "result"

        result = plan_and_invoke(
            policy=self.policy, planner=planner, request=self.request,
            model_bytes=self.model, evaluation_bytes=self.evaluation,
            backend="local", invoke=backend, ledger=ledger,
        )
        self.assertEqual(result.backend_result, "result")
        self.assertEqual(calls, ["planned"])
        planner.plan.assert_called_once_with(self.request)
        self.assertEqual(ledger.snapshot(), (0, 0))


if __name__ == "__main__":
    unittest.main()
