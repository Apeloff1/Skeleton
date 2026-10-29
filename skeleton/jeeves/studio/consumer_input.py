"""Consumer input.
Fail-closed input validation for end-user briefs.
"""
from typing import Any, Dict

class ConsumerInput:
    def validate(self, text: str, max_len: int = 200) -> Dict[str, Any]:
        if not isinstance(text, str):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.input.v1"}
        ok = 0 < len(text.strip()) <= max_len
        return {"ok": ok, "length": len(text), "reason": "ok" if ok else "length_failed", "schema": "skeleton.input.v1"}
