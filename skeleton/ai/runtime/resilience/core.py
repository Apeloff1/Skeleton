"""
Skeleton Resilience — Fortress, canaries, and fault tolerance

Provides:
- ResilienceFortress: Input sanitization and threat detection
- CanaryRegistry: Canary deployments for safe rollouts
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.events import EventBus


class ThreatLevel(Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SanitizationReport:
    """Result of input sanitization."""
    level: ThreatLevel
    confidence: float
    action_taken: str
    findings: List[str]


class ResilienceFortress:
    """Input sanitization and threat detection fortress."""

    PATTERNS = {
        "sql_injection": re.compile(r"(\b(union|select|insert|delete|drop|exec|script)\b)", re.IGNORECASE),
        "path_traversal": re.compile(r"\.\./|\.\.\\|%2e%2e%2f"),
        "command_injection": re.compile(r"[;&|`]\s*\b(cat|ls|rm|chmod|wget|curl|bash|sh|python)\b"),
        "xss": re.compile(r"<script|javascript:|on\w+\s*=", re.IGNORECASE),
    }

    def __init__(self, bus: Optional[EventBus] = None):
        self._bus = bus
        self._stats = {"checked": 0, "blocked": 0, "sanitized": 0}

    def process_input(self, raw_input: str, user_id: str = "anonymous") -> Tuple[str, SanitizationReport]:
        """Sanitize input and return cleaned text + report."""
        self._stats["checked"] += 1

        findings = []
        threat_score = 0.0

        for name, pattern in self.PATTERNS.items():
            if pattern.search(raw_input):
                findings.append(f"Detected: {name}")
                threat_score += 0.25

        # A terminated statement followed by a destructive SQL command is
        # stronger evidence than a harmless mention of a SQL keyword.
        if re.search(r";\s*(?:drop\s+(?:table|database)|delete\s+from|truncate\s+table)\b", raw_input, re.IGNORECASE):
            findings.append("Detected: destructive_sql_statement")
            threat_score = max(threat_score, 0.6)

        # Length-based heuristic
        if len(raw_input) > 10000:
            findings.append("Input exceeds length threshold")
            threat_score += 0.1

        level = self._score_to_level(threat_score)

        if level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            self._stats["blocked"] += 1
            sanitized = ""
            action = "blocked"
        elif level == ThreatLevel.MEDIUM:
            self._stats["sanitized"] += 1
            sanitized = self._sanitize(raw_input)
            action = "sanitized"
        else:
            sanitized = raw_input
            action = "allowed"

        report = SanitizationReport(
            level=level,
            confidence=min(threat_score, 1.0),
            action_taken=action,
            findings=findings,
        )

        if self._bus:
            self._bus.emit("resilience.fortress.check", {
                "user_id": user_id,
                "level": level.value,
                "action": action,
                "findings": len(findings),
            })

        return sanitized, report

    def process_output(self, output: str, user_id: str, query: str) -> Dict[str, Any]:
        """Use the existing output guardrails and exfiltration owner."""
        if not hasattr(self, "_output_fortress"):
            from skeleton.resilience.fortress import ResilienceFortress as OutputFortress
            self._output_fortress = OutputFortress(self._bus)
        return self._output_fortress.process_output(output, user_id, query)

    @staticmethod
    def _score_to_level(score: float) -> ThreatLevel:
        if score >= 0.8:
            return ThreatLevel.CRITICAL
        elif score >= 0.6:
            return ThreatLevel.HIGH
        elif score >= 0.3:
            return ThreatLevel.MEDIUM
        elif score >= 0.1:
            return ThreatLevel.LOW
        return ThreatLevel.NONE

    @staticmethod
    def _sanitize(text: str) -> str:
        """Basic HTML tag stripping."""
        return re.sub(r"<[^>]+>", "", text)

    def stats(self) -> Dict[str, Any]:
        output_stats = self._output_fortress.stats() if hasattr(self, "_output_fortress") else {}
        return {**output_stats, **self._stats,
                "inputs_blocked": self._stats["blocked"],
                "inputs_sanitized": self._stats["sanitized"]}


class CanaryRegistry:
    """Canary deployments for safe subsystem rollouts."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._canaries: Dict[str, Dict[str, Any]] = {}
        self._bus = bus

    def plant(self, subsystem: str, traffic_percentage: float = 5.0) -> None:
        """Register a new canary for a subsystem."""
        self._canaries[subsystem] = {
            "planted_at": time.time(),
            "traffic_percentage": traffic_percentage,
            "errors": 0,
            "requests": 0,
            "healthy": True,
        }
        if self._bus:
            self._bus.emit("resilience.canary.planted", {"subsystem": subsystem, "traffic": traffic_percentage})

    def record(self, subsystem: str, success: bool) -> None:
        """Record a canary request outcome."""
        if subsystem not in self._canaries:
            return

        canary = self._canaries[subsystem]
        canary["requests"] += 1
        if not success:
            canary["errors"] += 1

        # Auto-rollback if error rate > 10%
        if canary["requests"] > 20:
            error_rate = canary["errors"] / canary["requests"]
            if error_rate > 0.1:
                canary["healthy"] = False
                if self._bus:
                    self._bus.emit("resilience.canary.rollback", {
                        "subsystem": subsystem,
                        "error_rate": error_rate,
                    })

    def is_healthy(self, subsystem: str) -> bool:
        return self._canaries.get(subsystem, {}).get("healthy", True)

    def stats(self) -> Dict[str, Any]:
        return {
            "canaries": len(self._canaries),
            "healthy": sum(1 for c in self._canaries.values() if c["healthy"]),
            "details": dict(self._canaries),
        }
