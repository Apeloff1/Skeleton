"""Consumer privacy.
Local-only flag for end-user runs.
"""
from typing import Any, Dict

class ConsumerPrivacy:
    def check(self, local_only: bool = True) -> Dict[str, Any]:
        return {"ok": True, "local_only": bool(local_only), "reason": "ok", "schema": "skeleton.privacy.v1"}
