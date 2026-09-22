"""Knowledge exfiltration detection — split from resilience_extended (v16.2)."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus
from .types import ThreatLevel, ThreatCategory, ThreatReport

# =============================================================================
# KNOWLEDGE EXFILTRATION DETECTION
# =============================================================================

class ExfiltrationDetector:
    """
    Monitor I/O for data leakage patterns.
    Detects: model extraction attempts, training data reconstruction,
    membership inference, attribute inference.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._query_history: List[Dict[str, Any]] = []
        self._suspicious_patterns: Dict[str, int] = {}
        self._threshold = 5
        self._bus = bus

    def monitor_query(self, query: str, response: str, user_id: str) -> Optional[ThreatReport]:
        evidence: List[str] = []
        score = 0.0

        # Pattern 1: Repetitive similar queries (membership inference)
        similar_count = sum(
            1 for q in self._query_history[-20:]
            if self._similarity(query, q["query"]) > 0.8
        )
        if similar_count > 3:
            evidence.append(f"Repetitive similar queries: {similar_count} in last 20")
            score += 0.3

        # Pattern 2: Probing for specific training data
        probing_terms = ["training data", "your training", "what data", "dataset",
                        "examples you saw", "what you know about"]
        for term in probing_terms:
            if term.lower() in query.lower():
                evidence.append(f"Training data probe: '{term}'")
                score += 0.2

        # Pattern 3: Response contains memorised content
        if len(response) > 1000 and response.count(".") > 50:
            evidence.append("Long, structured response — possible extraction")
            score += 0.2

        # Pattern 4: Systematic attribute probing
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
                        payload={
                            "user_id": user_id,
                            "score": score,
                            "evidence": evidence,
                            "level": report.level.name,
                        },
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
