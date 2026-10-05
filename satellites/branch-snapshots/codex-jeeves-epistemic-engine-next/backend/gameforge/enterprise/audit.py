from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class AuditEvent:
    event_id: str
    ts: str
    tenant_id: str
    workspace_id: str
    actor_user_id: str
    action: str
    resource_type: str
    resource_id: str
    details: Dict[str, Any]


def audit_now(
    *,
    tenant_id: str,
    workspace_id: str,
    actor_user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid.uuid4())[:12],
        ts=datetime.utcnow().isoformat(),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
    )


class AuditLog:
    def __init__(self):
        self._events: List[Dict[str, Any]] = []

    async def emit(self, event: AuditEvent):
        self._events.append(asdict(event))
        if len(self._events) > 50_000:
            self._events = self._events[-40_000:]

    async def list_for_tenant(self, tenant_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        rows = [e for e in self._events if e.get("tenant_id") == tenant_id]
        return list(reversed(rows[-limit:]))


AUDIT = AuditLog()
