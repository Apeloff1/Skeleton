from __future__ import annotations
"""
Enterprise-grade handoffs between sandboxes (PFC, Jeeves, Math, Coherence, Exocortex).
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class HandoffState(str, Enum):
    CREATED = "created"
    ACKED = "acked"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    TIMEOUT = "timeout"


@dataclass
class HandoffEnvelope:
    handoff_id: str
    correlation_id: str
    source: str
    target: str
    intent: str
    payload: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    state: str = HandoffState.CREATED.value
    ack_required: bool = True
    timeout_s: int = 120
    attempts: int = 0
    max_attempts: int = 3
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class HandoffBus:
    """
    Durable in-process bus with ack, retry, dead-letter.
    All transitions twin-logged when twin service bound.
    """

    def __init__(self, twin_memory=None):
        self.twin = twin_memory
        self.pending: Dict[str, HandoffEnvelope] = {}
        self.completed: List[Dict[str, Any]] = []
        self.dead_letter: List[Dict[str, Any]] = []
        self.logs: List[dict] = []

    def _log(self, event: str, **kw):
        row = {"ts": datetime.utcnow().isoformat(), "event": event, **kw}
        self.logs.append(row)
        if self.twin:
            self.twin.twin_write(
                "handoff",
                row,
                original_filtered=False,
                original_kept=True,
                tags=["handoff", event],
            )

    def create(
        self,
        source: str,
        target: str,
        intent: str,
        payload: Optional[Dict[str, Any]] = None,
        constraints: Optional[List[str]] = None,
        timeout_s: int = 120,
    ) -> HandoffEnvelope:
        env = HandoffEnvelope(
            handoff_id=str(uuid.uuid4())[:12],
            correlation_id=str(uuid.uuid4())[:16],
            source=source,
            target=target,
            intent=intent,
            payload=payload or {},
            constraints=constraints or [],
            timeout_s=timeout_s,
        )
        self.pending[env.handoff_id] = env
        self._log("created", handoff_id=env.handoff_id, source=source, target=target, intent=intent)
        return env

    def ack(self, handoff_id: str) -> Dict[str, Any]:
        env = self.pending.get(handoff_id)
        if not env:
            return {"ok": False, "error": "not_found"}
        env.state = HandoffState.ACKED.value
        env.updated_at = datetime.utcnow().isoformat()
        self._log("acked", handoff_id=handoff_id)
        return {"ok": True, "envelope": env.to_dict()}

    def start(self, handoff_id: str) -> Dict[str, Any]:
        env = self.pending.get(handoff_id)
        if not env:
            return {"ok": False, "error": "not_found"}
        env.state = HandoffState.IN_PROGRESS.value
        env.attempts += 1
        env.updated_at = datetime.utcnow().isoformat()
        self._log("in_progress", handoff_id=handoff_id, attempts=env.attempts)
        return {"ok": True, "envelope": env.to_dict()}

    def complete(self, handoff_id: str, result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        env = self.pending.pop(handoff_id, None)
        if not env:
            return {"ok": False, "error": "not_found"}
        env.state = HandoffState.COMPLETED.value
        env.updated_at = datetime.utcnow().isoformat()
        row = env.to_dict()
        row["result"] = result or {}
        self.completed.append(row)
        self._log("completed", handoff_id=handoff_id)
        return {"ok": True, "envelope": row}

    def fail(self, handoff_id: str, error: str) -> Dict[str, Any]:
        env = self.pending.get(handoff_id)
        if not env:
            return {"ok": False, "error": "not_found"}
        env.error = error
        env.updated_at = datetime.utcnow().isoformat()
        if env.attempts >= env.max_attempts:
            env.state = HandoffState.DEAD_LETTER.value
            self.pending.pop(handoff_id, None)
            self.dead_letter.append(env.to_dict())
            self._log("dead_letter", handoff_id=handoff_id, error=error)
        else:
            env.state = HandoffState.FAILED.value
            self._log("failed", handoff_id=handoff_id, error=error, attempts=env.attempts)
        return {"ok": True, "envelope": env.to_dict()}

    def status(self) -> Dict[str, Any]:
        return {
            "pending": len(self.pending),
            "completed": len(self.completed),
            "dead_letter": len(self.dead_letter),
            "pending_ids": list(self.pending.keys())[-20:],
        }
