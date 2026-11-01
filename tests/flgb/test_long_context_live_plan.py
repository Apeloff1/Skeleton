"""Live-pressure fair-plan binding regression tests; no device claims."""
from __future__ import annotations

from hashlib import sha256
import json
from unittest import TestCase
from unittest.mock import MagicMock, patch

from skeleton.ai.model_runtime import LongContextLivePlanner as Exported
from skeleton.ai.model_runtime.long_context_live_plan import LongContextLivePlanner
from skeleton.ai.model_runtime.long_context_spool import LongContextSpoolError
from skeleton.ai.model_runtime.long_context_telemetry_fusion import LongContextTelemetryFusion
from skeleton.ai.model_runtime.long_context_pressure_latch import _FIELDS


def envelope(level="normal", *, event=0, state="observed"):
    value = {
        "schema": "skeleton.ai.long-context-telemetry-fusion.v1",
        "state": state,
        "signals": {key: level for key in ("cpu", "memory", "thermal", "energy")},
        "reasons": [],
        "event_state": "observed" if state == "observed" else "baseline_required",
        "event_deltas": ({"oom": event, "oom_kill": 0, "nr_throttled": 0}
                         if state == "observed" else None),
        "sources": ("host_psi", "cgroup_v2", "cgroup_events"),
        "cross_source_snapshot_atomic": False,
        "scope_membership_attested": False,
        "pressure_signals_attested": False,
        "device_qualified": False,
        "is_admission_grant": False,
        "is_execution_lease": False,
        "requires_live_backend_revalidation": True,
    }
    assert set(value) == _FIELDS - {"observation_digest"}
    value["observation_digest"] = sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return value


class TestLivePlan(TestCase):
    def setUp(self):
        self.monitor = LongContextTelemetryFusion()
        self.heads = MagicMock()
        self.proposal = {
            "state": "hold", "slots": [], "proposed_tokens": 0,
            "is_admission_grant": False, "is_execution_lease": False,
        }

    def invoke(self, observation, *, proposal=None):
        # Planner is mocked to isolate the observation binding contract.
        with patch("skeleton.ai.model_runtime.long_context_live_plan.LongContextProgressHead",
                   MagicMock), patch(
            "skeleton.ai.model_runtime.long_context_live_plan.LongContextFairPlanner"
        ) as planner, patch.object(self.monitor, "sample", return_value=observation):
            planner.return_value.plan.return_value = (
                self.proposal if proposal is None else proposal)
            adapter = LongContextLivePlanner(self.heads, self.monitor)
            result = adapter.plan(
                (), expected_tokenizer_digest="a" * 64, total_token_budget=1)
            signals = planner.return_value.plan.call_args.kwargs["signals"]
        return result, signals

    def test_normal_sample_is_hint_not_authority(self):
        self.assertIs(Exported, LongContextLivePlanner)
        proposed = {**self.proposal, "state": "proposed",
                    "proposed_tokens": 1, "slots": [{"proposed_tokens": 1}]}
        result, signals = self.invoke(envelope(), proposal=proposed)
        self.assertEqual(result["state"], "proposed")
        self.assertEqual(signals.cpu, "normal")
        self.assertFalse(result["is_execution_lease"])
        self.assertFalse(result["is_admission_grant"])
        self.assertFalse(result["device_qualified"])
        self.assertFalse(result["observation_digest_is_authenticity_proof"])
        self.assertTrue(result["requires_live_backend_revalidation"])
        self.assertEqual(len(result["live_plan_digest"]), 64)

    def test_unknown_thermal_never_claims_normal(self):
        result, signals = self.invoke(envelope("unknown"))
        self.assertEqual(result["state"], "hold")
        self.assertEqual(signals.thermal, "unknown")
        self.assertIsNone(result["observation_digest"])

    def test_oom_and_baseline_downgrade_all_signals(self):
        for value in (envelope(event=1), envelope(state="baseline_required")):
            with self.subTest(value=value["state"]):
                result, signals = self.invoke(value)
                self.assertEqual(result["state"], "hold")
                self.assertEqual(signals.cpu, "unknown")
                self.assertIsNone(result["observation_digest"])

    def test_forged_authority_is_not_used_as_hint(self):
        bad = {**envelope(), "is_execution_lease": True}
        result, signals = self.invoke(bad)
        self.assertEqual(result["observation_status"], "forged_authority")
        self.assertEqual(signals.memory, "unknown")

    def test_observer_exception_fails_closed(self):
        with patch("skeleton.ai.model_runtime.long_context_live_plan.LongContextProgressHead",
                   MagicMock), patch(
            "skeleton.ai.model_runtime.long_context_live_plan.LongContextFairPlanner"
        ) as planner, patch.object(self.monitor, "sample",
                                   side_effect=RuntimeError("unavailable")):
            planner.return_value.plan.return_value = self.proposal
            result = LongContextLivePlanner(self.heads, self.monitor).plan(
                (), expected_tokenizer_digest="a" * 64, total_token_budget=1)
            self.assertEqual(result["state"], "hold")
            self.assertEqual(result["observation_status"], "monitor_unavailable")

    def test_invalid_planner_promotion_is_rejected(self):
        proposed = {**self.proposal, "state": "proposed", "proposed_tokens": 1}
        with self.assertRaisesRegex(LongContextSpoolError, "unsafe planner"):
            self.invoke(envelope(event=1), proposal=proposed)

    def test_planner_authority_claim_rejected(self):
        bad = {**self.proposal, "is_execution_lease": True}
        with self.assertRaisesRegex(LongContextSpoolError, "unsupported authority"):
            self.invoke(envelope(), proposal=bad)

    def test_bad_monitor_type_rejected(self):
        with patch("skeleton.ai.model_runtime.long_context_live_plan.LongContextProgressHead",
                   MagicMock):
            with self.assertRaises(LongContextSpoolError):
                LongContextLivePlanner(self.heads, object())
