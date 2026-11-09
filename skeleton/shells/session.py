"""Execution sessions with aggregate budgets and receipt custody."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import uuid

from skeleton.shells.limits import ResourceBudget, ResourceLimits, ResourceUsage
from skeleton.shells.receipts import ExecutionReceipt
from skeleton.shells.errors import SessionBudgetExhausted, ShellErrorCode, ShellErrorContext


@dataclass(frozen=True)
class SessionSnapshot:
    session_id: str
    principal: str
    created_at: str
    closed: bool
    usage: ResourceUsage
    receipt_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "principal": self.principal,
            "created_at": self.created_at,
            "closed": self.closed,
            "usage": self.usage.to_dict(),
            "receipt_count": self.receipt_count,
        }


class ShellSession:
    """Bounded command session shared across sequential or parallel executors."""

    def __init__(
        self,
        limits: ResourceLimits | None = None,
        *,
        principal: str = "anonymous",
        session_id: str | None = None,
        max_receipts: int | None = None,
    ) -> None:
        self.session_id = session_id or uuid.uuid4().hex
        self.principal = principal
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.budget = ResourceBudget(limits or ResourceLimits())
        self.max_receipts = max_receipts or self.budget.limits.max_commands
        self._receipts: list[ExecutionReceipt] = []
        self._closed = False
        self._lock = threading.RLock()

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def close(self) -> None:
        with self._lock:
            self._closed = True

    def require_start(self, command: str) -> None:
        with self._lock:
            if self._closed:
                raise SessionBudgetExhausted(
                    ShellErrorContext(
                        ShellErrorCode.SESSION_BUDGET,
                        command=command,
                        detail="session is closed",
                    )
                )
            if not self.budget.healthy():
                reasons = ", ".join(self.budget.exceeded())
                raise SessionBudgetExhausted(
                    ShellErrorContext(
                        ShellErrorCode.SESSION_BUDGET,
                        command=command,
                        detail=f"session budget exhausted: {reasons}",
                    )
                )
            if not self.budget.reserve_command():
                raise SessionBudgetExhausted(
                    ShellErrorContext(
                        ShellErrorCode.SESSION_BUDGET,
                        command=command,
                        detail="command budget exhausted",
                    )
                )

    def require_retry(self, command: str) -> None:
        if not self.budget.record_retry():
            raise SessionBudgetExhausted(
                ShellErrorContext(
                    ShellErrorCode.SESSION_BUDGET,
                    command=command,
                    detail="retry budget exhausted",
                )
            )

    def record(self, receipt: ExecutionReceipt) -> None:
        with self._lock:
            if len(self._receipts) >= self.max_receipts:
                raise SessionBudgetExhausted(
                    ShellErrorContext(
                        ShellErrorCode.SESSION_BUDGET,
                        command=receipt.command,
                        detail="receipt capacity exhausted",
                    )
                )
            self._receipts.append(receipt)
            self.budget.record_result(
                ok=receipt.ok,
                duration_ms=receipt.duration_ms,
                stdout_bytes=receipt.stdout_bytes,
                stderr_bytes=receipt.stderr_bytes,
            )

    def receipts(self) -> tuple[ExecutionReceipt, ...]:
        with self._lock:
            return tuple(self._receipts)

    def snapshot(self) -> SessionSnapshot:
        with self._lock:
            return SessionSnapshot(
                self.session_id,
                self.principal,
                self.created_at,
                self._closed,
                self.budget.snapshot(),
                len(self._receipts),
            )
