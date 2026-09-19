"""Model-safe execution observations derived from shell evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable

from skeleton.shells.dispatch import DispatchResult
from skeleton.shells.plan_executor import PlanExecutionReport


@dataclass(frozen=True)
class AIObservation:
    observation_id: str
    correlation_id: str
    command: str
    ok: bool
    returncode: int | None
    timed_out: bool
    output_limited: bool
    duration_ms: float
    stdout_bytes: int
    stderr_bytes: int
    stdout_digest: str
    stderr_digest: str
    safe_excerpt: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "correlation_id": self.correlation_id,
            "command": self.command,
            "ok": self.ok,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "output_limited": self.output_limited,
            "duration_ms": self.duration_ms,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "stdout_digest": self.stdout_digest,
            "stderr_digest": self.stderr_digest,
            "safe_excerpt": self.safe_excerpt,
        }


class ObservationBuilder:
    """Default model observations contain metadata and digests, not output bytes."""

    def __init__(
        self,
        *,
        excerpt_filter: Callable[[bytes, bytes], str] | None = None,
        max_excerpt_chars: int = 2048,
    ) -> None:
        if max_excerpt_chars < 0:
            raise ValueError("max_excerpt_chars may not be negative")
        self.excerpt_filter = excerpt_filter
        self.max_excerpt_chars = max_excerpt_chars

    def dispatch(self, result: DispatchResult) -> AIObservation:
        shell_result = result.outcome.result
        receipt = result.outcome.final_receipt
        excerpt = ""
        if self.excerpt_filter is not None and self.max_excerpt_chars:
            value = self.excerpt_filter(shell_result.stdout, shell_result.stderr)
            if not isinstance(value, str):
                raise TypeError("excerpt filter must return a string")
            excerpt = value[: self.max_excerpt_chars]
        raw_id = (
            f"{receipt.receipt_id}:{result.context.correlation_id}:"
            f"{receipt.fingerprint}:{receipt.attempt}"
        )
        observation_id = hashlib.sha256(raw_id.encode()).hexdigest()[:32]
        return AIObservation(
            observation_id=observation_id,
            correlation_id=result.context.correlation_id,
            command=receipt.command,
            ok=shell_result.ok,
            returncode=shell_result.returncode,
            timed_out=shell_result.timed_out,
            output_limited=shell_result.output_limited,
            duration_ms=result.duration_ms,
            stdout_bytes=len(shell_result.stdout),
            stderr_bytes=len(shell_result.stderr),
            stdout_digest=hashlib.sha256(shell_result.stdout).hexdigest(),
            stderr_digest=hashlib.sha256(shell_result.stderr).hexdigest(),
            safe_excerpt=excerpt,
        )

    def plan(self, report: PlanExecutionReport) -> tuple[dict[str, object], ...]:
        result = []
        for step in report.steps:
            payload = step.to_dict()
            dispatch = step.dispatch
            if dispatch is not None:
                payload["observation"] = self.dispatch(dispatch).to_dict()
            result.append(payload)
        return tuple(result)
