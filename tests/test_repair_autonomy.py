"""Tests for the repair autonomy, telemetry, learned policy, and orchestrator segments."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from skeleton.intelligence.learned_repair import (
    _default_learned_policy,
    learn_from_repair,
    learned_policy_card,
    load_learned_policy,
    save_learned_policy,
    suggest_repair_strategy,
)
from skeleton.intelligence.repair_autonomy import (
    RepairAttempt,
    RepairSession,
    _learned_max_passes,
    _should_stop,
    repair_effectiveness,
    repair_session_card,
    run_multi_pass,
)
from skeleton.intelligence.repair_orchestrator import (
    orchestrated_repair,
    register_repair,
    repair_orchestrator_card,
)
from skeleton.intelligence.repair_telemetry import (
    capture_telemetry,
    error_summary,
    load_telemetry,
    telemetry_card,
)


class TestRepairAutonomy:
    def test_repair_attempt_dataclass(self):
        a = RepairAttempt(pass_n=1, surface="forge", before_score=0.5, after_score=0.8, actions=[{"path": "x.gd"}], accepted=True, reason="accepted")
        d = a.to_dict()
        assert d["pass_n"] == 1
        assert d["delta"] == 0.3
        assert d["accepted"]

    def test_repair_session_dataclass(self):
        s = RepairSession(surface="forge", target_id="test")
        s.attempts.append(RepairAttempt(1, "forge", 0.5, 0.8, [], True, "ok"))
        s.final_accepted = True
        s.status = "accepted"
        d = s.to_dict()
        assert d["status"] == "accepted"
        assert d["pass_count"] == 1

    def test_should_stop_accepted(self):
        s = RepairSession("forge", "t")
        s.attempts = [RepairAttempt(1, "forge", 0.5, 0.8, [], True, "ok")]
        assert _should_stop(s, max_passes=3) is True

    def test_should_stop_max_passes(self):
        s = RepairSession("forge", "t")
        s.attempts = [
            RepairAttempt(1, "forge", 0.5, 0.6, [], False, "low"),
            RepairAttempt(2, "forge", 0.6, 0.65, [], False, "low"),
            RepairAttempt(3, "forge", 0.65, 0.66, [], False, "low"),
        ]
        assert _should_stop(s, max_passes=3) is True

    def test_should_stop_no_improvement(self):
        s = RepairSession("forge", "t")
        s.attempts = [
            RepairAttempt(1, "forge", 0.5, 0.6, [], False, "low"),
            RepairAttempt(2, "forge", 0.6, 0.6, [], False, "low"),
        ]
        assert _should_stop(s, max_passes=3) is True

    def test_should_stop_continue(self):
        s = RepairSession("forge", "t")
        s.attempts = [RepairAttempt(1, "forge", 0.5, 0.6, [], False, "low")]
        assert _should_stop(s, max_passes=3) is False

    def test_run_multi_pass_blocked(self, tmp_path):
        from skeleton.organism.policy_state import save_policy
        policy = {"quality_thresholds": {}, "repair_enabled": {"forge": False}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        session = run_multi_pass("forge", "test", lambda **kw: {"ok": True}, root=tmp_path)
        assert session.status == "blocked"

    def test_run_multi_pass_success(self, tmp_path):
        from skeleton.organism.policy_state import save_policy
        policy = {"quality_thresholds": {}, "repair_enabled": {"forge": True}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        call_count = 0
        def repair_fn(**kw):
            nonlocal call_count
            call_count += 1
            return {"ok": True, "before": {"score": 0.5}, "after": {"score": 0.9}, "actions": [{"path": "x"}], "reason": "accepted"}
        session = run_multi_pass("forge", "test", repair_fn, root=tmp_path, max_passes=3)
        assert session.status == "accepted"
        assert call_count == 1  # stops early because accepted

    def test_repair_effectiveness_empty(self, tmp_path):
        eff = repair_effectiveness(root=tmp_path)
        assert eff["n"] == 0
        assert eff["success_rate"] == 0.0

    def test_repair_session_card_empty(self, tmp_path):
        card = repair_session_card(root=tmp_path)
        assert card["total_sessions"] == 0


class TestRepairTelemetry:
    def test_capture_telemetry(self, tmp_path):
        result = {"before": {"score": 0.4}, "after": {"score": 0.7}, "actions": [{"path": "x"}], "ok": True, "reason": "accepted"}
        telem = capture_telemetry("forge", 1, int(time.time() * 1000) - 10, result, root=tmp_path)
        assert telem.surface == "forge"
        assert telem.pass_n == 1
        assert telem.duration_ms >= 0
        assert telem.accepted
        assert telem.delta == 0.3

    def test_capture_telemetry_with_error(self, tmp_path):
        result = {"before": {"score": 0.4}, "after": {"score": 0.4}, "actions": [], "ok": False, "reason": "failed"}
        try:
            raise ValueError("test error")
        except Exception as e:
            telem = capture_telemetry("forge", 1, int(time.time() * 1000) - 10, result, error=e, root=tmp_path)
        assert telem.error == "test error"
        assert "ValueError" in telem.stack_trace

    def test_load_telemetry(self, tmp_path):
        result = {"before": {"score": 0.4}, "after": {"score": 0.7}, "actions": [], "ok": True, "reason": "ok"}
        capture_telemetry("forge", 1, int(time.time() * 1000) - 10, result, root=tmp_path)
        rows = load_telemetry(root=tmp_path, surface="forge")
        assert len(rows) >= 1
        assert rows[0]["surface"] == "forge"

    def test_telemetry_card(self, tmp_path):
        result = {"before": {"score": 0.4}, "after": {"score": 0.7}, "actions": [], "ok": True, "reason": "ok"}
        capture_telemetry("forge", 1, int(time.time() * 1000) - 10, result, root=tmp_path)
        card = telemetry_card(root=tmp_path)
        assert card["n"] >= 1
        assert card["accept_rate"] >= 0

    def test_error_summary_empty(self, tmp_path):
        summary = error_summary(root=tmp_path)
        assert summary["total_errors"] == 0


class TestLearnedRepair:
    def test_default_policy(self):
        p = _default_learned_policy()
        assert "surface_strategies" in p
        assert "action_effectiveness" in p

    def test_learn_from_repair(self, tmp_path):
        result = {"surface": "forge", "reason": "low_score", "ok": True, "actions": [{"path": "x.gd", "action": "patched"}]}
        policy = learn_from_repair(result, root=tmp_path)
        assert "forge:low_score" in policy["surface_strategies"]
        assert policy["surface_strategies"]["forge:low_score"]["attempts"] == 1
        assert policy["surface_strategies"]["forge:low_score"]["successes"] == 1

    def test_suggest_strategy_known(self, tmp_path):
        # Seed with learning
        result = {"surface": "forge", "reason": "low_score", "ok": True, "actions": [{"path": "x.gd", "action": "patched"}]}
        learn_from_repair(result, root=tmp_path)
        suggestion = suggest_repair_strategy("forge", "low_score", root=tmp_path)
        assert suggestion["known"] is True
        assert suggestion["historical_success_rate"] == 1.0

    def test_suggest_strategy_unknown(self, tmp_path):
        suggestion = suggest_repair_strategy("npc", "missing", root=tmp_path)
        assert suggestion["known"] is False
        assert suggestion["historical_success_rate"] == 0.0

    def test_learned_policy_card(self, tmp_path):
        result = {"surface": "forge", "reason": "low_score", "ok": True, "actions": [{"path": "x.gd"}]}
        learn_from_repair(result, root=tmp_path)
        card = learned_policy_card(root=tmp_path)
        assert card["total_attempts"] == 1
        assert card["overall_success_rate"] == 1.0


class TestRepairOrchestrator:
    def test_register_and_orchestrate(self, tmp_path):
        from skeleton.organism.policy_state import save_policy
        policy = {"quality_thresholds": {}, "repair_enabled": {"forge": True}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)

        def mock_repair(**kw):
            return {"ok": True, "before": {"score": 0.5}, "after": {"score": 0.9}, "actions": [{"path": "x"}], "reason": "accepted"}
        register_repair("forge", mock_repair)

        result = orchestrated_repair("forge", "test-target", root=tmp_path, max_passes=2)
        assert result["status"] == "accepted"
        assert result["final_accepted"] is True
        assert result["pass_count"] == 1

    def test_orchestrate_blocked(self, tmp_path):
        from skeleton.organism.policy_state import save_policy
        policy = {"quality_thresholds": {}, "repair_enabled": {"forge": False}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)

        result = orchestrated_repair("forge", "test", root=tmp_path)
        assert result["status"] == "blocked"
        assert result["reason"] == "repair-disabled-by-policy"

    def test_orchestrate_unknown_surface(self, tmp_path):
        from skeleton.organism.policy_state import save_policy
        policy = {"quality_thresholds": {}, "repair_enabled": {"unknown": True}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)

        result = orchestrated_repair("unknown", "test", root=tmp_path)
        assert result["status"] == "unknown-surface"

    def test_orchestrator_card(self, tmp_path):
        card = repair_orchestrator_card(root=tmp_path)
        assert card["kind"] == "repair-orchestrator-card"
        assert "registered_surfaces" in card
