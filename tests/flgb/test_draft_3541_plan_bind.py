"""Draft #3541: a plan receipt must carry the tokenizer digest."""
from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.plan_token_bind import PlanBindError, PlanIdentity
from skeleton.ai.model_runtime.slo_planner import RuntimeEstimate, SLOResourcePlanner, SLOTarget

DIGEST = "ab" * 32


class PlanBind(unittest.TestCase):
    def test_drift_does_not_plan(self) -> None:
        gate = PlanIdentity(SLOResourcePlanner(), DIGEST)
        with self.assertRaises(PlanBindError):
            gate.plan(
                tokenizer_digest="cd" * 32,
                prompt_tokens=8,
                estimate=RuntimeEstimate(20, 4, 8, 16),
                slo=SLOTarget(500, 50, 2000),
                kv_capacity_bytes=10_000,
                kv_used_bytes=0,
                queue_pressure_pct=0,
            )

    def test_receipt_binds_digest_and_pressure(self) -> None:
        gate = PlanIdentity(SLOResourcePlanner(), DIGEST)
        card = gate.plan(
            tokenizer_digest=DIGEST,
            prompt_tokens=8,
            estimate=RuntimeEstimate(20, 4, 8, 16),
            slo=SLOTarget(500, 50, 2000),
            kv_capacity_bytes=10_000,
            kv_used_bytes=0,
            queue_pressure_pct=10,
        )
        self.assertEqual(card["stored_prose"], 0)
        self.assertEqual(card["tokenizer_digest"], DIGEST)
        self.assertEqual(card["queue_pressure_pct"], 10)
        self.assertTrue(card["admitted"])
        self.assertEqual(len(card["digest"]), 64)


if __name__ == "__main__":
    unittest.main()
