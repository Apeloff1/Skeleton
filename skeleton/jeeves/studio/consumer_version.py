"""Consumer version.
Surface version and schema for end users.
"""
from typing import Any, Dict

class ConsumerVersion:
    def info(self) -> Dict[str, Any]:
        return {"ok": True, "version": "0.62", "schema": "skeleton.version.v1", "reason": "ok"}
