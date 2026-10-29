"""Consumer error.
Fail-closed error surface with reason codes.
"""
from typing import Any, Dict

class ConsumerError:
    def report(self, code: str, detail: str = "") -> Dict[str, Any]:
        if not isinstance(code, str) or not code.strip():
            return {"ok": False, "reason": "empty_code", "schema": "skeleton.error.v1"}
        return {"ok": True, "code": code, "detail": detail, "reason": "reported", "schema": "skeleton.error.v1"}
