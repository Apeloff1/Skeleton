from __future__ import annotations
"""
Multi-device sync plan (marathon pages) — local-first conflict rules.
Not a full network client yet; defines merge policy + queue for future transport.
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SyncOp:
    op_id: str
    surface: str
    entity_id: str
    revision: int
    payload: Dict[str, Any]
    device_id: str = "local"
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


class SyncQueue:
    """
    Outbound/inbound op log. Merge rule: higher revision wins; tie → latest created_at.
    """

    def __init__(self):
        self.outbound: List[SyncOp] = []
        self.inbound: List[SyncOp] = []
        self.applied: Dict[str, int] = {}  # entity_id -> revision

    def enqueue(self, surface: str, entity_id: str, payload: dict, revision: Optional[int] = None, device_id: str = "local") -> SyncOp:
        rev = revision if revision is not None else self.applied.get(entity_id, 0) + 1
        op = SyncOp(
            op_id=str(uuid.uuid4())[:12],
            surface=surface,
            entity_id=entity_id,
            revision=rev,
            payload=payload,
            device_id=device_id,
        )
        self.outbound.append(op)
        return op

    def accept(self, op: SyncOp) -> Dict[str, Any]:
        cur = self.applied.get(op.entity_id, 0)
        if op.revision < cur:
            return {"ok": False, "reason": "stale_revision", "current": cur}
        if op.revision == cur:
            return {"ok": False, "reason": "duplicate_revision", "current": cur}
        self.applied[op.entity_id] = op.revision
        self.inbound.append(op)
        return {"ok": True, "applied_revision": op.revision}

    def status(self) -> Dict[str, Any]:
        return {
            "outbound": len(self.outbound),
            "inbound": len(self.inbound),
            "entities": len(self.applied),
        }
