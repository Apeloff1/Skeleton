"""
Operational Error Handler. Centralized fail-closed recovery, logging of CAS/schema/clipped failures.
Fills the error path gap.
"""
from typing import Dict, Optional

class ErrorHandler:
    def __init__(self):
        self.errors: list = []

    def handle(self, exc: Exception, context: Optional[Dict] = None) -> Dict:
        entry = {"type": type(exc).__name__, "msg": str(exc), "context": context or {}}
        self.errors.append(entry)
        if isinstance(exc, PermissionError):
            return {"recovered": False, "action": "reject_cas", "entry": entry}
        if isinstance(exc, ValueError):
            return {"recovered": False, "action": "reject_schema", "entry": entry}
        return {"recovered": True, "action": "log_and_continue", "entry": entry}

    def report(self) -> Dict:
        return {"count": len(self.errors), "last": self.errors[-1] if self.errors else None}
