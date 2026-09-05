"""Doctor diagnostic card — deep inspection and troubleshooting.

Provides a diagnostic card that surfaces anomalies, error summaries,
and actionable recommendations across all subsystems.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.cortex.deck import CommandDeck


def doctor_card(*, root=None) -> Dict[str, Any]:
    deck = CommandDeck(root=root)
    errors = deck.repair_errors()
    learned = deck.repair_learned()
    effectiveness = deck.repair_effectiveness()
    telemetry = deck.repair_telemetry()
    kv = deck.kv_cache_stats()
    policy = deck.policy_state()
    alerts: List[Dict[str, Any]] = []
    if errors.get("total_errors", 0) > 5:
        alerts.append({"severity": "warning", "subsystem": "repair", "message": f"{errors['total_errors']} recent repair errors", "action": "inspect repair telemetry"})
    if effectiveness.get("success_rate", 1.0) < 0.3:
        alerts.append({"severity": "critical", "subsystem": "repair", "message": "repair success rate below 30%", "action": "review learned policy and thresholds"})
    if kv.get("hit_rate", 1.0) < 0.5:
        alerts.append({"severity": "info", "subsystem": "kv_cache", "message": "KV cache hit rate low", "action": "increase cache size or review access patterns"})
    if policy.get("mean_threshold", 0.7) > 0.95:
        alerts.append({"severity": "warning", "subsystem": "policy", "message": "mean threshold very high — may block generation", "action": "consider adaptive threshold tuning"})
    return {
        "kind": "doctor-card",
        "alerts": alerts,
        "error_summary": errors,
        "learned_policy": learned,
        "repair_effectiveness": effectiveness,
        "telemetry_summary": telemetry,
        "kv_cache": kv,
        "policy": policy,
        "recommendations": [
            {"action": "run repair orchestrator on weakest surface", "trigger": "effectiveness < 0.5"},
            {"action": "save policy version before threshold changes", "trigger": "always"},
            {"action": "review top failure patterns in learned policy", "trigger": "failure count > 3"},
        ],
        "stored_prose": 0,
    }
