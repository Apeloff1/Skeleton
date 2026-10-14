"""Synergy between the serving fence and the tokenizer identity. No network."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.closed_loop_serving import ClosedLoopServingController
from skeleton.ai.model_runtime.runtime_feedback import DeterministicRuntimeEstimator, FeedbackLimits
from skeleton.ai.model_runtime.runtime_policy import RuntimePolicy
from skeleton.ai.model_runtime.serving_telemetry import RequestTelemetry
from skeleton.ai.model_runtime.serving_token_synergy import (
    ServingTokenSynergy,
    SynergyError,
    TokenizerIdentity,
)
from skeleton.ai.model_runtime.slo_planner import RuntimeEstimate, SLOResourcePlanner, SLOTarget


DIGEST = "ab" * 32
OTHER = "cd" * 32


def _policy() -> RuntimePolicy:
    return RuntimePolicy(through_year=2026, capabilities=("local-serve",), experimental=(), digest="ef" * 32)


def _controller() -> ClosedLoopServingController:
    estimate = RuntimeEstimate(20, 4, 8, 16)
    return ClosedLoopServingController(
        policy=_policy(),
        estimator=DeterministicRuntimeEstimator(estimate, FeedbackLimits(min_samples=1, max_samples=8)),
        planner=SLOResourcePlanner(max_prefill_chunks=4, prefill_chunk_tokens=8),
    )


def _identity(digest: str = DIGEST) -> TokenizerIdentity:
    return TokenizerIdentity(digest=digest, vocab_size=4, unk=1)


def _synergy() -> ServingTokenSynergy:
    return ServingTokenSynergy(_controller(), _identity())


def _slo() -> SLOTarget:
    return SLOTarget(ttft_ms=500, inter_token_ms=50, end_to_end_ms=2000)


class SynergyLaw(unittest.TestCase):
    def test_admit_binds_tokenizer_digest_into_receipt(self) -> None:
        gate = _synergy()
        receipt = gate.admit(
            request_id="req-1",
            prompt_tokens=8,
            slo=_slo(),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=0,
            tokenizer_digest=DIGEST,
        )
        self.assertTrue(receipt.admitted)
        self.assertEqual(receipt.tokenizer_digest, DIGEST)
        self.assertEqual(receipt.card()["stored_prose"], 0)
        self.assertEqual(receipt.card()["parent"], "#80")
        drifted = _synergy()
        with self.assertRaises(SynergyError):
            drifted.admit(
                request_id="req-1",
                prompt_tokens=8,
                slo=_slo(),
                kv_capacity_bytes=10_000,
                kv_used_bytes=0,
                queue_pressure_pct=0,
                tokenizer_digest=OTHER,
            )

    def test_oversized_prefill_does_not_open_observe_fence(self) -> None:
        gate = _synergy()
        receipt = gate.admit(
            request_id="huge",
            prompt_tokens=10_000,
            slo=_slo(),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=0,
            tokenizer_digest=DIGEST,
        )
        self.assertFalse(receipt.admitted)
        telemetry = RequestTelemetry("huge", 10, 4, 40, 10_000, 2)
        with self.assertRaises(SynergyError):
            gate.observe(telemetry, kv_bytes_per_token=16, tokenizer_digest=DIGEST, admission_digest=receipt.digest)

    def test_observe_requires_same_identity_and_admission_digest(self) -> None:
        gate = _synergy()
        receipt = gate.admit(
            request_id="req-2",
            prompt_tokens=8,
            slo=_slo(),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=0,
            tokenizer_digest=DIGEST,
        )
        telemetry = RequestTelemetry("req-2", 12, 4, 40, 8, 2)
        with self.assertRaises(SynergyError):
            gate.observe(telemetry, kv_bytes_per_token=16, tokenizer_digest=OTHER, admission_digest=receipt.digest)
        with self.assertRaises(SynergyError):
            gate.observe(telemetry, kv_bytes_per_token=16, tokenizer_digest=DIGEST, admission_digest=OTHER)
        observed = gate.observe(
            telemetry, kv_bytes_per_token=16, tokenizer_digest=DIGEST, admission_digest=receipt.digest
        )
        self.assertEqual(observed.reason, "observed")
        with self.assertRaises(SynergyError):
            gate.observe(telemetry, kv_bytes_per_token=16, tokenizer_digest=DIGEST, admission_digest=receipt.digest)

    def test_prompt_divergence_does_not_train(self) -> None:
        gate = _synergy()
        receipt = gate.admit(
            request_id="req-3",
            prompt_tokens=8,
            slo=_slo(),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=0,
            tokenizer_digest=DIGEST,
        )
        telemetry = RequestTelemetry("req-3", 12, 4, 40, 7, 2)
        with self.assertRaises(SynergyError):
            gate.observe(telemetry, kv_bytes_per_token=16, tokenizer_digest=DIGEST, admission_digest=receipt.digest)
        self.assertEqual(gate.controller.estimator.receipt().samples, 0)

    def test_checkpoint_bind_accepts_matching_pair(self) -> None:
        gate = _synergy()
        receipt = gate.admit(
            request_id="req-5",
            prompt_tokens=4,
            slo=_slo(),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=0,
            tokenizer_digest=DIGEST,
        )
        gate.observe(
            RequestTelemetry("req-5", 11, 4, 30, 4, 1),
            kv_bytes_per_token=16,
            tokenizer_digest=DIGEST,
            admission_digest=receipt.digest,
        )
        feedback = gate.controller.estimator.checkpoint()
        token = {
            "digest": DIGEST,
            "vocabulary": ["a", "b", "c", "d"],
            "unknown_token_id": 1,
        }
        bound = gate.bind_checkpoints(token, feedback)
        self.assertEqual(bound["stored_prose"], 0)
        self.assertEqual(bound["merge_authority"], 0)
        self.assertEqual(bound["tokenizer_digest"], DIGEST)
        with self.assertRaises(SynergyError):
            gate.bind_checkpoints({**token, "digest": OTHER}, feedback)
        with self.assertRaises(SynergyError):
            gate.bind_checkpoints({**token, "vocabulary": ["a", "b"]}, feedback)


if __name__ == "__main__":
    unittest.main()
