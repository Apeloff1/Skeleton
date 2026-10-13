"""Low-cardinality metrics for AI shell planning and execution."""

from __future__ import annotations

from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class AICommandMetrics:
    planning_attempts: int = 0
    planning_failures: int = 0
    reviews: int = 0
    approvals: int = 0
    executions: int = 0
    execution_failures: int = 0
    verification_failures: int = 0
    guardrail_blocks: int = 0
    total_risk_score: int = 0

    @property
    def average_risk_score(self) -> float:
        return self.total_risk_score / self.reviews if self.reviews else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "planning_attempts": self.planning_attempts,
            "planning_failures": self.planning_failures,
            "reviews": self.reviews,
            "approvals": self.approvals,
            "executions": self.executions,
            "execution_failures": self.execution_failures,
            "verification_failures": self.verification_failures,
            "guardrail_blocks": self.guardrail_blocks,
            "average_risk_score": self.average_risk_score,
        }


class AIShellMetrics:
    """Metrics are keyed by logical command only, never raw argv or user text."""

    def __init__(self, *, max_commands: int = 4096) -> None:
        self.max_commands = max_commands
        self._items: dict[str, AICommandMetrics] = {}
        self._lock = threading.RLock()

    def _update(self, command: str, **delta: int) -> AICommandMetrics:
        if not command or len(command) > 128:
            raise ValueError("invalid metrics command key")
        with self._lock:
            current = self._items.get(command, AICommandMetrics())
            if command not in self._items and len(self._items) >= self.max_commands:
                raise RuntimeError("AI metrics command capacity exhausted")
            values = {
                "planning_attempts": current.planning_attempts,
                "planning_failures": current.planning_failures,
                "reviews": current.reviews,
                "approvals": current.approvals,
                "executions": current.executions,
                "execution_failures": current.execution_failures,
                "verification_failures": current.verification_failures,
                "guardrail_blocks": current.guardrail_blocks,
                "total_risk_score": current.total_risk_score,
            }
            for key, value in delta.items():
                values[key] += value
            updated = AICommandMetrics(**values)
            self._items[command] = updated
            return updated

    def planned(self, command: str, *, failed: bool = False) -> AICommandMetrics:
        return self._update(
            command,
            planning_attempts=1,
            planning_failures=int(bool(failed)),
        )

    def reviewed(self, command: str, *, risk_score: int) -> AICommandMetrics:
        if not 0 <= risk_score <= 100:
            raise ValueError("risk_score out of range")
        return self._update(command, reviews=1, total_risk_score=risk_score)

    def approved(self, command: str) -> AICommandMetrics:
        return self._update(command, approvals=1)

    def executed(
        self,
        command: str,
        *,
        ok: bool,
        verified: bool,
    ) -> AICommandMetrics:
        return self._update(
            command,
            executions=1,
            execution_failures=int(not ok),
            verification_failures=int(ok and not verified),
        )

    def guardrail_blocked(self, command: str) -> AICommandMetrics:
        return self._update(command, guardrail_blocks=1)

    def snapshot(self) -> dict[str, AICommandMetrics]:
        with self._lock:
            return {key: self._items[key] for key in sorted(self._items)}
