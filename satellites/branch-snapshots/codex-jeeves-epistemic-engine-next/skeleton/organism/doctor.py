"""Doctor diagnostic card — deep inspection and troubleshooting.

Provides a diagnostic card that surfaces anomalies, error summaries,
and actionable recommendations across all subsystems including the
new observability, resilience, and dashboard layers.
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
    circuit = deck.circuit_card()
    load_shedder = deck.load_shedder_card()
    health = deck.health_probe_card()
    audit = deck.audit_integrity()
    dashboard = deck.dashboard_card()
    alerts: List[Dict[str, Any]] = []
    if errors.get("total_errors", 0) > 5:
        alerts.append({"severity": "warning", "subsystem": "repair", "message": f"{errors['total_errors']} recent repair errors", "action": "inspect repair telemetry"})
    if effectiveness.get("success_rate", 1.0) < 0.3:
        alerts.append({"severity": "critical", "subsystem": "repair", "message": "repair success rate below 30%", "action": "review learned policy and thresholds"})
    if kv.get("hit_rate", 1.0) < 0.5:
        alerts.append({"severity": "info", "subsystem": "kv_cache", "message": "KV cache hit rate low", "action": "increase cache size or review access patterns"})
    if policy.get("mean_threshold", 0.7) > 0.95:
        alerts.append({"severity": "warning", "subsystem": "policy", "message": "mean threshold very high — may block generation", "action": "consider adaptive threshold tuning"})
    if circuit.get("state") == "open":
        alerts.append({"severity": "critical", "subsystem": "resilience", "message": "circuit breaker is open", "action": "investigate downstream failures and wait for recovery"})
    if load_shedder.get("shedding_rate", 0.0) > 0.5:
        alerts.append({"severity": "warning", "subsystem": "resilience", "message": f"load shedding at {load_shedder['shedding_rate']}", "action": "reduce load or scale resources"})
    if not health.get("readiness", True):
        alerts.append({"severity": "critical", "subsystem": "health", "message": "system not ready", "action": "run health probes and check dependencies"})
    if not audit.get("intact", True):
        alerts.append({"severity": "critical", "subsystem": "audit", "message": "audit log integrity compromised", "action": "investigate tampering immediately"})
    if dashboard.get("alert_counts", {}).get("critical", 0) > 0:
        alerts.append({"severity": "critical", "subsystem": "dashboard", "message": f"{dashboard['alert_counts']['critical']} critical alerts active", "action": "acknowledge or resolve alerts"})
    return {
        "kind": "doctor-card",
        "alerts": alerts,
        "error_summary": errors,
        "learned_policy": learned,
        "repair_effectiveness": effectiveness,
        "telemetry_summary": telemetry,
        "kv_cache": kv,
        "policy": policy,
        "circuit": circuit,
        "load_shedder": load_shedder,
        "health": health,
        "audit_integrity": audit,
        "dashboard": dashboard,
        "recommendations": [
            {"action": "run repair orchestrator on weakest surface", "trigger": "effectiveness < 0.5"},
            {"action": "save policy version before threshold changes", "trigger": "always"},
            {"action": "review top failure patterns in learned policy", "trigger": "failure count > 3"},
            {"action": "check circuit breaker state before deployments", "trigger": "circuit.state != closed"},
            {"action": "verify audit log integrity after policy changes", "trigger": "always"},
            {"action": "acknowledge dashboard alerts before proceeding", "trigger": "alerts > 0"},
        ],
        "stored_prose": 0,
    }
