"""Consumer license.
End-user license surface.
"""
from typing import Any, Dict

class ConsumerLicense:
    def accept(self, accepted: bool) -> Dict[str, Any]:
        return {"ok": bool(accepted), "accepted": bool(accepted), "reason": "ok" if accepted else "rejected", "schema": "skeleton.license.v1"}
