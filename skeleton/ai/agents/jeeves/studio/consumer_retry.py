"""Consumer retry.
Fail-closed retry with optical floor.
"""
from typing import Any, Dict

class ConsumerRetry:
    def attempt(self, tries: int, optical: float) -> Dict[str, Any]:
        if not isinstance(tries, int) or tries < 1:
            return {"ok": False, "reason": "bad_tries", "schema": "skeleton.retry.v1"}
        ok = optical >= 0.9
        return {"ok": ok, "tries": tries, "optical": optical, "reason": "ok" if ok else "gates_failed", "schema": "skeleton.retry.v1"}
