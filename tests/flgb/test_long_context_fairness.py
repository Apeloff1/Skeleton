"""Deterministic fail-closed offline fairness contract regressions."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.model_runtime import (
    LongContextFairPlanner, LongContextProgressHead, LongContextSpool,
    PressureSignals, StreamDemand,
)
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError

TOKENIZER = sha256(b"fair-plan-tokenizer").hexdigest()
SOURCE = sha256(b"fair-plan-source").hexdigest()
NORMAL = PressureSignals("normal", "normal", "normal", "normal")


@unittest.skipUnless(os.name == "posix", "POSIX durable head fairness")
class TestLongContextFairPlanner(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "spool"
        self.spool = LongContextSpool(self.root, disk_reserve_bytes=0)
        self.addCleanup(self.spool.close)
        self.heads = LongContextProgressHead(self.spool)
        self.planner = LongContextFairPlanner(self.heads)

    def stream(self, name: str, count: int = 20, weight: int = 1):
        checkpoint = self.spool.stage(
            TokenSequence(TOKENIZER, tuple(range(count)), SOURCE))
        self.heads.initialize(name, checkpoint, expected_tokenizer_digest=TOKENIZER)
        return StreamDemand(name, checkpoint, 0, max_tokens=16, weight=weight)

    def plan(self, *demands, signals=NORMAL, total_token_budget=64):
        return self.planner.plan(tuple(demands),
            expected_tokenizer_digest=TOKENIZER, signals=signals,
            total_token_budget=total_token_budget, quantum_tokens=4)

    def test_weighted_proposal_is_deterministic_and_payload_free(self):
        a = self.stream("story.alpha")
        b = self.stream("story.beta", weight=3)
        first = self.plan(b, a)
        self.assertEqual(first, self.plan(a, b))
        self.assertEqual(first["state"], "proposed")
        self.assertEqual(len(first["slots"]), 2)
        self.assertEqual(sorted(s["proposed_tokens"] for s in first["slots"]), [4, 12])
        self.assertEqual(first["proposed_tokens"], 16)
        self.assertEqual(len(first["plan_digest"]), 64)
        self.assertFalse(first["is_execution_lease"])
        self.assertFalse(first["is_admission_grant"])
        self.assertFalse(first["pressure_signals_attested"])
        self.assertNotIn("token_ids", str(first))
        self.assertNotIn("story.alpha", str(first))

    def test_pressure_unknown_elevated_critical_all_hold(self):
        a = self.stream("story.alpha")
        for name in ("cpu", "memory", "thermal", "energy"):
            for state in ("unknown", "elevated", "critical"):
                with self.subTest(name=name, state=state):
                    held = self.plan(a, signals=replace(NORMAL, **{name: state}))
                    self.assertEqual(held["state"], "hold")
                    self.assertEqual(held["slots"], [])
                    self.assertIn(name + "_" + state, held["reasons"])

    def test_unqualified_gpu_and_m_chip_hold(self):
        a = self.stream("story.alpha")
        for device in ("gpu", "m_chip"):
            held = self.plan(a, signals=replace(NORMAL, device_kind=device))
            self.assertEqual(held["state"], "hold")
            self.assertIn("device_not_qualified", held["reasons"])

    def test_insufficient_fair_cycle_budget_holds_everyone(self):
        a = self.stream("story.alpha")
        b = self.stream("story.beta")
        held = self.plan(a, b, total_token_budget=1)
        self.assertEqual(held["state"], "hold")
        self.assertEqual(held["slots"], [])
        self.assertIn("fair_cycle_budget_insufficient", held["reasons"])

    def test_minimum_viable_budget_never_starves_a_stream(self):
        a = self.stream("story.alpha", weight=1)
        b = self.stream("story.beta", weight=3)
        for budget in (2, 3, 4, 5, 6):
            with self.subTest(budget=budget):
                result = self.plan(a, b, total_token_budget=budget)
                self.assertEqual(result["state"], "proposed")
                self.assertEqual(len(result["slots"]), 2)
                self.assertTrue(all(s["proposed_tokens"] >= 1 for s in result["slots"]))
                self.assertLessEqual(result["proposed_tokens"], budget)
                self.assertEqual(result, self.plan(b, a, total_token_budget=budget))
        held = self.plan(a, b, total_token_budget=1)
        self.assertEqual(held["state"], "hold")
        self.assertEqual(held["slots"], [])

    def test_weighted_allocation_respects_caps_and_never_exceeds_budget(self):
        a = self.stream("story.alpha", count=2, weight=8)
        b = self.stream("story.beta", count=20, weight=1)
        c = self.stream("story.gamma", count=20, weight=3)
        for budget in range(3, 25):
            with self.subTest(budget=budget):
                result = self.plan(a, b, c, total_token_budget=budget)
                self.assertEqual(result["state"], "proposed")
                self.assertEqual(len(result["slots"]), 3)
                self.assertLessEqual(result["proposed_tokens"], budget)
                self.assertTrue(all(1 <= s["proposed_tokens"] <=
                    s["window_stop"] - s["window_start"] for s in result["slots"]))
                self.assertEqual(result, self.plan(c, a, b, total_token_budget=budget))

    def test_finished_stream_does_not_block_active_stream(self):
        a = self.stream("story.alpha", count=2)
        b = self.stream("story.beta", count=9)
        self.heads.advance("story.alpha",
            expected_checkpoint_digest=a.checkpoint_digest,
            expected_tokenizer_digest=TOKENIZER, consumed_tokens=2)
        current = self.heads.status("story.alpha",
                                    expected_tokenizer_digest=TOKENIZER)
        a = replace(a, checkpoint_digest=current["checkpoint_digest"], generation=1)
        result = self.plan(a, b)
        self.assertEqual(result["state"], "proposed")
        self.assertEqual(len(result["slots"]), 1)

    def test_stale_generation_and_tokenizer_drift_hold(self):
        a = self.stream("story.alpha")
        with self.assertRaisesRegex(LongContextSpoolError, "stale"):
            self.plan(replace(a, generation=1))
        with self.assertRaises(LongContextSpoolError):
            self.planner.plan((a,), expected_tokenizer_digest=SOURCE,
                              signals=NORMAL, total_token_budget=4)

    def test_duplicate_unbounded_and_invalid_inputs(self):
        a = self.stream("story.alpha")
        for demands in ((), (a, a), tuple([a] * 65)):
            with self.assertRaises(LongContextSpoolError):
                self.planner.plan(demands, expected_tokenizer_digest=TOKENIZER,
                                  signals=NORMAL, total_token_budget=64)
        for kwargs in (
            {"generation": True}, {"weight": 0}, {"weight": 9},
            {"max_tokens": 0}, {"max_tokens": 65537},
            {"requested_bytes": -1}, {"requested_bytes": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(LongContextSpoolError):
                replace(a, **kwargs)
        for budget in (True, 0, -1, 65537, "5"):
            with self.subTest(budget=budget), self.assertRaises(LongContextSpoolError):
                self.plan(a, total_token_budget=budget)
        with self.assertRaises(LongContextSpoolError):
            PressureSignals("normal", "normal", "bogus", "normal")

    def test_disk_capacity_failure_denies_all_slots(self):
        a = self.stream("story.alpha")
        with patch.object(self.spool, "capacity_snapshot", return_value={
            "request_observed_sufficient": False,
            "observed_publishable_bytes": 0,
        }):
            held = self.plan(a)
        self.assertEqual(held["state"], "hold")
        self.assertIn("spool_capacity_hold", held["reasons"])

    def test_restart_recomputes_same_plan_without_committing(self):
        a = self.stream("story.alpha")
        first = self.plan(a)
        self.spool.close()
        reopened = LongContextSpool(self.root, disk_reserve_bytes=0)
        try:
            result = LongContextFairPlanner(LongContextProgressHead(reopened)).plan(
                (a,), expected_tokenizer_digest=TOKENIZER,
                signals=NORMAL, total_token_budget=64, quantum_tokens=4)
            self.assertEqual(first["slots"], result["slots"])
            self.assertEqual(first["state"], result["state"])
            self.assertEqual(first["verified_heads"], result["verified_heads"])
            status = LongContextProgressHead(reopened).status(
                "story.alpha", expected_tokenizer_digest=TOKENIZER)
            self.assertEqual(status["generation"], 0)
        finally:
            reopened.close()

    def test_corrupt_ancestry_never_returns_proposal(self):
        a = self.stream("story.alpha")
        with patch.object(self.spool, "audit_history",
                          side_effect=LongContextSpoolError("corrupt ancestry")):
            with self.assertRaisesRegex(LongContextSpoolError, "corrupt ancestry"):
                self.plan(a)


if __name__ == "__main__":
    unittest.main()
