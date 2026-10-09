"""Cycle tests. Prompt length comes from the encoder. No network."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.closed_loop_serving import ClosedLoopServingController
from skeleton.ai.model_runtime.runtime_feedback import DeterministicRuntimeEstimator, FeedbackLimits
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicy
from skeleton.ai.model_runtime.serving_telemetry import RequestTelemetry, ServingTelemetryWindow
from skeleton.ai.model_runtime.serving_token_cycle import ServingTokenCycle
from skeleton.ai.model_runtime.serving_token_synergy import ServingTokenSynergy, SynergyError, TokenizerIdentity
from skeleton.ai.model_runtime.slo_planner import RuntimeEstimate, SLOResourcePlanner, SLOTarget

DIGEST = "ab" * 32


class _Counter:
    def __init__(self, digest: str = DIGEST) -> None:
        self.digest = digest
        self.calls = 0

    def encode_ids(self, text: str) -> tuple[int, ...]:
        self.calls += 1
        if text == "boom":
            raise SynergyError("encoder refused")
        return tuple(range(len(text)))


def _cycle(counter: _Counter | None = None) -> ServingTokenCycle:
    policy = RuntimePolicy(through_year=2026, capabilities=("local-serve",), experimental=(), digest="ef" * 32)
    controller = ClosedLoopServingController(
        policy=policy,
        estimator=DeterministicRuntimeEstimator(RuntimeEstimate(20, 4, 8, 16), FeedbackLimits(min_samples=1, max_samples=8)),
        planner=SLOResourcePlanner(max_prefill_chunks=4, prefill_chunk_tokens=8),
    )
    synergy = ServingTokenSynergy(controller, TokenizerIdentity(digest=DIGEST, vocab_size=4, unk=1))
    return ServingTokenCycle(synergy, counter or _Counter())


def _slo() -> SLOTarget:
    return SLOTarget(ttft_ms=500, inter_token_ms=50, end_to_end_ms=2000)


class CycleLaw(unittest.TestCase):
    def test_prompt_length_comes_from_encoder_not_caller(self) -> None:
        counter = _Counter()
        cycle = _cycle(counter)
        receipt = cycle.admit_text(
            request_id="req",
            text="abcd",
            slo=_slo(),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=0,
        )
        self.assertEqual(receipt.prompt_tokens, 4)
        self.assertEqual(counter.calls, 1)
        self.assertEqual(receipt.card()["stored_prose"], 0)

    def test_drifted_counter_cannot_admit_or_record(self) -> None:
        cycle = _cycle(_Counter("cd" * 32))
        with self.assertRaises(SynergyError):
            cycle.admit_text(
                request_id="req",
                text="ab",
                slo=_slo(),
                kv_capacity_bytes=10_000,
                kv_used_bytes=0,
                queue_pressure_pct=0,
            )

    def test_encoder_failure_does_not_open_fence(self) -> None:
        cycle = _cycle()
        with self.assertRaises(SynergyError):
            cycle.admit_text(
                request_id="req",
                text="boom",
                slo=_slo(),
                kv_capacity_bytes=10_000,
                kv_used_bytes=0,
                queue_pressure_pct=0,
            )
        self.assertEqual(cycle.synergy.controller.estimator.receipt().samples, 0)

    def test_observe_records_once_and_cohort_binds_tokenizer(self) -> None:
        cycle = _cycle()
        receipt = cycle.admit_text(
            request_id="req",
            text="abcd",
            slo=_slo(),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=0,
        )
        telemetry = RequestTelemetry("req", 12, 4, 40, 4, 2)
        observed = cycle.observe_and_record(telemetry, kv_bytes_per_token=16, admission_digest=receipt.digest)
        self.assertEqual(observed.reason, "observed")
        self.assertIn("req", cycle.window._records)
        with self.assertRaises(SynergyError):
            cycle.observe_and_record(telemetry, kv_bytes_per_token=16, admission_digest=receipt.digest)
        cohort = cycle.cohort(_slo())
        self.assertEqual(cohort["tokenizer_digest"], DIGEST)
        self.assertEqual(cohort["requests"], 1)
        self.assertEqual(cohort["stored_prose"], 0)
        self.assertEqual(len(cohort["digest"]), 64)

    def test_full_window_does_not_train(self) -> None:
        cycle = _cycle()
        cycle.window = ServingTelemetryWindow(max_records=1)
        cycle.window.record(RequestTelemetry("other", 1, 1, 1, 1, 1))
        receipt = cycle.admit_text(
            request_id="req",
            text="ab",
            slo=_slo(),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=0,
        )
        before = cycle.synergy.controller.estimator.receipt().samples
        with self.assertRaises(SynergyError):
            cycle.observe_and_record(
                RequestTelemetry("req", 10, 4, 20, 2, 1),
                kv_bytes_per_token=16,
                admission_digest=receipt.digest,
            )
        self.assertEqual(cycle.synergy.controller.estimator.receipt().samples, before)

    def test_bool_token_rejected(self) -> None:
        class Bad:
            digest = DIGEST

            def encode_ids(self, text: str) -> tuple[int, ...]:
                return (True,)  # type: ignore[return-value]

        cycle = _cycle()
        cycle.counter = Bad()
        with self.assertRaises(SynergyError):
            cycle.admit_text(
                request_id="req",
                text="a",
                slo=_slo(),
                kv_capacity_bytes=10_000,
                kv_used_bytes=0,
                queue_pressure_pct=0,
            )


if __name__ == "__main__":
    unittest.main()
