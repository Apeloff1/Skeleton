"""Full-repo install guarantee gate."""
from __future__ import annotations
from typing import Dict, Any

def guarantee_install(manifest_ok: bool, seals_ok: bool) -> Dict[str, Any]:
    if not manifest_ok or not seals_ok:
        return {"ok": False, "guaranteed": False, "reason": "missing_seals"}
    return {"ok": True, "guaranteed": True, "reason": "ok"}
