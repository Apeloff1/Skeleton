"""Shared quality contract for generated outputs.

A quality report is the common shape used by verifiers across forge,
plans, and pipelines. It names whether output is accepted, why, where the
weakest point is, and what evidence led there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class QualityIssue:
    path: str
    message: str
    severity: str = "soft"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class QualitySignal:
    path: str
    score: float
    subscores: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "score": round(self.score, 4),
            "subscores": {k: round(v, 4) for k, v in self.subscores.items()},
        }


@dataclass(frozen=True)
class QualityReport:
    accepted: bool
    reason: str
    score: float
    weakest_path: str = ""
    thresholds: Dict[str, float] = field(default_factory=dict)
    summary: Dict[str, int] = field(default_factory=dict)
    issues: Tuple[QualityIssue, ...] = ()
    signals: Tuple[QualitySignal, ...] = ()
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "score": round(self.score, 4),
            "weakest_path": self.weakest_path,
            "thresholds": {k: round(v, 4) for k, v in self.thresholds.items()},
            "summary": dict(self.summary),
            "issues": [i.to_dict() for i in self.issues],
            "signals": [s.to_dict() for s in self.signals],
            "metadata": dict(self.metadata),
        }
