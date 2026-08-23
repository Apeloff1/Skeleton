"""
================================================================================
skeleton.resilience — Adversarial Resilience Fortress (Part 2: Exfiltration + Shadow)
================================================================================
Knowledge exfiltration detection, shadow mode A/B testing, and unified fortress.
================================================================================
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from skeleton.kernel.errors import SkeletonError
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.resilience import ThreatLevel, ThreatCategory, ThreatReport


class ExfiltrationDetector:
    """Monitor I/O for data leakage patterns."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._query_history: List[Dict[str, Any]] = []
        self._suspicious_patterns: Dict[str, int] = {}
        self._threshold = 5
        self._bus = bus

    def monitor_query(self, query: str, response: str, user_id: str) -> Optional[ThreatReport]:
        evidence: List[str] = []
        score = 0.0

        similar_count = sum(
            1 for q in self._query_history[-20:]
            if self._similarity(query, q["query"]) > 0.8
        )
        if similar_count > 3:
            evidence.append(f"Repetitive similar queries: {similar_count} in last 20")
            score += 0.3

        probing_terms = ["training data", "your training", "what data", "dataset",
                        "examples you saw", "what you know about"]
        for term in probing_terms:
            if term.lower() in query.lower():
                evidence.append(f"Training data probe: '{term}'")
                score += 0.2

        if len(response) > 1000 and response.count(".") > 50:
            evidence.append("Long, structured response — possible extraction")
            score += 0.2

        user_patterns = self._suspicious_patterns.get(user_id, 0)
        if any(term in query.lower() for term in probing_terms):
            user_patterns += 1
            self._suspicious_patterns[user_id] = user_patterns
            if user_patterns > self._threshold:
                evidence.append(f"User {user_id}: {user_patterns} probing queries")
                score += 0.3

        self._query_history.append({
            "query": query,
            "response_hash": hashlib.sha256(response.encode()).hexdigest()[:16],
            "user_id": user_id,
            "timestamp": time.time(),
        })

        if len(self._query_history) > 1000:
            self._query_history = self._query_history[-500:]

        if score > 0.5:
            report = ThreatReport(
                level=ThreatLevel.MALICIOUS if score > 0.7 else ThreatLevel.SUSPICIOUS,
                category=ThreatCategory.MODEL_EXTRACTION,
                confidence=min(score, 0.99),
                evidence=evidence,
                action_taken="log_and_rate_limit" if score > 0.7 else "log",
            )
            if self._bus:
                self._bus.publish(
                    DomainEvent(
                        topic="resilience.exfiltration.detected",
                        payload={"user_id": user_id, "score": score, "evidence": evidence, "level": report.level.name},
                        correlation_id=f"exfil_{user_id}_{int(time.time())}",
                    )
                )
            return report
        return None

    def _similarity(self, a: str, b: str) -> float:
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return intersection / union if union > 0 else 0.0


@dataclass
class ShadowExperiment:
    """Definition of a shadow-mode A/B experiment."""
    experiment_id: str
    variant_a: str
    variant_b: str
    traffic_split: float = 0.1
    metrics: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    active: bool = True


class ShadowMode:
    """Silent A/B testing infrastructure."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._experiments: Dict[str, ShadowExperiment] = {}
        self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._bus = bus

    def create_experiment(self, experiment_id: str, variant_a: str, variant_b: str,
                         traffic_split: float = 0.1, metrics: Optional[List[str]] = None) -> ShadowExperiment:
        exp = ShadowExperiment(
            experiment_id=experiment_id, variant_a=variant_a, variant_b=variant_b,
            traffic_split=traffic_split, metrics=metrics or ["latency", "quality_score", "token_count"],
        )
        self._experiments[experiment_id] = exp
        self._results[experiment_id] = []
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="shadow.experiment.created",
                    payload={"experiment_id": experiment_id, "variant_a": variant_a, "variant_b": variant_b, "traffic_split": traffic_split},
                    correlation_id=f"shadow_{experiment_id}",
                )
            )
        return exp

    def should_shadow(self, experiment_id: str, user_id: str) -> bool:
        if experiment_id not in self._experiments:
            return False
        exp = self._experiments[experiment_id]
        if not exp.active:
            return False
        hash_input = f"{experiment_id}:{user_id}"
        hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        return (hash_value % 10000) / 10000 < exp.traffic_split

    def record_shadow_result(self, experiment_id: str, user_id: str,
                            variant_a_result: Dict[str, Any], variant_b_result: Dict[str, Any]) -> None:
        if experiment_id not in self._experiments:
            return
        record = {
            "timestamp": time.time(), "user_id": user_id,
            "variant_a": variant_a_result, "variant_b": variant_b_result,
            "differences": {
                k: variant_b_result.get(k, 0) - variant_a_result.get(k, 0)
                for k in self._experiments[experiment_id].metrics
                if k in variant_a_result and k in variant_b_result
            },
        }
        self._results[experiment_id].append(record)

    def get_experiment_results(self, experiment_id: str) -> Dict[str, Any]:
        if experiment_id not in self._results:
            return {"error": "Experiment not found"}
        results = self._results[experiment_id]
        if not results:
            return {"experiment_id": experiment_id, "samples": 0}
        stats: Dict[str, Dict[str, float]] = {}
        for metric in self._experiments[experiment_id].metrics:
            diffs = [r["differences"].get(metric, 0) for r in results if metric in r["differences"]]
            if diffs:
                stats[metric] = {
                    "mean_diff": sum(diffs) / len(diffs),
                    "min_diff": min(diffs), "max_diff": max(diffs), "samples": len(diffs),
                }
        return {
            "experiment_id": experiment_id, "samples": len(results),
            "duration_hours": (time.time() - self._experiments[experiment_id].start_time) / 3600,
            "statistics": stats,
        }

    def end_experiment(self, experiment_id: str) -> Optional[ShadowExperiment]:
        if experiment_id not in self._experiments:
            return None
        exp = self._experiments[experiment_id]
        exp.active = False
        exp.end_time = time.time()
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="shadow.experiment.ended",
                    payload={
                        "experiment_id": experiment_id,
                        "duration_hours": (exp.end_time - exp.start_time) / 3600,
                        "total_samples": len(self._results.get(experiment_id, [])),
                    },
                    correlation_id=f"shadow_{experiment_id}",
                )
            )
        return exp


class ResilienceFortress:
    """Unified adversarial resilience interface."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        from skeleton.resilience import InputSanitiser, OutputGuardrail
        self.sanitiser = InputSanitiser()
        self.guardrail = OutputGuardrail()
        self.exfiltration = ExfiltrationDetector(bus)
        self.shadow = ShadowMode(bus)
        self._bus = bus
        self._block_count = 0
        self._sanitize_count = 0

    def process_input(self, raw_input: str, user_id: str) -> Tuple[str, ThreatReport]:
        sanitized, report = self.sanitiser.sanitise(raw_input)
        if report.level == ThreatLevel.CRITICAL:
            self._block_count += 1
        elif report.level in (ThreatLevel.MALICIOUS, ThreatLevel.SUSPICIOUS):
            self._sanitize_count += 1
        return sanitized, report

    def process_output(self, output: str, user_id: str, query: str) -> Dict[str, Any]:
        guardrail_result = self.guardrail.evaluate(output)
        exfil_report = self.exfiltration.monitor_query(query, output, user_id)
        result = {
            "safe": guardrail_result["safe"] and exfil_report is None,
            "guardrail": guardrail_result,
            "exfiltration": exfil_report.to_dict() if exfil_report else None,
            "deliverable": (
                guardrail_result.get("redacted_output") or output
                if guardrail_result["safe"]
                else "[OUTPUT BLOCKED: SAFETY VIOLATION]"
            ),
        }
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="resilience.output.processed",
                    payload={"user_id": user_id, "safe": result["safe"],
                            "guardrail_score": guardrail_result["score"],
                            "exfiltration_detected": exfil_report is not None},
                    correlation_id=f"res_{user_id}_{int(time.time())}",
                )
            )
        return result

    def stats(self) -> Dict[str, Any]:
        return {
            "inputs_blocked": self._block_count,
            "inputs_sanitized": self._sanitize_count,
            "exfiltration_queries": len(self.exfiltration._query_history),
            "suspicious_users": len(self.exfiltration._suspicious_patterns),
            "shadow_experiments": len(self.shadow._experiments),
            "active_experiments": sum(1 for e in self.shadow._experiments.values() if e.active),
        }
