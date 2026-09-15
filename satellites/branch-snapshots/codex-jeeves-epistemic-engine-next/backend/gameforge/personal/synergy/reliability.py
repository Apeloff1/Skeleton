from __future__ import annotations
"""
Enterprise-grade trigger reliability: structured errors, retries, dead-letter, trigger logs.
"""

import asyncio
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Awaitable, Union

logger = logging.getLogger("gameforge.trigger_reliability")

T = TypeVar("T")


class TriggerErrorCode(str, Enum):
    VALIDATION = "validation"
    TIMEOUT = "timeout"
    DEPENDENCY = "dependency"
    CAPACITY = "capacity"
    LOCKED = "locked"
    TRANSIENT = "transient"
    FATAL = "fatal"
    UNKNOWN = "unknown"


@dataclass
class TriggerError:
    code: TriggerErrorCode
    message: str
    retryable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


@dataclass
class TriggerLogEntry:
    log_id: str
    trigger: str
    status: str  # started | success | retry | failed | dead_letter
    attempt: int
    started_at: str
    finished_at: Optional[str] = None
    duration_ms: Optional[float] = None
    error: Optional[Dict[str, Any]] = None
    result_summary: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class TriggerLog:
    def __init__(self, max_entries: int = 5000):
        self._entries: List[TriggerLogEntry] = []
        self.max_entries = max_entries

    def append(self, entry: TriggerLogEntry):
        self._entries.append(entry)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]

    def recent(self, n: int = 50, trigger: Optional[str] = None) -> List[dict]:
        rows = self._entries
        if trigger:
            rows = [e for e in rows if e.trigger == trigger]
        return [e.to_dict() for e in rows[-n:]]

    def stats(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        by_trigger: Dict[str, int] = {}
        for e in self._entries:
            by_status[e.status] = by_status.get(e.status, 0) + 1
            by_trigger[e.trigger] = by_trigger.get(e.trigger, 0) + 1
        return {
            "total": len(self._entries),
            "by_status": by_status,
            "by_trigger": by_trigger,
        }


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_ms: float = 50.0
    max_delay_ms: float = 2000.0
    exponential: bool = True
    retry_on: tuple = (
        TriggerErrorCode.TRANSIENT,
        TriggerErrorCode.TIMEOUT,
        TriggerErrorCode.DEPENDENCY,
    )


class ReliableTriggerExecutor:
    """
    Wraps sync/async trigger handlers with validation, retry, logging, dead-letter.
    """

    def __init__(self, policy: Optional[RetryPolicy] = None):
        self.policy = policy or RetryPolicy()
        self.log = TriggerLog()
        self.dead_letter: List[dict] = []

    def _classify(self, exc: BaseException) -> TriggerError:
        if isinstance(exc, TriggerExecutionError):
            return exc.error
        msg = str(exc)
        if "lock" in msg.lower():
            return TriggerError(TriggerErrorCode.LOCKED, msg, retryable=False)
        if "timeout" in msg.lower():
            return TriggerError(TriggerErrorCode.TIMEOUT, msg, retryable=True)
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            return TriggerError(TriggerErrorCode.TRANSIENT, msg, retryable=True)
        if isinstance(exc, (ValueError, TypeError, KeyError)):
            return TriggerError(TriggerErrorCode.VALIDATION, msg, retryable=False)
        return TriggerError(TriggerErrorCode.UNKNOWN, msg, retryable=True)

    def run_sync(
        self,
        trigger: str,
        fn: Callable[[], T],
        *,
        correlation_id: Optional[str] = None,
        validate: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
        cid = correlation_id or str(uuid.uuid4())[:12]
        attempt = 0
        last_err: Optional[TriggerError] = None
        while attempt < self.policy.max_attempts:
            attempt += 1
            started = time.perf_counter()
            started_at = datetime.utcnow().isoformat()
            self.log.append(
                TriggerLogEntry(
                    log_id=str(uuid.uuid4())[:10],
                    trigger=trigger,
                    status="started",
                    attempt=attempt,
                    started_at=started_at,
                    correlation_id=cid,
                )
            )
            try:
                if validate:
                    validate()
                result = fn()
                finished = datetime.utcnow().isoformat()
                dur = (time.perf_counter() - started) * 1000
                summary = None
                if isinstance(result, dict):
                    summary = {k: result[k] for k in list(result)[:8]}
                elif hasattr(result, "to_dict"):
                    summary = {"type": type(result).__name__}
                self.log.append(
                    TriggerLogEntry(
                        log_id=str(uuid.uuid4())[:10],
                        trigger=trigger,
                        status="success",
                        attempt=attempt,
                        started_at=started_at,
                        finished_at=finished,
                        duration_ms=round(dur, 2),
                        result_summary=summary,
                        correlation_id=cid,
                    )
                )
                return {
                    "ok": True,
                    "trigger": trigger,
                    "attempt": attempt,
                    "correlation_id": cid,
                    "result": result,
                }
            except Exception as exc:
                last_err = self._classify(exc)
                finished = datetime.utcnow().isoformat()
                dur = (time.perf_counter() - started) * 1000
                retryable = last_err.retryable and last_err.code in self.policy.retry_on
                status = "retry" if retryable and attempt < self.policy.max_attempts else "failed"
                self.log.append(
                    TriggerLogEntry(
                        log_id=str(uuid.uuid4())[:10],
                        trigger=trigger,
                        status=status,
                        attempt=attempt,
                        started_at=started_at,
                        finished_at=finished,
                        duration_ms=round(dur, 2),
                        error=last_err.to_dict(),
                        correlation_id=cid,
                    )
                )
                if not retryable or attempt >= self.policy.max_attempts:
                    break
                delay = self.policy.base_delay_ms * (
                    (2 ** (attempt - 1)) if self.policy.exponential else 1
                )
                delay = min(delay, self.policy.max_delay_ms)
                time.sleep(delay / 1000.0)

        # dead letter
        dl = {
            "trigger": trigger,
            "correlation_id": cid,
            "error": last_err.to_dict() if last_err else None,
            "at": datetime.utcnow().isoformat(),
        }
        self.dead_letter.append(dl)
        if len(self.dead_letter) > 500:
            self.dead_letter = self.dead_letter[-500:]
        self.log.append(
            TriggerLogEntry(
                log_id=str(uuid.uuid4())[:10],
                trigger=trigger,
                status="dead_letter",
                attempt=attempt,
                started_at=datetime.utcnow().isoformat(),
                error=last_err.to_dict() if last_err else None,
                correlation_id=cid,
            )
        )
        return {
            "ok": False,
            "trigger": trigger,
            "attempt": attempt,
            "correlation_id": cid,
            "error": last_err.to_dict() if last_err else {"message": "unknown"},
            "dead_lettered": True,
        }


class TriggerExecutionError(Exception):
    def __init__(self, error: TriggerError):
        super().__init__(error.message)
        self.error = error
