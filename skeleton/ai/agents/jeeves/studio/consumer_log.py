"""Consumer log.
Append-only event log for end-user runs.
"""
from typing import Any, Dict, List

class ConsumerLog:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def append(self, kind: str, detail: str = "") -> Dict[str, Any]:
        if not isinstance(kind, str) or not kind.strip():
            return {"ok": False, "reason": "empty_kind", "schema": "skeleton.log.v1"}
        self.events.append({"kind": kind, "detail": detail})
        return {"ok": True, "count": len(self.events), "reason": "ok", "schema": "skeleton.log.v1"}
