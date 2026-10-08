"""Adversarial preflight and observation regressions for FLGB-02 serving."""
import unittest

from skeleton.ai.model_runtime.closed_loop_serving import ClosedLoopServingController
from skeleton.ai.model_runtime.runtime_feedback import (
    DeterministicRuntimeEstimator, FeedbackLimits,
)
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicyCompiler
from skeleton.ai.model_runtime.serving_telemetry import (
    RequestTelemetry, ServingTelemetryWindow,
)
from skeleton.ai.model_runtime.slo_planner import (
    RuntimeEstimate, SLOResourcePlanner, SLOTarget,
)


class TestBoundedSLOPlanning(unittest.TestCase):
    def setUp(self):
        self.estimate = RuntimeEstimate(100, 10, 5, 8)
        self.slo = SLOTarget(500, 20, 1000)
        self.args = dict(
            estimate=self.estimate, slo=self.slo, kv_capacity_bytes=100_000,
            kv_used_bytes=0, queue_pressure_pct=0,
        )

    def test_huge_prompt_denies_without_constructing_chunks(self):
        planner = SLOResourcePlanner(prefill_chunk_tokens=2, max_prefill_chunks=3)
        first = planner.plan(prompt_tokens=10**100, **self.args)
        second = planner.plan(prompt_tokens=10**100, **self.args)
        self.assertEqual(first, second)
        self.assertFalse(first.admitted)
        self.assertEqual(first.reason, "prefill_chunk_limit_exceeded")
        self.assertEqual(first.prefill_chunks, ())
        self.assertEqual(first.reserved_kv_bytes, 0)

    def test_exact_prefill_boundary_is_chunked(self):
        planner = SLOResourcePlanner(prefill_chunk_tokens=2, max_prefill_chunks=3)
        result = planner.plan(prompt_tokens=6, **self.args)
        self.assertTrue(result.admitted)
        self.assertEqual(result.prefill_chunks, (2, 2, 2))
        self.assertEqual(result.reserved_kv_bytes, 88)

    def test_above_boundary_does_not_hide_kv_reservation(self):
        planner = SLOResourcePlanner(prefill_chunk_tokens=2, max_prefill_chunks=3)
        result = planner.plan(prompt_tokens=7, **self.args)
        self.assertFalse(result.admitted)
        self.assertEqual(result.reserved_kv_bytes, 0)

    def test_planner_policy_is_part_of_receipt_identity(self):
        one = SLOResourcePlanner(prefill_chunk_tokens=2, max_prefill_chunks=3)
        two = SLOResourcePlanner(prefill_chunk_tokens=3, max_prefill_chunks=3)
        left = one.plan(prompt_tokens=3, **self.args)
        right = two.plan(prompt_tokens=3, **self.args)
        self.assertNotEqual(left.digest, right.digest)

    def test_reject_invalid_constructor_numbers(self):
        for kw in (
            {"prefill_chunk_tokens": True},
            {"prefill_chunk_tokens": 1.5},
            {"max_prefill_chunks": False},
            {"max_prefill_chunks": 0},
            {"overload_reject_pct": 101},
            {"overload_reject_pct": 1.5},
        ):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                SLOResourcePlanner(**kw)

    def test_reject_wrong_forecast_and_slo_types(self):
        planner = SLOResourcePlanner()
        for field, value in (("estimate", object()), ("slo", object())):
            with self.subTest(field=field), self.assertRaises(ValueError):
                planner.plan(prompt_tokens=2, **(self.args | {field: value}))

    def test_pressure_and_kv_denials_remain_distinct(self):
        planner = SLOResourcePlanner(max_prefill_chunks=2)
        kv = planner.plan(prompt_tokens=4, **(self.args | {"kv_capacity_bytes": 1}))
        self.assertEqual(kv.reason, "insufficient_predicted_kv_capacity")
        estimate = RuntimeEstimate(900, 90, 5, 8)
        pressure = planner.plan(prompt_tokens=4, **(
            self.args | {"estimate": estimate, "queue_pressure_pct": 99}
        ))
        self.assertEqual(pressure.reason, "overload_predicted_slo_miss")


class TestBoundedTelemetry(unittest.TestCase):
    def test_reject_invalid_identity_and_metrics_types(self):
        for request_id in (None, 123, "", "x" * 257):
            with self.subTest(request_id=request_id), self.assertRaises(ValueError):
                RequestTelemetry(request_id, 1, 1, 1, 1, 1)
        window = ServingTelemetryWindow()
        for field in ("ttft_slo_ms", "inter_token_slo_ms", "e2e_slo_ms"):
            for value in (True, 0, 1.5):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    window.metrics(**(
                        dict(ttft_slo_ms=10, inter_token_slo_ms=10, e2e_slo_ms=10)
                        | {field: value}
                    ))

    def test_finite_window_denies_without_mutation(self):
        window = ServingTelemetryWindow(max_records=1)
        window.record(RequestTelemetry("first", 1, 1, 1, 1, 1))
        before = window.metrics(ttft_slo_ms=2, inter_token_slo_ms=2, e2e_slo_ms=2)
        with self.assertRaisesRegex(ValueError, "capacity"):
            window.record(RequestTelemetry("second", 1, 1, 1, 1, 1))
        after = window.metrics(ttft_slo_ms=2, inter_token_slo_ms=2, e2e_slo_ms=2)
        self.assertEqual(before, after)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            window.record(RequestTelemetry("first", 1, 1, 1, 1, 1))

    def test_window_requires_typed_records_and_limit(self):
        for value in (True, 0, 2.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ServingTelemetryWindow(max_records=value)
        with self.assertRaisesRegex(ValueError, "RequestTelemetry"):
            ServingTelemetryWindow().record(object())

    def test_metrics_independent_of_admission_order(self):
        a, b = ServingTelemetryWindow(), ServingTelemetryWindow()
        r1 = RequestTelemetry("a", 1, 2, 3, 9, 2)
        r2 = RequestTelemetry("b", 1, 2, 3, 10, 2)
        for r in (r1, r2):
            a.record(r)
        for r in (r2, r1):
            b.record(r)
        args = dict(ttft_slo_ms=2, inter_token_slo_ms=2, e2e_slo_ms=3)
        self.assertEqual(a.metrics(**args), b.metrics(**args))


class TestFeedbackReplayFence(unittest.TestCase):
    def estimator(self):
        return DeterministicRuntimeEstimator(
            RuntimeEstimate(100, 20, 4, 8),
            FeedbackLimits(min_samples=2, max_samples=2),
        )

    def test_recent_duplicate_cannot_train_estimator_twice(self):
        estimator = self.estimator()
        observation = RequestTelemetry("tenant/req-1", 200, 30, 300, 2, 2)
        estimator.observe(observation, kv_bytes_per_token=4)
        before = estimator.receipt()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            estimator.observe(observation, kv_bytes_per_token=4)
        self.assertEqual(before, estimator.receipt())
        self.assertEqual(estimator.receipt().samples, 1)

    def test_identity_even_if_observation_values_change(self):
        estimator = self.estimator()
        estimator.observe(RequestTelemetry("r", 10, 10, 10, 1, 1), kv_bytes_per_token=4)
        before = estimator.receipt()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            estimator.observe(
                RequestTelemetry("r", 9999, 999, 10000, 1, 99),
                kv_bytes_per_token=123,
            )
        self.assertEqual(before, estimator.receipt())

    def test_bounded_recent_history_eviction_is_explicit(self):
        estimator = self.estimator()
        for key in ("a", "b", "c"):
            estimator.observe(RequestTelemetry(key, 10, 10, 10, 1, 1), kv_bytes_per_token=4)
        # The replay fence has a bounded horizon; durable identity storage
        # remains the upstream caller's responsibility.
        with self.assertRaisesRegex(ValueError, "duplicate"):
            estimator.observe(RequestTelemetry("b", 10, 10, 10, 1, 1), kv_bytes_per_token=4)
        estimator.observe(RequestTelemetry("a", 10, 10, 10, 1, 1), kv_bytes_per_token=4)
        self.assertEqual(estimator.receipt().samples, 2)

    def test_failed_observation_does_not_consume_identity(self):
        estimator = self.estimator()
        obs = RequestTelemetry("a", 10, 10, 10, 1, 1)
        with self.assertRaises(ValueError):
            estimator.observe(obs, kv_bytes_per_token=True)
        estimator.observe(obs, kv_bytes_per_token=4)
        self.assertEqual(estimator.receipt().samples, 1)

    def test_closed_loop_honors_planner_bounds_and_type(self):
        controller = ClosedLoopServingController(
            policy=RuntimePolicyCompiler().compile(2024),
            estimator=self.estimator(),
            planner=SLOResourcePlanner(prefill_chunk_tokens=2, max_prefill_chunks=2),
        )
        result = controller.decide(
            prompt_tokens=5, slo=SLOTarget(500, 50, 1000),
            kv_capacity_bytes=10_000, kv_used_bytes=0, queue_pressure_pct=0,
        )
        self.assertEqual(result.resource_plan.reason, "prefill_chunk_limit_exceeded")
        with self.assertRaisesRegex(ValueError, "SLOResourcePlanner"):
            ClosedLoopServingController(
                policy=controller.policy, estimator=self.estimator(), planner=object()
            )



class TestFeedbackCheckpointIntegrity(unittest.TestCase):
    def make(self):
        return DeterministicRuntimeEstimator(
            RuntimeEstimate(100, 10, 5, 8),
            FeedbackLimits(min_samples=2, max_samples=3, max_observation_ms=500),
        )

    def observed(self):
        estimator = self.make()
        for key, latency in (("a", 200), ("b", 600), ("c", 300), ("d", 100)):
            estimator.observe(
                RequestTelemetry(key, latency, 10, latency + 1, 1, 1),
                kv_bytes_per_token=4,
            )
        return estimator

    def test_exact_portable_checkpoint_roundtrip(self):
        estimator = self.observed()
        record = estimator.checkpoint()
        import json
        portable = json.loads(json.dumps(record))
        restored = DeterministicRuntimeEstimator.from_checkpoint(portable)
        self.assertEqual(restored.checkpoint(), record)
        self.assertEqual(restored.receipt(), estimator.receipt())
        self.assertEqual(record["recent_request_ids"], ["b", "c", "d"])

    def test_recovered_recent_identity_cannot_retrain(self):
        restored = DeterministicRuntimeEstimator.from_checkpoint(
            self.observed().checkpoint()
        )
        before = restored.receipt()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            restored.observe(
                RequestTelemetry("c", 100, 10, 101, 1, 1),
                kv_bytes_per_token=4,
            )
        self.assertEqual(before, restored.receipt())
        restored.observe(
            RequestTelemetry("new", 100, 10, 101, 1, 1),
            kv_bytes_per_token=4,
        )
        self.assertEqual(restored.receipt().samples, 3)

    def test_checkpoint_does_not_alias_mutable_estimator_state(self):
        estimator = self.observed()
        record = estimator.checkpoint()
        record["recent_request_ids"].clear()
        record["estimate"]["prefill_ms"] = 0
        self.assertEqual(estimator.checkpoint()["recent_request_ids"], ["b", "c", "d"])
        self.assertNotEqual(estimator.checkpoint()["estimate"]["prefill_ms"], 0)

    def test_schema_and_digest_mutations_rejected(self):
        for field, value in (
            ("schema", "future-schema"),
            ("digest", "0" * 64),
            ("samples", 2),
            ("clipped_observations", True),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                record = self.observed().checkpoint()
                record[field] = value
                DeterministicRuntimeEstimator.from_checkpoint(record)

    def test_duplicate_reordered_and_missing_ids_rejected(self):
        for modified in (
            ["b", "b", "d"],
            ["b", "c"],
            [123, "c", "d"],
            ["x" * 257, "c", "d"],
        ):
            with self.subTest(modified=modified), self.assertRaises(ValueError):
                record = self.observed().checkpoint()
                record["recent_request_ids"] = modified
                DeterministicRuntimeEstimator.from_checkpoint(record)

    def test_malformed_limit_and_estimate_rejected(self):
        for field, value in (
            ("limits", {"min_samples": True}),
            ("estimate", {"prefill_ms": -1}),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                record = self.observed().checkpoint()
                record[field].update(value)
                DeterministicRuntimeEstimator.from_checkpoint(record)

    def test_unknown_and_missing_checkpoint_fields_rejected(self):
        record = self.observed().checkpoint()
        with self.assertRaises(ValueError):
            DeterministicRuntimeEstimator.from_checkpoint(record | {"extra": 1})
        with self.assertRaises(ValueError):
            DeterministicRuntimeEstimator.from_checkpoint(
                {key: value for key, value in record.items() if key != "digest"}
            )

    def test_checkpoint_restore_has_no_model_or_network_dependency(self):
        estimator = self.observed()
        restored = DeterministicRuntimeEstimator.from_checkpoint(
            estimator.checkpoint()
        )
        self.assertTrue(restored.ready)
        self.assertGreater(restored.receipt().clipped_observations, 0)


if __name__ == "__main__":
    unittest.main()
